import hashlib
import time
import uuid
from collections import defaultdict, namedtuple
from datetime import datetime, timedelta

import redis

from django.conf import settings
from django.db.models import Model
from django.template import Context
from django.template.loader import render_to_string
from django.utils import simplejson as json

from .models import (StreamItem as StreamItemModel,
    StreamCluster as StreamClusterModel)

# TODO: ...
def get_redis_connection():
    return redis.Redis(**settings.REDIS_SETTINGS)

class EventTypeMetaclass(type):
    def __new__(cls, name, bases, attrs):
        new_cls = super(EventTypeMetaclass, cls).__new__(cls, name, bases, attrs)
        if hasattr(new_cls, "context_shape"):
            for k, v in new_cls.context_shape.iteritems():
                if issubclass(v, Model):
                    class Klass(ModelContextItemType):
                        model = v
                    new_cls.context_shape[k] = Klass
        if hasattr(new_cls, "slug"):
            new_cls.registry[new_cls.slug] = new_cls
            assert new_cls.slug is not None
            assert new_cls.context_shape is not None
            assert new_cls.queryable_by is not None
            assert new_cls.default_cluster_by is not None

        return new_cls

class EventType(object):
    __metaclass__ = EventTypeMetaclass

    registry = {}

    cluster = True

    def __init__(self, context, timestamp=None, remove=False):
        if timestamp is None:
            timestamp = datetime.now()
        self.timestamp = timestamp
        for key, spec in self.context_shape.iteritems():
            if key not in context:
                raise ValueError("Missing value from context")
            if not spec.valid_obj(context[key]):
                raise TypeError("Invalid context item for %s: %s" % (key, context[key]))
        self.context = context
        self.remove = remove

    def serialize_context(self, context):
        result = {}
        for key, spec in self.context_shape.iteritems():
            result[key] = spec.serialize(context[key])
        return result

    @property
    def redis(self):
        if not hasattr(self, "_redis"):
            self._redis = get_redis_connection()
        return self._redis

    def save(self):
        context = self.serialize_context(self.context)
        s = StreamItemModel.objects.create(
            context = json.dumps(context),
            remove = self.remove,
        )

        t = self.timestamp
        timestamp = time.mktime(t.timetuple()) + 1e-6 * t.microsecond

        record = {
            "id": s.pk,
            "context": self.serialize_context(self.context),
            "remove": self.remove,
            "timestamp": tuple(t.timetuple())[:-3],
        }
        for field in self.queryable_by:
            obj_key = self.context_shape[field](self.context[field]).lookup_key()
            keys = [obj_key, "%s:%s" % (obj_key, self.slug)]
            c = None
            for key in keys:
                c = self._add_to_key(field, key, timestamp, record, c, s)
        self._add_to_key(
            self.default_cluster_by, "ALL_EVENTS", timestamp, record, c, s
        )

    def _add_to_key(self, field, key, timestamp, record, c, s):
        for item, score in self.redis.zrevrange(key, 0, 5, withscores=True):
            cluster_timestamp = datetime.fromtimestamp(score)
            data = json.loads(item)
            if (data["slug"] == self.slug and self.cluster and
                data["items"][0]["context"][data["clustered_on"]] == self.context_shape[field].serialize(self.context[field]) and
                self.timestamp - cluster_timestamp < timedelta(minutes=5)):
                c = StreamClusterModel.objects.get(pk=data["cluster_id"])
                c.items.add(s)
                data["items"].append(record)
                self.redis.zrem(key, item)
                self.redis.zadd(key, json.dumps(data), score)
                break
        else:
            if c is None:
                c = StreamClusterModel.objects.create(
                    event_type = self.slug,
                    clustered_on = field,
                )
                c.items.add(s)
            data = json.dumps({
                "slug": self.slug,
                "items": [record],
                "clustered_on": field,
                "cluster_id": c.pk,
            })
            self.redis.zadd(key, data, timestamp)
        return c

class ContextItemType(object):
    def __init__(self, obj):
        self.obj = obj

    def lookup_key(self):
        return self.obj

    @classmethod
    def unique_key(cls):
        return cls

    @classmethod
    def valid_obj(cls, obj):
        return True

    @classmethod
    def serialize(cls, obj):
        return obj

    @classmethod
    def deserialize(cls, obj):
        return obj

    @classmethod
    def deserialize_bulk(cls, objs):
        return dict(
            (obj, cls.deserialize(obj))
            for obj in objs
        )

class ModelContextItemType(ContextItemType):
    model = None

    def lookup_key(self):
        return "%s:%s:%s" % (
            self.model._meta.app_label,
            self.model._meta.object_name,
            self.obj.pk
        )

    @classmethod
    def unique_key(cls):
        return cls.model

    @classmethod
    def valid_obj(cls, obj):
        return isinstance(obj, cls.model) or isinstance(obj, (int, long))

    @classmethod
    def serialize(cls, obj):
        return obj.pk

    @classmethod
    def deserialize(cls, obj):
        return cls.model._default_manager.get(pk=obj)

    @classmethod
    def deserialize_bulk(cls, objs):
        return cls.model._default_manager.in_bulk(objs)

