from unittest2 import TestCase
from mock import patch, Mock, mock_open, MagicMock

from san_fault_check import SanFaultCheck
from san_fault_check import SAN_ALERT_THRESHOLD
from san_fault_check import SAN_ALERT_INACTIVE
from h_litp.litp_rest_client import LitpException
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from naslib.nasexceptions import NasConnectionException

mock_litp_response = {u'id': u'haproxy-int_internal_vip',
                   u'item-type-name': u'vip',
                   u'applied_properties_determinable': True,
                   u'state': u'Applied',
                   u'_links': {u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/deployments/enm/'
                                                  u'clusters/svc_cluster/services/haproxy-int/'
                                                  u'ipaddresses/haproxy-int_internal_vip'},
                               u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/'
                                                       u'item-types/vip'}},
                   u'properties': {u'ipaddress': u'192.110.10.12',
                                   u'network_name': u'internal'}}

mock_get_litp_nas_servers_items = {
    "_embedded": {
        "item": [
            {
                "id": "virtual_server_enm_2",
                "item-type-name": "sfs-virtual-server",
                "applied_properties_determinable": True,
                "state": "Applied",
                "_links": {
                    "self": {
                        "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/unityxt/virtual_servers/virtual_server_enm_2"
                    },
                    "item-type": {
                        "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-virtual-server"
                    }
                },
                "properties": {
                    "ipv4address": "10.150.72.138",
                    "subnet": "10.150.72.0/23",
                    "name": "dummy_nas_server_2",
                    "sp": "spb",
                    "ports": "0,2",
                    "ndmp_password_key": "key-for-ndmp",
                    "sharing_protocols": "nfsv3,nfsv4",
                    "san_pool": "ENM1071",
                    "gateway": "10.150.72.1"
                }
            },
            {
                "id": "virtual_server_enm_1",
                "item-type-name": "sfs-virtual-server",
                "applied_properties_determinable": True,
                "state": "Applied",
                "_links": {
                    "self": {
                        "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/unityxt/virtual_servers/virtual_server_enm_1"
                    },
                    "item-type": {
                        "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-virtual-server"
                    }
                },
                "properties": {
                    "ipv4address": "10.150.72.137",
                    "subnet": "10.150.72.0/23",
                    "name": "dummy_nas_server_1",
                    "sp": "spa",
                    "ports": "0,2",
                    "ndmp_password_key": "key-for-ndmp",
                    "sharing_protocols": "nfsv3,nfsv4",
                    "san_pool": "ENM1071",
                    "gateway": "10.150.72.1"
                }
            }
        ]
    },
    "item-type-name": "collection-of-sfs-virtual-server",
    "applied_properties_determinable": True,
    "state": "Applied",
    "_links": {
        "self": {
            "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/unityxt/virtual_servers"
        },
        "collection-of": {
            "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-virtual-server"
        }
    },
    "id": "virtual_servers"
}

mock_get_litp_nas_servers_no_nas_servers = {
    "_embedded": {
        "item": []
    },
    "item-type-name": "collection-of-sfs-virtual-server",
    "applied_properties_determinable": True,
    "state": "Applied",
    "_links": {
        "self": {
            "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/unityxt/virtual_servers"
        },
        "collection-of": {
            "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-virtual-server"
        }
    },
    "id": "virtual_servers"
}

mock_san_info = {u'dummy_san_name': [u'10.1.1.100',
                                     u'10.1.1.100',
                                     u'ENM123',
                                     u'global',
                                     u'unity',
                                     u'admin',
                                     u'pAsSw0rD1234!']}

mock_san = "dummy_san_name"

mock_nas_servers = [
             {'name': u'dummy_nas_server_2', 'sp': u'spb'},
             {'name': u'dummy_nas_server_1', 'sp': u'spa'}]

mock_nas_servers_not_found = [
             {'name': u'dummy_nas_server_3', 'sp': u'spa'}]

mock_nas_servers_no_home = [
             {'name': u'dummy_nas_server_4', 'sp': u'spa'}]

mock_nas_servers_no_current = [
             {'name': u'dummy_nas_server_5', 'sp': u'spa'}]

mock_nas_servers_no_match = [
             {'name': u'dummy_nas_server_6', 'sp': u'spa'}]

mock_nas_servers_no_connect = [
             {'name': u'dummy_nas_server_7', 'sp': u'spa'}]



