""" Helper class representing filesystem space usage values
for comparison and math operations"""
# pylint: disable=C0103,R0903,R0904,W0212
import re
from decimal import Decimal


class SizeDoesNotMatch(Exception):
    """ Exception raised if size does not match unit format """


class UnitNotAllowed(Exception):
    """ Exception raised if invalid unit format passed """


class Unit(int):
    """ Unit representation """
    def __new__(cls, value, *names):
        obj = int.__new__(cls, value)
        obj.names = names
        return obj


class Units(object):
    """ Class representing valid unit formats """
    b = Unit(1, "b", "B")
    k = Unit(1024 * b, "k", "K", "kb", "Kb", "kB", "KB")
    m = Unit(1024 * k, "m", "M", "mb", "Mb", "mB", "MB")
    g = Unit(1024 * m, "g", "G", "gb", "Gb", "gB", "GB")
    t = Unit(1024 * g, "t", "T", "tb", "Tb", "tB", "TB")

    @classmethod
    def units(cls):
        """ return all possible units """
        return sorted([(i, getattr(cls, i)) for i in dir(cls) if
                       isinstance(getattr(cls, i), Unit)], key=lambda x: x[1])

    @classmethod
    def allowed_units(cls):
        """ return allowed units """
        units = reduce(lambda a, b: a + b,
                       [[n for n in v.names] for _, v in cls.units()], [])
        return set(units)


class SizeMeta(type):
    """ This metaclass dynamically overrides the math operation methods.
    """

    operations = ['add', 'sub', 'mul', 'div', 'truediv', 'divmod', 'mod',
                  'floordiv', 'pow']
    operations = ['__%s__' % o for o in operations]

    def __new__(mcs, name, bases, attrs):

        def new_func(member):
            """ Wrapper """
            def func(self, other, context=None):
                """ Function overrides the math operation methods """
                result = member(self, other, context)
                if isinstance(result, Size):
                    return result
                return Size('%sb' % result)

            return func

        for op in mcs.operations:
            attrs[op] = new_func(getattr(bases[0], op))

        return type.__new__(mcs, name, bases, attrs)


