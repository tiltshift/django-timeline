from django.core.urlresolvers import reverse

from dg.views import template, notice
from dg.http import redirect

from shelfworthy.apps.members.models import Member

from shelfworthy.apps.events.base import Stream

def events(request, title=None, event_filter=None):
    # If we're on a wide device, start on the me page.
    if request.path == reverse('events') and request.wide_device:
        return redirect('all_events', request=request)

    # if we have a filter, we're not on the nav list
    detail_page = event_filter != None

    return_dict = {
        'state': 'Activity',

        'nav': True,
        'content': detail_page,
        'endpoint': detail_page,

        'back': "Activity",
        'page_title': "Activity",
        'nav_title': "Activity",

        'events': Stream(*(request.member.get_following() + [request.member]))
    }

    if title:
        return_dict['location'] = title

    if detail_page and not request.wide_device:
        return_dict['default_back'] = ("Events", reverse('events'))
        return_dict['back'] = "Activity"

        return_dict['nav_title'] = title

    return template(request, 'events/home.html', return_dict)

def all(request):
    return events(request, 'All', 'All')
