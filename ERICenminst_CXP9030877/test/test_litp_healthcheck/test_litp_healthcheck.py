from os.path import join, dirname
import unittest2
import os
import litp_healthcheck
from tempfile import gettempdir
from mock import patch

tmp_root = join(gettempdir(), 'TestHealthcheck')


class TestLitpHealthcheck(unittest2.TestCase):
    def setUp(self):
        basepath = dirname(dirname(dirname(__file__.replace(os.sep, '/'))))
        os.environ['ENMINST_CONF'] = join(basepath, 'src/main/resources/conf')
        self.tmp_conf = join(tmp_root, 'ENMINST_CONF')
        self.lhc = litp_healthcheck.LitpCheck()

    @patch('litp_healthcheck.LitpCheck.healthcheck_status')
    @patch('litp_healthcheck.exec_process')
    def test_check_services_status_error(
            self, exec_process, healthcheck_status):
        exec_process.side_effect = IOError
        self.lhc.check_services_status()
        self.assertTrue(exec_process.called)
        healthcheck_status.assert_called_with(4)

    def test_check_services_status_no_conf(self):
        self.lhc.litp_health_conf = 'non/existing/conf/file'
        self.assertRaises(SystemExit, self.lhc.check_services_status)

    @patch('litp_healthcheck.LitpCheck.healthcheck_status')
    @patch('litp_healthcheck.exec_process')
    def test_check_services_status_no_error(
            self, exec_process, healthcheck_status):
        self.lhc.check_services_status()
        self.assertTrue(exec_process.called)
        self.assertTrue(healthcheck_status.called)

    def test_healthcheck_status_error(self):
        self.assertRaises(SystemExit, self.lhc.healthcheck_status, 1)

    def test_healthcheck_status_no_error(self):
        self.assertEquals(self.lhc.log.info
                          ('-' * 67 + '\n All LITP services running\t\t\t'
                                      '{ SUCCESS }\n' + '-' * 67),
                          self.lhc.healthcheck_status(0))

    @patch('litp_healthcheck.LitpCheck')
    def test_main(self, lhc):
        litp_healthcheck.main()
        self.assertTrue(lhc.return_value.check_services_status.called)


if __name__ == '__main__':
    unittest2.main()
