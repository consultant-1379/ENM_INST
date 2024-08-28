import os
import shutil
import sys
from base64 import standard_b64encode
from os import makedirs
from os.path import join, exists
from tempfile import mktemp, gettempdir

import unittest2
from Crypto.Cipher import AES
from mock import MagicMock, PropertyMock
from mock import patch, call
from simplejson import loads, load
from json import dumps
import json
import redfish  # pylint: disable=import-error
# pylint: disable=import-error
from redfish.rest.v1 import BadRequestError, RetriesExhaustedError,\
    DecompressResponseError

import sys

sys.modules['naslib.log'] = MagicMock()
sys.modules['naslib.nasexceptions'] = MagicMock()
sys.modules['naslib.objects'] = MagicMock()
sys.modules['naslib.drivers'] = MagicMock()
sys.modules['naslib.drivers.sfs'] = MagicMock()
sys.modules['naslib.drivers.sfs.utils'] = MagicMock()

import enm_snapshots
import sanapiexception
from enm_snapshots import EnmSnap, EnmSnapException, main, Decryptor
from h_litp.litp_rest_client import LitpException
from h_puppet.mco_agents import EnminstAgent
from h_util.h_utils import ExitCodes, read_enminst_config, touch, \
    Redfishtool, RedfishToolException
from h_vcs.vcs_cli import Vcs
from litpd import LitpIntegration
from sanapiinfo import StorageGroupInfo, HbaInitiatorInfo, HluAluPairInfo, \
    LunInfo
from sanapi import Vnx2Api, UnityApi

if sys.platform.lower().startswith('win'):
    sys.modules['pwd'] = MagicMock()

TC_MODULE = 'enm_snapshots'
TC_UTIL_MODULE = 'h_util.h_utils'
san_cred = """{"properties": {
    "username": "admin",
    "name": "atvnx-45",
    "storage_network": "storage",
    "storage_site_id": "ENM281",
    "login_scope": "global",
    "ip_a": "10.151.40.89",
    "ip_b": "10.151.40.90",
    "san_type": "vnx1",
    "password_key": "key-for-san-atvnx-45"}}"""

sfs_service = """[{"path": "/infrastructure/storage/storage_providers/sfs",
                   "data": {"id": "sfs",
                            "item-type-name": "sfs-service",
                            "applied_properties_determinable": "True",
                            "state": "Applied",
                            "properties": {
                                "management_ipv4": "172.16.30.18",
                                "user_name": "support",
                                "name": "cloud-sfs",
                                "password_key": "key-for-sfs"}}}]"""

sfs_cred2 = """{"_embedded": {
        "item": [{"id": "enm-pool",
                "item-type-name": "sfs-pool",
                "applied_properties_determinable": true,
                "state": "Initial",
                "properties": {
                    "name": "enm"}}]}}"""
node_cred1 = """{
    "_embedded": {
        "item": [
                {"id": "svc-1_system",
                "item-type-name": "blade",
                "applied_properties_determinable": true,
                "state": "Initial",
                "properties": {
                    "system_name": "svc-1"}},
                {"id": "db-1_system",
                "item-type-name": "blade",
                "applied_properties_determinable": true,
                "state": "Applied",
                "properties": {
                    "system_name": "db-1"}},
                {"id": "management_server",
                "item-type-name": "system",
                "applied_properties_determinable": true,
                "state": "Initial",
                "properties": {
                    "system_name": "ieatlms3905-1"}},
                {"id": "db-2_system",
                "item-type-name": "blade",
                "applied_properties_determinable": true,
                "state": "Applied",
                "properties": {
                    "system_name": "db-2"}},
                {"id": "svc-2_system",
                "item-type-name": "blade",
                "applied_properties_determinable": true,
                "state": "Applied",
                "properties": {
                    "system_name": "svc-2"}}
                ]}}
"""
node_cred2 = """{    "properties": {
        "username": "root",
        "ipaddress": "10.32.231.108",
        "password_key": "key-for-db_node1_ilo"
    }
}

"""

sec_conf_file = """[keyset]
path: /path/key
[password]
path: /path/password
"""

cluster_removal = """
{
    "_embedded": {
        "item": [

        ]
    },
    "id": "aut-1",
    "item-type-name": "node",
    "applied_properties_determinable": "true",
    "state": "Applied",
    "_links": {
        "self": {
            "href": "https://localhost:9999/litp/rest/v1/deployments/enm/clusters/aut_cluster/nodes/aut-1"
        },
        "item-type": {
            "href": "https://localhost:9999/litp/rest/v1/item-types/node"
        }
    },
    "properties": {
        "is_locked": "false",
        "hostname": "ieatrcxb5850"
    }
}
"""

blade_info = [
    {'path': '/infrastructure/systems/db-1_system',
     'data': {u'id': u'db-1_system',
              u'item-type-name': u'blade',
              u'applied_properties_determinable': True,
              u'state': u'Applied',
              u'properties': {u'system_name': u'db-1'}}},
    {'path': '/infrastructure/systems/scp-2_system',
     'data': {u'id': u'scp-2_system',
              u'item-type-name': u'blade',
              u'applied_properties_determinable': True,
              u'state': u'Applied',
              u'properties': {u'system_name': u'scp-2'}}}]

class MockLitpObject(object):
    def __init__(self, path, state, properties, item_id):
        self.path = path
        self.state = state
        self.properties = properties
        self.item_id = item_id

    def get_property(self, key):
        return self.properties[key]

svc1_object  =  MockLitpObject("/deployments/enm/clusters/svc_cluster/nodes/svc-1" ,'Initial',
                                {'is_locked': 'false', 'hostname': 'ieatrcxb3388'},'svc-1')
svc2_object  =  MockLitpObject("/deployments/enm/clusters/svc_cluster/nodes/svc-2" ,'Applied',
                                {'is_locked': 'false', 'hostname': 'ieatrcxb3565'},'svc-2')

SVC_CLUSTER = 'svc_cluster'

SVC_CLUSTER_NODES = {'svc-1':svc1_object,
                     'svc-2':svc2_object}

MOCK_CLUSTER_NODES = {SVC_CLUSTER: SVC_CLUSTER_NODES}


