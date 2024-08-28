from decimal import Decimal
from unittest2 import TestCase

from h_util.h_units import UnitNotAllowed, Size, SizeDoesNotMatch


class TestSize(TestCase):

    def test_convert_bytes_to_unit_invalid_unit(self):
        """
            Assert UnitNotAllowed Exception when trying to convert
            bytes using undefined unit notation.

        """

        with self.assertRaises(UnitNotAllowed):
            Size.convert_bytes_to_unit(1024, 'X')

    def test_number_in_unit_valid_number_returned(self):
        """
            Assert value returned by number_in_unit is valid
            using all valid unit notations.

        """
        test_vals = ((1, ("b", "B")),
                     (1024, ("k", "K", "kb", "Kb", "kB", "KB")),
                     (1024 ** 2, ("m", "M", "mb", "Mb", "mB", "MB")),
                     (1024 ** 3, ("g", "G", "gb", "Gb", "gB", "GB")),
                     (1024 ** 4, ("t", "T", "tb", "Tb", "tB", "TB")))

        for val, units in test_vals:
            size = Size("%s%s" % (val, 'b'))
            for unit in units:
                res = size.number_in_unit(unit)
                self.assertEqual(1, res)

    def test_convert_to_unit(self):
        """
            Testing function that converts one unit value into a specified unit.
        """
        test_vals = (('1024b', 'k', '1'),
                     ('1024k', 'm', '1'),
                     ('1024m', 'g', '1'),
                     ('1024g', 't', '1'),
                     ('1k', 'b', '1024'),
                     ('2.3g', 'm', '2355.2'),
                     ('100.555k', 'm', '0.0981982421875'))

        for size, conv_unit, expected in test_vals:
            self.assertEqual(Size(size).convert_to_unit(conv_unit),
                             Decimal(expected))

    def test_new_size_does_not_match_format(self):
        """
            Testing SizeDoesNotMatch exception when invalid value passed
            to a Size constructor.
        """
        with self.assertRaises(SizeDoesNotMatch):
            Size('1')

        with self.assertRaises(SizeDoesNotMatch):
            Size(1)

        with self.assertRaises(SizeDoesNotMatch):
            Size('x')

        with self.assertRaises(SizeDoesNotMatch):
            Size('1x')

    def test_new_size_zero_value(self):
        s1 = Size(0)
        self.assertEqual(repr(s1), '<Size 0B>')
        self.assertEqual(str(s1), '0B')

        s1 = Size('0')
        self.assertEqual(repr(s1), '<Size 0B>')
        self.assertEqual(str(s1), '0B')

    def test_convert_size_str_over_1024(self):
        """
            Testing units converting to a next higher unit, i.e,
            1025b = 1.00k | 1024b = 1024b
        """
        test_vals = (('1024b', '1K'),
                     ('1025b', '1K'),
                     ('1025k', '1M'),
                     ('1025m', '1G'),
                     ('1025g', '1T'))

        for val, expected in test_vals:
            s1 = Size(val)
            self.assertEqual(str(s1), expected)

    def test_math_operations(self):
        """
            Testing math operations applied to a Size objects.
        """

        result = Size('2m') + Size('1023m')
        self.assertEqual(str(result), '1G')

        result = Size('2m') - Size('948k')
        self.assertEqual(str(result), '1.1M')

        result = Size('5m') * Size('3m')
        self.assertEqual(str(result), '15T')

        result = Size('15t') * Size('0m')
        self.assertEqual(str(result), '0B')

        result = Size('15t') / Size('3m')
        self.assertEqual(str(result), '5M')

        result = Size('1k') == Size('1024b')
        self.assertEqual(result, True)

    def test_half_k_blocks(self):
        """
            Testing function that returns total amount of half 'k' blocks
            from given unit value, i.e., 1024 / 512 = 2 k blocks
        """
        test_vals = (('1k', 1024 ** 1),
                     ('1m', 1024 ** 2),
                     ('1g', 1024 ** 3),
                     ('1t', 1024 ** 4))

        for test_val, expected in test_vals:
            test_case = Size(test_val).half_k_blocks
            self.assertEqual(int(test_case), expected / 512)

    def test_unit_from_size(self):
        """
            Testing function that obtain a unit notation from
            the Size object.
        """
        test_vals = (('2000b', 'b'),
                     ('3500k', 'k'),
                     ('2220m', 'm'),
                     ('33.33g', 'g'),
                     ('0.5t', 't'))

        for test_val, expected in test_vals:
            test_case = Size(test_val).unit
            self.assertEqual(test_case, expected)

    def test_units_to_kilos(self):
        """
            Testing unit conversion from bytes, megabytes,
            gigabytes, terabytes to kilobyte.
        """
        test_vals = (('2000b', '1.953125'),
                     ('3500k', '3500'),
                     ('2220m', '2273280'),
                     ('0.3g', '314572.8'),
                     ('0.01t', '10737418.24'))

        for test_val, expected in test_vals:
            test_case = Size(test_val).kilos
            self.assertEqual(test_case, Decimal(expected))

    def test_units_to_megas(self):
        """
            Testing unit conversion from bytes, kilobyte,
            gigabytes, terabytes to megabytes.
        """
        test_vals = (('1048576b', '1'),
                     ('1024k', '1'),
                     ('2220m', '2220'),
                     ('0.3g', '307.2'),
                     ('0.01t', '10485.76'))

        for test_val, expected in test_vals:
            test_case = Size(test_val).megas
            self.assertEqual(test_case, Decimal(expected))

    def test_units_to_gigas(self):
        """
            Testing unit conversion from bytes, kilobyte,
            megabytes, terabytes to gigabytes.
        """
        test_vals = (('1073741824b', '1'),
                     ('1048576k', '1'),
                     ('1024m', '1'),
                     ('0.3g', '0.3'),
                     ('0.01t', '10.24'))

        for test_val, expected in test_vals:
            test_case = Size(test_val).gigas
            self.assertEqual(test_case, Decimal(expected))

    def test_units_to_teras(self):
        """
            Testing unit conversion from bytes, kilobyte,
            megabytes, gigabytes to terabytes.
        """
        test_vals = (('109951162.7776b', '0.0001'),
                     ('1073741824k', '1'),
                     ('1048576m', '1'),
                     ('1024g', '1'),
                     ('0.01t', '0.01'))

        for test_val, expected in test_vals:
            test_case = Size(test_val).teras
            self.assertEqual(test_case, Decimal(expected))
