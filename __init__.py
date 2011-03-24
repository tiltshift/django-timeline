from django.conf import settings
from django.utils.importlib import import_module
from django.utils.module_loading import module_has_submodule

def autodiscover():
    """
    Automatically import the events module for all INSTALLED_APPS.  Based on
    ``django.contrib.admin.autodiscover``.
    """
    
    for app in settings.INSTALLED_APPS:
        mod = import_module(app)
        try:
            import_module("%s.events" % app)
        except ImportError:
            if module_has_submodule(mod, "events"):
                raise