class TestSanFaultCheck(TestCase):

    def setUp(self):
        self.san_fault = SanFaultCheck()
        self.logger = init_enminst_logging()

    @patch('san_fault_check.get_nas_type')
    def test_is_unityxt(self, get):
        self.logger.error = MagicMock()

        get.return_value = "unityxt"
        self.assertTrue(self.san_fault.is_unityxt())

        get.side_effect = LitpException(
            404,
            {'path': '/infrastructure/storage/storage_providers/unityxt',
             'reason': 'Not Found',
             'messages': [
                 {u'_links': {
                     u'self': {
                         u'href': u'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/unityxt'}},
                  u'message': u'Not found',
                  u'type': u'InvalidLocationError'}]})
        self.assertFalse(self.san_fault.is_unityxt())

        get.side_effect = LitpException(
            405,
            {'path': '/infrastructure/storage/storage_providers/unityxt',
             'reason': 'Method Not Allowed',
             'messages': [
                 {u'_links': {
                     u'self': {
                         u'href': u'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/unityxt'}},
                  u'message': u'Method Not Allowed',
                  u'type': u'MethodNotAllowedError'}]})
        self.assertFalse(self.san_fault.is_unityxt())
        self.logger.error.assert_called_with(
            "Cannot get SAN type from LITP: (405, {'path': '/infrastructure/storage/storage_providers/unityxt', "
            "'reason': 'Method Not Allowed', 'messages': [{u'type': u'MethodNotAllowedError', "
            "u'message': u'Method Not Allowed', u'_links': {u'self': "
            "{u'href': u'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/unityxt'}}}]})")

        get.side_effect = Exception("global name '' is not defined")
        self.assertFalse(self.san_fault.is_unityxt())
        self.logger.error.assert_called_with(
            "Cannot get SAN type from LITP: global name '' is not defined")

    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_all_items_by_type')
    def test_get_litp_nas_servers(self, get_type, get):
        self.logger.error = MagicMock()
        self.logger.info = MagicMock()

        get_type.return_value = [{'path': '/infrastructure/storage/storage_providers/unityxt'}]
        get.side_effect = LitpException(
            404,
            {'path': '/infrastructure/storage/storage_providers/unityxt/virtual_servers',
             'reason': 'Not Found',
             'messages': [
                 {u'_links': {
                     u'self': {
                         u'href': u'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/unityxt/virtual_servers'}},
                  u'message': u'Not found',
                  u'type': u'InvalidLocationError'}]})
        returned = self.san_fault.get_litp_nas_servers()
        self.logger.error.assert_called_with(
            "Cannot get NAS servers from LITP: (404, {'path': '/infrastructure/storage/storage_providers/unityxt/virtual_servers', "
            "'reason': 'Not Found', 'messages': [{u'type': u'InvalidLocationError', "
            "u'message': u'Not found', u'_links': {u'self': "
            "{u'href': u'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/unityxt/virtual_servers'}}}]})")
        self.assertEqual(returned, [])

        get.side_effect = Exception("global name '' is not defined")
        returned = self.san_fault.get_litp_nas_servers()
        self.logger.error.assert_called_with(
            "Cannot get NAS servers from LITP: global name '' is not defined")
        self.assertEqual(returned, [])

        get.reset_mock()
        get.side_effect = None
        get.return_value = mock_get_litp_nas_servers_no_nas_servers
        returned = self.san_fault.get_litp_nas_servers()
        self.logger.error.assert_called_with(
            "2 NAS servers expected, 0 found. Check the LITP model.")
        self.logger.info.assert_called_with(
            "Items found: {'_embedded': {'item': []}, 'item-type-name': 'collection-of-sfs-virtual-server', "
            "'applied_properties_determinable': True, 'state': 'Applied', '_links': {'self': "
            "{'href': 'https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/unityxt/virtual_servers'}, "
            "'collection-of': {'href': 'https://localhost:9999/litp/rest/v1/item-types/sfs-virtual-server'}}, 'id': 'virtual_servers'}")
        self.assertEqual(returned, [])

        get.reset_mock()
        get.side_effect = None
        get.return_value = mock_get_litp_nas_servers_items
        returned = self.san_fault.get_litp_nas_servers()
        self.assertEqual(returned, mock_nas_servers)

        get.reset_mock()
        get.side_effect = None
        del mock_get_litp_nas_servers_items["_embedded"]["item"][0]["properties"]["name"]
        get.return_value = mock_get_litp_nas_servers_items
        returned = self.san_fault.get_litp_nas_servers()
        self.logger.error.assert_called_with(
            "Missing NAS server information: 'name'. Check the LITP model.")
        self.assertEqual(returned, [])

    @patch('san_fault_check.SanFaultCheck.get_litp_nas_servers')
    def test_check_nas_servers(self, m_get):
        self.logger.error = MagicMock()

        m_get.return_value = mock_nas_servers
        returned = self.san_fault.check_nas_servers(mock_san_info, mock_san)
        self.assertEqual(m_get.call_count,1)
        self.assertEqual(returned, None)
        self.assertEqual(self.san_fault.nas_server_fault, False)

        m_get.return_value = mock_nas_servers_not_found
        returned = self.san_fault.check_nas_servers(mock_san_info, mock_san)
        self.logger.error.assert_called_with('Cannot get NAS server details: Not found')
        self.assertEqual(returned, None)
        self.assertEqual(self.san_fault.nas_server_fault, False)

        m_get.return_value = mock_nas_servers_no_home
        returned = self.san_fault.check_nas_servers(mock_san_info, mock_san)
        self.logger.error.assert_called_with("NAS server 'dummy_nas_server_4' home SP not found: {u'currentSP': {u'id': u'spa'}, u'name': u'dummy_nas_server_4'}")
        self.assertEqual(returned, None)
        self.assertEqual(self.san_fault.nas_server_fault, False)

        m_get.return_value = mock_nas_servers_no_current
        returned = self.san_fault.check_nas_servers(mock_san_info, mock_san)
        self.logger.error.assert_called_with("NAS server 'dummy_nas_server_5' current SP not found: {u'homeSP': {u'id': u'spa'}, u'name': u'dummy_nas_server_5'}")
        self.assertEqual(returned, None)
        self.assertEqual(self.san_fault.nas_server_fault, False)

        m_get.return_value = mock_nas_servers_no_connect
        returned = self.san_fault.check_nas_servers(mock_san_info, mock_san)
        self.logger.error.assert_called_with("Cannot connect to the SAN. Check the LITP model.")
        self.assertEqual(returned, None)
        self.assertEqual(self.san_fault.nas_server_fault, False)

        m_get.return_value = mock_nas_servers_no_match
        returned = self.san_fault.check_nas_servers(mock_san_info, mock_san)
        self.logger.error.assert_called_with("The SP 'spa' for NAS server 'dummy_nas_server_6' in LITP does not match the SAN - home SP = 'spc' current SP = 'spc'")
        self.assertEqual(returned, None)
        self.assertEqual(self.san_fault.nas_server_fault, True)

    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_set_haproxy_internal_ip(self, m_litp_response):
        m_litp_response.return_value = mock_litp_response

        self.san_fault.set_haproxy_internal_ip()
        self.assertEqual(self.san_fault.haproxy_int_ip, "192.110.10.12")

    def test_build_alarm_message(self):
        mock_alert = Mock(message="Message1",
                          description="Description1",
                          severity=2)
        valid_message = '{\"recordType\": \"ALARM\", \"probableCause\": \"Message1\", ' \
                        '\"eventType\": \"SAN Issue", "specificProblem\": ' \
                        '\"Dell EMC SAN Storage Critical Alert\", ' \
                        '\"perceivedSeverity\": \"CRITICAL\", \"managedObjectInstance\":' \
                        ' \"ENM\"}'
        alarm_message = self.san_fault.build_alarm_message(mock_alert)
        self.assertEqual(alarm_message, valid_message)

    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_build_alarm_url(self, m_litp_response):
        m_litp_response.return_value = mock_litp_response

        self.san_fault.set_haproxy_internal_ip()
        url = self.san_fault.build_alarm_url()
        valid_url = "http://192.110.10.12:8081/internal-alarm-service/internalalarm/" \
                    "internalalarmservice/translate"

        self.assertEqual(valid_url, url)

    @patch('san_fault_check.SanFaultCheck.write_alarms_to_file')
    @patch('san_fault_check.SanFaultCheck.get_current_alarms')
    def test_store_alerts_locally(self, m_current_alarm,
                                  m_write_alarms):
        mock_san_alert = Mock(message="TestMessage",
                              description="TestDescription",
                              severity=2)

        current_alarm = ['{\"recordType\": \"ALARM\", \"probableCause\": \"Message1\", '
                         '\"eventType\": \"SAN Issue", "specificProblem\": ' \
                         '\"Dell EMC SAN Storage Critical Alert\", ' \
                         '\"perceivedSeverity\": \"CRITICAL\", \"managedObjectInstance\":'
                         ' \"ENM\"}']

        new_alarm = '{"recordType": "ALARM", "probableCause": "TestMessage", ' \
                    '"eventType": "SAN Issue", "specificProblem": '\
                    '"Dell EMC SAN Storage Critical Alert", ' \
                    '"perceivedSeverity": "CRITICAL", "managedObjectInstance": "ENM"}!'

        m_current_alarm.return_value = current_alarm

        self.san_fault.san_alerts.append(mock_san_alert)

        self.san_fault.get_alarms_to_create_and_clear()
        self.assertEqual(self.san_fault.alerts_to_create[0], new_alarm.replace('!', ''))
        self.assertEqual(self.san_fault.alerts_to_clear[0], current_alarm[0].replace('!', ''))
        self.assertTrue(m_write_alarms.called)

    @patch('requests.post')
    @patch('san_fault_check.SanFaultCheck.build_alarm_url')
    def test_create_fmalarm_success(self, m_alarm_url,
                                    m_post):
        m_post.return_value = Mock(status_code=200)

        self.san_fault.alerts_to_create = ['{"recordType": "ALARM", "probableCause": "TestMessage", '
                                           '"eventType": "SAN Issue", '
                                           '"specificProblem": "Dell EMC SAN Storage Critical Alert", '
                                           '"perceivedSeverity": "CRITICAL", "managedObjectInstance": "ENM"}!']
        self.san_fault.create_fmalarm()
        self.assertTrue(m_alarm_url.called)
        self.assertTrue(m_post.called)

    @patch('requests.post')
    @patch('san_fault_check.SanFaultCheck.build_alarm_url')
    def test_create_fmalarm_failure(self, m_alarm_url,
                                    m_post):
        m_post.return_value = Mock(status_code=404)

        self.san_fault.alerts_to_create = ['{"recordType": "ALARM", "probableCause": "TestMessage", '
                                           '"eventType": "SAN Issue", '
                                           '"specificProblem": "Dell EMC SAN Storage Critical Alert", '
                                           '"perceivedSeverity": "CRITICAL", "managedObjectInstance": "ENM"}!']
        self.san_fault.create_fmalarm()
        self.assertTrue(m_alarm_url.called)
        self.assertTrue(m_post.called)

    @patch('json.loads')
    @patch('json.dumps')
    @patch('requests.post')
    @patch('san_fault_check.SanFaultCheck.build_alarm_url')
    def test_clear_fmalarm_success(self, m_alarm_url,
                                   m_post,
                                   m_json_dumps,
                                   m_json_loads):
        m_post.return_value = Mock(status_code=200)

        self.san_fault.alerts_to_clear = ['{"recordType": "ALARM", "probableCause": "TestMessage", '
                                          '"eventType": "SAN Issue", '
                                          '"specificProblem": "Dell EMC SAN Storage Critical Alert", '
                                          '"perceivedSeverity": "CRITICAL", "managedObjectInstance": "ENM"}!']
        self.san_fault.clear_fmalarm()
        self.assertTrue(m_json_loads.called)
        self.assertTrue(m_json_dumps.called)
        self.assertTrue(m_alarm_url.called)
        self.assertTrue(m_post.called)

    @patch('json.loads')
    @patch('json.dumps')
    @patch('requests.post')
    @patch('san_fault_check.SanFaultCheck.build_alarm_url')
    def test_clear_fmalarm_failure(self, m_alarm_url,
                                   m_post,
                                   m_json_dumps,
                                   m_json_loads):
        m_post.return_value = Mock(status_code=404)

        self.san_fault.alerts_to_clear = ['{"recordType": "ALARM", "probableCause": "TestMessage", '
                                          '"eventType": "SAN Issue", '
                                          '"specificProblem": "Dell EMC SAN Storage Critical Alert", '
                                          '"perceivedSeverity": "CRITICAL", "managedObjectInstance": "ENM"}!']
        self.san_fault.clear_fmalarm()
        self.assertTrue(m_json_loads.called)
        self.assertTrue(m_json_dumps.called)
        self.assertTrue(m_alarm_url.called)
        self.assertTrue(m_post.called)

    @patch('os.stat')
    @patch('os.mknod')
    @patch('os.path.exists')
    @patch('__builtin__.open')
    def test_get_current_alarms(self, m_open,
                                m_os_exists,
                                m_os_mknod,
                                m_os_stat):

        m_os_exists.return_value = False

        mock_data = '{"recordType": "ALARM", "probableCause": "TestMessage", '\
                    '"eventType": "SAN Issue", '\
                    '"specificProblem": "Dell EMC SAN Storage Critical Alert", '\
                    '"perceivedSeverity": "CRITICAL", "managedObjectInstance": "ENM"}!'

        m_open.side_effect = [
            mock_open(read_data=mock_data).return_value
        ]

        self.san_fault.get_current_alarms()

        self.assertTrue(m_os_exists.called)
        self.assertTrue(m_os_mknod.called)
        self.assertTrue(m_os_stat.called)

    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    def test_check_litp_maintenance(self, m_litp_maintenance):
        m_litp_maintenance.return_value = True
        self.assertTrue(self.san_fault.check_litp_maintenance())

    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    def test_check_litp_not_maintenance(self, m_litp_maintenance):
        m_litp_maintenance.return_value = False
        self.assertFalse(self.san_fault.check_litp_maintenance())

    @patch('h_litp.litp_maintenance.LitpMaintenance.is_maintenance_mode')
    def test_check_litp_maintenance_raise_exception(self, m_litp_maintenance):
        m_litp_maintenance.side_effect = ValueError
        self.assertRaises(SystemExit, self.san_fault.check_litp_maintenance)

    @patch('os.path.exists')
    def test_make_alert_filter_when_no_filter_file_exists(self, m_os_exists):
        m_os_exists.return_value = False
        alert_filter = 'state ne {0} and severity eq {1}' \
            .format(SAN_ALERT_INACTIVE, SAN_ALERT_THRESHOLD)
        self.assertEqual(self.san_fault.make_alert_filter(), alert_filter)

    @patch('os.stat')
    @patch('os.path.exists')
    def test_make_alert_filter_when_filter_file_size_zero(self,
                                                          m_os_exists,
                                                          m_os_stat):
        m_os_exists.return_value = True
        m_os_stat.return_value.st_size = 0
        alert_filter = 'state ne {0} and severity eq {1}' \
            .format(SAN_ALERT_INACTIVE, SAN_ALERT_THRESHOLD)
        self.assertEqual(self.san_fault.make_alert_filter(), alert_filter)

    @patch('os.stat')
    @patch('os.path.exists')
    def test_make_alert_filter(self,
                               m_os_exists,
                               m_os_stat):
        m_os_exists.return_value = True
        m_os_stat.return_value.st_size = 1024

        mock_data = """
# This file contains the message IDs of Dell EMC Unity storage alerts
# that do not have CRITICAL severity but should be raised as critical
# ENM FM alarms by the ENMinst SAN fault checker script san_fault_check.py.

# These are in addition to CRITICAL severity Unity alerts which are always
# raised as critical ENM FM alarms.

# A Unity alert message ID identifies the alert in the Unity message
# catalog and is used for localization purposes.

# Format:
# One Unity alert message ID per line.
# Message IDs commented out with '#' are skipped.
# Before each message ID, add an example of the corresponding alert message
# text as a comment line. For information only.

# Example: "FSN port SP A FSN Port Ocp 0 1 link is down."
14:60ed9

# Example: "Port SP A 4-Port Card Ethernet Port 1 link is down"
14:60580

# Example: "Configured Port SP A 4-Port Card Ethernet Port 1 link is down"
14:60594

# Example: "SP A 4-Port Card is missing"
14:603f3

# Example: "Unable to detect Ethernet port or link aggregation for the network interface 192.168.0.5 configured on NAS server nas01"
14:603c2"""

        alert_filter = 'state ne {0} and (severity eq {1} or (messageId eq "14:60ed9" or messageId eq "14:60580" or messageId eq "14:60594" or messageId eq "14:603f3" or messageId eq "14:603c2"))'.format(SAN_ALERT_INACTIVE, SAN_ALERT_THRESHOLD)

        with patch('__builtin__.open', mock_open(read_data=mock_data)) as mocked_open:
            mocked_open.return_value.__iter__.return_value = mock_data.splitlines()
            self.assertEqual(self.san_fault.make_alert_filter(), alert_filter)
