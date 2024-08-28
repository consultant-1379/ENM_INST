""" Module to format datetime outputs and record time it takes
to execute wrapped code block"""
from collections import OrderedDict
import datetime
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

SECOND = 1
MINUTE = SECOND * 60
HOUR = MINUTE * 60
DAY = HOUR * 24
MONTH = DAY * 30
YEAR = DAY * 365


def microsec_to_sec(microsec, approx=0.1):
    """ Converts microseconds to seconds
    :param microsec:
    :param approx:
    :return: Decimal
    """
    return (Decimal(microsec) / 1000000).quantize(Decimal(str(approx)))


def delta_to_ms(delta):
    """ Converts delta to microseconds
    :param delta:
    :return: int
    """
    secs = delta.seconds
    days = delta.days
    microsec = (Decimal(delta.microseconds) / 1000).quantize(Decimal("0."))
    return int(secs * 1000 + microsec + days * DAY * 1000)


def sec_pretty(seconds, short=False, rounded=0):
    """ Converts seconds into human readable time format.
    >>> sec_pretty(12931)
    3 hours, 35 minutes and 31 seconds
    """
    seconds = Decimal(str(seconds)).quantize(Decimal("0.1"),
                                             rounding=ROUND_HALF_UP)
    periods = OrderedDict([
        ('year', {'short': 'y', 'seconds': YEAR}),
        ('month', {'short': 'M', 'seconds': MONTH}),
        ('day', {'short': 'd', 'seconds': DAY}),
        ('hour', {'short': 'h', 'seconds': HOUR}),
        ('minute', {'short': 'm', 'seconds': MINUTE}),
        ('second', {'short': 's', 'seconds': SECOND})
    ])

    def display(value, name):
        """ Prepares time period for string output """
        name = periods[name]['short'] if short else " %s" % name
        plural = 's' if not short and value > 1 else ''
        return "%s%s%s" % (value, name, plural)

    join_string = "" if short else ", "
    times = []
    if seconds < 1:
        times.append(display(seconds, "second"))
    else:
        count = 0
        for period_name, short_seconds in periods.items():
            period_seconds = short_seconds['seconds']
            period_value, seconds = divmod(seconds, period_seconds)
            seconds = int(Decimal(str(seconds)).quantize(Decimal("1."),
                                                         rounding=ROUND_DOWN))
            if not period_value:
                continue
            times.append(display(period_value, period_name))
            count += 1
            if count == rounded:
                break
    period_one = join_string.join(times[:-1])
    period_two = times[-1] if times else "0s"
    if not short and len(times) > 1:
        period_two = " and %s" % period_two
    return "%s%s" % (period_one, period_two)


def delta_to_seconds(delta, approx=0.1):
    """ Converts delta to seconds
    :param delta:
    :param approx:
    :return: int
    """
    days = delta.days
    mics = delta.microseconds
    return delta.seconds + microsec_to_sec(mics, approx) + days * DAY


class TimeWindow(object):
    """ A Context Manager that holds the time during the execution in the
    "with" statement.
    """

    def __init__(self, msg="Time window"):
        """ Constructor
        """
        self.msg = msg
        self.initial_time = None
        self.end = None

    def __repr__(self):
        """ Object representation in string """
        return "<%s: %s>" % (self.__class__.__name__, self.msg)

    def __enter__(self):
        """ Starts the "with" statement and prints the title msg indented in
        the corresponding level. It sets the initial time, stops the spinner
        animation of all nested parents and it starts a new spinner.
        :return: self
        """
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ It sets the end time and it stops the spinner animation.
        :param exc_type:
        :param exc_val:
        :param exc_tb:
        :return:
        """
        self.stop()

    def start(self):
        """ Takes initial timestamp on "with" entrance """
        if self.initial_time is None:
            self.initial_time = datetime.datetime.now()
        return self

    def stop(self):
        """ Takes timestamp on "with" exit """
        if self.end is None:
            self.end = datetime.datetime.now()

    @property
    def duration_ms(self):
        """ it returns the duration of execution of the "with" block in
        milliseconds.
        :return: int
        """
        end = datetime.datetime.now() if self.end is None else self.end
        return delta_to_ms(end - self.initial_time)

    @property
    def duration(self):
        """ it returns the duration of execution of the "with" block in
        seconds.
        :return: int
        """
        end = datetime.datetime.now() if self.end is None else self.end
        return delta_to_seconds(end - self.initial_time)

    @property
    def duration_display(self):
        """ Returns the duration as a string, e.g.: "46 seconds"
        :return: str
        """
        return sec_pretty(self.duration)

    @property
    def duration_display_short(self):
        """ Returns the duration as a string in a short format, e.g.: "2m13s"
        :return: str
        """
        return sec_pretty(self.duration, True)

    @property
    def elapsed_ms(self):
        """ It returns the duration in milliseconds of the execution since the
        beginning until this property is called.
        :return: int
        """
        return delta_to_ms(datetime.datetime.now() - self.initial_time)

    @property
    def elapsed(self):
        """ It returns the duration of execution since the beginning until this
        property is called.
        :return: int
        """
        return delta_to_seconds(datetime.datetime.now() - self.initial_time)

    @property
    def elapsed_display(self):
        """ Returns the elapsed time as a string, e.g.: "8 seconds"
        :return: str
        """
        return sec_pretty(self.elapsed)

    @property
    def elapsed_display_short(self):
        """ Returns the elapsed time in a short format, e.g.: "4m58s"
        :return: str
        """
        return sec_pretty(self.elapsed, True)
