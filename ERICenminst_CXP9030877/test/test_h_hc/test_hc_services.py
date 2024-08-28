import httplib
import os
from json import dumps
from os.path import join, dirname
from subprocess import STDOUT

import unittest2
from mock import patch

from h_hc.hc_services import Services
from h_litp.litp_rest_client import LitpRestClient
from test_h_litp.test_h_litp_rest_client import setup_mock as setup_litp_mock

myservices = '''
'cat', 'cabbage'
'''


class TestServices(unittest2.TestCase):
    def setUp(self):
        basepath = dirname(dirname(dirname(__file__.replace(os.sep, '/'))))
        os.environ['ENMINST_BIN'] = join(basepath, 'src/main/bin')

        self.services = Services()
        self.services.lms_hostname = 'cloud-ms-1'

    def mock_litp_nodes(self, *nodes):
        mocked_litp = LitpRestClient()
        getc_deploy = {'_embedded': {'item': [{'id': 'enm'}]}}
        getc_clstr = {'_embedded': {'item': [{'id': 'svc_cluster'}]}}

        json_nodes = []
        for node in nodes:
            json_nodes.append({'id': node[0],
                               'state': node[1],
                               'item-type-name': 'node',
                               'properties': {'hostname': node[0]},
                               '_links': {'self': {'href': '/litp/rest/v1/'}}})

        getc_nodes = {'_embedded': {'item': json_nodes}}

        get_lms = {'id': 'ms',
                   'state': 'Applied',
                   'item-type-name': 'node',
                   'properties': {'hostname': 'cloud-ms-1'},
                   '_links': {'self': {'href': '/litp/rest/v1/'}}}

        setup_litp_mock(mocked_litp, [
            ['GET', dumps(getc_deploy), httplib.OK],
            ['GET', dumps(getc_clstr), httplib.OK],
            ['GET', dumps(getc_nodes), httplib.OK],
            ['GET', dumps(get_lms), httplib.OK]
        ])
        return mocked_litp

    def test__get_service_status_struct(self):
        struct = self.services._get_service_status_struct('a', 'b', 'c', 'd')
        self.assertEqual('a', struct[self.services.H_SYSTEM])
        self.assertEqual('b', struct[self.services.H_SERVICE_NAME])
        self.assertEqual('c', struct[self.services.H_STATE])
        self.assertEqual('d', struct[self.services.H_LEVEL])

    def test__get_node_status_struct(self):
        struct = self.services._get_node_status_struct('ga', 'nt')
        self.assertEqual('ga', struct[self.services.H_SYSTEM])
        self.assertEqual('nt', struct[self.services.H_STATE])

    @patch('h_hc.hc_services.report_tab_data')
    @patch('h_hc.hc_services.Services._ping_nodes')
    def test_verify_node_status(self, ping_nodes, tab_data):
        data = [{'State': 'ONLINE', 'Run Level': '3',
                 'System': 'cloud-ms-1', 'Service': 'puppet'}]
        ping_nodes.side_effect = [(Services.SERVICE_STATE_TABLE_HEADER, data,
                                   True)]
        self.services.verify_node_status(None, verbose=True)
        self.assertTrue(tab_data.called)

    @patch('h_hc.hc_services.report_tab_data')
    @patch('h_hc.hc_services.Services._get_runlevels')
    def test_verify_service_status_False(self, m_get_runlevels, tab_data):
        data = [{'State': 'ONLINE', 'Run Level': '2',
                 'System': 'cloud-ms-1', 'Service': 'puppet'}]
        m_get_runlevels.side_effect = [(Services.SERVICE_STATE_TABLE_HEADER,
                                        data)]
        self.assertRaises(IOError, self.services.verify_service_status, None,
                          verbose=False)
        self.assertTrue(tab_data.called)

    @patch('h_hc.hc_services.Services._get_runlevels')
    def test_verify_service_status_EXCEPTION(self, m_get_runlevels):
        data = [{'State': 'ONLINE', 'Run Level': '2',
                 'System': 'cloud-ms-1', 'Service': 'puppet'}]
        m_get_runlevels.side_effect = [(Services.SERVICE_STATE_TABLE_HEADER,
                                        data)]
        self.assertRaises(IOError, self.services.verify_service_status, None,
                          verbose=True)

    @patch('h_hc.hc_services.Services.litp')
    @patch('h_hc.hc_services.exec_process')
    def test_ping_nodes(self, exec_process, m_litp):
        stdout = '64 bytes from ieatlms4352-1 (127.0.0.1): ' \
                 'icmp_seq=1 ttl=64 time=0.022 ms'
        exec_process.return_value = stdout

        mocked_litp = self.mock_litp_nodes(
                ('svc-1', 'Applied', 'svc-1'),
                ('svc-2', 'Applied', 'svc-2')
        )
        m_litp.return_value = mocked_litp

        _, data, ok = self.services._ping_nodes()
        self.assertTrue(ok)
        self.assertEqual(3, len(data))
        for row in data:
            self.assertEqual(Services.STATE_ONLINE, row[Services.H_STATE])

    @patch('h_hc.hc_services.exec_process')
    @patch('h_hc.hc_services.Services.litp')
    def test_ping_nodes_IOError(self, m_litp, exec_process):
        m_litp.return_value = self.mock_litp_nodes(
                ('svc-1', 'Applied', 'svc-1'),
                ('svc-2', 'Applied', 'svc-2')
        )

        exec_process.side_effect = IOError
        _, data, ok = self.services._ping_nodes()
        self.assertFalse(ok)
        self.assertEqual(3, len(data))
        for row in data:
            self.assertEqual(Services.STATE_OFFLINE, row[Services.H_STATE])

    @patch('h_hc.hc_services.Services.source_nodes')
    def test_service_check_EXCEPT(self, m_source_nodes):
        m_source_nodes.side_effect = IOError
        self.assertRaises(IOError, self.services._get_runlevels)

    @patch('h_hc.hc_services.exec_process')
    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch('h_hc.hc_services.Services.litp')
    def test_service_check_4(self, m_litp, m_run_rpc_command,
                             m_exec_process):
        m_litp.return_value = self.mock_litp_nodes(
                ('cloud-svc-1', 'Applied', 'cloud-svc-1'),
                ('cloud-svc-2', 'Applied', 'cloud-svc-2'),
                ('cloud-db-1', 'Applied', 'cloud-db-1'),
                ('cloud-evt-1', 'Initial', 'cloud-evt-1'),
        )

        data_runlevel = {'cloud-svc-1': {'errors': '',
                                         'data': {'retcode': 0, 'err': None,
                                                  'out': '2'}},
                         'cloud-ms-1': {'errors': '',
                                        'data': {'retcode': 0, 'err': None,
                                                 'out': '3'}}}

        ping_results = {
            'cloud-ms-1': 1,
            'cloud-db-1': 1,
            'cloud-svc-1': 1,
            'cloud-svc-2': 0,
            'cloud-evt-1': 0,
        }

        def proxy_exec_process(command, ignore_error=False, sudo=None,
                               environ=None, stderr=STDOUT, use_shell=False):
            if ping_results[command[-1]] == 1:
                return True
            else:
                raise IOError()

        m_exec_process.side_effect = proxy_exec_process

        data_service_list = {'cloud-svc-1': {'errors': '',
                                             'data': {'retcode': 0, 'err': '',
                                                      'out': 'puppet'}},
                             'cloud-ms-1': {'errors': '',
                                            'data': {'retcode': 0,
                                                     'err': '',
                                                     'out': 'puppet'}}}

        data_check_services = {
            'cloud-ms-1': {'errors': '',
                           'data': {
                               'retcode': 0,
                               'err': '',
                               'out': {'puppet': 0
                                       }
                           }},
            'cloud-svc-1': {'errors': '',
                            'data': {
                                'retcode': 0,
                                'err': '',
                                'out':
                                    {'puppet': 3,
                                     'mcollective': 0
                                     }
                            }}

        }

        def stubbed_run_rpc_command(nodes, agent, action,
                                    action_kwargs=None,
                                    timeout=None, retries=0):
            if 'runlevel' == action:
                return data_runlevel
            elif 'service_list' == action:
                return data_service_list
            elif 'check_service' == action:
                return {nodes[0]: data_check_services[nodes[0]]}
            else:
                raise Exception('Missed implementation!!!!')

        m_run_rpc_command.side_effect = stubbed_run_rpc_command

        _, data = self.services._get_runlevels()
        self.assertEqual(6, len(data))

        hosts = set()
        for row in data:
            hostname = row[Services.H_SYSTEM]
            hosts.add(hostname)
            if hostname == 'cloud-ms-1':
                self.assertEqual('3', row[Services.H_LEVEL])
                self.assertEqual(Services.STATE_ONLINE, row[Services.H_STATE])
            elif hostname == 'cloud-db-1':
                self.assertEqual('-', row[Services.H_LEVEL])
                self.assertEqual('MCollective Unresponsive',
                                 row[Services.H_STATE])
            elif hostname == 'cloud-svc-2':
                self.assertEqual('-', row[Services.H_LEVEL])
                self.assertEqual('Host Unavailable', row[Services.H_STATE])
            elif hostname == 'cloud-svc-1':
                self.assertEqual('2', row[Services.H_LEVEL])
                if row[Services.H_SERVICE_NAME] == 'puppet':
                    self.assertEqual(Services.STATE_NOTRUNNING,
                                     row[Services.H_STATE])
                elif row[Services.H_SERVICE_NAME] == 'mcollective':
                    self.assertEqual(Services.STATE_ONLINE,
                                     row[Services.H_STATE])
                else:
                    self.fail('Unknown service in test [{0}]'.
                              format(row[Services.H_SERVICE_NAME]))
            elif hostname == 'cloud-evt-1':
                self.assertEqual('-', row[Services.H_LEVEL])
                self.assertEqual(LitpRestClient.ITEM_STATE_INITIAL,
                                 row[Services.H_STATE])
            else:
                self.fail('Unknown host in test [{0}]'.format(hostname))
        expected_modeled_nodes = ['cloud-svc-1', 'cloud-svc-2',
                                  'cloud-db-1', 'cloud-ms-1',
                                  'cloud-evt-1']
        self.assertListEqual(sorted(expected_modeled_nodes), sorted(hosts))

    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch('h_hc.hc_services.Services.source_nodes')
    def test_service_check_IO_ERROR(self, m_source_nodes, m_run_rpc_command):
        m_source_nodes.return_value = ['node-3']
        data_runlevel = {'cloud-svc-1': {'errors': '',
                                         'data': {'retcode': 0, 'err': None,
                                                  'out': '2'}},
                         'cloud-ms-1': {'errors': '',
                                        'data': {'retcode': 0, 'err': None,
                                                 'out': '3'}}}
        m_run_rpc_command.side_effect = [
            data_runlevel, IOError
        ]
        self.assertRaises(IOError, self.services._get_runlevels)