class TestEnmSnap(unittest2.TestCase):
    def setUp(self):
        self.alist = []

        self.config = read_enminst_config()
        self.snap = EnmSnap(self.config)

        # To prevent side_effect persisting on subsequent tests
        self.orig_info = self.snap.logger.info
        self.orig_debug = self.snap.logger.debug

        # Create temporary file
        fake_file = join(gettempdir(), 'removed_blades_info')
        data_in_file = {'svc-1': {'cluster': 'svc_cluster',
                                  'hostname': 'ieatrcxb5850',
                                  'username': 'root',
                                  'iloaddress': '10.32.231.108',
                                  'password': 'psw'}}
        with open(fake_file, 'w') as _w:
            _w.write(dumps(data_in_file))
            _w.close()

    def tearDown(self):
        self.snap.logger.info = self.orig_info
        self.snap.logger.debug = self.orig_debug
        if exists(join(gettempdir(), 'removed_blades_info')):
            os.remove(join(gettempdir(), 'removed_blades_info'))

    def mock_system_pools(self, litp, lun1_pool, lun2_pool):
        systems = [
            {'path': 's1'}, {'path': 's2'},
        ]

        sys1_lun = [{
            'path': 'lun1',
            'data': {
                'item-type-name': 'lun-disk',
                'properties': {'storage_container': lun1_pool}
            }
        }]

        sys2_lun = [{
            'path': 'lun2',
            'data': {
                'item-type-name': 'lun-disk',
                'properties': {'storage_container': lun2_pool}
            }
        }]

        litp.return_value.get_children.side_effect = [
            systems, sys1_lun, sys2_lun
        ]

    def mock_sfs_model(self, litp):
        node_svc = [
            {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1',
             'data': {'id': 'svc-1'}},
            {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-2',
             'data': {'id': 'svc-2'}}
        ]
        node_db = [
            {'path': '/deployments/enm/clusters/db_cluster/nodes/db-1',
             'data': {'id': 'db-1'}},
            {'path': '/deployments/enm/clusters/db_cluster/nodes/db-2',
             'data': {'id': 'db-2'}}]
        litp.return_value.get_children.side_effect = [
            node_svc, node_db
        ]
        filesystem_1 = [
            {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/'
                     'file_systems/nfsm-batch',
             'data': {'id': 'nfsm-batch', 'properties': {
                 'provider': 'vs_enm_2'}}},
            {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/'
                     'file_systems/nfsm-smrs',
             'data': {'id': 'nfsm-smrs', 'properties': {
                 'provider': 'vs_enm_1'}}},
            {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/'
                     'file_systems/nfsm-data',
             'data': {'id': 'nfsm-data', 'properties': {'provider': 'vs_pm'}}}]

        filesystem_2 = [
            {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-2/'
                     'file_systems/nfsm-batch',
             'data': {'id': 'nfsm-batch', 'properties': {
                 'provider': 'vs_enm_2'}}},
            {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-2/'
                     'file_systems/nfsm-smrs',
             'data': {'id': 'nfsm-smrs', 'properties': {
                 'provider': 'vs_enm_1'}}},
            {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-2/'
                     'file_systems/nfsm-data',
             'data': {'id': 'nfsm-data', 'properties': {'provider': 'vs_pm'}}}]
        infra_provider = [
            {'path': '/infrastructure/storage/storage_providers/sfs',
             'data': {'id': 'sfs', 'item-type-name': 'sfs-service',
                      'properties': {'management_ipv4': '10.140.1.29',
                                     'pool': 'enm', 'user_name': 'support',
                                     'name': 'atsfsx148mgt',
                                     'password_key': 'key-for-sfs'}}},
            {'path': '/infrastructure/storage/storage_providers/san1',
             'data': {'id': 'san1', 'item-type-name': 'san-emc'}}]
        virtual_server = [
            {'path': '/infrastructure/storage/storage_providers/sfs/'
                     'virtual_servers/virtual_server_enm_2',
             'data': {'properties': {'name': 'vs_enm_2'}}},
            {'path': '/infrastructure/storage/storage_providers/sfs/'
                     'virtual_servers/virtual_server_enm_1',
             'data': {'properties': {'name': 'vs_enm_1'}}},
            {'path': '/infrastructure/storage/storage_providers/sfs/'
                     'virtual_servers/virtual_server_pm',
             'data': {'properties': {'name': 'vs_pm'}}}]
        pool = [
            {'path': '/infrastructure/storage/storage_providers/sfs/'
                     'pools/enm-pool',
             'data': {'properties': {'name': 'enm'}}}]

        litp.return_value.get_deployment_clusters.side_effect = [
            {'enm': ['svc_cluster', 'db_cluster']}
        ]

        litp.return_value.get_children.side_effect = [node_svc,
                                                      filesystem_1,
                                                      filesystem_2,
                                                      node_db,
                                                      filesystem_1,
                                                      filesystem_2,
                                                      infra_provider,
                                                      virtual_server,
                                                      pool]

    def mock_san_storage_provider(self, litp):
        storage_container = [{'data': {'id': 'pool1',
                                       'item-type-name': 'storage-container',
                                       'properties': {
                                           'type': 'POOL',
                                           'name': 'ENM223'}}}]

        san_details = [{'path': 'path1', 'data': {
            'item-type-name': 'san-emc',
            'properties': loads(san_cred)['properties']}}]

        litp.return_value.get_children.side_effect = [san_details,
                                                      storage_container]

    @patch('enm_snapshots.LitpRestClient')
    def test_get_systems_storage_container(self, litp):
        snapper = EnmSnap(self.config)
        self.assertIsNone(snapper.get_systems_storage_container())

        self.mock_system_pools(litp, 'pool1', 'pool1')
        pool = snapper.get_systems_storage_container()
        self.assertEqual('pool1', pool)

        litp.reset()
        self.mock_system_pools(litp, 'pool1', 'pool2')
        self.assertRaises(EnmSnapException,
                          snapper.get_systems_storage_container)

    @patch('enm_snapshots.EnmSnap.get_systems_storage_container')
    @patch('enm_snapshots.EnmSnap.get_psw')
    @patch('enm_snapshots.LitpRestClient')
    def test_get_san_cred(self, litp, get_psw, get_systems_storage_container):
        snapper = EnmSnap(self.config)
        self.mock_san_storage_provider(litp)
        get_systems_storage_container.return_value = 'ENM223'
        get_psw.return_value = 'psw'
        output = snapper.get_san_cred()
        self.assertEqual("admin", output['san_user'])
        self.assertEqual("psw", output['san_psw'])
        self.assertEqual("ENM223", output['san_pool'])

        litp.return_value.get_children.reset()
        litp.return_value.get_children.side_effect = [[]]
        self.assertRaises(EnmSnapException, snapper.get_san_cred)

    @patch('enm_snapshots.EnmSnap.get_psw')
    @patch('enm_snapshots.EnmSnap.get_nas_service_container')
    def test_get_nas_cred(self, serv_container, gpw):
        gpw.return_value = 'password'
        serv_container.return_value = {'management_ipv4': '10.140.1.29',
                                       'user_name': 'support',
                                       'name': 'atsfsx148mgt',
                                       'password_key': 'key-for-sfs',
                                       'pool_name': 'enm'}

        compareresult = {'nas_supsw': 'password',
                         'nas_supuser': 'support',
                         'nas_pool': 'enm',
                         'nas_name': 'atsfsx148mgt',
                         'nas_console': '10.140.1.29'}
        snapper = EnmSnap(self.config)
        result = snapper.get_nas_cred()
        self.assertEqual(result, compareresult)

    @patch('enm_snapshots.LitpRestClient')
    def test_get_nas_service_container(self, litp):
        snapper = EnmSnap(self.config)
        self.mock_sfs_model(litp)
        result = snapper.get_nas_service_container()
        self.assertEqual('10.140.1.29', result['management_ipv4'])
        self.assertEqual('support', result['user_name'])
        self.assertEqual('atsfsx148mgt', result['name'])
        self.assertEqual('key-for-sfs', result['password_key'])
        self.assertEqual('enm', result['pool'])

    @patch('enm_snapshots.EnmSnap.get_psw')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_get_node_cred(self, litp, get_psw):
        litp.side_effect = [loads(node_cred1), loads(node_cred2),
                            loads(node_cred2), loads(node_cred2),
                            loads(node_cred2)]
        get_psw.return_value = 'psw'
        output = self.snap.get_node_cred()
        self.assertEqual("root", output['db-1']['username'])
        self.assertEqual("psw", output['svc-1']['password'])
        self.assertEqual("10.32.231.108", output['svc-2']['iloaddress'])

    @patch('enm_snapshots.EnmSnap.load_list')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    @patch('enm_snapshots.EnmSnap.get_psw')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_get_node_cred_with_removed_nodes(self, litp, get_psw,
                                              m_file_exists, m_load_list):
        m_file_exists.return_value = True
        m_load_list.return_value = ['svc-2']
        litp.side_effect = [loads(node_cred1), loads(node_cred2),
                            loads(node_cred2), loads(node_cred2),
                            loads(node_cred2)]
        get_psw.return_value = 'psw'
        output = self.snap.get_node_cred()
        self.assertTrue("db-1" in output.keys())
        self.assertTrue("svc-1" in output.keys())
        self.assertTrue("svc-2" not in output.keys())

    @patch('enm_snapshots.get_removed_blades_info_filename')
    @patch('enm_snapshots.EnmSnap.get_psw')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    def test_get_removed_node_cred(self, m_file_exists, m_get_psw,
                                   get_info_file):
        fake_file = join(gettempdir(), 'test_file')
        m_file_exists.return_value = True
        m_get_psw.return_value = 'psw'
        get_info_file.return_value = fake_file
        data_in_file = {'svc-1': {'cluster': 'svc_cluster',
                                  'hostname': 'ieatrcxb5850',
                                  'username': 'root',
                                  'iloaddress': '10.32.231.108',
                                  'password': 'psw'}}
        expected_output = {'svc-1': {'username': 'root', 'iloaddress':
            '10.32.231.108', 'password': 'psw'}}
        with open(fake_file, 'w') as _w:
            _w.write(dumps(data_in_file))
            _w.close()

        output = self.snap.get_removed_node_cred()
        self.assertEqual(output, expected_output)

    @patch(TC_MODULE + '.exec_process')
    def test_manage_lms_services(self, ep):
        actions = ['stop', 'start']
        for action in actions:
            services = ['puppet', 'httpd']
            self.snap.manage_lms_services(action, services)

            for service in services:
                ep.assert_any_call(['service', service, action])

        ep.side_effect = IOError("unrecognized service")
        action = 'stop'
        service = ['puppet']
        self.snap.manage_lms_services(action, service,
                                      skip_uninstalled_service=True)

        ep.side_effect = IOError('this is on error')
        action = 'stop'
        service = ['testservice']
        self.assertRaises(IOError, self.snap.manage_lms_services, action,
                          service)

    @patch(TC_MODULE + '.discover_all_nodes')
    @patch(TC_MODULE + '.h_puppet.puppet_trigger_wait')
    def test_check_puppet_catalog(self, m_puppet_trigger_wait,
                                  m_discover_all_nodes):
        m_discover_all_nodes.side_effect = [['n1', 'n2']]
        self.snap.check_puppet_catalog()
        m_puppet_trigger_wait.assert_called_once_with(
                False, self.snap.logger.info, host_list=['n1', 'n2']
        )

    @patch(TC_MODULE + '.sleep')
    @patch(TC_MODULE + '.EnmSnap.load_list')
    @patch(TC_MODULE + '.check_blade_info_file_exists')
    @patch(TC_MODULE + '.EnmSnap.manage_lms_services')
    @patch(TC_MODULE + '.Redfishtool')
    def test_shutdown_nodes(self, mock_redfish, mls, iblade, load_list, m_sleep):
        mock_redfish.power_status.side_effect = [True, True, False, False]
        iblade.return_value = True
        load_list.return_value = ['db-1', 'svc-1', 'db-3', 'db-4']
        node_cred = {'db-1': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-1_system'},
                     'svc-1': {'username': 'root',
                               'iloaddress': '10.32.231.108',
                               'password': 'psw', 'id': 'svc-1_system'}}
        self.snap.shutdown_nodes(mock_redfish, node_cred)
        self.assertEqual(2, mls.call_count)
        mls.assert_has_calls(
                [call('stop', ['puppet', 'httpd', 'crond']),
                 call('stop', ['consul'], skip_uninstalled_service=True)])

        mock_redfish.power_status.side_effect = [True, True]
        self.assertRaises(EnmSnapException, self.snap.shutdown_nodes, mock_redfish,
                          node_cred, 1)

    @patch(TC_MODULE + '.sleep')
    @patch(TC_MODULE + '.EnmSnap.load_list')
    @patch(TC_MODULE + '.check_blade_info_file_exists')
    @patch(TC_MODULE + '.EnmSnap.manage_lms_services')
    @patch(TC_MODULE + '.Redfishtool')
    def test_shutdown_db3_first(self, mock_redfish, mls, iblade, load_list, m_sleep):
        mock_redfish.power_status.side_effect = [True, False, False, False, False]
        iblade.return_value = True
        load_list.return_value = ['db-1', 'db-2', 'svc-1']
        node_cred = {'db-1': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-1_system'},
                     'db-2': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-2_system'},
                     'db-3': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-3_system'},
                     'svc-1': {'username': 'root',
                               'iloaddress': '10.32.231.108',
                               'password': 'psw', 'id': 'svc-1_system'}}
        self.snap.shutdown_nodes(mock_redfish, node_cred)
        self.assertListEqual(m_sleep.mock_calls, [call(85)])
        self.assertEqual(2, mls.call_count)
        mls.assert_has_calls(
                [call('stop', ['puppet', 'httpd', 'crond']),
                 call('stop', ['consul'], skip_uninstalled_service=True)])

    @patch(TC_MODULE + '.check_blade_info_file_exists')
    @patch(TC_MODULE + '.EnmSnap.manage_lms_services')
    @patch(TC_MODULE + '.Redfishtool')
    @patch(TC_MODULE + '.EnmSnap.poweroff_node')
    def test_shutdown_nodes_not_all_threads_result(self, power, mock_redfish, mls,
                                                   iblade):
        node_cred = {'db-1': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-1_system'},
                     'svc-1': {'username': 'root',
                               'iloaddress': '10.32.231.108',
                               'password': 'psw', 'id': 'svc-1_system'}}
        iblade.return_value = False
        power.side_effect = [(True, None, "db-1")]
        self.assertRaises(EnmSnapException, self.snap.shutdown_nodes, mock_redfish,
                          node_cred, 1)

        power.side_effect = []
        self.assertRaises(EnmSnapException, self.snap.shutdown_nodes, mock_redfish,
                          node_cred, 1)

    @patch(TC_MODULE + '.is_dps_using_neo4j')
    @patch(TC_MODULE + '.Redfishtool')
    def test_start_nodes(self, mock_redfish, is_dps_neo4j):
        is_dps_neo4j.return_value = False
        mock_redfish.power_status.side_effect = [False, True, False, True]
        node_cred = {'db-1': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-1_system'},
                     'svc-1': {'username': 'root',
                               'iloaddress': '10.32.231.108',
                               'password': 'psw', 'id': 'svc-1_system'}}
        self.snap.start_nodes(mock_redfish, node_cred, sleeptime=2)
        mock_redfish.power_status.side_effect = [False, False]
        self.assertRaises(EnmSnapException, self.snap.start_nodes, mock_redfish,
                          node_cred, 1, 2)
        mock_redfish.power_status.side_effect = [True]
        self.assertRaises(EnmSnapException, self.snap.start_nodes, mock_redfish,
                          node_cred, 1, 2)

    @patch(TC_MODULE + '.is_dps_using_neo4j')
    @patch(TC_MODULE + '.Redfishtool')
    @patch(TC_MODULE + '.EnmSnap.power_up_node')
    def test_start_nodes_exception(self, power, mock_redfish, is_dps_neo4j):
        is_dps_neo4j.return_value = True
        node_cred = {'db-1': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-1_system'},
                     'svc-1': {'username': 'root',
                               'iloaddress': '10.32.231.108',
                               'password': 'psw', 'id': 'svc-1_system'},
                     'svc-2': {'username': 'root',
                               'iloaddress': '10.32.231.108',
                               'password': 'psw', 'id': 'svc-2_system'}}
        power.side_effect = [(True, None, "db-1")]
        self.assertRaises(EnmSnapException, self.snap.start_nodes, mock_redfish,
                          node_cred, 1, 1)
        power.side_effect = [(True, None, "db-1"), (True, None, "svc-1")]
        self.assertRaises(EnmSnapException, self.snap.start_nodes, mock_redfish,
                          node_cred, 1, 1)
        power.side_effect = [(True, None, "db-1"), (True, None, "svc-1"),
                             (False, "Exceptions", "svc-2")]
        self.assertRaises(EnmSnapException, self.snap.start_nodes, mock_redfish,
                          node_cred, 1, 1)

    @patch(TC_MODULE + '.sleep')
    @patch(TC_MODULE + '.is_dps_using_neo4j')
    @patch(TC_MODULE + '.Redfishtool')
    @patch(TC_MODULE + '.EnmSnap.power_up_node')
    def test_start_nodes_60k_neo4j(self, power, mock_redfish, is_dps_neo4j, m_sleep):
        is_dps_neo4j.return_value = True
        power.side_effect = [(True, None, "db-2"),
                             (True, None, "db-3"), (True, None, "svc-1")]
        node_cred = {'db-2': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-2_system'},
                     'db-3': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-3_system'},
                     'svc-1': {'username': 'root',
                               'iloaddress': '10.32.231.108',
                               'password': 'psw', 'id': 'svc-1_system'}}
        self.snap.start_nodes(mock_redfish, node_cred, sleeptime=1)
        self.assertListEqual(m_sleep.call_args_list, [call(300), call(1)])
        power.assert_has_calls([call(mock_redfish, 'db-3', node_cred, 60, False),
                                call(mock_redfish, 'db-2', node_cred, 60, False),
                                call(mock_redfish, 'svc-1', node_cred, 60, False)])
        m_sleep.reset_mock()
        power.reset_mock()
        power.side_effect = [(True, None, "db-2"),
                             (True, None, "db-3"),
                             (False, "Exceptions", "svc-1")]
        self.assertRaises(EnmSnapException, self.snap.start_nodes, mock_redfish,
                          node_cred, 1, 1)
        self.assertListEqual(m_sleep.call_args_list, [call(300), call(1)])
        power.assert_has_calls([call(mock_redfish, 'db-3', node_cred, 1, False),
                                call(mock_redfish, 'db-2', node_cred, 1, False),
                                call(mock_redfish, 'svc-1', node_cred, 1, False)])

    @patch(TC_MODULE + '.Redfishtool')
    def test_power_up_node(self, mock_redfish):
        node_cred = {'db-1': {'username': 'root',
                              'iloaddress': '10.32.231.108',
                              'password': 'psw', 'id': 'db-1_system'}}
        ret_val = self.snap.power_up_node(mock_redfish, 'db-1', node_cred, 1, True)
        self.assertTupleEqual(ret_val, (True, None, 'db-1'))
        ret_val = self.snap.power_up_node(mock_redfish, 'db-1', node_cred, 1, False)
        self.assertTupleEqual(ret_val, (False,
                                        'System db-1 is already powered on',
                                        'db-1'))

    @patch(TC_MODULE + '.os.remove')
    def test_rm_file(self, rm):
        self.snap.rm_file('bla')
        self.assertTrue(rm.called)

    @patch(TC_MODULE + '.os.remove')
    def test_rm_file_err_13(self, rm):
        rm.side_effect = OSError(13, 'Permission denied')
        self.assertRaises(SystemExit, self.snap.rm_file, 'bla')

    @patch(TC_MODULE + '.os.remove')
    def test_rm_file_err_2(self, rm):
        rm.side_effect = OSError(2, 'No such file')

        logged_messages = list()
        file_name = 'bla'

        def side_effect(msg):
            logged_messages.append(msg)

        self.snap.logger.info = side_effect
        self.snap.logger.debug = side_effect
        self.snap.rm_file(file_name)
        self.assertIn('File {0} does not exist'.format(file_name),
                      logged_messages)

    @patch(TC_MODULE + '.os.remove')
    def test_rm_file_err_other(self, rm):
        rm.side_effect = OSError(55, 'Other error')
        self.assertRaises(OSError, self.snap.rm_file, 'bla')

    @patch(TC_MODULE + '.EnmSnap.create_restore_file')
    @patch(TC_MODULE + '.EnmSnap.rm_dir_contents')
    @patch(TC_MODULE + '.EnmSnap.rm_file')
    def test_post_restore_tasks(self, rf, rdc, crf):
        self.snap.create_sfwk_restore_info()
        self.assertTrue(rdc.called)
        self.assertTrue(crf.called)
        self.assertTrue(rf.called)

    @patch(TC_MODULE + '.os.walk')
    @patch(TC_MODULE + '.os.remove')
    @patch(TC_MODULE + '.shutil.rmtree')
    def test_rm_dir_contents(self, sr, orm, ow):
        self.alist = []

        def se(st):
            self.alist.append(st)

        snap = EnmSnap(self.config)
        snap.logger = MagicMock()
        snap.logger.info = se
        snap.rm_dir_contents('bla')
        self.assertTrue(any('Successfully removed' in line for line in
                            self.alist))
        ow.return_value = ('bla', 'bla', 'bla')
        orm.side_effect = [OSError, True]
        self.assertRaises(EnmSnapException, self.snap.rm_dir_contents, 'bla')
        sr.side_effect = OSError
        self.assertRaises(EnmSnapException, self.snap.rm_dir_contents, 'bla')

    @patch(TC_MODULE + '.exec_process')
    def test_create_restore_file(self, ep):
        ep.side_effect = IOError
        self.assertRaises(EnmSnapException, self.snap.create_restore_file,
                          'bla')

    @patch(TC_MODULE + '.exists')
    def test_verify_file(self, opi):
        opi.return_value = False
        self.assertRaises(EnmSnapException, self.snap.verify_file, 'bla')

    @patch('__builtin__.open')
    @patch(TC_MODULE + '.dump')
    @patch(TC_MODULE + '.makedirs')
    def test_backup_list(self, m_makedirs, du, op):
        self.snap.backup_list(['bla'], 'bla')
        self.assertTrue(op.called)
        self.assertTrue(du.called)
        self.assertTrue(m_makedirs.called)

    @patch('enm_snapshots.VNXSnap')
    @patch('enm_snapshots.LVMSnapshots')
    @patch('enm_snapshots.SfsSnapshots')
    @patch('enm_snapshots.EnmSnap.get_san_cred')
    @patch('enm_snapshots.EnmSnap.get_nas_cred')
    def test_check_any_snapshots_exist_true(self,
                                            m_get_nas_cred,
                                            m_get_san_cred,
                                            m_sfs_snap,
                                            m_lvm_snap,
                                            m_vnx_snap):
        m_sfs_snap.return_value.list_snapshots.return_value = []
        m_lvm_snap.return_value.list_snapshots.return_value = (['abc'], {})
        m_vnx_snap.return_value.list_snapshots.return_value = []
        snapper = EnmSnap(self.config)
        self.assertTrue(snapper.check_any_snapshots_exist())
        self.assertTrue(m_get_nas_cred.called)
        self.assertTrue(m_get_san_cred.called)
        self.assertTrue(m_sfs_snap.called)
        self.assertTrue(m_lvm_snap.called)
        self.assertTrue(m_vnx_snap.called)

    @patch('enm_snapshots.VNXSnap')
    @patch('enm_snapshots.LVMSnapshots')
    @patch('enm_snapshots.SfsSnapshots')
    @patch('enm_snapshots.EnmSnap.get_san_cred')
    @patch('enm_snapshots.EnmSnap.get_nas_cred')
    def test_check_any_snapshots_exist_false(self,
                                             m_get_nas_cred,
                                             m_get_san_cred,
                                             m_sfs_snap,
                                             m_lvm_snap,
                                             m_vnx_snap):
        m_sfs_snap.return_value.list_snapshots.return_value = []
        m_lvm_snap.return_value.list_snapshots.return_value = ([], {})
        m_vnx_snap.return_value.list_snapshots.return_value = []
        snapper = EnmSnap(self.config)
        self.assertFalse(snapper.check_any_snapshots_exist())
        self.assertTrue(m_get_nas_cred.called)
        self.assertTrue(m_get_san_cred.called)
        self.assertTrue(m_sfs_snap.called)
        self.assertTrue(m_lvm_snap.called)
        self.assertTrue(m_vnx_snap.called)

    @patch('os.path.exists')
    @patch('enm_snapshots.exec_process_via_pipes')
    def test_neo4j_presnapshots_prepare_true(self, m_exec_process_via_pipes,
                                       m_script_exists):
        m_exec_process_via_pipes.return_value = ""
        m_script_exists.return_value=True
        snapper = EnmSnap(self.config)
        snapper.neo4j_presnapshots_prepare()
        self.assertTrue(m_exec_process_via_pipes.called)

    @patch('os.path.exists')
    @patch('enm_snapshots.exec_process_via_pipes')
    def test_neo4j_presnapshots_prepare_false(self, m_exec_process_via_pipes,
                                       m_script_exists):
        m_exec_process_via_pipes.return_value = ""
        m_script_exists.return_value=False
        snapper = EnmSnap(self.config)
        snapper.neo4j_presnapshots_prepare()
        self.assertFalse(m_exec_process_via_pipes.called)

    @patch('os.path.exists')
    @patch('enm_snapshots.exec_process_via_pipes')
    def test_neo4j_postsnapshots_remove_true(self, m_exec_process_via_pipes,
                                       m_script_exists):
        m_exec_process_via_pipes.return_value = ""
        m_script_exists.return_value=True
        snapper = EnmSnap(self.config)
        snapper.neo4j_postsnapshots_remove()
        self.assertTrue(m_exec_process_via_pipes.called)

    @patch('os.path.exists')
    @patch('enm_snapshots.exec_process_via_pipes')
    def test_neo4j_postsnapshots_remove_false(self, m_exec_process_via_pipes,
                                       m_script_exists):
        m_exec_process_via_pipes.return_value = ""
        m_script_exists.return_value=False
        snapper = EnmSnap(self.config)
        snapper.neo4j_postsnapshots_remove()
        self.assertFalse(m_exec_process_via_pipes.called)

    @patch('enm_snapshots.get_snapshots_indicator_filename')
    def test_check_snapshots_indicator_file_exists(self, m_get):
        m_get.return_value = 'somefile'
        self.assertFalse(enm_snapshots.check_snapshots_indicator_file_exists())

        m_get.return_value = gettempdir()
        self.assertFalse(enm_snapshots.check_snapshots_indicator_file_exists())

        m_get.return_value = join(gettempdir(), 'afile')
        touch(m_get.return_value)
        try:
            self.assertTrue(
                    enm_snapshots.check_snapshots_indicator_file_exists())
        finally:
            os.remove(m_get.return_value)

    @patch('enm_snapshots.get_snapshots_indicator_filename')
    def test_create_snapshots_indicator_file(self, m_get):
        m_get.return_value = join(gettempdir(), 'afile')
        if exists(m_get.return_value):
            os.remove(m_get.return_value)
        try:
            enm_snapshots.create_snapshots_indicator_file()
            self.assertTrue(exists(m_get.return_value))
        finally:
            if exists(m_get.return_value):
                os.remove(m_get.return_value)

    @patch('enm_snapshots.read_enminst_config')
    def test_get_snapshots_indicator_filename(self, m_read):
        m_read.return_value = {
            'enminst_runtime': gettempdir()
        }
        actual = enm_snapshots.get_snapshots_indicator_filename()
        self.assertEqual(
                actual,
                '{0}/{1}'.format(gettempdir(),
                                 enm_snapshots.UPGRADE_SNAPSHOTS_TAKEN))

    @patch('enm_snapshots.get_removed_blades_info_filename')
    @patch('enm_snapshots.delete_file')
    def test_remove_removed_blades_info_file(self, m_del_file, m_get):
        m_get.return_value = 'removed_blades_file'
        enm_snapshots.remove_removed_blades_info_file()
        m_del_file.assert_called_with(m_get.return_value)

    @patch('enm_snapshots.get_snapshots_indicator_filename')
    @patch('os.remove')
    def test_remove_snapshots_indicator_file(self, m_remove, m_get):
        m_get.return_value = 'afile'
        enm_snapshots.remove_snapshots_indicator_file()
        m_remove.assert_any_call(m_get.return_value)

        m_remove.reset_mock()
        m_remove.side_effect = OSError('')
        try:
            enm_snapshots.remove_snapshots_indicator_file()
        except Exception as e:
            self.fail('No error excpected {0}'.format(e))

    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.get_blade_info_filename')
    def test_create_blade_info_file(self, m_get, litp):
        m_get.return_value = join(gettempdir(), 'test_file')
        litp.return_value.get_items_by_type.return_value = blade_info
        if exists(m_get.return_value):
            os.remove(m_get.return_value)
        try:
            enm_snapshots.create_blade_info_file()
            self.assertTrue(exists(m_get.return_value))
        finally:
            if exists(m_get.return_value):
                os.remove(m_get.return_value)

    @patch(TC_UTIL_MODULE + '.get_removed_clusters')
    @patch(TC_UTIL_MODULE + '.get_removed_nodes')
    @patch('enm_snapshots.get_removed_blades_info_filename')
    def test_removed_blades_info_file(self, m_get, m_nodes, m_clusters):
        litpd = LitpIntegration()
        litpd.setup_svc_cluster()

        m_get.return_value = join(gettempdir(), 'test_removed_blades_file')
        m_clusters.return_value = ['/deployments/enm/clusters/svc_cluster']
        m_nodes.return_value = []

        with patch('enm_snapshots.LitpRestClient') as _litp:
            _litp.return_value = litpd
            enm_snapshots.create_removed_blades_info_file()

            _file = join(gettempdir(), 'test_removed_blades_file')
            self.assertTrue(exists(_file))

            with open(_file, 'r') as _reader:
                data = load(_reader)
            self.assertDictEqual(data, {
                "svc-1": {"username": "root", "cluster": "svc_cluster",
                          "password": "password-key", "hostname": "svc-1",
                          "iloaddress": "1.1.1.1"}
            })

    @patch('enm_snapshots.get_blade_info_filename')
    def test_check_blade_info_file_exists(self, m_get):
        m_get.return_value = 'test_file2'
        self.assertFalse(enm_snapshots.check_blade_info_file_exists())

        m_get.return_value = gettempdir()
        self.assertFalse(enm_snapshots.check_blade_info_file_exists())

        m_get.return_value = join(gettempdir(), 'test_file3')
        touch(m_get.return_value)
        try:
            self.assertTrue(
                    enm_snapshots.check_blade_info_file_exists())
        finally:
            os.remove(m_get.return_value)

    @patch('enm_snapshots.get_removed_blades_info_filename')
    def test_check_blade_info_file_exists2(self, m_get):
        m_get.return_value = 'test_removed_blades_file2'
        self.assertFalse(enm_snapshots.check_removed_blades_info_file_exists())

        m_get.return_value = gettempdir()
        self.assertFalse(enm_snapshots.check_removed_blades_info_file_exists())

        m_get.return_value = join(gettempdir(), 'test_removed_blades_file3')
        touch(m_get.return_value)
        try:
            self.assertTrue(
                    enm_snapshots.check_removed_blades_info_file_exists())
        finally:
            os.remove(m_get.return_value)

    @patch('enm_snapshots.api_builder')
    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.SanCleanup')
    def test_cleanup_blade_expansion_unity_check_order(self, m_sanclean, m_litp, m_sanapi):
        m_sanclean.return_value.get_san_info.return_value = {
            'san1': ['1.0.0.1', '1.0.0.2', 'enm1', 'global', 'UnItY', 'admin',
                     'test']}

        hba1 = HbaInitiatorInfo('00:01', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('00:02', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '3')
        hlu2 = HluAluPairInfo('2', '4')

        sgp = StorageGroupInfo('blah', 'uid', True, [hba1, hba2], [hlu1, hlu2])

        lun1 = LunInfo('5', 'LITP2_enm1_boot', 'uid', 'pool1', '1Gb',
                       'StoragePool', '5')
        lun2 = LunInfo('6', 'LITP2_enm1_fencing', 'uid', 'rg1', '1Gb',
                       'RaidGroup', '5')

        unity_mock = MagicMock(spec=UnityApi)
        unity_mock.rest = MagicMock()
        unity_mock.rest.delete_instance = MagicMock()
        unity_mock.get_storage_group.return_value = sgp
        sgp.hlualu_list = [hlu1, hlu2]
        unity_mock.get_lun.side_effect = [lun1, lun2]
        m_sanapi.return_value = unity_mock

        calls = [call.initialise(('1.0.0.1', '1.0.0.2'), 'admin', 'test', 'global', esc_pwd=True),
                 call.get_storage_group('enm1-enm-db_cluster-db-1'),
                 call.disconnect_host('enm1-enm-db_cluster-db-1',
                                      m_litp.return_value.get.return_value.get.return_value.get.return_value),
                 call.deregister_hba_uid('00:01'), call.deregister_hba_uid('00:02'),
                 call.get_lun(lun_id='3'), call.get_lun(lun_id='4'),
                 call.remove_luns_from_storage_group('enm1-enm-db_cluster-db-1', sgp.hlualu_list),
                 call.delete_storage_group('enm1-enm-db_cluster-db-1')]

        enm_snapshots.cleanup_blade_expansion(['db-1'], ['3', '4'])
        unity_mock.assert_has_calls(calls, any_order=False)

    @patch('enm_snapshots.api_builder')
    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.SanCleanup')
    def test_cleanup_blade_expansion_vnx_check_order(self, m_sanclean, m_litp, m_sanapi):
        m_sanclean.return_value.get_san_info.return_value = {
            'san1': ['1.0.0.1', '1.0.0.2', 'enm1', 'global', 'vnx2', 'admin',
                     'test']}

        hba1 = HbaInitiatorInfo('00:01', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('00:02', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '3')
        hlu2 = HluAluPairInfo('2', '4')

        sgp = StorageGroupInfo('enm1-enm-db_cluster-db-1', 'uid', True,
                               [hba1, hba2], [hlu1, hlu2])

        lun1 = LunInfo('5', 'LITP2_enm1_versantdb', 'uid', 'pool1', '1Gb',
                       'StoragePool', '5')
        lun2 = LunInfo('6', 'LITP2_enm16_postgresdb', 'uid', 'rg1', '1Gb',
                       'StoragePool', '5')

        vnx_mock = MagicMock(spec=Vnx2Api)
        vnx_mock.get_storage_group.return_value = sgp
        vnx_mock.get_lun.side_effect = [lun1, lun2]
        m_sanapi.return_value = vnx_mock

        calls = [call.initialise(('1.0.0.1', '1.0.0.2'), 'admin', 'test', 'global', esc_pwd=True),
                 call.get_storage_group('enm1-enm-db_cluster-db-1', logmsg=False),
                 call.disconnect_host('enm1-enm-db_cluster-db-1',
                                      m_litp.return_value.get.return_value.get.return_value.get.return_value),
                 call.deregister_hba_uid('00:01'), call.deregister_hba_uid('00:02'),
                 call.remove_luns_from_storage_group('enm1-enm-db_cluster-db-1', sgp.hlualu_list),
                 call.get_lun(lun_id='3'), call.get_lun(lun_id='4'),
                 call.delete_storage_group('enm1-enm-db_cluster-db-1')]

        enm_snapshots.cleanup_blade_expansion(['db-1'], ['3', '4'])
        vnx_mock.assert_has_calls(calls, any_order=False)

    @patch('enm_snapshots.api_builder')
    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.SanCleanup')
    @patch('enm_snapshots.LitpObject')
    def test_cleanup_luns_with_snapshot(self, obj, m_sanclean, m_litp,
                                        m_sanapi):
        m_sanclean.return_value.get_san_info.return_value = {
            'san1': ['1.0.0.1', '1.0.0.2', 'enm1', 'global', 'vnx2', 'admin',
                     'test']}

        hba1 = HbaInitiatorInfo('00:01', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('00:02', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '3')
        hlu2 = HluAluPairInfo('2', '4')

        sgp = StorageGroupInfo('enm1-enm-db_cluster-db-1', 'uid', True,
                               [hba1, hba2], [hlu1, hlu2])

        lun1 = LunInfo('5', 'LITP2_enm1_versantdb', 'uid', 'pool1', '1Gb',
                       'StoragePool', '5')
        lun2 = LunInfo('6', 'LITP2_enm16_postgresdb', 'uid', 'rg1', '1Gb',
                       'StoragePool', '5')

        vnx_mock = MagicMock(spec=Vnx2Api)
        vnx_mock.get_storage_group.return_value = sgp
        vnx_mock.get_lun.side_effect = [lun1, lun2]

        m_sanapi.return_value = vnx_mock

        enm_snapshots.cleanup_blade_expansion(['db-1'], ['3', '4'])

        m_sanclean.return_value.delete_luns.assert_called_with(
                m_sanapi.return_value, [])
        vnx_mock.delete_storage_group.assert_called_with(
                'enm1-enm-db_cluster-db-1')
        vnx_mock.get_storage_group.assert_called_with(
                'enm1-enm-db_cluster-db-1', logmsg=False)

    @patch('enm_snapshots.api_builder')
    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.SanCleanup')
    @patch('enm_snapshots.LitpObject')
    def test_cleanup_luns_with_snapshot_for_unity(self, obj, m_sanclean, m_litp,
                                        m_sanapi):
        m_sanclean.return_value.get_san_info.return_value = {
            'san1': ['1.0.0.1', '1.0.0.2', 'enm1', 'global', 'Unity', 'admin',
                     'test']}

        hba1 = HbaInitiatorInfo('00:01', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('00:02', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '3')
        hlu2 = HluAluPairInfo('2', '4')

        sgp = StorageGroupInfo('enm1-enm-db_cluster-db-1', 'uid', True,
                               [hba1, hba2], [hlu1, hlu2])

        lun1 = LunInfo('5', 'LITP2_enm1_versantdb', 'uid', 'pool1', '1Gb',
                       'StoragePool', '5')
        lun2 = LunInfo('6', 'LITP2_enm16_postgresdb', 'uid', 'rg1', '1Gb',
                       'StoragePool', '5')

        unity_mock = MagicMock(spec=UnityApi)
        unity_mock.get_storage_group.return_value = sgp
        unity_mock.rest = MagicMock()
        unity_mock.rest.delete_instance = MagicMock()
        unity_mock.get_lun.side_effect = [lun1, lun2]

        m_sanapi.return_value = unity_mock

        enm_snapshots.cleanup_blade_expansion(['db-1'], ['3', '4'])

        m_sanclean.return_value.delete_luns.assert_called_with(
                m_sanapi.return_value, [])
        unity_mock.delete_storage_group.assert_called_with(
                'enm1-enm-db_cluster-db-1')
        unity_mock.get_storage_group.assert_called_with(
                'enm1-enm-db_cluster-db-1')

    @patch('enm_snapshots.api_builder')
    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.SanCleanup')
    def test_cleanup_luns_no_snapshot_no_excluded(self, m_sanclean, m_litp,
                                                  m_sanapi):
        m_sanclean.return_value.get_san_info.return_value = {
            'san1': ['1.0.0.1', '1.0.0.2', 'enm1', 'global', 'vnx2', 'admin',
                     'test']}

        hba1 = HbaInitiatorInfo('00:01', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('00:02', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '5')
        hlu2 = HluAluPairInfo('2', '6')

        sgp = StorageGroupInfo('blah', 'uid', True, [hba1, hba2], [hlu1, hlu2])

        lun1 = LunInfo('5', 'LITP2_enm1_boot', 'uid', 'pool1', '1Gb',
                       'StoragePool', '5')
        lun2 = LunInfo('6', 'LITP2_enm1_fencing', 'uid', 'rg1', '1Gb',
                       'RaidGroup', '5')

        vnx_mock = MagicMock(spec=Vnx2Api)
        vnx_mock.get_storage_group.return_value = sgp
        vnx_mock.get_lun.side_effect = [lun1, lun2]
        m_sanapi.return_value = vnx_mock

        enm_snapshots.cleanup_blade_expansion(['db-1'], ['3', '4'])

        m_sanclean.return_value.delete_luns.assert_called_with(
                m_sanapi.return_value, ['5'])
        self.assertTrue(m_sanapi.return_value.delete_storage_group.called)
        vnx_mock.get_storage_group.assert_called_with(
                'enm1-enm-db_cluster-db-1', logmsg=False)

    @patch('enm_snapshots.api_builder')
    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.SanCleanup')
    def test_cleanup_luns_no_snapshot_no_excluded_for_unity(self, m_sanclean,
                                                            m_litp, m_sanapi):
        m_sanclean.return_value.get_san_info.return_value = {
            'san1': ['1.0.0.1', '1.0.0.2', 'enm1', 'global', 'UnItY', 'admin',
                     'test']}

        hba1 = HbaInitiatorInfo('00:01', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('00:02', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '5')
        hlu2 = HluAluPairInfo('2', '6')

        sgp = StorageGroupInfo('blah', 'uid', True, [hba1, hba2], [hlu1, hlu2])

        lun1 = LunInfo('5', 'LITP2_enm1_boot', 'uid', 'pool1', '1Gb',
                       'StoragePool', '5')
        lun2 = LunInfo('6', 'LITP2_enm1_fencing', 'uid', 'rg1', '1Gb',
                       'RaidGroup', '5')

        unity_mock = MagicMock(spec=UnityApi)
        unity_mock.rest = MagicMock()
        unity_mock.rest.delete_instance = MagicMock()
        unity_mock.get_storage_group.return_value = sgp
        unity_mock.get_lun.side_effect = [lun1, lun2]
        m_sanapi.return_value = unity_mock

        enm_snapshots.cleanup_blade_expansion(['db-1'], ['3', '4'])

        m_sanclean.return_value.delete_luns.assert_called_with(
                m_sanapi.return_value, ['5'])
        self.assertTrue(m_sanapi.return_value.delete_storage_group.called)
        unity_mock.get_storage_group.assert_called_with(
                'enm1-enm-db_cluster-db-1')

    @patch('enm_snapshots.api_builder')
    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.SanCleanup')
    def test_cleanup_luns_excluded(self, m_sanclean, m_litp, m_sanapi):
        m_sanclean.return_value.get_san_info.return_value = {
            'san1': ['1.0.0.1', '1.0.0.2', 'enm1', 'global', 'vnx2', 'admin',
                     'test']}
        m_sanclean.return_value.get_sg_hbauids.return_value = ['00:01',
                                                               '00:02']
        m_sanclean.return_value.remove_luns_from_sg.return_value = ['7', '8']
        name_property = PropertyMock(side_effect=[
            'LITP2_enm1_elasticsearchdb', 'LITP2_enm1_versant_bur'])
        type(m_sanapi.return_value.get_lun.return_value).name = name_property
        type_property = PropertyMock(side_effect=['StoragePool',
                                                  'StoragePool'])
        type(m_sanapi.return_value.get_lun.return_value).type = type_property
        enm_snapshots.cleanup_blade_expansion(['db-1'],
                                              ['3', '4'])
        m_sanclean.return_value.delete_luns.assert_called_with(
                m_sanapi.return_value, [])
        self.assertTrue(m_sanapi.return_value.delete_storage_group.called)

    @patch('enm_snapshots.api_builder')
    @patch('enm_snapshots.LitpRestClient')
    @patch('enm_snapshots.SanCleanup')
    def test_cleanup_blade_expansion_raise_sg_not_found(self, m_sanclean,
                                                        m_litp, m_sanapi):
        m_sanapi.return_value.get_storage_group.side_effect = \
            sanapiexception.SanApiEntityNotFoundException()
        enm_snapshots.cleanup_blade_expansion(['svc-1', 'svc-2'], ['3', '4'])
        self.assertTrue(m_sanclean.return_value.get_san_info.called)
        self.assertTrue(m_sanapi.return_value.initialise.called)
        self.assertTrue(m_litp.return_value.get.called)
        self.assertTrue(m_sanapi.return_value.get_storage_group.called)
        self.assertFalse(m_sanclean.return_value.get_sg_hbauids.called)
        self.assertFalse(m_sanclean.return_value.disconnect_host.called)
        self.assertFalse(m_sanclean.return_value.deregister_hbauid.called)
        self.assertFalse(m_sanclean.return_value.remove_luns_from_sg.called)
        self.assertFalse(m_sanclean.return_value.delete_luns.called)
        self.assertFalse(m_sanclean.return_value.destroy_sg.called)

    @patch('enm_snapshots.read_enminst_config')
    def test_get_blade_info_filename(self, m_read_enminst):
        m_read_enminst.return_value = {'enminst_runtime': '/tmp/runtime'}
        self.assertEqual(enm_snapshots.get_blade_info_filename(),
                         '/tmp/runtime/blade_info')

    @patch('enm_snapshots.read_enminst_config')
    def test_get_removed_blades_info_filename(self, m_read_enminst):
        m_read_enminst.return_value = {'enminst_runtime': '/tmp/runtime'}
        self.assertEqual(enm_snapshots.get_removed_blades_info_filename(),
                         '/tmp/runtime/removed_blades_info')

    @patch(TC_MODULE + '.EnmSnap.get_san_cred')
    @patch(TC_MODULE + '.EnmSnap.get_nas_cred')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap.get_node_cred')
    def test_main_list(self, node_cred, lvm, san, sfs, m_san_cred, nas_cred):
        lvm.return_value.list_snapshots = MagicMock()
        san.return_value.list_snapshots = MagicMock()
        sfs.return_value.list_snapshots = MagicMock()
        main(['--action', 'list_snapshot'])
        self.assertTrue(lvm.return_value.list_snapshots.called)
        self.assertTrue(sfs.return_value.list_snapshots.called)
        self.assertTrue(san.return_value.list_snapshots.called)
        self.assertTrue(m_san_cred.called)
        self.assertTrue(nas_cred.called)
        self.assertFalse(node_cred.called)

    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    def test_main_validate(self, lvm, san, sfs, enm):
        lvm.return_value.validate = MagicMock()
        san.return_value.validate = MagicMock()
        sfs.return_value.validate = MagicMock()
        main(['--action', 'validate_snapshot'])
        self.assertTrue(lvm.return_value.validate.called)
        self.assertTrue(sfs.return_value.validate.called)
        self.assertTrue(san.return_value.validate.called)
        self.assertTrue(enm.called)

    @patch(TC_MODULE + '.remove_migration_lockfile')
    @patch(TC_MODULE + '.remove_removed_blades_info_file')
    @patch(TC_MODULE + '.remove_snapshots_indicator_file')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.migrate_elasticsearch_indexes')
    def test_main_remove_snapshots(self, es, lvm, san, sfs, enm,
                                   m_remove_snapshots_indicator_file,
                                   m_remove_removed_blades_info_file,
                                   m_remove_migration_lockfile):
        es.return_value = 0
        lvm.return_value.remove_snapshots = MagicMock()
        san.return_value.remove_snapshots = MagicMock()
        sfs.return_value.remove_snapshots = MagicMock()
        main(['--action', 'remove_snapshot'])
        self.assertTrue(lvm.return_value.remove_snapshots.called)
        self.assertTrue(sfs.return_value.remove_snapshots.called)
        self.assertTrue(san.return_value.remove_snapshots.called)
        self.assertTrue(enm.called)
        self.assertTrue(m_remove_snapshots_indicator_file.called)
        self.assertTrue(m_remove_migration_lockfile.called)

    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.Redfishtool')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.clear_and_unmount')
    @patch('import_iso.mount')
    @patch('import_iso.umount')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    @patch('enm_snapshots.get_removed_blades_info_filename')
    def test_main_restore_snapshots(self, get_info_file, m_file_exists,
                                    mnt, umnt, cau, litp, mock_redfish,
                                    lvm, san, sfs, enm):
        lvm.return_value.restore_snapshots = MagicMock()
        lvm.return_value.reboot = MagicMock()
        san.return_value.restore_snapshots = MagicMock()
        sfs.return_value.restore_snapshots = MagicMock()
        lvm.return_value.validate = MagicMock()
        san.return_value.validate = MagicMock()
        sfs.return_value.validate = MagicMock()
        enm.return_value.shutdown_nodes = MagicMock()
        enm.return_value.start_nodes = MagicMock()
        litp.return_value.is_plan_running.return_value = False
        m_file_exists.return_value = True
        get_info_file.return_value = os.path.join(gettempdir(),
                                                  'removed_blades_info')
        main(['--action', 'restore_snapshot'])
        self.assertTrue(lvm.return_value.restore_lms_snapshots.called)
        self.assertTrue(sfs.return_value.restore_snapshots.called)
        self.assertTrue(san.return_value.restore_snapshots.called)
        self.assertTrue(lvm.return_value.validate.called)
        self.assertTrue(sfs.return_value.validate.called)
        self.assertTrue(san.return_value.validate.called)
        self.assertTrue(lvm.return_value.reboot.called)
        self.assertTrue(enm.return_value.shutdown_nodes)
        self.assertTrue(enm.return_value.start_nodes)
        self.assertTrue(mock_redfish.called)
        self.assertTrue((call().manage_lms_services(
            'stop', ['puppetserver',
            'puppetserver_monitor']) in enm.mock_calls))

    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.Redfishtool')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.clear_and_unmount')
    @patch('import_iso.mount')
    @patch('import_iso.umount')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    @patch('enm_snapshots.get_removed_blades_info_filename')
    @patch('enm_snapshots.LVMSnapshots.is_migration')
    def test_main_restore_snapshots_Rhel7_upift(self, m_migration,
                                    get_info_file, m_file_exists,
                                    mnt, umnt, cau, litp, mock_redfish,
                                    lvm, san, sfs, enm):
        m_migration.side_effect = True
        lvm.return_value.restore_snapshots = MagicMock()
        lvm.return_value.reboot = MagicMock()
        san.return_value.restore_snapshots = MagicMock()
        sfs.return_value.restore_snapshots = MagicMock()
        lvm.return_value.validate = MagicMock()
        san.return_value.validate = MagicMock()
        sfs.return_value.validate = MagicMock()
        enm.return_value.shutdown_nodes = MagicMock()
        enm.return_value.start_nodes = MagicMock()
        litp.return_value.is_plan_running.return_value = False
        m_file_exists.return_value = True
        get_info_file.return_value = os.path.join(gettempdir(),
                                                  'removed_blades_info')
        main(['--action', 'restore_snapshot'])
        self.assertTrue(lvm.return_value.restore_lms_snapshots.called)
        self.assertTrue(sfs.return_value.restore_snapshots.called)
        self.assertTrue(san.return_value.restore_snapshots.called)
        self.assertTrue(lvm.return_value.validate.called)
        self.assertTrue(sfs.return_value.validate.called)
        self.assertTrue(san.return_value.validate.called)
        self.assertTrue(lvm.return_value.reboot.called)
        self.assertTrue(enm.return_value.shutdown_nodes)
        self.assertTrue(enm.return_value.start_nodes)
        self.assertTrue(mock_redfish.called)
        self.assertTrue((call().manage_lms_services(
            'stop', ['puppetserver',
            'puppetserver_monitor']) in enm.mock_calls))

    @patch(TC_MODULE + '.remove_removed_blades_info_file')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.SanCleanup')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.Redfishtool')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.check_blade_info_file_exists')
    @patch(TC_MODULE + '.clear_and_unmount')
    @patch('import_iso.mount')
    @patch('import_iso.umount')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    @patch('enm_snapshots.get_removed_blades_info_filename')
    def test_main_restore_snapshots_remove_blades(
            self, get_info_file, m_file_exists,
            umnt, mnt, cau, blade, litp, mock_redfish, lvm,
            san, sfs, cleanup_sancleanup, enm,
            m_remove_removed_blades_info_file):
        lvm.return_value.restore_snapshots = MagicMock()
        lvm.return_value.reboot = MagicMock()
        san.return_value.restore_snapshots = MagicMock()
        sfs.return_value.restore_snapshots = MagicMock()
        lvm.return_value.validate = MagicMock()
        san.return_value.validate = MagicMock()
        sfs.return_value.validate = MagicMock()
        enm.return_value.shutdown_nodes = MagicMock()
        enm.return_value.start_nodes = MagicMock()
        enm.return_value.load_list = MagicMock()
        litp.return_value.is_plan_running.return_value = False
        blade.return_value = True
        m_file_exists.return_value = True
        get_info_file.return_value = os.path.join(gettempdir(),
                                                  'removed_blades_info')
        main(['--action', 'restore_snapshot'])
        self.assertTrue(lvm.return_value.restore_lms_snapshots.called)
        self.assertTrue(sfs.return_value.restore_snapshots.called)
        self.assertTrue(san.return_value.restore_snapshots.called)
        self.assertTrue(lvm.return_value.validate.called)
        self.assertTrue(sfs.return_value.validate.called)
        self.assertTrue(san.return_value.validate.called)
        self.assertTrue(lvm.return_value.reboot.called)
        self.assertTrue(enm.return_value.shutdown_nodes)
        self.assertTrue(enm.return_value.start_nodes)
        self.assertTrue(mock_redfish.called)
        self.assertTrue((call().manage_lms_services(
            'stop', ['puppetserver',
            'puppetserver_monitor']) in enm.mock_calls))

    @patch(TC_MODULE + '.is_mount_option_migrated')
    @patch(TC_MODULE + '.discover_vcs_clusters')
    @patch(TC_MODULE + '.SnapAgents.ensure_installed')
    @patch(TC_MODULE + '.EnmSnap.get_san_cred')
    @patch(TC_MODULE + '.EnmSnap.get_nas_cred')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap.get_node_cred')
    @patch(TC_MODULE + '.EnmSnap.backup_list')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.EnmSnap.manage_lms_services')
    @patch(TC_MODULE + '.EnmSnap.check_puppet_catalog')
    @patch(TC_MODULE + '.EnmSnap.neo4j_presnapshots_prepare')
    @patch(TC_MODULE + '.create_blade_info_file')
    def test_main_create(self, blade_file, presnap_prepare,
                         cpc, mls, litp, bl, node_cred, lvm, san, sfs,
                         m_san_cred, nas_cred, m_ensure_installed,
                         m_discover_vcs_clusters,
                         m_is_mount_option_migrated):

        m_is_mount_option_migrated.return_value = True
        lvm.return_value.create_snapshots.return_value = (
            MagicMock(name='lv_list'), MagicMock(name='nodelv_list'))
        san.return_value.create_snapshots = MagicMock()
        sfs.return_value.create_snapshots = MagicMock()

        litp.return_value.is_plan_running.return_value = False
        m_discover_vcs_clusters.side_effect = [{
            Vcs.ENM_DB_CLUSTER_NAME: ['n1', 'n2']
        }]

        main(['--action', 'create_snapshot'])

        self.assertTrue(lvm.return_value.create_snapshots.called)
        self.assertTrue(sfs.return_value.create_snapshots.called)
        self.assertTrue(san.return_value.create_snapshots.called)
        self.assertTrue(m_san_cred.called)
        self.assertTrue(nas_cred.called)
        self.assertFalse(node_cred.called)
        self.assertTrue(bl.called)
        self.assertTrue(mls.called)
        self.assertTrue(cpc.called)
        self.assertTrue(blade_file.called)
        self.assertTrue(m_discover_vcs_clusters.called)
        self.assertEqual(2, m_ensure_installed.call_count)
        self.assertTrue(presnap_prepare.called)

        m_ensure_installed.assert_has_calls(
                [call('NaviCLI-Linux-64-x86-en_US', 'n1'),
                 call('NaviCLI-Linux-64-x86-en_US', 'n2')],
                any_order=True)

    def test_main_help(self):
        self.assertRaises(SystemExit, main, ['--action', 'bla'])

    @patch(TC_MODULE + '.is_mount_option_migrated')
    @patch(TC_MODULE + '.discover_vcs_clusters')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.create_blade_info_file')
    def test_create_snap_running_plan(self, blade_file,
                                      litp, snapper, lvm, vnx, sfs,
                                      m_discover_vcs_clusters,
                                      m_is_mount_option_migrated):

        m_is_mount_option_migrated.return_value = True
        litp.return_value.is_plan_running.return_value = False
        lvm.return_value.create_snapshots = MagicMock()
        lvm.return_value.create_snapshots.return_value = (
            MagicMock(name='lv_list'), MagicMock(name='nodelv_list'))
        vnx.return_value.create_snapshots = MagicMock()
        sfs.return_value.create_snapshots = MagicMock()
        main(['--action', 'create_snapshot'])
        self.assertTrue(lvm.return_value.create_snapshots.called)
        self.assertTrue(sfs.return_value.create_snapshots.called)
        self.assertTrue(vnx.return_value.create_snapshots.called)
        self.assertTrue(blade_file.called)

        litp.return_value.is_plan_running.return_value = True
        self.assertRaises(SystemExit, main, ['--action', 'create_snapshot'])

    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.clear_and_unmount')
    @patch('import_iso.mount')
    @patch('import_iso.umount')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    @patch('enm_snapshots.get_removed_blades_info_filename')
    def test_restore_snap_running_plan(self, get_info_file, m_file_exists,
                                       umnt, mnt, cau, litp,
                                       snapper, lvm, vnx, sfs):
        lvm.return_value.create_snapshots.return_value = (
            MagicMock(name='lv_list'), MagicMock(name='nodelv_list'))
        vnx.return_value.restore_snapshots = MagicMock()
        sfs.return_value.restore_snapshots = MagicMock()
        m_file_exists.return_value = True
        get_info_file.return_value = os.path.join(gettempdir(),
                                                  'removed_blades_info')
        main(['--action', 'restore_snapshot'])
        self.assertTrue(lvm.return_value.restore_lms_snapshots.called)
        self.assertTrue(sfs.return_value.restore_snapshots.called)
        self.assertTrue(vnx.return_value.restore_snapshots.called)

    @patch(TC_MODULE + '.LitpRestClient')
    def test_manage_litp_snapshots_create(self, litp):

        litp.return_value.list_snapshots.return_value = []

        main(['--action', 'create_snapshot',
              '--snap_type', 'litp'])
        self.assertTrue(litp.return_value.create_snapshot.called)
        self.assertTrue(litp.return_value.monitor_plan.called)

        litp.return_value.create_snapshot.reset_mock()
        litp.return_value.monitor_plan.reset_mock()
        litp.return_value.list_snapshots.return_value = ['snapshot1']
        main(['--action', 'create_snapshot',
              '--snap_type', 'litp'])
        self.assertTrue(litp.return_value.create_snapshot.called)
        self.assertTrue(litp.return_value.monitor_plan.called)

        litp.return_value.list_snapshots.return_value = ['snapshot']
        self.assertRaises(SystemExit, main, ['--action', 'create_snapshot',
                                             '--snap_type', 'litp'])

    @patch(TC_MODULE + '.LitpRestClient')
    def test_manage_litp_snapshots_remove(self, litp):
        litp.return_value.list_snapshots.return_value = []
        main(['--action', 'remove_snapshot', '--snap_type', 'litp'])
        self.assertFalse(litp.return_value.remove_snapshot.called)

        litp.return_value.list_snapshots.return_value = ['snapshot']
        main(['--action', 'remove_snapshot',
              '--snap_type', 'litp', '--force'])
        self.assertTrue(litp.return_value.remove_snapshot.called)
        m_remove_snapshot = litp.return_value.remove_snapshot
        m_remove_snapshot.assert_has_calls(
                [
                    call().remove_snapshot(force=True, name='snapshot')
                ], any_order=True)

        litp.return_value.list_snapshots.return_value = ['snapshot1']
        self.assertRaises(SystemExit, main, ['--action', 'remove_snapshot',
                                             '--snap_type', 'litp'])

        litp.return_value.list_snapshots.return_value = ['snapshot', 'snap1']
        main(['--action', 'remove_snapshot',
              '--snap_type', 'litp', '--snap_name', 'snap1'])
        self.assertTrue(litp.return_value.remove_snapshot.called)
        m_remove_snapshot = litp.return_value.remove_snapshot
        m_remove_snapshot.assert_has_calls(
                [
                    call().remove_snapshot(force=False, name='snap1')
                ], any_order=True)

    @patch(TC_MODULE + '.LitpRestClient')
    def test_manage_litp_snapshots_errors(self, litp):

        litp.return_value.list_snapshots.side_effect = IOError
        self.assertRaises(IOError, main, ['--action', 'create_snapshot',
                                          '--snap_type', 'litp'])

        litp.return_value.list_snapshots.side_effect = LitpException(
                1, {}
        )
        self.assertRaises(LitpException, main, ['--action', 'create_snapshot',
                                                '--snap_type', 'litp'])

        litp.return_value.list_snapshots.side_effect = LitpException(
                1, {'messages': [{'message': 'msg1'}, {'message': 'msg2'}]}
        )
        self.assertRaises(SystemExit, main, ['--action', 'create_snapshot',
                                             '--snap_type', 'litp'])

    @patch(TC_MODULE + '.LitpRestClient')
    def test_manage_litp_snapshots_restore(self, litp):
        litp.return_value.list_snapshots.return_value = ['snapshot']
        main(['--action', 'restore_snapshot',
              '--snap_type', 'litp'])
        self.assertTrue(litp.return_value.restore_snapshot.called)
        m_restore_snapshot = litp.return_value.restore_snapshot
        m_restore_snapshot.assert_has_calls(
                [call().remove_snapshot(force=False, name='snapshot')],
                any_order=True)
        self.assertTrue(litp.return_value.monitor_plan.called)

        litp.return_value.list_snapshots.return_value = []
        self.assertRaises(SystemExit, main, ['--action', 'restore_snapshot',
                                             '--snap_type', 'litp'])

        litp.return_value.list_snapshots.return_value = ['snap1']
        self.assertRaises(SystemExit, main, ['--action', 'restore_snapshot',
                                             '--snap_type', 'litp'])

        litp.return_value.list_snapshots.return_value = ['snap1']
        self.assertRaises(SystemExit, main, ['--action', 'restore_snapshot',
                                             '--snap_type', 'litp',
                                             '--snap_name', 'nosnap'])

    @patch(TC_MODULE + '.LitpRestClient')
    def test_manage_litp_snapshots_other(self, litp):
        self.assertRaises(SystemExit, main, ['--action', 'rrrestore_snapshot',
                                             '--snap_type', 'litp'])

    @patch(TC_MODULE + '.LitpSnapshots.list_snapshots')
    def test_manage_litp_snapshots_list(self, m_list_snapshots):
        main(['--action', 'list_snapshot',
              '--snap_type', 'litp'])
        m_list_snapshots.assert_has_calls([
            call('snapshot', detailed=False, force=False, verbose=False)]
        )

        m_list_snapshots.reset_mock()
        main(['--action', 'list_snapshot',
              '--snap_type', 'litp', '--detailed'])
        m_list_snapshots.assert_has_calls([
            call('snapshot', detailed=True, force=False, verbose=False)]
        )

        m_list_snapshots.reset_mock()
        main(['--action', 'list_snapshot',
              '--snap_type', 'litp', '--detailed', '--verbose'])
        m_list_snapshots.assert_has_calls([
            call('snapshot', detailed=True, force=False, verbose=True)]
        )

        m_list_snapshots.reset_mock()
        main(['--action', 'list_snapshot',
              '--snap_type', 'litp', '--force'])
        m_list_snapshots.assert_has_calls([
            call('snapshot', detailed=False, force=True, verbose=False)]
        )

    @patch(TC_MODULE + '.LitpSnapshots.validate_snapshots')
    def test_manage_litp_snapshots_validate(self, m_validate_snapshots):
        main(['--action', 'validate_snapshot',
              '--snap_type', 'litp'])
        m_validate_snapshots.assert_has_calls([
            call('snapshot', force=False, verbose=False)]
        )

        m_validate_snapshots.reset_mock()
        main(['--action', 'validate_snapshot',
              '--snap_type', 'litp', '--force'])
        m_validate_snapshots.assert_has_calls([
            call('snapshot', force=True, verbose=False)]
        )

        m_validate_snapshots.reset_mock()
        main(['--action', 'validate_snapshot',
              '--snap_type', 'litp', '--verbose'])
        m_validate_snapshots.assert_has_calls([
            call('snapshot', force=False, verbose=True)]
        )

    @patch(TC_MODULE + '.remove_migration_lockfile')
    @patch(TC_MODULE + '.remove_removed_blades_info_file')
    @patch(TC_MODULE + '.remove_snapshots_indicator_file')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.migrate_elasticsearch_indexes')
    def test_manage_all_snapshots_remove(self, es,  litp, lvm, san, sfs, enm,
                                         m_remove_snapshots_indicator_file,
                                         m_remove_removed_blades_info_file,
                                         m_remove_migration_lockfile):
        es.return_value = 0
        lvm.return_value.remove_snapshots = MagicMock()
        san.return_value.remove_snapshots = MagicMock()
        sfs.return_value.remove_snapshots = MagicMock()
        enm.return_value.neo4j_postsnapshots_remove = MagicMock()
        litp.return_value.list_snapshots.return_value = []
        main(['--action', 'remove_snapshot', '--snap_type', 'all'])
        self.assertFalse(litp.return_value.remove_snapshot.called)
        litp.return_value.list_snapshots.return_value = ['snapshot']
        main(['--action', 'remove_snapshot',
              '--snap_type', 'all', '--force'])
        self.assertTrue(litp.return_value.remove_snapshot.called)
        m_remove_snapshot = litp.return_value.remove_snapshot
        m_remove_snapshot.assert_has_calls(
                [
                    call().remove_snapshot(force=True, name='snapshot')
                ], any_order=True)

        litp.return_value.list_snapshots.return_value = ['snapshot1']
        self.assertRaises(SystemExit, main, ['--action', 'remove_snapshot',
                                             '--snap_type', 'all'])

        litp.return_value.list_snapshots.return_value = ['snapshot', 'snap1']
        main(['--action', 'remove_snapshot',
              '--snap_type', 'all'])
        self.assertTrue(litp.return_value.remove_snapshot.called)
        m_remove_snapshot = litp.return_value.remove_snapshot
        m_remove_snapshot.assert_has_calls(
                [
                    call().remove_snapshot(force=False, name='snap1')
                ], any_order=True)
        m_remove_snapshot.assert_has_calls(
                [
                    call().remove_snapshot(force=False, name='snapshot')
                ], any_order=True)
        self.assertTrue(lvm.return_value.remove_snapshots.called)
        self.assertTrue(sfs.return_value.remove_snapshots.called)
        self.assertTrue(san.return_value.remove_snapshots.called)
        self.assertTrue(enm.called)
        self.assertTrue(enm.return_value.neo4j_postsnapshots_remove.called)
        self.assertTrue(m_remove_snapshots_indicator_file.called)
        self.assertTrue(m_remove_migration_lockfile.called)

    @patch(TC_MODULE + '.EnmSnap.get_san_cred')
    @patch(TC_MODULE + '.EnmSnap.get_nas_cred')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.LitpSnapshots')
    def test_manage_all_snapshots_list(self, m_litp, lvm, san, sfs,
                                       m_get_nas_cred, m_get_san_cred):
        m_litp.return_value.list_snapshot_names.return_value = MagicMock()
        m_litp.return_value.list_snapshots.return_value = MagicMock()
        lvm.return_value.list_snapshots = MagicMock()
        san.return_value.list_snapshots = MagicMock()
        sfs.return_value.list_snapshots = MagicMock()
        main(['--action', 'list_snapshot',
              '--snap_type', 'all'])
        self.assertTrue(lvm.return_value.list_snapshots.called)
        self.assertTrue(sfs.return_value.list_snapshots.called)
        self.assertTrue(san.return_value.list_snapshots.called)
        self.assertTrue(m_litp.return_value.list_snapshot_names.called)
        self.assertTrue(m_litp.return_value.list_snapshots.called)

        m_litp.reset_mock()
        main(['--action', 'list_snapshot',
              '--snap_type', 'all', '--detailed'])
        self.assertTrue(lvm.return_value.list_snapshots.called)
        self.assertTrue(sfs.return_value.list_snapshots.called)
        self.assertTrue(san.return_value.list_snapshots.called)
        self.assertTrue(m_litp.return_value.list_snapshot_names.called)
        self.assertTrue(m_litp.return_value.list_snapshots.called)

        m_litp.reset_mock()
        main(['--action', 'list_snapshot',
              '--snap_type', 'all', '--detailed', '--verbose'])
        self.assertTrue(lvm.return_value.list_snapshots.called)
        self.assertTrue(sfs.return_value.list_snapshots.called)
        self.assertTrue(san.return_value.list_snapshots.called)
        self.assertTrue(m_litp.return_value.list_snapshot_names.called)
        self.assertTrue(m_litp.return_value.list_snapshots.called)

        m_litp.reset_mock()
        main(['--action', 'list_snapshot',
              '--snap_type', 'all', '--force'])
        self.assertTrue(lvm.return_value.list_snapshots.called)
        self.assertTrue(sfs.return_value.list_snapshots.called)
        self.assertTrue(san.return_value.list_snapshots.called)
        self.assertTrue(m_litp.return_value.list_snapshot_names.called)
        self.assertTrue(m_litp.return_value.list_snapshots.called)

    @patch('enm_snapshots.is_mount_option_migrated')
    @patch('enm_snapshots.create_blade_info_file')
    @patch('enm_snapshots.LVMSnapshots.create_snapshots')
    @patch('enm_snapshots.discover_vcs_clusters')
    @patch('enm_snapshots.LitpRestClient.is_plan_running')
    @patch('enm_snapshots.EnmSnap.check_puppet_catalog')
    @patch('enm_snapshots.EnmSnap.manage_lms_services')
    @patch('enm_snapshots.EnmSnap.get_nas_cred')
    @patch('enm_snapshots.EnmSnap.get_san_cred')
    @patch('enm_snapshots.get_logger')
    @patch('enm_snapshots.read_enminst_config')
    def test_enm_snapshots_vol_list_bkup_mixed_racks(self,
                                                     m_read_enminst_config,
                                                     m_get_logger,
                                                     m_get_san_cred,
                                                     m_get_nas_cred,
                                                     m_manage_lms_services,
                                                     m_check_puppet_catalog,
                                                     m_is_plan_running,
                                                     m_discover_vcs_clusters,
                                                     m_lvm_create_snapshots,
                                                     create_blade_info_file,
                                                     m_is_mount_option_migrated):
        # Test to ensure the backup vol list files get created
        m_is_mount_option_migrated.return_value = True
        tmpdir = join(gettempdir(), 'test_enm_snapshots_no_racks')
        if exists(tmpdir):
            shutil.rmtree(tmpdir)
        makedirs(tmpdir)
        m_read_enminst_config.return_value = {
            'enminst_runtime': tmpdir
        }

        m_get_san_cred.return_value = None
        m_get_nas_cred.return_value = None
        m_is_plan_running.return_value = False

        # Regression i.e. only blades in the deployment
        m_lvm_create_snapshots.return_value = (['vol_a', 'vol_b'], {})

        def assert_file_contents(file_path, contents):
            self.assertTrue(exists(file_path))
            with open(file_path, 'r') as _reader:
                self.assertEqual(contents, '\n'.join(_reader.readlines()))

        try:
            enm_snapshots.manage_enminst_snapshots('create_snapshot')
            assert_file_contents(join(tmpdir, 'lms_vol_list_bkup.txt'),
                                 '["vol_a", "vol_b"]')
            assert_file_contents(join(tmpdir, 'node_vol_list_bkup.txt'),
                                 '{}')

            # With racks in the deployment e.g. streaming
            m_lvm_create_snapshots.return_value = (['vol_a', 'vol_b'], {
                'node-1': ['fs_a'], 'node-2': ['fs_a']
            })
            enm_snapshots.manage_enminst_snapshots('create_snapshot')
            assert_file_contents(join(tmpdir, 'lms_vol_list_bkup.txt'),
                                 '["vol_a", "vol_b"]')
            assert_file_contents(join(tmpdir, 'node_vol_list_bkup.txt'),
                                 '{"node-1": ["fs_a"], "node-2": ["fs_a"]}')
        finally:
            if exists(tmpdir):
                shutil.rmtree(tmpdir)

    @patch('enm_snapshots.remove_migration_lockfile')
    @patch('enm_snapshots.EnmSnap.manage_lms_services')
    @patch('enm_snapshots.EnmSnap.poweroff_node')
    @patch('enm_snapshots.cleanup_blade_expansion')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('enm_snapshots.get_removed_blades_info_filename')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    @patch('enm_snapshots.VNXSnap')
    @patch('enm_snapshots.LVMSnapshots')
    @patch('enm_snapshots.migrate_elasticsearch_indexes')
    @patch('enm_snapshots.get_logger')
    @patch('enm_snapshots.EnmSnap.get_removed_node_cred')
    @patch('enm_snapshots.LVMSnapshots.create_snapshots')
    @patch('enm_snapshots.EnmSnap.get_nas_cred')
    @patch('enm_snapshots.EnmSnap.get_san_cred')
    @patch('enm_snapshots.read_enminst_config')
    def test_remove_snapshot_luns(self, m_read_enminst_config,
                                  m_get_san_cred, m_get_nas_cred,
                                  m_lvm_create_snapshots, node_cred,
                                  logger, es, lvs, vnx, m_file_exists_mock,
                                  removed_blades, litp_exists, cleanup,
                                  shutdown, lms_services,
                                  remove_migration_lockfile):
        tmpdir = join(gettempdir(), 'test_enm_snapshots_no_racks')
        fake_file = join(gettempdir(), 'removed_blades_file')
        if exists(tmpdir):
            shutil.rmtree(tmpdir)
        makedirs(tmpdir)
        with open(fake_file, 'w') as w:
            w.writelines(
                    '{"aut-1": {"cluster": "aut_cluster", "hostname": "ieatrcxb5850"}}')
            w.close()
        m_read_enminst_config.return_value = {
            'enminst_runtime': tmpdir
        }

        m_get_san_cred.return_value = "abc"
        m_get_nas_cred.return_value = None
        node_cred.return_value = "cats"
        es.return_value = 0
        vnx.return_value = MagicMock()
        vnx.return_value.remove_snapshots = MagicMock()
        m_file_exists_mock.return_value = True
        removed_blades.return_value = fake_file
        litp_exists.return_value = False

        m_lvm_create_snapshots.return_value = (['vol_a', 'vol_b'], {})

        enm_snapshots.manage_enminst_snapshots('remove_snapshot')
        cleanup.assert_has_calls([
            call().cleanup_blade_expansion(['aut-1'], [])
        ])

        self.assertTrue(shutdown.called)
        self.assertTrue(remove_migration_lockfile.called)

        lms_services.assert_has_calls([
            call().manage_lms_services('restart', ['httpd'])
        ])

    @patch('enm_snapshots.remove_migration_lockfile')
    @patch('enm_snapshots.EnmSnap.manage_lms_services')
    @patch('enm_snapshots.EnmSnap.poweroff_node')
    @patch('enm_snapshots.remove_cobbler_files')
    @patch('enm_snapshots.cleanup_blade_expansion')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('enm_snapshots.get_removed_blades_info_filename')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    @patch('enm_snapshots.VNXSnap')
    @patch('enm_snapshots.LVMSnapshots')
    @patch('enm_snapshots.migrate_elasticsearch_indexes')
    @patch('enm_snapshots.get_logger')
    @patch('enm_snapshots.EnmSnap.get_removed_node_cred')
    @patch('enm_snapshots.LVMSnapshots.create_snapshots')
    @patch('enm_snapshots.EnmSnap.get_nas_cred')
    @patch('enm_snapshots.EnmSnap.get_san_cred')
    @patch('enm_snapshots.read_enminst_config')
    def test_remove_snapshot_luns_exception(self, m_read_enminst_config,
                                            m_get_san_cred, m_get_nas_cred,
                                            m_lvm_create_snapshots, node_cred,
                                            logger, es, lvs, vnx,
                                            m_file_exists_mock,
                                            removed_blades,
                                            litp_exists, cleanup, cobbler,
                                            shutdown, lms_services,
                                            remove_migration_lockfile):

        tmpdir = join(gettempdir(), 'test_enm_snapshots_no_racks')
        fake_file = join(gettempdir(), 'removed_blades_file')
        if exists(tmpdir):
            shutil.rmtree(tmpdir)
        makedirs(tmpdir)
        with open(fake_file, 'w') as w:
            w.writelines('{"aut-1": {"cluster": "aut_cluster", '
                         '"hostname": "ieatrcxb5850"}}')
            w.close()
        m_read_enminst_config.return_value = {
            'enminst_runtime': tmpdir
        }

        m_get_san_cred.return_value = "abc"
        m_get_nas_cred.return_value = None
        node_cred.return_value = "cats"
        es.return_value = 0
        vnx.return_value = MagicMock()
        vnx.return_value.remove_snapshots = MagicMock()
        m_file_exists_mock.return_value = True
        removed_blades.return_value = fake_file
        litp_exists.return_value = False

        m_lvm_create_snapshots.return_value = (['vol_a', 'vol_b'], {})
        cobbler.side_effect = [IOError()]
        cleanup.side_effect = [IOError()]
        enm_snapshots.manage_enminst_snapshots('remove_snapshot')
        self.assertTrue(shutdown.called)
        self.assertTrue(lms_services.called)
        self.assertTrue(remove_migration_lockfile.called)

    @patch('enm_snapshots.delete_file')
    @patch('h_snapshots.lvm_snapshot.LVMSnapshots.is_migration')
    def test_remove_migration_lockfile(self, p_is_migration,
                                       p_del_file):
        enm_snapshots.remove_migration_lockfile()
        self.assertTrue(p_is_migration.called)
        self.assertTrue(p_del_file.called)

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_vxfenclearpre(self, m_run_rpc_command):
        litpd = LitpIntegration()
        litpd.setup_svc_cluster()
        litpd.setup_db_cluster(node_count=2)

        tmpdir = gettempdir()

        config = {
            'enminst_runtime': tmpdir
        }
        snapper = EnmSnap(config)
        snapper.litp = litpd

        m_run_rpc_command.side_effect = [
            {'db-1': {
                'errors': None,
                'data': {
                    'retcode': 0,
                    'out': '',
                    'err': ''
                }
            }}
        ]

        mco_hosts_called = []

        class EnminstAgentTest(EnminstAgent):
            def vxfenclearpre(self, node):
                mco_hosts_called.append(node)
                return super(EnminstAgentTest, self).vxfenclearpre(node)

        agent = EnminstAgentTest()

        with patch('enm_snapshots.EnminstAgent') as _mock:
            _mock.return_value = agent

            snapper.vxfenclearpre()

        self.assertEqual(1, len(mco_hosts_called))
        self.assertIn('db-1', mco_hosts_called)

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_vxfenclearpre_one_bad_host(self, m_run_rpc_command):
        litpd = LitpIntegration()
        litpd.setup_svc_cluster()
        litpd.setup_db_cluster(node_count=2)

        tmpdir = gettempdir()

        config = {
            'enminst_runtime': tmpdir
        }
        snapper = EnmSnap(config)
        snapper.litp = litpd

        m_run_rpc_command.side_effect = [
            {'db-1': {
                'errors': ['Some mco error'],
                'data': {
                    'retcode': 0,
                    'out': '',
                    'err': ''
                }
            }},
            {'db-2': {
                'errors': None,
                'data': {
                    'retcode': 0,
                    'out': '',
                    'err': ''
                }
            }}
        ]

        mco_hosts_called = []

        class EnminstAgentTest(EnminstAgent):
            def vxfenclearpre(self, node):
                mco_hosts_called.append(node)
                return super(EnminstAgentTest, self).vxfenclearpre(node)

        agent = EnminstAgentTest()

        with patch('enm_snapshots.EnminstAgent') as _mock:
            _mock.return_value = agent

            snapper.vxfenclearpre()

        self.assertEqual(2, len(mco_hosts_called))
        self.assertIn('db-1', mco_hosts_called)
        self.assertIn('db-2', mco_hosts_called)

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_vxfenclearpre_all_bad_hosts(self, m_run_rpc_command):
        litpd = LitpIntegration()
        litpd.setup_svc_cluster()
        litpd.setup_db_cluster(node_count=2)

        tmpdir = gettempdir()

        config = {
            'enminst_runtime': tmpdir
        }
        snapper = EnmSnap(config)
        snapper.litp = litpd

        m_run_rpc_command.side_effect = [
            {'db-1': {
                'errors': ['Some mco error'],
                'data': {
                    'retcode': 0,
                    'out': '',
                    'err': ''
                }
            }},
            {'db-2': {
                'errors': ['Some mco error'],
                'data': {
                    'retcode': 0,
                    'out': '',
                    'err': ''
                }
            }}
        ]

        mco_hosts_called = []

        class EnminstAgentTest(EnminstAgent):
            def vxfenclearpre(self, node):
                mco_hosts_called.append(node)
                return super(EnminstAgentTest, self).vxfenclearpre(node)

        agent = EnminstAgentTest()

        with patch('enm_snapshots.EnminstAgent') as _mock:
            _mock.return_value = agent
            with self.assertRaises(EnmSnapException) as exception:
                snapper.vxfenclearpre()

        self.assertIsNotNone(exception)
        self.assertEqual(2, len(mco_hosts_called))
        self.assertIn('db-1', mco_hosts_called)
        self.assertIn('db-2', mco_hosts_called)


class TestRedfishTool(unittest2.TestCase):
    preamble = '._toggle_power: '
    power_status_preamble = '.power_status: '
    login_preamble = 'login: '

    def setUp(self):
        self.redfishapi = Redfishtool()

    def tearDown(self):
        pass

    @staticmethod
    def read_data(filename):
        """
        open the file and reads data from
        the path specified in the arguments
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))
        path = os.path.join(os.path.join(parent_dir, 'Resources'), filename)
        with open(path, 'r') as f:
            return f.read()

    def get_mock_response(self, response_status, resource_text):
        """
        set the response with the provided arguments
        and return mocked response
        """
        response = MagicMock()
        response.status = response_status
        response.text = self.read_data(resource_text)
        if resource_text in ['invalid_parameter_response',
                             'response_with_error_message']:
            response.dict = json.loads(response.text)
        return response

    @patch('redfish.rest.v1.HttpClient')
    def test_valid_login(self, mock_redfish):
        """
        Validating the login functionality in a positive
        workflow when all the arguments are provided correctly
        """
        mock_client_instance = MagicMock()
        mock_redfish.return_value = mock_client_instance
        self.redfishapi.login('ilo', 'user', 'psw')
        mock_client_instance.login.assert_called_once_with()

    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_login_retries_exhausted_error(self, mock_redfish, log_mock):
        """
        Validating the login functionality in a negative
        workflow when retries exhausted error arises
        """
        excep_msg = "Max number of retries exhausted"
        mock_client_instance = MagicMock()
        mock_client_instance.login.side_effect = RetriesExhaustedError(excep_msg)
        mock_redfish.return_value = mock_client_instance
        self.assertRaises(RedfishToolException, self.redfishapi.login, 'ilo', 'user', 'psw')
        log_mock.error.assert_called_with(self.login_preamble + excep_msg)

    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_login_invalid_credentials_error(self, mock_redfish, log_mock):
        """
        Validating the login functionality in a positive
        workflow when the credentials is incorrect
        """
        excep_msg = "Invalid credentials provided for BMC"
        mock_client_instance = MagicMock()
        mock_client_instance.login.side_effect = redfish.rest.v1.InvalidCredentialsError(excep_msg)
        mock_redfish.return_value = mock_client_instance
        self.assertRaises(RedfishToolException, self.redfishapi.login, 'ilo', 'user', 'psw')
        log_mock.error.assert_called_with(self.login_preamble + excep_msg)

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_successful_poweron(self, mock_redfish, log_mock, login_mock):
        """
        Validating the toggle power functionality in a positive
        workflow when all the arguments are provided correctly
        """
        mocked_response = self. \
            get_mock_response(200, 'success_response')
        mock_redfish.post.return_value = mocked_response
        login_mock.return_value = mock_redfish
        response = self.redfishapi.toggle_power('ilo', 'user', 'psw', 'On')
        self.assertEqual(response, mocked_response.status)
        log_mock.debug.assert_called_with(self.preamble +
                                          "Power On Outcome: Success")

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_retries_exhausted_error(self, mock_redfish, log_mock, login_mock):
        """
        Validating the toggle power functionality when the number of
        retries exhausted
        """
        excep_msg = "Max number of retries exhausted"
        login_mock.return_value = mock_redfish
        mock_redfish.post.side_effect = RetriesExhaustedError(excep_msg)
        self.assertRaises(RedfishToolException, self.redfishapi.toggle_power, 'ilo', 'user', 'psw', 'On')
        log_mock.error.assert_called_with(self.preamble + excep_msg)

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_decompress_error(self, mock_redfish, log_mock, login_mock):
        """
        Validating the toggle power functionality when the number of
        retries exhausted
        """
        excep_msg = "Decompressing response failed."
        login_mock.return_value = mock_redfish
        mock_redfish.post.side_effect = DecompressResponseError(excep_msg)
        self.assertRaises(RedfishToolException, self.redfishapi.toggle_power, 'ilo', 'user', 'psw', 'On')
        log_mock.error.assert_called_with(self.preamble + excep_msg)

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_invalid_parameter(self, mock_redfish, log_mock, login_mock):
        """
        Validating the toggle power functionality when an invalid
        parameter is passed as an argument
        """
        mock_redfish.post.return_value = self. \
            get_mock_response(400, 'invalid_parameter_response')
        login_mock.return_value = mock_redfish
        self.assertRaises(RedfishToolException,
                          self.redfishapi.toggle_power, 'ilo', 'user', 'psw', 'On')
        log_mock.error.assert_called_with(self.preamble +
                                          "Power On Outcome: Failure,"
                                          " status:400 :"
                                          " 'Base.1.0."
                                          "ActionNotSupported'")

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_invalid_session(self, mock_redfish, log_mock, login_mock):
        """
        Validating the toggle power functionality when a session
        becomes invalid
        """
        mock_redfish.post.return_value = self. \
            get_mock_response(401, 'invalid_parameter_response')
        login_mock.return_value = mock_redfish
        self.assertRaises(RedfishToolException,
                          self.redfishapi.toggle_power, 'ilo', 'user', 'psw', 'On')
        log_mock.error.assert_called_with(self.preamble +
                                          "Power On Outcome: Failure,"
                                          " status:401 :"
                                          " 'Base.1.0."
                                          "ActionNotSupported'")

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_get_successful_powerstatus(self, mock_redfish, log_mock, login_mock):
        """
        Validating the retrieval of power status functionality in a positive
        workflow when all the arguments are provided correctly
        """
        mock_redfish.get.return_value = self. \
            get_mock_response(200, 'power_status_success_response')
        login_mock.return_value = mock_redfish
        self.assertTrue(self.redfishapi.power_status('ilo', 'user', 'psw'))
        log_mock.debug.assert_called_with(self.power_status_preamble +
                                          "Get Power Status: Success")

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    @patch("json.loads")
    def test_get_successful_powerstatus_non_utf8_encoding(
            self, loads_mock, mock_redfish, log_mock, login_mock):
        """
        Validating the retrieval of power status functionality in a positive
        workflow when all the arguments are provided correctly
        """
        mock_redfish.get.return_value = self. \
            get_mock_response(200, 'power_status_success_response')
        login_mock.return_value = mock_redfish
        loads_mock.side_effect = [
            UnicodeDecodeError("utf8", "", 12, 14, "invalid continuation byte"),
            {"PowerState": "On"}]
        self.assertTrue(self.redfishapi.power_status('ilo', 'user', 'psw'))
        log_mock.warn.assert_called_with("Problem decoding power status response: 'utf8' "
                                         "codec can't decode bytes in position 12-13: "
                                         "invalid continuation byte")
        log_mock.debug.assert_called_with(self.power_status_preamble +
                                          "Get Power Status: Success")

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_get_unsuccessful_powerstatus(self, mock_redfish, log_mock, login_mock):
        """
        Validating the retrieval of power status functionality in a positive
        workflow when all the arguments are provided correctly
        """
        mock_redfish.get.return_value = self. \
            get_mock_response(200, 'power_status_unsuccessful_response')
        login_mock.return_value = mock_redfish
        self.assertFalse(self.redfishapi.power_status('ilo', 'user', 'psw'))
        log_mock.debug.assert_called_with(self.power_status_preamble +
                                          "Get Power Status: Success")

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_get_powerstatus_invalid_parameter(self, mock_redfish, log_mock, login_mock):
        """
        Validating the power status functionality when an invalid
        parameter is passed as an argument
        """
        mock_redfish.get.return_value = self. \
            get_mock_response(400, 'invalid_parameter_response')
        login_mock.return_value = mock_redfish
        self.assertRaises(RedfishToolException,
                          self.redfishapi.power_status, 'ilo', 'user', 'psw')
        log_mock.error.assert_called_with(self.power_status_preamble +
                                          "Power Status Outcome: Failure, "
                                          "status:400 : "
                                          "'Base.1.0.ActionNotSupported'")

    @patch(TC_UTIL_MODULE + '.Redfishtool.login')
    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_get_powerstatus_invalid_session(self, mock_redfish, log_mock, login_mock):
        """
        Validating the toggle power functionality when a session
        becomes invalid
        """
        mock_redfish.get.return_value = self. \
            get_mock_response(401, 'invalid_parameter_response')
        login_mock.return_value = mock_redfish
        self.assertRaises(RedfishToolException,
                          self.redfishapi.power_status, 'ilo', 'user', 'psw')
        log_mock.error.assert_called_with(self.power_status_preamble +
                                          "Power Status Outcome: Failure, "
                                          "status:401 : "
                                          "'Base.1.0.ActionNotSupported'")

    def test_get_error_message_with_id(self):
        """
        Validating the get_error_message functionality when the response
        object contains only message id
        """
        response = self.get_mock_response(401,
                                          'invalid_parameter_response')
        message = self.redfishapi.get_error_message(response)
        self.assertEqual(message, "Base.1.0.ActionNotSupported")

    def test_get_error_message_with_message(self):
        """
        Validating the get_error_message functionality when the response
        object contains the actual message
        """
        response = self.get_mock_response(401,
                                          'response_with_error_message')
        message = self.redfishapi.get_error_message(response)
        self.assertEqual(message, "Base Action Not Supported")

    @patch('redfish.rest.v1.HttpClient')
    def test_valid_logout(self, mock_redfish):
        """
        Validating the logout functionality in a positive
        workflow when all the arguments are provided correctly
        """
        self.redfishapi.logout(mock_redfish)
        mock_redfish.logout.assert_called_once_with()

    @patch(TC_UTIL_MODULE + '.LOG')
    @patch('redfish.rest.v1.HttpClient')
    def test_logout_bad_request_error(self, mock_redfish, log_mock):
        """
        Validating the logout functionality for bad request error case
        """
        excep_msg = "Bad request error. Invalid session resource"
        mock_redfish.logout.side_effect = BadRequestError(excep_msg)
        self.redfishapi.logout(mock_redfish)
        mock_redfish.logout.assert_called_once_with()
        log_mock.error.assert_called_with("log out :" + excep_msg)

    @patch('os.path')
    @patch('os.access')
    def test_redfish_cloud_tool_exec(self, mock_os_path, mock_access):
        """
        Validating when Redfish tool path file exist and is accessible.
        """
        mock_os_path.isfile.return_value = True
        mock_access.return_value = True
        self.assertTrue(self.redfishapi.is_cloud_env())

    @patch('os.path')
    def test_redfish_no_cloud_tool(self, mock_os_path):
        """
        Validating when Redfish tool file doesn't exist.
        """
        mock_os_path.isfile.return_value = False
        self.assertFalse(self.redfishapi.is_cloud_env())

    @patch('os.access')
    @patch('os.path')
    def test_redfish_cloud_tool_no_exec(self, mock_os_path, mock_access):
        """
        Validating when Redfish tool path file exist but is not accessible.
        """
        mock_os_path.isfile.return_value = True
        mock_access.return_value = False
        self.assertFalse(self.redfishapi.is_cloud_env())

    @patch('os.path')
    def test_redfish_cloud_tool_exception(self, mock_os_path):
        """
        Validating when Redfish tool path resource throw an exception.
        """
        mock_os_path.isfile.side_effect = OSError
        self.assertFalse(self.redfishapi.is_cloud_env())

    @patch('os.path')
    @patch('os.access')
    def test_redfish_cloud_adapter(self, mock_os_path, mock_access):
        """
        Validating cloud adapter invocation
        """
        mock_os_path.isfile.return_value = True
        mock_access.return_value = True
        self.assertTrue(self.redfishapi.is_cloud_env())

        sys.modules['redfishtool'] = MagicMock()

        with patch('imp.load_source') as module:
            cloud_adapter_mock = MagicMock()
            module.return_value = cloud_adapter_mock
            self.redfishapi.login('ilo', 'user', 'psw')
            self.assertTrue(module.called)


class TestDecryptor(unittest2.TestCase):
    def setUp(self):
        self.location = mktemp()
        self.security = mktemp()
        self.pass_file = mktemp()

    def tearDown(self):
        if os.path.exists(self.location):
            os.remove(self.location)

        if os.path.exists(self.security):
            os.remove(self.security)

        if os.path.exists(self.pass_file):
            os.remove(self.pass_file)

    def make_file(self, file_name, content):
        with open(file_name, 'w') as f:
            f.write(content)
            f.write('\n')

    def encrypt(self, key, text):
        enc = AES.new(key, AES.MODE_CFB, '0' * AES.block_size,
                      segment_size=128)
        secret = enc.encrypt(text)
        return standard_b64encode(secret)

    def test_get_key_and_password_files(self):
        self.make_file(self.security, sec_conf_file)

        dec = Decryptor()
        dec.SECURITY_CONF_FILE_PATH = self.security
        keyf, passf = dec.get_key_and_password_files()
        self.assertEqual(keyf, '/path/key')
        self.assertEqual(passf, '/path/password')

    def test_decrypt(self):
        key_phrase = 'alabala-portocal'
        self.make_file(self.location, standard_b64encode(key_phrase))
        text = 'something stupid'
        secret = self.encrypt(key_phrase, text)

        dec = Decryptor()
        answer = dec.decrypt(self.location, secret)
        self.assertEqual(answer, text)

    def test_get_password(self):
        password = 'my_secret_passwd'
        key_phrase = 'alabala-portocal'
        secret = self.encrypt(key_phrase, password)
        self.make_file(self.location, standard_b64encode(key_phrase))
        self.make_file(self.pass_file, '[service]\nuser={0}\n'.format(secret))

        def side_effect():
            return self.location, self.pass_file

        dec = Decryptor()
        dec.get_key_and_password_files = side_effect
        got_pass = dec.get_password('service', 'user')
        self.assertEqual(got_pass, password)

    def test_read_key(self):
        phrase = 'alabala'
        self.make_file(self.location, standard_b64encode(phrase))

        dec = Decryptor()
        key = dec.read_key(self.location)
        self.assertEqual(key, phrase)

    @patch(TC_MODULE + '.is_mount_option_migrated')
    @patch(TC_MODULE + '.discover_vcs_clusters')
    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.init_enminst_logging')
    @patch('import_iso.umount')
    @patch('import_iso.mount')
    def test_exit_interrupted_create(self, umnt, mnt, iel, litp,
                                     m_snapper, lvm, vnx, sfs,
                                     m_discover_vcs_clusters,
                                     m_is_mount_option_migrated):
        m_is_mount_option_migrated.return_value = True
        messages = []

        def log(log_message):
            print log_message
            messages.append(log_message)

        iel.return_value = MagicMock()
        iel.return_value.info = log
        iel.return_value.error = log
        iel.return_value.warning = log

        action = 'create_snapshot'

        litp.return_value.is_plan_running.return_value = False

        sys.argv = ['--action', action]

        sfs.return_value.create_snapshots.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main(sys.argv)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)
        self.assertIn(
                enm_snapshots.ITRP_MSG[action], messages)

        sfs.reset_mock()
        del messages[:]
        sfs.return_value.create_snapshots.side_effect = IOError()
        self.assertRaises(SystemExit, main, sys.argv)
        self.assertNotIn(
                enm_snapshots.ITRP_MSG[action], messages)

    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.LitpRestClient')
    def test_exit_interrupted_list(self, litp, m_snapper, lvm, vnx, sfs):
        action = 'list_snapshot'

        sys.argv = ['--action', action]

        sfs.return_value.list_snapshots.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main(sys.argv)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        sfs.reset_mock()
        sfs.return_value.list_snapshots.side_effect = IOError()
        self.assertRaises(IOError, main, sys.argv)

    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.init_enminst_logging')
    @patch(TC_MODULE + '.migrate_elasticsearch_indexes')
    def test_exit_interrupted_remove(self, es, iel, litp, m_snap, lvm, vnx,
                                     sfs):
        messages = []

        def log(log_message):
            print log_message
            messages.append(log_message)

        es.return_value = 0
        iel.return_value = MagicMock()
        m_snap.return_value.neo4j_postsnapshots_remove = MagicMock()
        iel.return_value.info = log
        iel.return_value.error = log
        iel.return_value.warning = log

        action = 'remove_snapshot'

        sys.argv = ['--action', action]

        sfs.return_value.remove_snapshots.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main(sys.argv)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)
        self.assertTrue(m_snap.return_value.neo4j_postsnapshots_remove.called)
        self.assertIn(
                enm_snapshots.ITRP_MSG[action], messages)

        sfs.reset_mock()
        del messages[:]
        sfs.return_value.remove_snapshots.side_effect = IOError()
        self.assertRaises(SystemExit, main, sys.argv)
        self.assertNotIn(
                enm_snapshots.ITRP_MSG[action], messages)

    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.init_enminst_logging')
    @patch(TC_MODULE + '.clear_and_unmount')
    @patch('import_iso.mount')
    @patch('import_iso.umount')
    @patch('enm_snapshots.check_removed_blades_info_file_exists')
    @patch('enm_snapshots.get_removed_blades_info_filename')
    def test_exit_interrupted_restore(self, get_info_file, m_file_exists,
                                      umnt, mnt, cau, iel,
                                      litp, m_snapper, lvm, vnx,
                                      sfs):
        messages = []

        def log(log_message):
            print log_message
            messages.append(log_message)

        iel.return_value = MagicMock()
        iel.return_value.info = log
        iel.return_value.error = log
        iel.return_value.warning = log
        m_file_exists.return_value = True
        get_info_file.return_value = os.path.join(gettempdir(),
                                                  'removed_blades_info')
        fake_file = join(gettempdir(), 'removed_blades_info')
        data_in_file = {'svc-1': {'cluster': 'svc_cluster',
                                  'hostname': 'ieatrcxb5850',
                                  'username': 'root',
                                  'iloaddress': '10.32.231.108',
                                  'password': 'psw'}}
        with open(fake_file, 'w') as _w:
            _w.write(dumps(data_in_file))
            _w.close()

        action = 'restore_snapshot'
        litp.return_value.is_plan_running.return_value = False

        sys.argv = ['--action', action]

        sfs.return_value.restore_snapshots.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main(sys.argv)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)
        self.assertIn(
                enm_snapshots.ITRP_MSG[action], messages)

        sfs.reset_mock()
        del messages[:]
        sfs.return_value.restore_snapshots.side_effect = IOError()
        self.assertRaises(IOError, main, sys.argv)
        self.assertNotIn(
                enm_snapshots.ITRP_MSG[action], messages)

    @patch(TC_MODULE + '.SfsSnapshots')
    @patch(TC_MODULE + '.VNXSnap')
    @patch(TC_MODULE + '.LVMSnapshots')
    @patch(TC_MODULE + '.EnmSnap')
    @patch(TC_MODULE + '.LitpRestClient')
    def test_exit_interrupted_validate(self, litp, m_snapper, lvm, vnx, sfs):
        sys.argv = ['--action', 'validate_snapshot']

        sfs.return_value.validate.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main(sys.argv)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        sfs.reset_mock()
        sfs.return_value.validate.side_effect = IOError()
        self.assertRaises(IOError, main, sys.argv)

    @patch(TC_MODULE + '.sleep')
    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.get_logger')
    @patch(TC_MODULE + '.kill_processes_dir')
    @patch('import_iso.umount')
    def test_clear_and_unmount(self, umnt, kpd, glog, execproc, slp):
        umnt.side_effect = IOError()
        self.assertRaises(IOError, enm_snapshots.clear_and_unmount, 'path')
        self.assertEqual(glog.call_count, 9)
        self.assertEqual(execproc.call_count, 6)
        self.assertEqual(slp.call_count, 2)
        self.assertEqual(kpd.call_count, 2)

        glog.reset_mock()
        execproc.reset_mock()
        slp.reset_mock()
        kpd.reset_mock()
        umnt.side_effect = [IOError(), None]
        enm_snapshots.clear_and_unmount('path')
        self.assertEqual(glog.call_count, 4)
        self.assertEqual(execproc.call_count, 2)
        self.assertEqual(slp.call_count, 1)
        self.assertEqual(kpd.call_count, 1)

    @patch(TC_MODULE + '.run_agent')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.get_logger')
    @patch(TC_MODULE + '.gethostname')
    def test_set_device_timeout_option(self, m_gethostname, m_get_logger,
                                           m_exec_proc, m_litp, m_run_agent):

        m_litp.get_cluster_nodes.return_value = MOCK_CLUSTER_NODES
        m_litp.ITEM_STATE_INITIAL = 'Initial'
        m_gethostname.return_value = 'ms-1'

        def m_exec_proc_side_effect (*args, **kwargs):
            if args[0] == ["/usr/bin/grep 'x-systemd.device-timeout=300' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp"] or \
               args[0] == ["/usr/bin/grep 'x-systemd.device-timeout=300' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ieatrcxb3565.pp"]:
                return 'x-systemd.device-timeout=300'
            else:
                return ''

        m_exec_proc.side_effect = m_exec_proc_side_effect
        enm_snapshots.set_device_timeout_option(m_litp)
        self.assertEqual(m_exec_proc.call_count, 8)

        expected_calls = [call(['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ieatrcxb3565.pp'], ignore_error=True, use_shell=True),
call(['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp'], ignore_error=True, use_shell=True),
call(['sed -i.bak -e \'s/^\\( *options => "defaults\\)", *$/\\1,x-systemd.device-timeout=300",/g\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ieatrcxb3565.pp'], use_shell=True),
call(["/usr/bin/grep 'x-systemd.device-timeout=300' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ieatrcxb3565.pp"], ignore_error=True, use_shell=True),
call(['sed -i.bak -e \'s/^\\( *options => "defaults\\)", *$/\\1,x-systemd.device-timeout=300",/g\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp'], use_shell=True),
call(["/usr/bin/grep 'x-systemd.device-timeout=300' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp"], ignore_error=True, use_shell=True),
call(['mco  rpc puppetcache clean -I ms-1'], use_shell=True),
call(['rm -f /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/*.pp.bak'], use_shell=True)]
        m_exec_proc.assert_has_calls(expected_calls, False)
        self.assertEqual(m_run_agent.call_count, 1)
        expected_calls = [call(['ieatrcxb3565', 'ms-1'], 'puppet', 'disable')]
        m_run_agent.assert_has_calls(expected_calls, False)

    @patch(TC_MODULE + '.run_agent')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.get_logger')
    @patch(TC_MODULE + '.gethostname')
    def test_device_timeout_option_set_already(self, m_gethostname,
                                                 m_get_logger,
                                                 m_exec_proc,
                                                 m_litp, m_run_agent):

        m_litp.get_cluster_nodes.return_value = MOCK_CLUSTER_NODES
        m_litp.ITEM_STATE_INITIAL = 'Initial'
        m_gethostname.return_value = 'ms-1'
        m_exec_proc.return_value = 'x-systemd.device-timeout=300'
        enm_snapshots.set_device_timeout_option(m_litp)
        self.assertEqual(m_exec_proc.call_count, 2)
        expected_calls = [call(['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ieatrcxb3565.pp'], ignore_error=True, use_shell=True),
                          call(['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp'], ignore_error=True, use_shell=True)]
        m_exec_proc.assert_has_calls(expected_calls, False)

    @patch(TC_MODULE + '.run_agent')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.get_logger')
    @patch(TC_MODULE + '.gethostname')
    def test_set_device_timeout_option_SExit(self, m_gethostname,
                                                 m_get_logger,
                                                 m_exec_proc,
                                                 m_litp,
                                                 m_run_agent):

        m_litp.get_cluster_nodes.return_value = MOCK_CLUSTER_NODES
        m_litp.ITEM_STATE_INITIAL = 'Initial'
        m_gethostname.return_value = 'ms-1'
        m_run_agent.return_value =  MagicMock()

        def m_exec_proc_side_effect (*args, **kwargs):
            if args[0] == ['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp'] or\
               args[0] == ['/usr/bin/grep \'x-systemd.device-timeout=300\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp']:
                    return ''
            else:
                return 'x-systemd.device-timeout=300'

        m_exec_proc.side_effect = m_exec_proc_side_effect
        self.assertRaises(SystemExit,
                    enm_snapshots.set_device_timeout_option, m_litp)

        self.assertEqual(m_exec_proc.call_count, 4)
        expected_calls = [call(['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ieatrcxb3565.pp'], ignore_error=True, use_shell=True),
 call(['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp'], ignore_error=True, use_shell=True),
 call(['sed -i.bak -e \'s/^\\( *options => "defaults\\)", *$/\\1,x-systemd.device-timeout=300",/g\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp'], use_shell=True),
 call(["/usr/bin/grep 'x-systemd.device-timeout=300' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp"], ignore_error=True, use_shell=True)]
        m_exec_proc.assert_has_calls(expected_calls, True)

        expected_calls = [call(['ms-1'], 'puppet', 'disable'),
                          call(['ms-1'], 'puppet', 'enable')]
        m_run_agent.assert_has_calls(expected_calls, False)

        m_run_agent.reset_mock()
        m_exec_proc.reset_mock()
        m_run_agent.side_effect = SystemExit()

        self.assertRaises(SystemExit,
                    enm_snapshots.set_device_timeout_option, m_litp)

        self.assertEqual(m_exec_proc.call_count, 2)
        expected_calls = [call(['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ieatrcxb3565.pp'], ignore_error=True, use_shell=True),
 call(['/usr/bin/grep \'options => "defaults\' /opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms-1.pp'], ignore_error=True, use_shell=True)]
        m_exec_proc.assert_has_calls(expected_calls, True)


if __name__ == '__main__':
    unittest2.main()

