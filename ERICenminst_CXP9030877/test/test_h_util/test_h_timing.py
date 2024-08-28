from decimal import Decimal
from unittest2 import TestCase
import datetime

from h_util.h_timing import microsec_to_sec, delta_to_ms, delta_to_seconds, \
    sec_pretty, TimeWindow


class TestTiming(TestCase):
    def setUp(self):
        self.dt_now = datetime.datetime(2020, 6, 4, 12, 43, 3, 133727)
        self.dt_past = datetime.datetime(2020, 6, 4, 9, 7, 31, 363234)
        self.delta = self.dt_now - self.dt_past

    def test_microsec_to_sec(self):
        seconds = microsec_to_sec(self.delta.microseconds)
        self.assertEquals(str(seconds), '0.8')

    def test_delta_to_ms(self):
        self.assertEquals(delta_to_ms(self.delta), 12931770)

    def test_delta_to_seconds(self):
        self.assertEquals(delta_to_seconds(self.delta), Decimal("12931.8"))

    def test_sec_pretty(self):
        self.assertEquals(sec_pretty(59), "59 seconds")
        self.assertEquals(sec_pretty(60), "1 minute")
        self.assertEquals(sec_pretty(61), "1 minute and 1 second")
        self.assertEquals(sec_pretty(3600), "1 hour")
        self.assertEquals(sec_pretty(3601), "1 hour and 1 second")
        self.assertEquals(sec_pretty(3660), "1 hour and 1 minute")
        self.assertEquals(sec_pretty(self.delta.seconds), "3 hours, 35 minutes and 31 seconds")

    def test_time_window(self):
        # Purpose of this function is to mock datetime because Python built-in
        # types are immutable and cannot be set mocked through @patch
        def new_datetime(secs=0, dt_obj=None):
            class NewDatetime(datetime.datetime):
                @classmethod
                def now(cls, tz=None):
                    return dt_obj or datetime.datetime(2020, 6, 4, 12, 43, secs, 133727)

            return NewDatetime

        # preserve original builtin functionality
        original_datetime = datetime.datetime
        try:
            # set datetime builtin to mock
            datetime.datetime = new_datetime(dt_obj=self.dt_now)
            with TimeWindow("Unit Tests") as tm:
                datetime.datetime = new_datetime(secs=10)
                self.assertEquals(tm.elapsed, 7)
                datetime.datetime = new_datetime(secs=11)
                self.assertEquals(tm.elapsed_ms, 8000)
                self.assertEquals(tm.elapsed_display, "8 seconds")
                self.assertEquals(tm.elapsed_display_short, "8s")

                datetime.datetime = new_datetime(secs=59)

            self.assertEquals(tm.duration_ms, 56000)
            self.assertEquals(tm.duration, 56)
            self.assertEquals(tm.duration_display, "56 seconds")
            self.assertEquals(tm.duration_display_short, "56s")
        finally:
            # set back original datetime builtin
            datetime.datetime = original_datetime
