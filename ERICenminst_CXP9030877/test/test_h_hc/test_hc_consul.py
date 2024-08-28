from h_hc.hc_consul import ConsulHC
from mock import patch, MagicMock
from urllib2 import URLError, HTTPError
from unittest2.case import TestCase

members_ok = [{u'Status': 1, u'DelegateCur': 4, u'Name': u'cloud-ms-1',
               u'Tags': {u'wan_join_port': u'8302', u'vsn_max': u'3',
               u'raft_vsn': u'3', u'vsn_min': u'2', u'dc': u'dc1', u'port':
               u'8300', u'ft_si': u'1', u'acls': u'0', u'role': u'consul',
               u'expect': u'5', u'build': u'1.9.5:3c1c2267', u'segment':
               u'', u'id': u'1626f95b-ad1b-d8b3-6193-42b2600019da',
               u'vsn': u'2', u'ft_fs': u'1'}, u'ProtocolMax': 5,
               u'DelegateMin': 2, u'ProtocolMin': 1, u'ProtocolCur': 2,
               u'Port': 8301, u'DelegateMax': 5, u'Addr': u'10.247.246.42'},
               {u'Status': 1, u'DelegateCur': 4, u'Name': u'cloud-svc-1',
               u'Tags': {u'vsn_max': u'3', u'vsn_min': u'2', u'raft_vsn':
               u'2', u'dc': u'dc1', u'port': u'8300', u'wan_join_port':
               u'8302', u'role': u'consul', u'expect': u'3', u'id':
               u'9d0c9ba1', u'vsn': u'2', u'build': u'0.9.2:75ca2ca'},
               u'ProtocolMax': 5, u'DelegateMin': 2, u'ProtocolMin': 1,
               u'ProtocolCur': 2, u'Port': 8301, u'DelegateMax': 5,
               u'Addr': u'10.247.246.2'}, {u'Status': 1, u'DelegateCur': 4,
               u'Name': u'cloud-svc-2', u'Tags': {u'vsn_max': u'3',
               u'vsn_min': u'2', u'raft_vsn': u'2', u'dc': u'dc1', u'port':
               u'8300', u'wan_join_port': u'8302', u'role': u'consul',
               u'expect': u'3', u'id': u'8c5d823a', u'vsn': u'2', u'build':
               u'0.9.2:75ca2ca'}, u'ProtocolMax': 5, u'DelegateMin': 2,
               u'ProtocolMin': 1, u'ProtocolCur': 2, u'Port': 8301,
               u'DelegateMax': 5, u'Addr': u'10.247.246.3'}]
members_nok = [{u'Status': 1, u'DelegateCur': 4, u'Name': u'cloud-ms-1',
               u'Tags': {u'wan_join_port': u'8302', u'vsn_max': u'3',
               u'raft_vsn': u'3', u'vsn_min': u'2', u'dc': u'dc1', u'port':
               u'8300', u'ft_si': u'1', u'acls': u'0', u'role': u'consul',
               u'expect': u'5', u'build': u'1.9.5:3c1c2267', u'segment':
               u'', u'id': u'1626f95b-ad1b-d8b3-6193-42b2600019da',
               u'vsn': u'2', u'ft_fs': u'1'}, u'ProtocolMax': 5,
               u'DelegateMin': 2, u'ProtocolMin': 1, u'ProtocolCur': 2,
               u'Port': 8301, u'DelegateMax': 5, u'Addr': u'10.247.246.42'},
               {u'Status': 2, u'DelegateCur': 4, u'Name': u'cloud-svc-1',
               u'Tags': {u'vsn_max': u'3', u'vsn_min': u'2', u'raft_vsn':
               u'2', u'dc': u'dc1', u'port': u'8300', u'wan_join_port':
               u'8302', u'role': u'consul', u'expect': u'3', u'id':
               u'9d0c9ba1', u'vsn': u'2', u'build': u'0.9.2:75ca2ca'},
               u'ProtocolMax': 5, u'DelegateMin': 2, u'ProtocolMin': 1,
               u'ProtocolCur': 2, u'Port': 8301, u'DelegateMax': 5,
               u'Addr': u'10.247.246.2'}, {u'Status': 1, u'DelegateCur': 4,
               u'Name': u'cloud-svc-2', u'Tags': {u'vsn_max': u'3',
               u'vsn_min': u'2', u'raft_vsn': u'2', u'dc': u'dc1', u'port':
               u'8300', u'wan_join_port': u'8302', u'role': u'consul',
               u'expect': u'3', u'id': u'8c5d823a', u'vsn': u'2', u'build':
               u'0.9.2:75ca2ca'}, u'ProtocolMax': 5, u'DelegateMin': 2,
               u'ProtocolMin': 1, u'ProtocolCur': 2, u'Port': 8301,
               u'DelegateMax': 5, u'Addr': u'10.247.246.3'}]
