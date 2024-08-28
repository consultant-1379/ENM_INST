# -*- coding: utf-8 -*-
from mock import patch, Mock
import test_utils

fcaps_healthcheck_modules = test_utils.mock_fcaps_healthcheck_module()
fcaps_healthcheck_module_patcher = patch.dict('sys.modules', fcaps_healthcheck_modules)
fcaps_healthcheck_module_patcher.start()

from nasaudit_error_check import NasAuditCheck
from h_litp.litp_rest_client import LitpException
from restapi import RESTapi
from enm_healthcheck import HealthCheck
import unittest2


class NasAuditCheckUnitTests(unittest2.TestCase):

    @patch('h_litp.litp_rest_client.LitpRestClient.get', return_value={"properties":{"ipaddress":"172.16.206.140"}})
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    def test_build_alarm_url(self, mock_ip_path, *_):
        mock_ip_path.side_effect = [[{"data": {"id": "svc_cluster"}, "path": "/litp/haproxy_int_ip"}], \
                                    [{"path": "/litp/haproxy_int_ip"}]]
        nac = NasAuditCheck()
        alarm_url = "http://172.16.206.140:8081/internal-alarm-service/internalalarm/internalalarmservice/translate"
        self.assertEquals(nac.build_alarm_url(), alarm_url)

    @patch('h_litp.litp_rest_client.LitpRestClient.get', side_effect=LitpException)
    @patch('nasaudit_error_check.init_enminst_logging')
    def test_build_alarm_url_exception(self, mock_log, *_):
        nac = NasAuditCheck()
        with self.assertRaises(LitpException):
            nac.build_alarm_url()
            self.assertEquals(mock_log.return_value.error.call_count, 1)

    @patch('nasaudit_error_check.NasAuditCheck.build_alarm_url')
    @patch.object(RESTapi, 'post')
    def test_build_alarm(self, mock_rest, *_):
        nac = NasAuditCheck()
        mock_rest.return_value = 'Success'
        self.assertEquals(nac.build_alarm(), "Success")

    @patch('nasaudit_error_check.NasAuditCheck.build_alarm')
    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    @patch('nasaudit_error_check.NasConsole')
    @patch.object(HealthCheck,'_get_nas_info')
    @patch.object(HealthCheck,'_get_psw')
    @patch('enm_healthcheck.get_nas_type')
    @patch('nasaudit_error_check.init_enminst_logging')
    def test_nasaudit_main_minor(self, mock_log, mock_nas_type,
                                 mock_pwd, mock_nas_info,
                                 mock_exec, mock_litp_maintenance, *_):
        nac = NasAuditCheck()
        mock_nas_info.return_value = {'nas': ["sfs-service", "sfs-pool",
                                              "sfs-filesystem"]}
        mock_pwd.return_value = 'some_pwd'
        mock_exec.return_value.exec_basic_nas_command.side_effect = (
            [(0, "success", "no_error", "clear"),
             (0, "success", "no_error", "clear"),
             (3, "success", "minor", "cleared")])
        mock_litp_maintenance.return_value=False
        mock_nas_type.return_value = ''
        nac.nasaudit_main()
        self.assertEquals(mock_log.return_value.info.call_count, 2)

    @patch('nasaudit_error_check.NasAuditCheck.build_alarm')
    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    @patch('nasaudit_error_check.NasConsole')
    @patch.object(HealthCheck,'_get_nas_info')
    @patch.object(HealthCheck,'_get_psw')
    @patch('enm_healthcheck.get_nas_type')
    @patch('nasaudit_error_check.init_enminst_logging')
    def test_nasaudit_main_critical(self, mock_log, mock_nas_type,
                                    mock_pwd, mock_nas_info,
                                    mock_exec, mock_litp_maintenance, *_):
        nac = NasAuditCheck()
        mock_nas_info.return_value = {'nas': ["sfs-service", "sfs-pool",
                                              "sfs-filesystem"]}
        mock_pwd.return_value = 'some_pwd'
        mock_exec.return_value.exec_basic_nas_command.side_effect = (
            [(0, "success", "no_error", "clear"),
             (0, "success", "no_error", "clear"),
             (1, "success", "critical", "cleared")])
        mock_litp_maintenance.return_value=False
        mock_nas_type.return_value = ''
        nac.nasaudit_main()
        self.assertEquals(mock_log.return_value.info.call_count, 2)

    @patch('nasaudit_error_check.NasAuditCheck.build_alarm')
    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    @patch('nasaudit_error_check.NasConsole')
    @patch.object(HealthCheck, '_get_nas_info')
    @patch.object(HealthCheck, '_get_psw')
    @patch('enm_healthcheck.get_nas_type')
    @patch('nasaudit_error_check.init_enminst_logging')
    def test_nasaudit_main_cleared(self, mock_log, mock_nas_type,
                                   mock_pwd, mock_nas_info,
                                   mock_exec, mock_litp_maintenance, *_):
        nac = NasAuditCheck()
        mock_nas_info.return_value = {'nas': ["sfs-service", "sfs-pool",
                                              "sfs-filesystem"]}
        mock_pwd.return_value = 'some_pwd'
        mock_exec.return_value.exec_basic_nas_command.side_effect = (
            [(0, "success", "no_error", "clear"),
             (0, "success", "no_error", "clear"),
             (0, "success", "no_error", "cleared")])
        mock_litp_maintenance.return_value=False
        mock_nas_type.return_value = ''
        nac.nasaudit_main()
        self.assertEquals(mock_log.return_value.info.call_count, 2)

    @patch('nasaudit_error_check.NasConsole')
    @patch.object(HealthCheck, '_get_nas_info')
    @patch.object(HealthCheck, '_get_psw')
    @patch('enm_healthcheck.get_nas_type')
    @patch('nasaudit_error_check.init_enminst_logging')
    def test_nasaudit_main_error(self, mock_log, mock_nas_type,
                                 mock_pwd, mock_nas_info,
                                 mock_exec, *_):
        nac = NasAuditCheck()
        mock_nas_info.return_value = {'nas': ["sfs-service", "sfs-pool",
                                              "sfs-filesystem"]}
        mock_pwd.return_value = 'some_pwd'
        mock_exec.return_value.exec_basic_nas_command.side_effect = (
            [(1, "fail", "error", "no_clear"),
             (1, "fail", "error", "no_clear"),
             (4, "fail", "error", "no_clear")])
        mock_nas_type.return_value = ''
        with self.assertRaises(SystemExit):
            nac.nasaudit_main()
            mock_log.assert_called_with("HealthCheck status: FAILED.")

    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    @patch('nasaudit_error_check.init_enminst_logging')
    def test_check_litp_maintenance(self, mock_log, m_litp_maintenance):
        nac = NasAuditCheck()
        m_litp_maintenance.return_value = True
        self.assertTrue(nac.check_litp_maintenance())
        mock_log.return_value.warning.assert_called_with("LITP is in maintenance mode")

    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    def test_check_litp_not_maintenance(self, m_litp_maintenance):
        nac = NasAuditCheck()
        m_litp_maintenance.return_value = False
        self.assertFalse(nac.check_litp_maintenance())

    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    def test_check_litp_maintenance_raise_exception(self, m_litp_maintenance):
        nac = NasAuditCheck()
        m_litp_maintenance.side_effect = ValueError
        self.assertRaises(SystemExit, nac.check_litp_maintenance)


if __name__ == "__main__":
    unittest2.main(verbosity=2)

