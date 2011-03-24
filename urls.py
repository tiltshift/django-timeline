from django.conf.urls.defaults import *

section_name = "activity"

urlpatterns = patterns('shelfworthy.apps.events.views',
    url(r'^%s/$' % section_name, 'events', name='events'),
    
    url(r'^%s/all/$' % section_name, 'all', name='all_events'),
)