members_nok_no_error = [{u'Status': 1, u'DelegateCur': 4, u'Name': u'cloud-ms-1',
               u'Tags': {u'wan_join_port': u'8302', u'vsn_max': u'3',
               u'raft_vsn': u'3', u'vsn_min': u'2', u'dc': u'dc1', u'port':
               u'8300', u'ft_si': u'1', u'acls': u'0', u'role': u'consul',
               u'expect': u'5', u'build': u'1.9.5:3c1c2267', u'segment':
               u'', u'id': u'1626f95b-ad1b-d8b3-6193-42b2600019da',
               u'vsn': u'2', u'ft_fs': u'1'}, u'ProtocolMax': 5,
               u'DelegateMin': 2, u'ProtocolMin': 1, u'ProtocolCur': 2,
               u'Port': 8301, u'DelegateMax': 5, u'Addr': u'10.247.246.42'},
               {u'Status': 3, u'DelegateCur': 4, u'Name': u'cloud-svc-1',
               u'Tags': {u'vsn_max': u'3', u'vsn_min': u'2', u'raft_vsn':
               u'2', u'dc': u'dc1', u'port': u'8300', u'wan_join_port':
               u'8302', u'role': u'consul', u'expect': u'3', u'id':
               u'9d0c9ba1', u'vsn': u'2', u'build': u'0.9.2:75ca2ca'},
               u'ProtocolMax': 5, u'DelegateMin': 2, u'ProtocolMin': 1,
               u'ProtocolCur': 2, u'Port': 8301, u'DelegateMax': 5,
               u'Addr': u'10.247.246.2'}, {u'Status': 1, u'DelegateCur': 4,
               u'Name': u'cloud-svc-2', u'Tags': {u'vsn_max': u'3',
               u'vsn_min': u'2', u'raft_vsn': u'2', u'dc': u'dc1', u'port':
               u'8300', u'wan_join_port': u'8302', u'role': u'consul',
               u'expect': u'3', u'id': u'8c5d823a', u'vsn': u'2', u'build':
               u'0.9.2:75ca2ca'}, u'ProtocolMax': 5, u'DelegateMin': 2,
               u'ProtocolMin': 1, u'ProtocolCur': 2, u'Port': 8301,
               u'DelegateMax': 5, u'Addr': u'10.247.246.3'}]