class StreamItem(object):
    def __init__(self, slug, timestamp, context, item_id, cluster_id):
        self.slug = slug
        self.timestamp = timestamp
        self.context = context
        self.item_id = item_id
        self.cluster_id = cluster_id

    def __getattr__(self, name):
        return self.context[name]

class StreamCluster(object):
    def __init__(self, slug, date_added, events, clustered_on=None,
        cluster_id=None):
        self.slug = slug
        self.date_added = date_added
        self.events = events
        self.clustered_on = clustered_on
        self.cluster_id = cluster_id

    def __iter__(self):
        return iter(self.events)

    def __len__(self):
        return len(self.events)

    def __unicode__(self):
        return self.render()

    @property
    def date_updated(self):
        return max(e.timestamp for e in self.events)

    def render(self, context=None):
        if context is None:
            context = Context()
        context.push()
        context["query_object"] = self.clustered_on
        if len(self.events) == 1:
            context["event"] = self.events[0]
            # The context variable for a full stream is often named events,
            # since we're providing the full context, set this to None so the
            # event template isn't confused (since events means something
            # different).  This is safe since we push and pop the context
            # before and after modifying it.
            context["events"] = None
        else:
            context["events"] = self
            # Same reason as above.
            context["event"] = None
        try:
            return render_to_string("events/event/%s.html" % self.slug, context)
        finally:
            context.pop()

RawResults = namedtuple("RawResults", ["field", "vals"])
Status = namedtuple("Status", ["adds", "removes"])

class Stream(object):
    def __init__(self, *objs, **kwargs):
        event_type = kwargs.pop("event_type", None)
        limit = kwargs.pop("limit", 20)
        offset = kwargs.pop("offset", 0)

        if kwargs:
            raise TypeError("Unexpected keyword argument: %s" % kwargs)

        final_objs = []
        for obj in objs:
            if isinstance(obj, Model):
                class Klass(ModelContextItemType):
                    model = type(obj)
                final_objs.append(Klass(obj))
            else:
                final_objs.append(obj)

        self.objs = final_objs
        self.event_type = event_type
        self.limit = limit
        self.offset = offset

    def __iter__(self):
        redis = get_redis_connection()

        postfix = ""
        if self.event_type is not None:
            postfix += ":%s" % (self.event_type.slug)
        lookup_keys = [
            obj.lookup_key() + postfix
            for obj in self.objs
        ]

        if len(lookup_keys) >= 2:
            s = hashlib.sha1()
            for lookup_key in lookup_keys:
                s.update(lookup_key)
            key = s.hexdigest()
            redis.zunionstore(key, lookup_keys, aggregate="MIN")
            # Expire it in 5 minutes, enough that paginating shouldn't require
            # a recompute, but short enough to not clutter the place up.
            redis.expire(key, 60 * 5)
        elif len(lookup_keys) == 1:
            key = lookup_keys[0]
        else:
            assert not self.event_type
            key = "ALL_EVENTS"

        statuses = defaultdict(lambda: Status(0, 0))
        items = list(redis.zrevrange(key, self.offset, self.limit, withscores=True))
        parsed_items = []
        context_items = {}
        for cluster, score in items:
            data = json.loads(cluster)
            parsed_items.append((data, score))
            for o in data["items"]:
                status_key = self._status_key(data["slug"], o)
                status = statuses[status_key]
                if o["remove"]:
                    statuses[status_key] = status._replace(removes=status.removes+1)
                else:
                    statuses[status_key] = status._replace(adds=status.adds+1)
                for key, val in o["context"].iteritems():
                    field = EventType.registry[data["slug"]].context_shape[key]
                    key = field.unique_key()
                    if key not in context_items:
                        context_items[key] = RawResults(field, set())
                    context_items[key].vals.add(val)

        final_context_items = {}
        for key, (field, vals) in context_items.iteritems():
            final_context_items[key] = field.deserialize_bulk(vals)

        for data, score in parsed_items:
            cluster_items = []
            timestamp = datetime.fromtimestamp(score)
            for o in data["items"]:
                item = self._convert_item(
                    data["slug"], o, timestamp, statuses, final_context_items, data["cluster_id"]
                )
                if item is not None:
                    cluster_items.append(item)
            if cluster_items:
                clustered_on = None
                if data["clustered_on"] is not None:
                    clustered_on = cluster_items[0].context[data["clustered_on"]]
                yield StreamCluster(
                    data["slug"],
                    timestamp,
                    cluster_items,
                    clustered_on,
                    data["cluster_id"]
                )

    def _convert_item(self, slug, data, timestamp, statuses, context_items,
        cluster_id):
        status_key = self._status_key(slug, data)
        status = statuses[status_key]
        if data["remove"]:
            current_attr, other_attr = "removes", "adds"
        else:
            current_attr, other_attr = "adds", "removes"

        if getattr(status, current_attr) <= getattr(status, other_attr):
            return
        statuses[status_key] = status._replace(**{
            current_attr: getattr(status, current_attr) - 1
        })

        context = {}
        for key, value in data["context"].iteritems():
            field = EventType.registry[slug].context_shape[key]
            context[key] = context_items[field.unique_key()][value]

        return StreamItem(
            slug,
            datetime(*data["timestamp"]),
            context,
            data["id"],
            cluster_id,
        )

    def _status_key(self, slug, data):
        return (
            slug,
            tuple(sorted(data["context"].items()))
        )
