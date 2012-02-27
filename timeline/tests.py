from contextlib import contextmanager
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User as UserModel
from django.db import connection, connections, DEFAULT_DB_ALIAS
from django.template import TemplateDoesNotExist
from django.test import TestCase

from .base import get_redis_connection, EventType, ContextItemType, Stream, StreamCluster
from .models import StreamItem, StreamCluster as StreamClusterModel

class EventTestCase(TestCase):
    @contextmanager
    def assert_raises(self, error_type):
        exc_info = {}
        try:
            yield exc_info
        except error_type, e:
            exc_info["exception"] = e
        except Exception, e:
            self.fail("Exception of type %s expected, %s gotten" % (error_type, e))
        else:
            self.fail("Exception of type %s expected, but not raised" % error_type)


class User(ContextItemType):
    @classmethod
    def valid_obj(cls, obj):
        return isinstance(obj, basestring)


class Follow(EventType):
    slug = "follow"
    context_shape = {
        "follower": User,
        "following": User,
    }
    queryable_by = ["follower", "following"]
    default_cluster_by = "follower"

class Poke(EventType):
    slug = "poke"
    context_shape = {
        "poker": User,
        "pokee": User,
    }
    queryable_by = ["poker", "pokee"]
    default_cluster_by = "poker"

class SomeEvent(EventType):
    slug = "some-event"
    context_shape = {
        "user": UserModel
    }
    queryable_by = ["user"]
    default_cluster_by = "user"

class AnotherEvent(EventType):
    slug = "another-event"
    context_shape = {
        "user": UserModel
    }
    queryable_by = ["user"]
    default_cluster_by = "user"

class Review(EventType):
    slug = "review"
    context_shape = {
        "reviewer": User,
    }
    queryable_by = ["reviewer"]
    cluster = False
    default_cluster_by = "reviewer"

_missing = object()

