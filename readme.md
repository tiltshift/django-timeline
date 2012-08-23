Timeline (event streams)
========================

Timeline is a flexable event stream app that uses redis as the backend to keep things fast.

Instalation
-----------

1. make sure you have redis installed.
2. `pip install django-timeline` (or clone the source from https://github.com/tiltshift/django-timeline)
3. add `timeline` to the `INSTALLED_APPS` list in your project&rsquo;s settings.py file.

How to Use Timeline
-------------------

First up you need to define an event type. Generally the best practice is to add an `events.py` file in the
application related to the event you are creating, but you can define the event anywhere.

The following will walk you thorugh the steps needed to create a new event definition, add an event of that type, and then display the resulting event in a timeline (stream).

Here is a generic example for an event definition where a user is adding an item:

``` python
    from django.contrib.auth.models import User

    from timeline.base import EventType
    
    from yourapp.apps.items.models import Item

    class UserAddedItem(EventType):
        slug = "user-added-item"
        context_shape = {
            "user": User,
            "item": Item,
        }
        queryable_by = ["user", "item"]
```

As you can see the event definition—`UserAddedItem`—is made up of the following:

- `slug`: a unique ID for the event type
- `context_shape`: think of this as variables for your event type. This is the stuff you'll be storing for each event of this type.
- `queryable_by`: these are the variables from the context_shape that can be used to find this event. We&rsquo;ll go over this later on.

Next you&rsquo;ll need to write some code to create actual event objects:

``` python
    from yourapp.apps.items.events import UserAddedItem
    
    def Add_Item(user, item):
        # app code for adding the item here.
        
        UserAddedItem({
            'user': user,
            'item': item
        }).save()
```

This code is hopefully pretty self explanitory. To create an event of the type `UserAddedItem` you pass your variables—`user` and `item` in this case—and then save the event.

Now that you've got an event saved, lets look at how to display it:

``` python
    from timeline.base import Stream
    
    events = Stream(request.user)
```

Also hopefully pretty simple. By default the stream will take the given query, `request.user` in this case, and find all events where that query exists in the event type&rsquo;s `queryable_by`.

Stream can take any number of positional arguments and it will combine their streams.

It also takes a number of keyword arguments:

- `event_type` will return only `Events` for a given slug. 
- `limit` a number saying how many `Events` should be included, defaults to 20.
- `cluster` a boolean saying whether the data returned should be clustered, if it is than it yields a list
of `Events`, rather than discrete `Events`.
