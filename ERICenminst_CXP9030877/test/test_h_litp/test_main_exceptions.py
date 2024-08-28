from mock import MagicMock
from unittest2 import TestCase

from h_litp.litp_rest_client import LitpException
from h_litp.litp_utils import main_exceptions
from h_util.h_utils import ExitCodes


class TestMainExceptions(TestCase):
    @staticmethod
    def dummy_main(exception):
        if exception:
            raise exception

    @staticmethod
    def dummy_main1():
        pass

    def test_main_exceptions_interrupts(self):
        with self.assertRaises(SystemExit) as error:
            main_exceptions(TestMainExceptions.dummy_main,
                            KeyboardInterrupt('This is an expected error'))
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        m_interrupt_handler = MagicMock()
        with self.assertRaises(SystemExit) as error:
            main_exceptions(TestMainExceptions.dummy_main,
                            KeyboardInterrupt('This is an expected error'))
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)
        self.assertTrue('interrupt_handler was not called!',
                        m_interrupt_handler.called)

    def test_main_exceptions_litp(self):
        le = LitpException(1, 'This is an expected error')
        self.assertRaises(SystemExit, main_exceptions,
                          TestMainExceptions.dummy_main,
                          le)

        le = LitpException(1, {'a': 'This is an expected error'})
        self.assertRaises(SystemExit, main_exceptions,
                          TestMainExceptions.dummy_main,
                          le)

        le = LitpException(1,
                           {'messages':  ['This is an expected error']})
        self.assertRaises(SystemExit, main_exceptions,
                          TestMainExceptions.dummy_main,
                          le)

        le = LitpException(1,
                           {'messages':  [{'a': 'This is an expected error'}]})
        self.assertRaises(SystemExit, main_exceptions,
                          TestMainExceptions.dummy_main,
                          le)

    def test_main_exceptions(self):
        main_exceptions(TestMainExceptions.dummy_main1, None)

        self.assertRaises(IOError, main_exceptions,
                          TestMainExceptions.dummy_main,
                          IOError())
        self.assertRaises(SystemExit, main_exceptions,
                          TestMainExceptions.dummy_main,
                          SystemExit())
