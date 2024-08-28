import datetime
from unittest2 import TestCase


from h_util.h_decorators import cached_classmethod, cached_method, \
    cached_property, retry_if_fail, clear_cache


class TestDecorators(TestCase):
    def test_cached_classmethod(self):
        class A(object):
            x = 1

            @cached_classmethod()
            def method(cls):
                v = cls.x
                cls.x += 1
                return v

        a = A()
        self.assertEquals(A.x, 1)
        self.assertEquals(a.method(), 1)
        self.assertEquals(a.method(), 1)

    def test_cached_method(self):
        class A(object):
            x = 1

            @cached_method()
            def method(self):
                v = self.x
                self.x += 1
                return v

        a = A()
        self.assertEquals(A.x, 1)
        self.assertEquals(a.method(), 1)
        self.assertEquals(a.method(), 1)

    def test_cached_property(self):
        # Purpose of this function is to mock datetime because Python built-in
        # types are immutable and cannot be set mocked through @patch
        def new_datetime(secs):
            class NewDatetime(datetime.datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime.datetime(2019, 4, 17, 9, 25, secs, 561000)
            return NewDatetime
        # preserve original builtin functionality
        original_datetime = datetime.datetime

        class A(object):
            x = 1

            @cached_property(10)
            def prop(self):
                v = self.x
                self.x += 1
                return v

        try:
            # set datetime builtin to mock
            datetime.datetime = new_datetime(42)
            a = A()
            self.assertEquals(A.x, 1)
            self.assertEquals(a.prop, 1)
            datetime.datetime = new_datetime(49)
            self.assertEquals(a.prop, 1)

            datetime.datetime = new_datetime(53)
            self.assertEquals(a.prop, 2)
        finally:
            # set back original datetime builtin
            datetime.datetime = original_datetime

    def test_cache_cleared(self):
        class A(object):
            x = 1

            @cached_property()
            def prop(self):
                v = self.x
                self.x += 1
                return v

        a = A()
        self.assertEquals(A.x, 1)
        self.assertEquals(a.prop, 1)
        clear_cache(a, 'prop')
        self.assertEquals(a.prop, 2)

    def test_retry_if_fail(self):
        d = {'count': 0}

        @retry_if_fail(3, 0.1, KeyError, ["invalid_key"])
        def func(data):
            data['count'] += 1
            return data["invalid_key"]

        self.assertEquals(d['count'], 0)
        with self.assertRaises(KeyError):
            func(d)
        self.assertEquals(d['count'], 4)
