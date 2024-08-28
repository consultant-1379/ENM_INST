from unittest2 import TestCase
from h_util.h_collections import ExceptHandlingDict


class TestCollections(TestCase):

    def test_except_handling_dict(self):
        class MyException(Exception):
            pass

        tester = {
            "dict1": {
                "string": "test string"
            },
            "dict_list": [
                {
                    "num1": 1,
                    "num2": 2
                },
                {
                    "num3": 3,
                    "num4": 4
                }]
        }

        exc_handling_dict = ExceptHandlingDict.get_dict(tester, MyException)

        self.assertIs(type(exc_handling_dict), ExceptHandlingDict)
        self.assertIs(type(exc_handling_dict['dict1']), ExceptHandlingDict)
        self.assertIs(type(exc_handling_dict['dict_list'][0]),
                      ExceptHandlingDict)

        self.assertEquals(exc_handling_dict['dict_list'][0]['num2'], 2)

        with self.assertRaises(MyException):
            res = exc_handling_dict['invalid_key']

        with self.assertRaises(MyException):
            res = exc_handling_dict['dict1']['invalid_key']

        with self.assertRaises(MyException):
            res = exc_handling_dict['dict_list'][0]['invalid_key']
