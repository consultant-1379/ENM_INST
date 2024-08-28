import os
import sys
from os.path import exists
from StringIO import StringIO

from mock import MagicMock

if sys.platform.lower().startswith('win'):
    sys.modules['pwd'] = MagicMock()
import logging
import unittest2
from mock import patch
from tempfile import NamedTemporaryFile
import h_logging.enminst_logger as enminst_logger
import codecs

log_cfg = '''[loggers]
keys=root,enminst

[handlers]
keys=consoleHandler

[formatters]
keys=consoleFormatter

[logger_root]
level=CRITICAL
handlers=

[logger_enminst]
level=DEBUG
handlers=consoleHandler
qualname=enminst

[handler_consoleHandler]
class=StreamHandler
level=INFO
formatter=consoleFormatter
args=(sys.stdout,)

[formatter_consoleFormatter]
format=%(asctime)19s %(levelname)-5s %(funcName)-20s: %(message)s
datefmt=%Y-%m-%d %H:%M:%S
'''


class TestEnminstLogger(unittest2.TestCase):
    def setUp(self):
        if sys.__stdout__.encoding == 'UTF-8':
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout, 'strict')
        self.cfg_file = NamedTemporaryFile().name
        with open(self.cfg_file, 'w') as ofile:
            ofile.write(log_cfg)
        self.cmd_arg_file = NamedTemporaryFile().name

    def tearDown(self):
        if exists(self.cfg_file):
            os.remove(self.cfg_file)

    def test_init_enminst_logging_no_config_file(self):
        with patch('sys.stdout', new_callable=StringIO) as _stdout:
            enminst_logger.init_enminst_logging('no_config',
                                                'no_logging_config')
        self.assertTrue('Using basicConfig' in _stdout.getvalue())

    @patch('logging.getLogger')
    def test_init_enminst_logging(self, logger):
        logger.return_value = logging.Logger('enminst')
        log = enminst_logger.init_enminst_logging(
            logger_config=self.cfg_file)
        self.assertIsInstance(log, logging.Logger)

    @patch('logging.getLogger')
    def test_init_enminst_logging_existing(self, logger):
        logger.return_value = logging.Logger('enminst')
        _ = enminst_logger.init_enminst_logging(
            logger_config=self.cfg_file)
        log = enminst_logger.init_enminst_logging(
            logger_config=self.cfg_file)
        self.assertIsInstance(log, logging.Logger)

    @patch('logging.getLogger')
    def test_set_logging_level(self, logger):
        logger.return_value = logging.Logger('enminst')
        log = enminst_logger.init_enminst_logging(
            logger_config=self.cfg_file)
        enminst_logger.set_logging_level(log, 'DEBUG')
        for h in log.handlers:
            self.assertEquals(h.level, logging._levelNames['DEBUG'])

    @patch('h_logging.enminst_logger.read_enminst_config')
    def test_log_upgrade_cmd(self, m_read_config):
        args = ['/opt/ericsson/enminst/lib/upgrade.py', '-s',
                    '/tmp/SED', '-m', '/tmp/MODEL']
        calling_script = "upgrade_enm.sh"

        m_read_config.return_value = {'enm_cmd_arg_file': self.cmd_arg_file}
        enminst_logger.log_cmdline_args(calling_script, args)
        self.assertTrue(m_read_config.called)

        compare_str = "./upgrade_enm.sh -s /tmp/SED -m /tmp/MODEL"
        result = open(self.cmd_arg_file).readlines()[-1].strip("\n")
        try:
            self.assertEqual(compare_str, result)
        finally:
            os.remove(self.cmd_arg_file)


if __name__ == '__main__':
    unittest2.main()
