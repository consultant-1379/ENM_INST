import os
import socket

from mock import patch
from unittest2 import TestCase

from h_litp import litp_maintenance
from h_litp.litp_maintenance import LitpMaintenance, JOB_STATE_RUNNING, JOB_STATE_DONE, JOB_STATE_NONE
from h_litp.litp_rest_client import LitpException, LitpRestClient
from test_utils import mock_litp_get_requests

current_path = os.path.dirname(__file__)


class TestLitpMaintenance(TestCase):
    def setUp(self):
        litp = LitpRestClient()
        self.instance = LitpMaintenance(client=litp)
        litp_maintenance.MAINTENANCE_READ_WAIT_SECONDS = 0.1

    def test_get_status_no_maintenance(self):
        mock_litp_get = self.prepare_litp_maintenance_instance(["/litp/maintenance"],
                                                               ["_litp_maintenance_not_enabled.json"])

        status = self.instance.get_status()
        self.assertEqual(JOB_STATE_NONE, status)
        self.assertFalse(self.instance.is_operation_running(status))

        self.assertTrue(mock_litp_get.called)

    def test_get_status_running(self):
        mock_litp_get = self.prepare_litp_maintenance_instance(["/litp/maintenance"],
                                                               ["_litp_maintenance_running.json"])

        status = self.instance.get_status()
        self.assertEqual(JOB_STATE_RUNNING, status)
        self.assertTrue(self.instance.is_operation_running(status))

        self.assertTrue(mock_litp_get.called)

    def test_status_finished(self):
        mock_litp_get = self.prepare_litp_maintenance_instance(["/litp/maintenance"],
                                                               ["_litp_maintenance_done.json"])

        status = self.instance.get_status()
        self.assertEqual(JOB_STATE_DONE, status)
        self.assertFalse(self.instance.is_operation_running(status))

        self.assertTrue(mock_litp_get.called)

    def test_maintenance_mode_not_enabled_status_finished(self):
        mock_litp_get = self.prepare_litp_maintenance_instance(["/litp/maintenance"],
                                                               ["_litp_maintenance_not_enabled_done.json"])

        status = self.instance.get_status()
        self.assertEqual(JOB_STATE_DONE, status)
        self.assertFalse(self.instance.is_operation_running(status))

        mode = self.instance.is_maintenance_mode()
        self.assertFalse(mode)

        self.assertTrue(mock_litp_get.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_status_litp_problems(self, m_litp_get):
        m_litp_get.side_effect = LitpException('Problem')

        self.assertRaises(ValueError, self.instance.get_status)

    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_status_socket_problems(self, m_litp_get):
        m_litp_get.side_effect = socket.error(111, "Connection refused")

        self.assertRaises(ValueError, self.instance.get_status)

    def test_is_maintenance_mode_when_not_enabled(self):
        mock_litp_get = self.prepare_litp_maintenance_instance(["/litp/maintenance"],
                                                               ["_litp_maintenance_not_enabled.json"])
        mode = self.instance.is_maintenance_mode()
        self.assertFalse(mode)

        self.assertTrue(mock_litp_get.called)

    def test_is_maintenance_mode_when_running(self):
        mock_litp_get = self.prepare_litp_maintenance_instance(["/litp/maintenance"],
                                                               ["_litp_maintenance_running.json"])
        mode = self.instance.is_maintenance_mode()
        self.assertTrue(mode)

        self.assertTrue(mock_litp_get.called)

    def test_is_maintenance_mode_when_done(self):
        mock_litp_get = self.prepare_litp_maintenance_instance(["/litp/maintenance"],
                                                               ["_litp_maintenance_done.json"])
        mode = self.instance.is_maintenance_mode()
        self.assertTrue(mode)

        self.assertTrue(mock_litp_get.called)

    def prepare_litp_maintenance_instance(self, urls, paths=None):
        mock_litp_get = mock_litp_get_requests(
            current_path, urls, paths
        )
        self.instance.litp.get = mock_litp_get
        return mock_litp_get