ms_nok = [{u'Status': 3, u'DelegateCur': 4, u'Name': u'cloud-ms-1',
               u'Tags': {u'wan_join_port': u'8302', u'vsn_max': u'3',
               u'raft_vsn': u'3', u'vsn_min': u'2', u'dc': u'dc1', u'port':
               u'8300', u'ft_si': u'1', u'acls': u'0', u'role': u'consul',
               u'expect': u'5', u'build': u'1.9.5:3c1c2267', u'segment':
               u'', u'id': u'1626f95b-ad1b-d8b3-6193-42b2600019da',
               u'vsn': u'2', u'ft_fs': u'1'}, u'ProtocolMax': 5,
               u'DelegateMin': 2, u'ProtocolMin': 1, u'ProtocolCur': 2,
               u'Port': 8301, u'DelegateMax': 5, u'Addr': u'10.247.246.42'},
               {u'Status': 1, u'DelegateCur': 4, u'Name': u'cloud-svc-1',
               u'Tags': {u'vsn_max': u'3', u'vsn_min': u'2', u'raft_vsn':
               u'2', u'dc': u'dc1', u'port': u'8300', u'wan_join_port':
               u'8302', u'role': u'consul', u'expect': u'3', u'id':
               u'9d0c9ba1', u'vsn': u'2', u'build': u'0.9.2:75ca2ca'},
               u'ProtocolMax': 5, u'DelegateMin': 2, u'ProtocolMin': 1,
               u'ProtocolCur': 2, u'Port': 8301, u'DelegateMax': 5,
               u'Addr': u'10.247.246.2'}, {u'Status': 1, u'DelegateCur': 4,
               u'Name': u'cloud-svc-2', u'Tags': {u'vsn_max': u'3',
               u'vsn_min': u'2', u'raft_vsn': u'2', u'dc': u'dc1', u'port':
               u'8300', u'wan_join_port': u'8302', u'role': u'consul',
               u'expect': u'3', u'id': u'8c5d823a', u'vsn': u'2', u'build':
               u'0.9.2:75ca2ca'}, u'ProtocolMax': 5, u'DelegateMin': 2,
               u'ProtocolMin': 1, u'ProtocolCur': 2, u'Port': 8301,
               u'DelegateMax': 5, u'Addr': u'10.247.246.3'}]
members_nok_ignore_svc3 = \
              [{u'Status': 1, u'DelegateCur': 4, u'Name': u'cloud-ms-1',
               u'Tags': {u'wan_join_port': u'8302', u'vsn_max': u'3',
               u'raft_vsn': u'3', u'vsn_min': u'2', u'dc': u'dc1', u'port':
               u'8300', u'ft_si': u'1', u'acls': u'0', u'role': u'consul',
               u'expect': u'5', u'build': u'1.9.5:3c1c2267', u'segment':
               u'', u'id': u'1626f95b-ad1b-d8b3-6193-42b2600019da',
               u'vsn': u'2', u'ft_fs': u'1'}, u'ProtocolMax': 5,
               u'DelegateMin': 2, u'ProtocolMin': 1, u'ProtocolCur': 2,
               u'Port': 8301, u'DelegateMax': 5, u'Addr': u'10.247.246.42'},
               {u'Status': 2, u'DelegateCur': 4, u'Name': u'cloud-svc-1',
               u'Tags': {u'vsn_max': u'3', u'vsn_min': u'2', u'raft_vsn':
               u'2', u'dc': u'dc1', u'port': u'8300', u'wan_join_port':
               u'8302', u'role': u'consul', u'expect': u'3', u'id':
               u'9d0c9ba1', u'vsn': u'2', u'build': u'0.9.2:75ca2ca'},
               u'ProtocolMax': 5, u'DelegateMin': 2, u'ProtocolMin': 1,
               u'ProtocolCur': 2, u'Port': 8301, u'DelegateMax': 5,
               u'Addr': u'10.247.246.2'}, {u'Status': 1, u'DelegateCur': 4,
               u'Name': u'cloud-svc-2', u'Tags': {u'vsn_max': u'3',
               u'vsn_min': u'2', u'raft_vsn': u'2', u'dc': u'dc1', u'port':
               u'8300', u'wan_join_port': u'8302', u'role': u'consul',
               u'expect': u'3', u'id': u'8c5d823a', u'vsn': u'2', u'build':
               u'0.9.2:75ca2ca'}, u'ProtocolMax': 5, u'DelegateMin': 2,
               u'ProtocolMin': 1, u'ProtocolCur': 2, u'Port': 8301,
               u'DelegateMax': 5, u'Addr': u'10.247.246.3'}, {u'Status': 2,
               u'DelegateCur': 4, u'Name': u'cloud-svc-3', u'Tags':
               {u'vsn_max': u'3', u'vsn_min': u'2', u'raft_vsn':
               u'2', u'dc': u'dc1', u'port': u'8300', u'wan_join_port':
               u'8302', u'role': u'consul', u'expect': u'3', u'id':
               u'9d0c9ba1', u'vsn': u'2', u'build': u'0.9.2:75ca2ca'},
               u'ProtocolMax': 5, u'DelegateMin': 2, u'ProtocolMin': 1,
               u'ProtocolCur': 2, u'Port': 8301, u'DelegateMax': 5,
               u'Addr': u'10.247.246.2'}]


