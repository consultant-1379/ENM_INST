import os
import unittest2
from h_logging.enminst_logger import init_enminst_logging
from os.path import dirname, join
from unittest2 import TestCase


class TestEnminstLogger(TestCase):
    def setUp(self):
        thispath = dirname(__file__.replace(os.sep, '/'))
        thispath = dirname(thispath)
        thispath = dirname(thispath)
        os.environ['ENMINST_CONF'] = join(thispath, 'src/main/resources/conf')
        self.logger = init_enminst_logging()

    def test_info(self):
        self.logger.info('woo')

    def test_debug(self):
        self.logger.debug('woo')

    def test_error(self):
        self.logger.error('woo')

    def test_warning(self):
        self.logger.warning('woo')


if __name__ == '__main__':
    unittest2.main()
