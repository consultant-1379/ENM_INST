"""
Module containing general decorators
"""
##############################################################################
# COPYRIGHT Ericsson AB 2019
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import re
import datetime
import time
from functools import wraps

from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import to_ordinal


def retry_if_fail(retries, interval=10, exception=Exception, msgs=None,
                  stdout=False):
    """ Decorator to retry the execution of a method in case it fails.
    :param retries: int
    :param interval: int
    :param exception: Exception based class
    :param msgs: list of str
    :param stdout:
    :return: function/method
    """
    log = init_enminst_logging(logger_name="retry-if-failed")

    def decorator(func):
        """
        Decorator implementation
        :param func: function that requires a retry in case
        it fails with an exception
        :return: decorated function wrapper
        """
        @wraps(func)
        def wrapper(*args, **kwargs):  # pylint: disable=W0703, W0142, W1201
            """
            Decorated function wrapper
            :param args: from original function
            :param kwargs: from original function
            :return: _run(n) function
            """
            def _run(count):
                """
                Runs decorated function
                :param count: number of retries
                """
                try:
                    return func(*args, **kwargs)
                except exception as err:
                    retry_cond = True
                    if msgs is not None:
                        retry_cond = any([m in str(err) for m in msgs])
                    if retry_cond and count < retries:
                        count += 1
                        msg = 'Failed to run "%s": %s: %s. Retrying to run ' \
                              'it again for the %s time in %s seconds.' % \
                              (func.__name__, type(err).__name__, str(err),
                               to_ordinal(count), interval)
                        log.info(msg)
                        if stdout:
                            print msg
                        time.sleep(interval)
                        return _run(count)
                    else:
                        raise
            return _run(0)
        return wrapper
    return decorator


def _get_cached_method_decorator(method_type=lambda x: x):
    """
    Factory for decorators to cache functions, class methods and
    properties results.
    :param method_type:
    :return: function
    """
    def _cache_decorator(expires=None):
        """
        Setups the decorator based on the expires value.
        :param expires: int
        :return: function
        """

        chars = re.compile(r'[^A-Za-z0-9]+')  # replace special chars

        def cached(method):
            """
            The actual decorator that will behave as method, or class method
            or property.
            :param method:
            :return: function
            """

            def wrap(obj, *args, **kwargs):
                """
                The function that wraps the decorated method and
                caches the results of it.
                :param obj:
                :param args:
                :param kwargs:
                :return: function
                """
                suffix = '_'.join([chars.sub('_', str(a)) for a in args])
                suffix += '_'.join(["%s_%s" % (chars.sub('_', str(k)),
                                               chars.sub('_', str(v)))
                                   for k, v in kwargs.items()])
                suffix = "_%s" % suffix if suffix else ""
                attr_name = "_cache_%s%s" % (method.__name__, suffix)
                expires_attr = "%s_expires" % attr_name
                cache = getattr(obj, attr_name, None)
                exp_dt = getattr(obj, expires_attr, None)

                if cache is not None and expires is not None and \
                    exp_dt is None:
                    delta = datetime.timedelta(seconds=expires)
                    setattr(obj, expires_attr, datetime.datetime.now() + delta)

                if cache is None or (exp_dt and
                                     datetime.datetime.now() > exp_dt):
                    setattr(obj, attr_name, method(obj, *args, **kwargs))
                    if expires is not None:
                        delta = datetime.timedelta(seconds=expires)
                        setattr(obj, expires_attr,
                                datetime.datetime.now() + delta)
                return getattr(obj, attr_name)
            wrap.expires = expires
            return method_type(wrap)

        return cached

    return _cache_decorator


def cached_classmethod(expires=None):
    """
    Cached class method
    :param expires:
    :return: method
    """
    return _get_cached_method_decorator(classmethod)(expires)


def cached_method(expires=None):
    """
    Cached method
    :param expires:
    :return: method
    """
    return _get_cached_method_decorator()(expires)


def cached_property(expires=None):
    """
    Cached property
    :param expires:
    :return: method
    """
    return _get_cached_method_decorator(property)(expires)


def clear_cache(obj, attr):
    """
    Clears specified attribute cache of a given object
    :param obj:
    :param attr:
    :return:
    """
    cache_attr = "_cache_%s" % attr
    for attr in dir(obj):
        if not attr.startswith(cache_attr):
            continue
        delattr(obj, attr)