class Size(Decimal):
    """ It wraps the size of file systems for comparison and math operations
    purposes.
    """

    __metaclass__ = SizeMeta

    size_regex = re.compile(r"^\s*([\-]{0,1})([\d\.]+)\s*((?:%s))\s*$" %
                            '|'.join(Units.allowed_units()))

    def __new__(cls, value, *args, **kwargs):
        """ The size must match the size_regex.
        >>> Size("1024m") == Size("1g")
        True
        >>> Size("1t") / Decimal("2") == Size("0.5t")
        True
        >>> Size("1.5m") + Size("512k") == Size("2m")
        True
        """
        value = str(value).strip()
        if value.isdigit() and int(value) == 0:
            _sign, digit, unit = False, 0, "b"
        else:
            match = cls.size_regex.match(value)
            if match is None:
                raise SizeDoesNotMatch("The size %s does not match format" %
                                       value)
            _sign, digit, unit = match.groups()
        sign = -1 if _sign else 1
        unit = unit.lower()
        num_bytes = Size._convert_to_bytes(digit, unit) * sign
        obj = super(Size, cls).__new__(cls, num_bytes, *args, **kwargs)
        obj._unit = unit[0]
        obj._bytes = num_bytes
        return obj

    def __repr__(self):
        """ Returns the representation string of this object
        >>> Size("2.5t")
        <Size 2.5T>
        """
        return "<Size %s>" % str(self)

    def __str__(self, *args, **kwargs):
        """ Returns the size and unit as a str.
        """
        number = self._bytes
        units = Units.units()
        units.reverse()
        unit_name, unit = units.pop()
        while number >= 1024:
            unit_name, unit = units.pop()
            number = self._bytes / unit
        num = str(number.quantize(Decimal(".1"))).rstrip("0").rstrip(".")
        return Size._display(num, unit_name)

    @staticmethod
    def _clean_unit(unit):
        """ Validates the size unit whether is allowed or not and returns it as
        a lower case.
        >>> Size._clean_unit('K')
        'k'
        >>> Size._clean_unit('G')
        'g'
        >>> Size._clean_unit('m')
        'm'
        >>> try:
        ...    Size._clean_unit('X')
        ... except Exception, err:
        ...    pass
        ...
        >>> err
        UnitSizeNotAllowed('The unit size x must be one of the: b, k, m, g, \
t',)
        """
        unit = unit.lower()
        allowed = Units.allowed_units()
        if unit not in allowed:
            raise UnitNotAllowed("The unit size %s must be one of the: %s"
                                 % (unit, ', '.join(allowed)))
        return unit

    @classmethod
    def _display(cls, digit, unit):
        """ Return a string as the default format of a storage Size:
        >>> Size._display(10, 'k')
        '10K'
        >>> Size._display(2.5, 'g')
        '2.5G'
        """
        unit = cls._clean_unit(unit)
        return "%s%s" % (digit, unit.upper())

    @classmethod
    def _unit_num_bytes(cls, unit):
        """ Return the number of bytes given a unit in: K, M, G, T.
        """
        unit = cls._clean_unit(unit)
        return Decimal(str(getattr(Units, unit[0])))

    @classmethod
    def _convert_to_bytes(cls, digit, unit):
        """ Return the number of bytes given a digit and a unit in: K, M, G, T.
        """
        unit = cls._clean_unit(unit)
        return Decimal(digit) * Size._unit_num_bytes(unit)

    @classmethod
    def convert_bytes_to_unit(cls, num_bytes, convert_unit):
        """ Coverts num_bytes to a given unit in: K, M, G, T.
        """
        convert_unit = Size._clean_unit(convert_unit)
        return num_bytes / Size._unit_num_bytes(convert_unit)

    def number_in_unit(self, convert_unit):
        """ Return the number of bytes given a digit and a unit in: K, M, G, T.
        """
        return Size.convert_bytes_to_unit(self.num_bytes, convert_unit)

    def convert_to_unit(self, convert_unit):
        """ Returns the size converted to the given unit.
        """
        digit = Size.convert_bytes_to_unit(self.num_bytes, convert_unit)
        return digit

    def display_relative_to(self, other):
        """ The default display of a Size is based on __str__ which displays
        at maximum 3 decimal places with the corresponding unit and rounded
        with quantize("0.01"). Sometimes, when comparing 2 sizes, for instance,
        Size('1.001G') and Size('1.002G'), it will be displayed as same as
        '1.00G' and '1.00G' respectively, they might look the same, but they
         are different. They are just rounded and displayed as the same.

        This method will display a rounded size compared against another one,
        using the previous unit, to avoid the scenario mentioned above. It will
        happen only if the sizes are too close to each other, to avoid looking
        the same. If not, the size will be display normally.
        For example:

        >>> "%s is greater than %s" % (Size("1.003G"), Size("1.001g"))
        '1.00G is greater than 1.00G'
        >>> # above doesn't look well
        ...
        >>> s1 = Size("1.003G").display_relative_to(Size("1.001g"))
        >>> s2 = Size("1.001g").display_relative_to(Size("1.003g"))
        >>> "%s is greater than %s" % (s1, s2)
        '1027.07M is greater than 1025.02M'
        >>> # much better now, now both showing with 4 decimal places for a
        ... # higher precision of comparison

        :param Size other: Size instance
        :return str: str
        """
        if not self:
            return str(self)
        if str(self) != str(other):
            return str(self)
        units = [u[0] for u in Units.units()]
        unit = str(self)[-1].lower()
        try:
            index = units.index(unit)
        except ValueError:
            return str(self)
        if not index:
            return str(self)
        prev_unit = units[index - 1]
        converted = self.convert_to_unit(prev_unit).quantize(Decimal(".01"))
        return self._display(converted, prev_unit)

    @property
    def num_bytes(self):
        """ Return the number of bytes of this size object.
        """
        return self._bytes

    @property
    def half_k_blocks(self):
        """ Return the number of blocks in (512 bytes) of this size object.
        """
        return self.num_bytes / 512

    @property
    def unit(self):
        """ Return the unit of this size object.
        """
        return self._unit

    @property
    def kilos(self):
        """ Returns this object size as kilos Size.
        """
        return self.convert_to_unit('k')

    @property
    def megas(self):
        """ Returns this object size as megas Size.
        """
        return self.convert_to_unit('m')

    @property
    def gigas(self):
        """ Returns this object size as gigas Size.
        """
        return self.convert_to_unit('g')

    @property
    def teras(self):
        """ Returns this object size as teras Size.
        """
        return self.convert_to_unit('t')
