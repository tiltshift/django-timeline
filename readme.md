Timeline (event streams)
========================

There are two parts to using event streams.  The first is to declare an Event,
it looks like this::

    from django.contrib.auth.models import User

    from timeline.base import EventType
    from yourapp.library.models import Item


    class AddedToLibrary(EventType):
        slug = "added-to-library"
        context_shape = {
            "user": User,
            "item": Item,
        }
        queryable_by = ["user", "item"]

And then there is querying, all querying is encapsulated in the
``timeline.base.Stream`` class.  It is used like so::

    Stream(request.user)

will return a ``Stream`` for all of the events for the ``request.user.pk`` User.
It can take any number of positional arguments and it will combine their streams.

It also takes a number of keyword arguments.  ``event_type`` which will return
only ``Events`` for a given slug.  ``limit`` a number saying how many
``Events`` should be included, defaults to 20.  ``cluster`` a boolean saying
whether the data returned should be clustered, if it is than it yields a list
of ``Events``, rather than discrete ``Events``.