class EventTests(EventTestCase):
    def setUp(self):
        self.original_REDIS_SETTINGS = getattr(settings, "REDIS_SETTINGS", _missing)
        settings.REDIS_SETTINGS = {
            "db": 9,
        }

    def tearDown(self):
        get_redis_connection().flushdb()
        if self.original_REDIS_SETTINGS is _missing:
            del settings.REDIS_SETTINGS
        else:
            settings.REDIS_SETTINGS = self.original_REDIS_SETTINGS

    def assert_stream_equal(self, stream, objs):
        got = list(stream)
        self.assertEqual(len(got), len(objs))
        for cluster, expected in zip(got, objs):
            self.assertEqual(len(cluster), len(expected))
            self.assertEqual(cluster.slug, expected.slug)
            self.assertEqual(cluster.date_added, expected.date_added)
            self.assertEqual(cluster.date_updated, expected.date_updated)
            # This isn't relevant to most tests, so we make it optional.
            if expected.clustered_on is not None:
                self.assertEqual(cluster.clustered_on, expected.clustered_on)
            for res, obj in zip(cluster, expected):
                self.assertEqual(res.timestamp, obj.timestamp)
                self.assertEqual(res.context, obj.context)
                self.assertEqual(res.slug, obj.slug)


    def test_context_item_coercion(self):
        with self.assert_raises(ValueError):
            Follow({
                "follower": "alex",
            }, timestamp=datetime(2010, 10, 8))
        with self.assert_raises(TypeError):
            Follow({
                "following": "alex",
                "follower": 2
            }, timestamp=datetime(2010, 10, 8))

    def test_event_save(self):
        event = Follow({
            "follower": "alex",
            "following": "einstein",
        })
        event.save()

        self.assertEqual(StreamItem.objects.count(), 1)
        # One for the follower, one for the following,
        self.assertEqual(StreamClusterModel.objects.count(), 2)
        s = Stream(User("alex"))
        c = iter(s).next()
        self.assertEqual(
            c.cluster_id,
            StreamClusterModel.objects.get(clustered_on="follower").pk
        )

    def test_event_stream_single(self):
        event = Follow({
            "following": "alex",
            "follower": "einstein",
        }, timestamp=datetime(2010, 10, 8))
        event.save()

        self.assert_stream_equal(Stream(User("alex")), [
            StreamCluster("follow", datetime(2010, 10, 8), [
                Follow({
                    "following": "alex",
                    "follower": "einstein",
                }, datetime(2010, 10, 8)),
            ])
        ])

    def test_event_stream_multiple(self):
        event = Follow({
            "following": "alex",
            "follower": "jacob",
        }, timestamp=datetime(2010, 10, 8, 12, 30, 12))
        event.save()

        self.assert_stream_equal(Stream(User("alex"), User("jacob")), [
            StreamCluster("follow", datetime(2010, 10, 8, 12, 30, 12), [
                Follow({
                    "following": "alex",
                    "follower": "jacob",
                }, datetime(2010, 10, 8, 12, 30, 12)),
            ]),
            StreamCluster("follow", datetime(2010, 10, 8, 12, 30, 12), [
                Follow({
                    "following": "alex",
                    "follower": "jacob",
                }, datetime(2010, 10, 8, 12, 30, 12)),
            ]),
        ])

    def test_cluster(self):
        Follow({
            "following": "alex",
            "follower": "jacob",
        }, timestamp=datetime(2010, 10, 8, 12, 30)).save()
        Follow({
            "following": "alex",
            "follower": "daniel",
        }, timestamp=datetime(2010, 10, 8, 12, 31)).save()
        Follow({
            "following": "alex",
            "follower": "james",
        }, timestamp=datetime(2010, 10, 8, 13, 30)).save()

        self.assert_stream_equal(Stream(User("alex")), [
            StreamCluster("follow", datetime(2010, 10, 8, 13, 30), [
                Follow({
                    "following": "alex",
                    "follower": "james",
                }, datetime(2010, 10, 8, 13, 30))
            ]),
            StreamCluster("follow", datetime(2010, 10, 8, 12, 30), [
                Follow({
                    "following": "alex",
                    "follower": "jacob",
                }, datetime(2010, 10, 8, 12, 30)),
                Follow({
                    "following": "alex",
                    "follower": "daniel",
                }, datetime(2010, 10, 8, 12, 31)),
            ]),
        ])

    def test_model(self):
        u = UserModel.objects.create_user("joe", "joe@schmoe.net", "abc123")
        d = datetime(2010, 10, 21, 15, 56, 22)
        SomeEvent({
            "user": u,
        }, timestamp=d).save()

        self.assert_stream_equal(Stream(u), [
            StreamCluster("some-event", d, [
                SomeEvent({
                    "user": u,
                }, d)
            ])
        ])

    def test_model_clustered_on(self):
        u = UserModel.objects.create_user("joe", "joe@schmoe.net", "abc123")
        d = datetime(2010, 10, 21, 15, 56, 22, 330000)
        SomeEvent({
            "user": u,
        }, timestamp=d).save()

        s = Stream(u)
        c = iter(s).next()
        self.assertEqual(c.clustered_on, u)

    def test_render_cluster(self):
        Follow({
            "following": "alex",
            "follower": "daniel",
        }).save()
        Follow({
            "following": "alex",
            "follower": "aaron",
        }).save()
        s = Stream(User("alex"))
        f = iter(s).next()

        with self.assert_raises(TemplateDoesNotExist) as exc_info:
            f.render()
        self.assertEqual(exc_info["exception"].args, ("events/event/follow.html",))

    def test_remove(self):
        d1 = datetime(2010, 10, 8, 9, 32)
        d2 = datetime(2010, 10, 8, 9, 30)
        c = {
            "following": "alex",
            "follower": "daniel",
        }
        Follow(c, d1).save()
        Follow(c, d2, remove=True).save()

        self.assert_stream_equal(Stream(User("alex")), [])

    # TODO: Design decision
    # def test_remove_first(self):
    #     '''
    #     A case when event is removed, but there was no paired event before that.
    #     This can happend if event for following was not created before unfollowing
    #     '''
    #     d1 = datetime(2010, 10, 8, 9, 32)
    #     d2 = datetime(2010, 10, 8, 9, 30)
    #     c = {
    #         "following": "alex",
    #         "follower": "daniel",
    #     }
    #     Follow(c, d1, remove=True).save()
    #     # Follow(c, d2).save()
    # 
    #     self.assert_stream_equal(Stream(User("alex")), [])

    def test_remove_cluster(self):
        d1 = datetime(2010, 10, 8, 9, 30)
        d2 = datetime(2010, 10, 8, 9, 32)
        c = {
            "following": "alex",
            "follower": "daniel",
        }
        Follow(c, d1).save()
        Follow(c, d1, remove=True).save()
        Follow({
            "following": "alex",
            "follower": "jacob",
        }, d2).save()

        self.assert_stream_equal(Stream(User("alex")), [
            StreamCluster("follow", d1, [
                Follow({
                    "following": "alex",
                    "follower": "jacob",
                }, d2)
            ]),
        ])

    def test_cluster_types(self):
        d1 = datetime(2010, 10, 8, 9, 32)
        d2 = datetime(2010, 10, 8, 9, 33)
        fc1 = {
            "following": "alex",
            "follower": "daniel"
        }
        fc2 = {
            "following": "alex",
            "follower": "ryan"
        }
        pc1 = {
            "pokee": "alex",
            "poker": "michael"
        }
        pc2 = {
            "pokee": "alex",
            "poker": "ralph"
        }
        Follow(fc1, d1).save()
        Follow(fc2, d2).save()
        Poke(pc1, d1).save()
        Poke(pc2, d2).save()

        self.assert_stream_equal(Stream(User("alex")), [
            StreamCluster("poke", d1, [
                Poke(pc1, d1),
                Poke(pc2, d2),
            ]),
            StreamCluster("follow", d1, [
                Follow(fc1, d1),
                Follow(fc2, d2),
            ])
        ])

    def test_unpaired_remove(self):
        d = datetime(2010, 10, 8, 9, 32)
        c = {
            "following": "alex",
            "follower": "daniel"
        }
        Follow(c, d, remove=True).save()
        self.assert_stream_equal(Stream(User("alex")), [
            StreamCluster("follow", d, [
                Follow(c, d, remove=True)
            ]),
        ])

    def test_clustered_on(self):
        d = datetime(2010, 10, 8, 9, 32)
        c1 = {
            "following": "alex",
            "follower": "daniel"
        }
        Follow(c1, d).save()
        s = Stream(User("alex"))
        c = iter(s).next()
        self.assertEqual(c.clustered_on, "alex")

    def test_no_cluster(self):
        d = datetime(2010, 10, 8, 9, 32)
        c = {"reviewer": "Chris"}
        Review(c, d).save()
        Review(c, d).save()
        self.assert_stream_equal(Stream(User("Chris")), [
            StreamCluster("review", d, [
                Review(c, d),
            ]),
            StreamCluster("review", d, [
                Review(c, d),
            ]),
        ])

    def test_efficient_context_deserialize(self):
        d1 = datetime(2010, 10, 8, 9, 32)
        d2 = datetime(2010, 10, 8, 9, 33)
        u1 = UserModel.objects.create_user("joe", "joe@schmoe.net", "abc123")
        u2 = UserModel.objects.create_user("bob", "bob@schmoe.net", "123abc")
        SomeEvent({"user": u1}, d1).save()
        SomeEvent({"user": u2}, d2).save()

        # 1 query to get all of the users, that's it.
        with self.assertNumQueries(1):
            list(Stream(u1, u2))

    def test_efficient_context_deserialiez_different_events(self):
        d1 = datetime(2010, 10, 8, 9, 32)
        d2 = datetime(2010, 10, 8, 9, 33)
        u1 = UserModel.objects.create_user("joe", "joe@schmoe.net", "abc123")
        u2 = UserModel.objects.create_user("bob", "bob@schmoe.net", "123abc")
        SomeEvent({"user": u1}, d1).save()
        AnotherEvent({"user": u2}, d2).save()

        # 1 query to get all of the users, even though they're on different
        # event types.
        with self.assertNumQueries(1):
            list(Stream(u1, u2))

    def test_multiple_create_remove(self):
        c = {
            "follower": "alex",
            "following": "daniel"
        }
        ds = [
            datetime(2010, 10, 8, 12) + timedelta(minutes=1) * i for i in xrange(4)
        ]
        for d in ds:
            Follow(c, d).save()
            Follow(c, d + timedelta(seconds=30), remove=True).save()
        Follow(c, datetime(2010, 10, 8, 12, 4, 30)).save()

        self.assert_stream_equal(Stream(User("alex")), [
            StreamCluster("follow", datetime(2010, 10, 8, 12), [
                Follow(c, datetime(2010, 10, 8, 12)),
            ])
        ])

    def test_cluster_db(self):
        c = {
            "follower": "alex",
            "following": "daniel"
        }
        ds = [
            datetime(2010, 10, 8, 12) + timedelta(minutes=1) * i for i in xrange(4)
        ]
        for d in ds:
            Follow(c, d).save()

        self.assertEqual(StreamClusterModel.objects.count(), 2)
        s = StreamClusterModel.objects.get(clustered_on="follower")
        self.assertEqual(s.event_type, "follow")
        self.assertEqual(s.items.count(), 4)

    def test_all_stream(self):
        d1 = datetime(2010, 10, 8, 12, 30)
        d2 = datetime(2010, 10, 8, 12, 33)

        c1 = {
            "follower": "alex",
            "following": "daniel"
        }
        c2 = {
            "follower": "aaron",
            "following": "charlie",
        }

        Follow(c1, d1).save()
        Follow(c2, d2).save()

        self.assert_stream_equal(Stream(), [
            StreamCluster("follow", d2, [
                Follow(c2, d2),
            ], clustered_on="aaron"),
            StreamCluster("follow", d1, [
                Follow(c1, d1),
            ], clustered_on="alex")
        ])

    def test_shared_key(self):
        d1 = datetime(2010, 10, 8, 12, 30)
        d2 = datetime(2010, 10, 8, 12, 33)
        c1 = {
            "follower": "alex",
            "following": "daniel"
        }
        c2 = {
            "follower": "aaron",
            "following": "charlie",
        }
        Follow(c1, d1).save()
        Follow(c2, d2).save()

        redis = get_redis_connection()
        # 1 - ALL_EVENTS
        # 8 - each username + each username:follow
        # 9
        self.assertEqual(len(redis.keys()), 9)

        list(Stream(User("alex"), User("aaron")))
        self.assertEqual(len(redis.keys()), 10)
        list(Stream(User("alex"), User("aaron")))
        self.assertEqual(len(redis.keys()), 10)

    def test_offset(self):
        d1 = datetime(2010, 10, 8, 12, 30)
        d2 = datetime(2010, 10, 8, 12, 33)
        c1 = {
            "follower": "alex",
            "following": "daniel"
        }
        c2 = {
            "follower": "aaron",
            "following": "charlie",
        }
        Follow(c1, d1).save()
        Follow(c2, d2).save()

        self.assert_stream_equal(Stream(offset=1), [
            StreamCluster("follow", d1, [
                Follow(c1, d1)
            ])
        ])

    def test_cluster_by_model(self):
        u = UserModel.objects.create_user("me", "hi", "me@me.com")

        d1 = datetime(2010, 10, 8, 12, 30)
        d2 = datetime(2010, 10, 8, 12, 33)
        c = {"user": u}
        SomeEvent(c, d1).save()
        SomeEvent(c, d2).save()

        self.assert_stream_equal(Stream(u), [
            StreamCluster("some-event", d1, [
                SomeEvent(c, d1),
                SomeEvent(c, d2),
            ])
        ])

    def test_cluster_id(self):
        d1 = datetime(2010, 10, 8, 12, 30)
        d2 = datetime(2010, 10, 8, 12, 33)
        c1 = {
            "follower": "alex",
            "following": "daniel"
        }
        c2 = {
            "follower": "alex",
            "following": "aaron",
        }
        Follow(c1, d1).save()

        s = iter(Stream(User("alex"))).next()
        self.assertEqual(
            s.cluster_id,
            StreamClusterModel.objects.get(clustered_on="follower").pk
        )
        self.assertEqual(s.events[0].cluster_id, s.cluster_id)

        Follow(c2, d2).save()
        s = iter(Stream(User("alex"))).next()
        self.assertEqual(
            s.cluster_id,
            StreamClusterModel.objects.get(clustered_on="follower").pk
        )
        self.assertEqual(s.events[0].cluster_id, s.cluster_id)
        self.assertEqual(s.events[1].cluster_id, s.cluster_id)

    def test_times(self):
        d1 = datetime(2010, 10, 8, 12, 30)
        d2 = datetime(2010, 10, 8, 12, 33)
        c1 = {
            "follower": "alex",
            "following": "daniel"
        }
        c2 = {
            "follower": "alex",
            "following": "aaron",
        }
        Follow(c1, d1).save()
        Follow(c2, d2).save()

        s = iter(Stream(User("alex"))).next()
        self.assertEqual(s.date_added, d1)
        self.assertEqual(s.date_updated, d2)
