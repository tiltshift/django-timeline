from django import template

from templatetag_sugar.register import tag
from templatetag_sugar.parser import Variable

register = template.Library()

@tag(register, [Variable("event")])
def render_event(context, event):
    return event.render(context)
