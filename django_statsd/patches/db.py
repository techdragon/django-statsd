import django
from django.db.backends import utils

from django_statsd.patches.utils import wrap, patch_method
from django_statsd.clients import statsd


def key(db, attr):
    return 'db.%s.%s.%s' % (db.client.executable_name, db.alias, attr)


def pre_django_1_6_cursorwrapper_getattr(self, attr):
    """
    The CursorWrapper is a pretty small wrapper around the cursor.
    If you are NOT in debug mode, this is the wrapper that's used.
    Sadly if it's in debug mode, we get a different wrapper.
    """
    if self.db.is_managed():
        self.db.set_dirty()
    if attr in self.__dict__:
        return self.__dict__[attr]
    else:
        if attr in ['execute', 'executemany', 'callproc']:
            return wrap(getattr(self.cursor, attr), key(self.db, attr))
        return getattr(self.cursor, attr)


def _get_query_type(query):
    return (query.split(None, 1) or ['__empty__'])[0].lower()


def patched_execute(orig_execute, self, query, *args, **kwargs):
    with statsd.timer(key(self.db, 'execute.%s' % _get_query_type(query))):
        return orig_execute(self, query, *args, **kwargs)

def patched_executemany(orig_executemany, self, query, *args, **kwargs):
    with statsd.timer(key(self.db, 'executemany.%s' % _get_query_type(query))):
        return orig_executemany(self, query, *args, **kwargs)


def patched_callproc(orig_callproc, self, query, *args, **kwargs):
    with statsd.timer(key(self.db, 'callproc.%s' % _get_query_type(query))):
        return orig_callproc(self, query, *args, **kwargs)


def patch():
    """
    The CursorWrapper is a pretty small wrapper around the cursor.  If
    you are NOT in debug mode, this is the wrapper that's used.  Sadly
    if it's in debug mode, we get a different wrapper for version
    earlier than 1.6.
    """

    if django.VERSION > (1, 6):
        # In 1.6+ utils.CursorDebugWrapper just makes calls to CursorWrapper
        # As such, we only need to instrument CursorWrapper.
        # Instrumenting both will result in duplicated metrics
        patch_method(utils.CursorWrapper, 'execute')(patched_execute)
        patch_method(utils.CursorWrapper, 'executemany')(patched_executemany)
        patch_method(utils.CursorWrapper, 'callproc')(patched_callproc)
    else:
        utils.CursorWrapper.__getattr__ = pre_django_1_6_cursorwrapper_getattr
        patch_method(utils.CursorDebugWrapper, 'execute')(patched_execute)
        patch_method(
            utils.CursorDebugWrapper, 'executemany')(patched_executemany)