class MockResponse(object):
    def __init__(self, resp_data, code=200, msg='OK'):
        self.resp_data = resp_data
        self.code = code
        self.msg = msg
        self.headers = {'content-type': 'text/plain; charset=utf-8'}

    def read(self):
        return self.resp_data

    def getcode(self):
        return self.code


class TestConsulHealthCheck(TestCase):

    def __init__(self, methodName='runTest'):
        super(TestConsulHealthCheck, self).__init__(methodName)
        self.consul = ConsulHC(verbose=True)

    def setUp(self):
        self.testurl = 'http://myconsulagent:8500'

    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    @patch('h_hc.hc_consul.ConsulHC.check_members_count')
    def test_check_consul_members_ok(self, m_check_members_count, m_url_data, m_get_lms, m_get_items_by_type):
        m_get_items_by_type.return_value = [{'data': {'properties': {'hostname': 'cloud-svc-1'}}},
                                            {'data': {'properties': {'hostname': 'cloud-svc-2'}}}]
        m_get_lms().get_property.return_value = 'cloud-ms-1'
        m_url_data.return_value = members_ok
        m_check_members_count.return_value = 3
        self.consul.check_consul_members()

    @patch('h_hc.hc_consul.EnminstAgent.consul_service_restart')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    @patch('h_hc.hc_consul.ConsulHC.check_members_count')
    def test_check_consul_members_nok_node_off(self, m_check_members_count, m_url_data, m_get_lms, m_get_items_by_type, m_consul_restart):
        m_url_data.return_value = members_nok
        m_check_members_count.return_value = 3
        m_get_items_by_type.return_value = [
            {'data': {'properties': {'hostname': 'cloud-svc-1'}}},
            {'data': {'properties': {'hostname': 'cloud-svc-2'}}}]
        m_get_lms().get_property.return_value = 'cloud-ms-1'
        m_consul_restart.return_value = {'cloud-svc-1': {'errors': 'No answer from node',
                                                         'data': {}}}
        with self.assertRaises(SystemExit):
            self.consul.check_consul_members()

    @patch('h_hc.hc_consul.EnminstAgent.consul_service_restart')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    @patch('h_hc.hc_consul.ConsulHC.check_members_count')
    def test_check_consul_members_nok_service_off(self, m_check_members_count, m_url_data, m_get_lms, m_get_items_by_type, m_consul_restart):
        m_url_data.return_value = members_nok
        m_check_members_count.return_value = 3
        m_get_items_by_type.return_value = [
            {'data': {'properties': {'hostname': 'cloud-svc-1'}}},
            {'data': {'properties': {'hostname': 'cloud-svc-2'}}}]
        m_get_lms().get_property.return_value = 'cloud-ms-1'
        m_consul_restart.return_value = {'node': 'cloud-svc-1', 'retcode': 1,
                                         'err': 'Job for consul.service failed because \
                                         the control process exited with error code...',
                                         'out': ''}
        with self.assertRaises(SystemExit):
            self.consul.check_consul_members()

    @patch('h_hc.hc_consul.EnminstAgent.consul_service_restart')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    @patch('h_hc.hc_consul.ConsulHC.check_members_count')
    def test_check_consul_members_nok_systemd_unit_brk(self, m_check_members_count, m_url_data, m_get_lms, m_get_items_by_type, m_consul_restart):
        m_url_data.return_value = members_nok
        m_check_members_count.return_value = 3
        m_get_items_by_type.return_value = [
            {'data': {'properties': {'hostname': 'cloud-svc-1'}}},
            {'data': {'properties': {'hostname': 'cloud-svc-2'}}}]
        m_get_lms().get_property.return_value = 'cloud-ms-1'
        m_consul_restart.return_value = {'node': 'cloud-svc-1', 'retcode': 1,
                                         'err': 'Failed to restart consul.service: Unit'
                                         'is not loaded properly: Invalid argument.',
                                         'out': ''}
        with self.assertRaises(SystemExit):
            self.consul.check_consul_members()

    @patch('h_hc.hc_consul.EnminstAgent.consul_service_restart')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    @patch('h_hc.hc_consul.ConsulHC.check_members_count')
    def test_check_consul_members_nok_no_error(self, m_check_members_count, m_url_data, m_get_lms, m_get_items_by_type, m_consul_restart):
        m_url_data.return_value = members_nok_no_error
        m_check_members_count.return_value = 3
        m_get_items_by_type.return_value = [
            {'data': {'properties': {'hostname': 'cloud-svc-1'}}},
            {'data': {'properties': {'hostname': 'cloud-svc-2'}}}]
        m_get_lms().get_property.return_value = 'cloud-ms-1'
        m_consul_restart.return_value = {'cloud-svc-1': ''}
        self.consul.check_consul_members()
        m_consul_restart.assert_called_with(['cloud-svc-1'])

    @patch('h_hc.hc_consul.EnminstAgent.consul_service_restart')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    @patch('h_hc.hc_consul.ConsulHC.check_members_count')
    def test_check_consul_ms_nok(self, m_check_members_count, m_url_data, m_get_lms, m_get_items_by_type, m_consul_restart):
        m_url_data.return_value = ms_nok
        m_check_members_count.return_value = 3
        m_get_items_by_type.return_value = [
            {'data': {'properties': {'hostname': 'cloud-svc-1'}}},
            {'data': {'properties': {'hostname': 'cloud-svc-2'}}}]
        m_get_lms().get_property.return_value = 'cloud-ms-1'
        m_consul_restart.return_value = {'cloud-ms-1': ''}
        self.consul.check_consul_members()
        m_consul_restart.assert_called_with(['cloud-ms-1'])

    @patch('h_hc.hc_consul.EnminstAgent.consul_service_restart')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    @patch('h_hc.hc_consul.ConsulHC.check_members_count')
    def test_check_consul_members_nok_ignore_not_in_litp_model(self, m_check_members_count, m_url_data, m_get_lms, m_get_items_by_type, m_consul_restart):
        m_url_data.return_value = members_nok_ignore_svc3
        m_check_members_count.return_value = 4
        m_get_items_by_type.return_value = [
            {'data': {'properties': {'hostname': 'cloud-svc-1'}}},
            {'data': {'properties': {'hostname': 'cloud-svc-2'}}}]
        m_get_lms().get_property.return_value = 'cloud-ms-1'
        m_consul_restart.return_value = {'cloud-svc-1': ''}
        self.consul.check_consul_members()
        m_consul_restart.assert_not_called_with(['cloud-svc-3'])

    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    def test_check_consul_leader_nok(self, m_url_data):
        m_url_data.return_value = []
        self.assertRaises(SystemExit, self.consul.check_consul_leader)

    @patch('h_hc.hc_consul.ConsulHC.consul_get_url_data')
    def test_check_consul_leader_ok(self, m_url_data):
        m_url_data.return_value = ['ms-1']
        self.consul.check_consul_leader()

    @patch('h_hc.hc_consul.urlopen')
    def testconsul_get_url_data_http_url_exception(self, m_urlopen):
        m_urlopen.side_effect = HTTPError('', 404, '', {}, MagicMock())
        self.assertRaises(SystemExit, self.consul.consul_get_url_data, self.testurl, self.testurl)
        m_urlopen.return_value = URLError('reason')
        self.assertRaises(SystemExit, self.consul.consul_get_url_data, self.testurl, self.testurl)

    @patch('h_hc.hc_consul.urlopen')
    def testconsul_get_url_data_non200(self, m_urlopen):
        response_mock = MockResponse(members_ok, 201)
        m_urlopen.return_value = response_mock
        self.assertRaises(SystemExit, self.consul.consul_get_url_data, self.testurl, self.testurl)

    @patch('h_hc.hc_consul.urlopen')
    @patch('h_hc.hc_consul.json.load')
    def testconsul_get_url_data_200(self, m_json, m_urlopen):
        response_mock = MockResponse(members_ok)
        m_urlopen.return_value = response_mock
        self.consul.consul_get_url_data(self.testurl, self.testurl)
        self.assertTrue(m_json.called)

    @patch('h_hc.hc_consul.ConsulHC.check_consul_leader')
    @patch('h_hc.hc_consul.ConsulHC.check_consul_members')
    def test_healthcheck_consul(self, gcm, gcl):
        self.assertEquals(self.consul.healthcheck_consul(), None)
        for mk in [gcl, gcm]:
            self.assertTrue(mk.called, 'Mock {0} not called!'.format(mk))

    @patch('__builtin__.open')
    def test_check_members_count(self, m_open):
        m_open.return_value.read.return_value = '''{
          "bind_addr": "10.247.246.42",
          "advertise_addr": "10.247.246.42",
          "node_name": "cloud-ms-1",
          "bootstrap_expect": 3,
          "server": true,
          "datacenter": "dc1",
          "disable_remote_exec": true,
          "data_dir": "/var/consul",
          "log_level": "INFO",
          "enable_syslog": true,
          "domain": "enm",
          "ports":{
            "dns": 8600
          },
          "dns_config":{
            "only_passing": false
          },
          "raft_protocol": 3,
          "enable_script_checks": false,
          "retry_join": ["10.247.246.42","10.247.246.2","10.247.246.3"],
          "rejoin_after_leave": true,
          "disable_update_check": true,
          "client_addr": "10.247.246.42",
          "recursors": []
      }'''
        mock_members_dict = {u'cloud-svc-1': [1], u'cloud-svc-2': [1], u'cloud-ms-1': [1]}
        self.consul.check_members_count(mock_members_dict, 'mock_cfg_file_location')

    @patch('__builtin__.open')
    def test_check_members_count_nok(self, m_open):
        m_open.return_value.read.return_value = '{'\
          '"bind_addr": "10.247.246.42",'\
          '"advertise_addr": "10.247.246.42",'\
          '"node_name": "cloud-ms-1",'\
          '"bootstrap_expect": 3,'\
          '"server": true,'\
          '"datacenter": "dc1",'\
          '"disable_remote_exec": true,'\
          '"data_dir": "/var/consul",'\
          '"log_level": "INFO",'\
          '"enable_syslog": true,'\
          '"domain": "enm",'\
          '"ports":{'\
          '  "dns": 8600'\
          '},'\
          '"dns_config":{'\
          '  "only_passing": false'\
          '},'\
          '"raft_protocol": 3,'\
          '"enable_script_checks": false,'\
          '"retry_join": ["10.247.246.42","10.247.246.2","10.247.246.3"],'\
          '"rejoin_after_leave": true,'\
          '"disable_update_check": true,'\
          '"client_addr": "10.247.246.42",'\
          '"recursors": []'\
      '}'
        mock_members_dict = {u'cloud-svc-1': [1], u'cloud-ms-1': [1]}
        self.assertRaises(SystemExit, self.consul.check_members_count, mock_members_dict,
                                                                'mock_cfg_file_location')
