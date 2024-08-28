import httplib
import time
from json import dumps

import unittest2
from mock import MagicMock
from mock import patch, ANY

from clean_san_luns import SanCleanup, NavisecCliException, teardown_san, \
    poweroff_node, poweron_node
from h_litp.litp_rest_client import LitpException
from test_h_litp.test_h_litp_rest_client import setup_mock as setup_litp_mock
from sanapiinfo import StorageGroupInfo, HbaInitiatorInfo, HluAluPairInfo
from sanapiexception import SanApiException

enm_get = {
    '_embedded': {'item': [{'item-type-name': 'collection-of-cluster-base',
                            'applied_properties_determinable': True,
                            'state': 'Applied',
                            '_links': {'self': {
                                'href': 'https://localhost:9999/litp/rest/v1/deployments/enm/clusters'},
                                'collection-of': {
                                    'href': 'https://localhost:9999/litp/rest/v1/item-types/cluster-base'}},
                            'id': 'clusters'}]},
    'item-type-name': 'deployment', 'applied_properties_determinable': True,
    'state': 'Applied',
    '_links': {'self': {
        'href': 'https://localhost:9999/litp/rest/v1/deployments/enm'},
        'item-type': {
            'href': 'https://localhost:9999/litp/rest/v1/item-types/deployment'}},
    'id': 'enm'}

dep_get_child = [
    {'path': '/deployments/enm',
     'data': {'item-type-name': 'deployment',
              'applied_properties_determinable': True,
              'state': 'Applied', '_links': {'self': {
             'href': 'https://localhost:9999/litp/rest/v1/deployments/enm'},
             'item-type': {
                 'href': 'https://localhost:9999/litp/rest/v1/item-types/deployment'}},
              'id': 'enm'}}]

san_emc_find = [
    {'_embedded': {
        'item': [{'item-type-name': 'collection-of-storage-container',
                  'applied_properties_determinable': True, 'state': 'Applied',
                  '_links': {'self': {
                      'href': 'https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/san1/storage_containers'},
                      'collection-of': {
                          'href': 'https://localhost:9999/litp/rest/v1/item-types/storage-container'}},
                  'id': 'storage_containers'}]}, 'id': 'san1',
        'item-type-name': 'san-emc',
        'applied_properties_determinable': True, 'state': 'Applied',
        '_links': {'self': {
            'href': 'https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/san1'},
            'item-type': {
                'href': 'https://localhost:9999/litp/rest/v1/item-types/san-emc'}},
        'properties': {'username': 'admin', 'name': 'ieatvnx-72',
                       'storage_network': 'storage',
                       'storage_site_id': 'enm17', 'login_scope': 'global',
                       'ip_a': '10.151.32.49',
                       'ip_b': '10.151.32.50', 'san_type': 'vnx2',
                       'password_key': 'key-for-san-ieatvnx-72'}}]

cluster_ids_get_child = [
    {'path': '/deployments/enm/clusters/svc_cluster',
     'data': {'id': 'svc_cluster', 'item-type-name': 'vcs-cluster',
              'applied_properties_determinable': True, 'state': 'Applied',
              '_links': {'self': {
                  'href': 'https://localhost:9999/litp/rest/v1/deployments/enm/clusters/svc_cluster'},
                  'item-type': {
                      'href': 'https://localhost:9999/litp/rest/v1/item-types/vcs-cluster'}},
              'properties': {'low_prio_net': 'services',
                             'default_nic_monitor': 'mii',
                             'cluster_type': 'vcs',
                             'ha_manager': 'vcs',
                             'llt_nets': 'heartbeat1,heartbeat2',
                             'cluster_id': '235'}}},
    {'path': '/deployments/enm/clusters/db_cluster',
     'data': {'id': 'db_cluster', 'item-type-name': 'vcs-cluster',
              'applied_properties_determinable': True,
              'state': 'Applied', '_links': {'self': {
             'href': 'https://localhost:9999/litp/rest/v1/deployments/enm/clusters/db_cluster'},
             'item-type': {
                 'href': 'https://localhost:9999/litp/rest/v1/item-types/vcs-cluster'}},
              'properties': {'low_prio_net': 'services',
                             'default_nic_monitor': 'mii',
                             'cluster_type': 'sfha', 'ha_manager': 'vcs',
                             'llt_nets': 'heartbeat1,heartbeat2',
                             'cluster_id': '1127'}}}]

nodes_get_child = [
    {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1',
     'data': {'id': 'svc-1', 'item-type-name': 'node',
              'applied_properties_determinable': True,
              'state': 'Applied', '_links': {'self': {
             'href': 'https://localhost:9999/litp/rest/v1/deployments/enm/clusters/svc_cluster/nodes/svc-1'},
             'item-type': {
                 'href': 'https://localhost:9999/litp/rest/v1/item-types/node'}},
              'properties': {'is_locked': 'false',
                             'hostname': 'ieatrcxb3845-1'}}}]


class TestBladePowerManagement(unittest2.TestCase):
    @patch('clean_san_luns.Redfishtool.toggle_power')
    @patch('clean_san_luns.Redfishtool.power_status')
    def test_poweroff_nodes_SystemExit(self, power_status, poweroff):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.22', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.23', 'db2_user', 'db2_password']}
        # Given that a node is powered on
        power_status.return_value = True
        # When the poweroff is called and the node is not powering off after
        # x attempts
        poweroff.return_value = 400
        # Then a System exit gets raised
        self.assertRaises(SystemExit, poweroff_node, sys_bmc, 'db-1')

    @patch('clean_san_luns.Redfishtool.toggle_power')
    @patch('clean_san_luns.Redfishtool.power_status')
    def test_poweroff_not_called_when_node_is_off(self, power_status, poweroff):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.8', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.9', 'db2_user', 'db2_password']}
        # Given a blade that is already powered off
        power_status.return_value = False
        # When power off is called
        poweroff_node(sys_bmc, 'db-1')
        # Then no redfish poweroff commands get fired.
        assert not poweroff.called

    @patch('clean_san_luns.Redfishtool.toggle_power')
    @patch('clean_san_luns.Redfishtool.power_status')
    def test_poweroff_nodes(self, power_status, poweroff):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.6', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.7', 'db2_user', 'db2_password']}
        # Given a server that is powered on
        power_status.return_value = True
        poweroff.return_value = 200
        # When power off is called
        poweroff_node(sys_bmc, 'db-1')
        # Then it powers off the node
        poweroff.assert_called_with('10.10.10.6', 'db1_user', 'db1_password', 'ForceOff')

    @patch('clean_san_luns.Redfishtool.toggle_power')
    @patch('clean_san_luns.Redfishtool.power_status')
    def test_poweron_nodes_SystemExit(self, power_status, poweron):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.20', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.21', 'db2_user', 'db2_password']}
        # Given a node that is powered off
        power_status.return_value = False
        # When the power on node is called and node is still off after
        #  x retries
        poweron.return_value = 400
        # Then a SystemExit is raised
        self.assertRaises(SystemExit, poweron_node, sys_bmc, 'db-1')

    @patch('clean_san_luns.Redfishtool.toggle_power')
    @patch('clean_san_luns.Redfishtool.power_status')
    def test_poweron_not_called_when_node_is_on(self, power_status, poweron):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.10', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.11', 'db2_user', 'db2_password']}

        # Given a node that is already powered on
        power_status.return_value = True
        # When the poweron_node gets called
        poweron_node(sys_bmc, 'db-1')
        # Then power on redfish commands should not have been called
        assert not poweron.called

    @patch('clean_san_luns.Redfishtool.toggle_power')
    @patch('clean_san_luns.Redfishtool.power_status')
    def test_power_on_nodes(self, power_status, poweron):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.31', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.32', 'db2_user', 'db2_password']}
        # Given a node that is powered off
        power_status.return_value = False
        poweron.return_value = 200
        # When poweron_node gets called
        poweron_node(sys_bmc, 'db-1')
        # Then it powers on the node
        poweron.assert_called_with('10.10.10.31', 'db1_user', 'db1_password', 'On')

    @patch('clean_san_luns.exec_process')
    @patch('clean_san_luns.Redfishtool.power_status')
    def test_power_on_nodes_with_teardown_p(self, power_status, exec_process):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.31', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.32', 'db2_user', 'db2_password']}
        exec_process.return_value = 'ProLiant DL360 Gen9'
        power_status.return_value = True
        node_on = poweron_node(sys_bmc, 'db-1', True)
        self.assertEqual(node_on, True)

    @patch('clean_san_luns.exec_process')
    @patch('clean_san_luns.Redfishtool.toggle_power')
    @patch('clean_san_luns.Redfishtool.power_status')
    def test_power_on_nodes_with_teardown_n(self, power_status, poweron,
                                            exec_p):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.31', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.32', 'db2_user', 'db2_password']}
        power_status.return_value = False
        exec_p.return_value = 'ProLiant DL360 Gen9'
        poweron.return_value = 200
        node_on = poweron_node(sys_bmc, 'db-1', True)
        self.assertEqual(node_on, False)

    @patch('clean_san_luns.exec_process')
    def test_power_on_nodes_with_teardown_vapp(self, exec_process):
        time.sleep = MagicMock()
        sys_bmc = {'db-1': ['10.10.10.31', 'db1_user', 'db1_password'],
                   'db-2': ['11.11.11.32', 'db2_user', 'db2_password']}
        exec_process.return_value = "VMware Virtual Platform"
        node_on = poweron_node(sys_bmc, 'db-1', True)
        self.assertEqual(node_on, True)


class TestSanCleanup(unittest2.TestCase):
    def setUp(self):
        super(TestSanCleanup, self).setUp()

    def tearDown(self):
        super(TestSanCleanup, self).tearDown()

    @patch('clean_san_luns.get_nas_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_children')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_find_items(self, rest_get, rest_child, m_get_nas_type):
        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        rest_get.return_value = enm_get
        rest_child.side_effect = [dep_get_child, []]
        output = sc.find_items('test_path', 'deployment', [])
        self.assertTrue(rest_get.called)
        self.assertTrue(rest_child.called)
        self.assertEqual(output[0]['id'], 'enm')

        rest_get.side_effect = LitpException(1)
        self.assertRaises(LitpException, sc.find_items, 'test_path',
                          'deployment', [])

        rest_get.side_effect = LitpException(404)
        output = sc.find_items('test_path', 'deployment', [])
        self.assertEqual(output, [])

    @patch('clean_san_luns.get_nas_type')
    @patch('litp.core.base_plugin_api.BasePluginApi.get_password')
    @patch('clean_san_luns.SanCleanup.find_items')
    def test_get_san_info(self, find_item, get_pass, m_get_nas_type):
        find_item.return_value = san_emc_find
        get_pass.return_value = 'test_pass'
        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        san_info = sc.get_san_info()
        self.assertDictEqual(
                san_info, {'san1': ['10.151.32.49', '10.151.32.50', 'enm17',
                                    'global', 'vnx2', 'admin', 'test_pass']})

    @patch('clean_san_luns.get_nas_type')
    def test_build_sg_names(self, m_get_nas_type):
        sc = SanCleanup()
        m_get_nas_type.return_value = ''

        getc_deploy = {'_embedded': {'item': [{'id': 'enm'}]}}
        getc_clstr = {'_embedded': {'item': [{'id': 'svc_cluster'},
                                             {'id': 'db_cluster'}]}}
        strc_nodes = {'_embedded': {'item': [
            {'id': 'svc-1',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'ieatrcxb3845-1'},
             '_links': {'self': {'href': '/litp/rest/v1/deployment/enm/'
                                         'clusters/svc_cluster/nodes/svc-1'}}}
        ]}}
        dbc_nodes = {'_embedded': {'item': [
            {'id': 'db-1',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'ieatrcxb3846-1'},
             '_links': {'self': {'href': '/litp/rest/v1/deployment/enm/'
                                         'clusters/db_cluster/nodes/db-1'}}}
        ]}}
        setup_litp_mock(sc.rest, [
            ['GET', dumps(getc_deploy), httplib.OK],
            ['GET', dumps(getc_clstr), httplib.OK],
            ['GET', dumps(strc_nodes), httplib.OK],
            ['GET', dumps(dbc_nodes), httplib.OK],
        ])

        sg_names = sc.build_sg_names()
        self.assertEqual(2, len(sg_names))
        self.assertIn('ieatrcxb3845-1', sg_names)
        self.assertDictEqual(sg_names['ieatrcxb3845-1'], {
            'deployment': 'enm',
            'cluster_name': 'svc_cluster',
            'node_id': 'svc-1'
        })
        self.assertIn('ieatrcxb3846-1', sg_names)
        self.assertDictEqual(sg_names['ieatrcxb3846-1'], {
            'deployment': 'enm',
            'cluster_name': 'db_cluster',
            'node_id': 'db-1'
        })

    @patch('clean_san_luns.get_nas_type')
    @patch('litp.core.base_plugin_api.BasePluginApi.get_password')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('clean_san_luns.SanCleanup.find_items')
    def test_get_sys_bmc(self, find_item, get, get_pass, m_get_nas_type):
        find_item.return_value = [{'properties': {'system_name': 'svc-1'}}]
        get.return_value = {'properties': {'password_key': 'test_key',
                                           'username': 'test_user',
                                           'ipaddress': '11.1.1.1'}}
        get_pass.return_value = 'test_pass'
        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        sys_bmc = sc.get_sys_bmc()
        self.assertDictEqual(sys_bmc, {'svc-1': ['11.1.1.1', 'test_user',
                                                 'test_pass']})

    @patch('clean_san_luns.get_nas_type')
    def test_delete_luns(self, m_get_nas_type):
        san_api = MagicMock()
        all_luns = ['1']
        sc = SanCleanup()
        m_get_nas_type.return_value = ''

        san_api.get_lun.return_value.type = 'StoragePool'
        deleted_luns = sc.delete_luns(san_api, all_luns)
        san_api.delete_lun.assert_called_with(
            lun_id='1',
            array_specific_options='-destroySnapshots -forceDetach')
        self.assertEqual(deleted_luns, ['1'])

        san_api.get_lun.return_value.type = 'RaidGroup'
        deleted_luns = sc.delete_luns(san_api, all_luns)
        san_api.delete_lun.assert_called_with(lun_id='1')
        self.assertEqual(deleted_luns, ['1'])

        san_api.delete_lun.side_effect = SanApiException
        deleted_luns = sc.delete_luns(san_api, all_luns)
        self.assertEqual(deleted_luns, [])

    @patch('clean_san_luns.get_nas_type')
    @patch('clean_san_luns.exec_process')
    def test_clean_navi_certs(self, mock_exec_process,
                              m_get_nas_type):
        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        sc.clean_navi_certs()
        self.assertEqual(mock_exec_process.call_count, 2)
        mock_exec_process.assert_any_call(
            'export HOME=/; /opt/Navisphere/bin/naviseccli '
            'security -certificate -cleanup', use_shell=True)
        mock_exec_process.assert_any_call(
            'export HOME=/root; /opt/Navisphere/bin/naviseccli '
            'security -certificate -cleanup', use_shell=True)

        # simulate failure of naviseccli cert cleanup command
        mock_exec_process.side_effect = [IOError]
        self.assertRaises(NavisecCliException, sc.clean_navi_certs)

    @patch('clean_san_luns.get_nas_type')
    def test_delete_unity_luns(self, m_get_nas_type):
        san_api = MagicMock()
        all_luns = ['1', '2']
        san_api.get_snapshots.return_value = []
        san_api.delete_lun.return_value = True

        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        deleted_luns = sc.delete_unity_luns(san_api, all_luns)
        self.assertEqual(deleted_luns, ['1', '2'])

        san_api.delete_lun.side_effect = [True, SanApiException]
        deleted_luns = sc.delete_unity_luns(san_api, all_luns)
        self.assertEqual(deleted_luns, ['1'])

    @patch('clean_san_luns.get_nas_type')
    def test_delete_unity_snapshots(self, m_get_nas_type):
        san_api = MagicMock()
        all_luns = ['1']
        snap1_obj = MagicMock()
        snap1_obj.snap_name = 'snap1'
        snap1_obj.resource_id = '1'
        san_api.get_snapshots.return_value = [snap1_obj]

        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        sc.delete_unity_snapshots(san_api, all_luns)
        san_api.delete_snapshot.assert_called_with('snap1')

    @patch('clean_san_luns.get_nas_type')
    @patch('clean_san_luns.SanCleanup.find_items')
    def test_delete_unity_pool(self, find_item, m_get_nas_type):
        san_api = MagicMock()
        pool1_obj = MagicMock()
        pool1_obj.sp_name = 'pool_1'
        pool1_obj.sp_id = 'pool_1'
        san_api.get_storage_pool.return_value = [pool1_obj]
        find_item.return_value = [{'properties':
                                  {'type': 'POOL', 'name': 'pool_1'}}]

        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        sc.delete_unity_pool(san_api)
        san_api.delete_storage_pool.assert_called_with('pool_1')

    @patch('clean_san_luns.get_nas_type')
    @patch('clean_san_luns.SanCleanup.find_items')
    def test_get_data_luns(self, find_item, m_get_nas_type):
        find_item.return_value = [{'properties':
                                  {'lun_name': 'test1', 'name': 'sdb',
                                   'storage_container': 'TEST1'}}]
        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        luns = sc.get_data_luns()
        self.assertEqual(['test1'], luns)

    @patch('clean_san_luns.get_nas_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_deployment_clusters')
    @patch('clean_san_luns.SanCleanup.find_items')
    def test_get_fencing_disks(self, find_item, clusters, m_get_nas_type):
        clusters.return_value = {'enm': ['db_cluster']}
        find_item.return_value = [
            {'properties': {'lun_name': 'test1', 'name': 'sdb',
                            'storage_container': 'TEST1'}
             }]
        sc = SanCleanup()
        m_get_nas_type.return_value = ''
        luns = sc.get_fencing_disks()
        self.assertEqual(['test1'], luns)

    @patch('clean_san_luns.is_env_on_rack')
    @patch('clean_san_luns.get_nas_type')
    @patch('clean_san_luns.poweron_node')
    @patch('clean_san_luns.poweroff_node')
    @patch('sanapi.VnxCommonApi.disconnect_host')
    @patch('sanapi.VnxCommonApi.deregister_hba_uid')
    @patch('sanapi.VnxCommonApi.remove_luns_from_storage_group')
    @patch('sanapi.VnxCommonApi.get_luns')
    @patch('sanapi.VnxCommonApi.get_storage_groups')
    @patch('sanapi.VnxCommonApi.delete_storage_group')
    @patch('sanapi.api_builder')
    @patch('clean_san_luns.SanCleanup')
    @patch('logging.getLogger')
    def test_teardown_san(self, log, cleanup, san_api, del_sg, get_sg,
                          get_luns, rem_luns, dereg_hba, disc_host, power_off,
                          power_on, m_get_nas_type, m_is_env_on_rack):
        log.return_value = MagicMock()
        san_info = {'san1': ['10.151.32.49', '10.151.32.50', 'enm17',
                             'global', 'vnx2', 'admin', 'test_pass']}
        sys_bmc = {'svc-1': ['11.1.1.1', 'test_user', 'test_pass']}
        sg_names = {'ieatrcxb3845-1': {'deployment': 'enm',
                                       'cluster_name': 'svc_cluster',
                                       'node_id': 'svc-1'}}

        hba1 = HbaInitiatorInfo('00:00', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('11:11', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '2')
        hlu2 = HluAluPairInfo('2', '4')

        sgp2 = StorageGroupInfo('enm17-enm-svc_cluster-svc-1', 'uid', True,
                                [hba1, hba2], [hlu1, hlu2])

        lun1_obj = MagicMock()
        lun2_obj = MagicMock()
        lun1_obj.name = 'lun1'
        lun2_obj.name = 'lun2'
        lun1_obj.id = '2'
        lun2_obj.id = '4'

        cleanup.return_value.get_san_info.return_value = san_info
        cleanup.return_value.get_sys_bmc.return_value = sys_bmc
        cleanup.return_value.build_sg_names.return_value = sg_names
        cleanup.return_value.get_data_luns.return_value = \
            ['lun1', 'lun2']
        cleanup.return_value.get_fencing_disks.return_value = []

        m_get_nas_type.return_value = ''

        m_is_env_on_rack.return_value = ''

        # No SGs and no LUNS to delete
        get_sg.return_value = []
        get_luns.return_value = []
        teardown_san()
        get_sg.assert_called_with()
        get_luns.assert_called_with()
        cleanup.return_value.clean_navi_certs.assert_called_with()

        # VNX - delete SGs and LUNs
        get_sg.return_value = [sgp2]
        del_sg.return_value = True
        get_luns.return_value = [lun1_obj, lun2_obj]
        cleanup.return_value.delete_luns.return_value = ['2', '4']

        teardown_san()
        power_off.assert_called_with(sys_bmc, 'svc-1')
        disc_host.assert_called_with('enm17-enm-svc_cluster-svc-1',
                                     'ieatrcxb3845-1')
        rem_luns.assert_called_with('enm17-enm-svc_cluster-svc-1',
                                    [hlu1, hlu2])
        del_sg.assert_called_with('enm17-enm-svc_cluster-svc-1')
        power_on.assert_called_with(sys_bmc, 'svc-1')
        get_luns.assert_called_with()
        cleanup.return_value.delete_luns.assert_called_with(ANY, ['2', '4'])
        cleanup.return_value.clean_navi_certs.assert_called_with()

        # Failed to delete one LUN
        cleanup.return_value.delete_luns.return_value = ['2']
        self.assertRaises(SystemExit, teardown_san)

        # Call delete_luns even if there are no SGs defined on SAN
        get_sg.return_value = []
        cleanup.return_value.delete_luns.return_value = ['2', '4']

        teardown_san()
        power_off.assert_called_with(sys_bmc, 'svc-1')
        power_on.assert_called_with(sys_bmc, 'svc-1')
        del_sg.assert_called_with('enm17-enm-svc_cluster-svc-1')
        get_luns.assert_called_with()
        cleanup.return_value.delete_luns.assert_called_with(ANY, ['2', '4'])

    @patch('clean_san_luns.is_env_on_rack')
    @patch('clean_san_luns.get_nas_type')
    @patch('clean_san_luns.poweron_node')
    @patch('clean_san_luns.poweroff_node')
    @patch('sanapi.VnxCommonApi.disconnect_host')
    @patch('sanapi.VnxCommonApi.deregister_hba_uid')
    @patch('sanapi.VnxCommonApi.remove_luns_from_storage_group')
    @patch('sanapi.VnxCommonApi.get_luns')
    @patch('sanapi.VnxCommonApi.get_storage_groups')
    @patch('sanapi.VnxCommonApi.delete_storage_group')
    @patch('sanapi.api_builder')
    @patch('clean_san_luns.SanCleanup')
    @patch('logging.getLogger')
    def test_teardown_san_sg_has_no_hba_or_lun(self, log, cleanup, san_api,
                                               del_sg, get_sg, get_luns,
                                               rem_luns, dereg_hba, disc_host,
                                               power_off, power_on,
                                               m_get_nas_type, m_is_env_on_rack):
        log.return_value = MagicMock()
        san_info = {'san1': ['10.151.32.49', '10.151.32.50', 'enm17',
                             'global', 'vnx2', 'admin', 'test_pass']}
        sys_bmc = {'svc-1': ['11.1.1.1', 'test_user', 'test_pass']}
        sg_names = {'ieatrcxb3845-1': {'deployment': 'enm',
                                       'cluster_name': 'svc_cluster',
                                       'node_id': 'svc-1'}}

        sgp2 = StorageGroupInfo('enm17-enm-svc_cluster-svc-1', 'uid', True,
                                None, None)

        lun1_obj = MagicMock()
        lun2_obj = MagicMock()
        lun1_obj.name = 'lun1'
        lun2_obj.name = 'lun2'
        lun1_obj.id = '2'
        lun2_obj.id = '4'

        cleanup.return_value.get_san_info.return_value = san_info
        cleanup.return_value.get_sys_bmc.return_value = sys_bmc
        cleanup.return_value.build_sg_names.return_value = sg_names
        cleanup.return_value.get_data_luns.return_value = \
            ['lun1', 'lun2']
        cleanup.return_value.get_fencing_disks.return_value = []

        m_get_nas_type.return_value = ''

        m_is_env_on_rack.return_value = ''

        # No SGs and no LUNS to delete
        get_sg.return_value = []
        get_luns.return_value = []
        teardown_san()
        get_sg.assert_called_with()
        rem_luns.assert_not_called()
        get_luns.assert_called_with()
        cleanup.return_value.clean_navi_certs.assert_called_with()

        # VNX - delete SGs and LUNs
        get_sg.return_value = [sgp2]
        del_sg.return_value = True
        get_luns.return_value = [lun1_obj, lun2_obj]
        cleanup.return_value.delete_luns.return_value = ['2', '4']

        teardown_san()
        power_off.assert_called_with(sys_bmc, 'svc-1')
        disc_host.assert_called_with('enm17-enm-svc_cluster-svc-1',
                                     'ieatrcxb3845-1')
        del_sg.assert_called_with('enm17-enm-svc_cluster-svc-1')
        power_on.assert_called_with(sys_bmc, 'svc-1')
        rem_luns.assert_not_called()
        get_luns.assert_called_with()
        cleanup.return_value.delete_luns.assert_called_with(ANY, ['2', '4'])
        cleanup.return_value.clean_navi_certs.assert_called_with()

        # Failed to delete one LUN
        cleanup.return_value.delete_luns.return_value = ['2']
        self.assertRaises(SystemExit, teardown_san)

        # Call delete_luns even if there are no SGs defined on SAN
        get_sg.return_value = []
        cleanup.return_value.delete_luns.return_value = ['2', '4']

        teardown_san()
        power_off.assert_called_with(sys_bmc, 'svc-1')
        power_on.assert_called_with(sys_bmc, 'svc-1')
        del_sg.assert_called_with('enm17-enm-svc_cluster-svc-1')
        rem_luns.assert_not_called()
        get_luns.assert_called_with()
        cleanup.return_value.delete_luns.assert_called_with(ANY, ['2', '4'])

    @patch('clean_san_luns.is_env_on_rack')
    @patch('clean_san_luns.get_nas_type')
    @patch('clean_san_luns.poweron_node')
    @patch('clean_san_luns.poweroff_node')
    @patch('sanapi.UnityApi.disconnect_host')
    @patch('sanapi.UnityApi.get_luns')
    @patch('sanapi.UnityApi.get_storage_groups')
    @patch('sanapi.UnityApi.delete_storage_group')
    @patch('sanapi.api_builder')
    @patch('clean_san_luns.SanCleanup')
    @patch('logging.getLogger')
    def test_teardown_san_unity(self, log, cleanup, san_api, del_sg, get_sg,
                                get_luns, disc_host, power_off, power_on,
                                m_get_nas_type, m_is_env_on_rack):
        log.return_value = MagicMock()
        san_info = {'san1': ['10.151.32.49', '10.151.32.50', 'enm16',
                             'global', 'unity', 'admin', 'test_pass']}

        sys_bmc = {'svc-1': ['11.1.1.1', 'test_user', 'test_pass']}
        sg_names = {'ieatrcxb3845-1': {'deployment': 'enm',
                                       'cluster_name': 'svc_cluster',
                                       'node_id': 'svc-1'}}
        san_info = {'san1': ['10.151.32.49', '10.151.32.50', 'enm16',
                             'global', 'unity', 'admin', 'test_pass']}

        hba1 = HbaInitiatorInfo('00:00', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('11:11', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '2')
        hlu2 = HluAluPairInfo('2', '4')
        sgp1 = StorageGroupInfo('enm16-enm-svc_cluster-svc-1', 'uid', True,
                                [hba1, hba2], [hlu1, hlu2])

        lun1_obj = MagicMock()
        lun2_obj = MagicMock()
        lun1_obj.name = 'lun1'
        lun2_obj.name = 'lun2'
        lun1_obj.id = '2'
        lun2_obj.id = '4'

        cleanup.return_value.get_san_info.return_value = san_info
        cleanup.return_value.get_sys_bmc.return_value = sys_bmc
        cleanup.return_value.build_sg_names.return_value = sg_names
        cleanup.return_value.get_data_luns.return_value = \
            ['lun1', 'lun2']
        cleanup.return_value.get_fencing_disks.return_value = []

        get_sg.return_value = [sgp1]
        del_sg.return_value = True
        get_luns.return_value = [lun1_obj, lun2_obj]
        cleanup.return_value.delete_unity_luns.return_value = ['2', '4']

        m_get_nas_type.return_value = ''

        m_is_env_on_rack.return_value = ''

        teardown_san()
        power_off.assert_called_with(sys_bmc, 'svc-1')
        disc_host.assert_called_with('enm16-enm-svc_cluster-svc-1',
                                     'ieatrcxb3845-1')
        del_sg.assert_called_with('enm16-enm-svc_cluster-svc-1')
        get_luns.assert_called_with()
        cleanup.return_value.delete_unity_snapshots.assert_called_with(
            ANY, ['2', '4'])
        cleanup.return_value.delete_unity_luns.assert_called_with(ANY,
                                                                  ['2', '4'])

    @patch('clean_san_luns.is_env_on_rack')
    @patch('clean_san_luns.get_nas_type')
    @patch('clean_san_luns.poweron_node')
    @patch('clean_san_luns.poweroff_node')
    @patch('sanapi.UnityApi.disconnect_host')
    @patch('sanapi.UnityApi.get_luns')
    @patch('sanapi.UnityApi.get_storage_groups')
    @patch('sanapi.UnityApi.delete_storage_group')
    @patch('sanapi.api_builder')
    @patch('clean_san_luns.SanCleanup')
    @patch('logging.getLogger')
    def test_teardown_san_exclude_fs(self, log, cleanup, san_api, del_sg, get_sg,
                                get_luns, disc_host, power_off, power_on,
                                m_get_nas_type, m_is_env_on_rack):
        log.return_value = MagicMock()
        san_info = {'san1': ['10.151.32.49', '10.151.32.50', 'enm16',
                             'global', 'unity', 'admin', 'test_pass']}

        sys_bmc = {'svc-1': ['11.1.1.1', 'test_user', 'test_pass']}
        sg_names = {'ieatrcxb3845-1': {'deployment': 'enm',
                                       'cluster_name': 'svc_cluster',
                                       'node_id': 'svc-1'}}

        hba1 = HbaInitiatorInfo('00:00', 'blah', 'blah')
        hba2 = HbaInitiatorInfo('11:11', 'blah', 'blah')

        hlu1 = HluAluPairInfo('1', '2')
        hlu2 = HluAluPairInfo('2', '4')
        sgp1 = StorageGroupInfo('enm16-enm-svc_cluster-svc-1', 'uid', True,
                                [hba1, hba2], [hlu1, hlu2])

        lun1_obj = MagicMock()
        lun2_obj = MagicMock()
        lun1_obj.name = 'lun1'
        lun2_obj.name = 'lun2'
        lun1_obj.id = '2'
        lun2_obj.id = '4'

        cleanup.return_value.get_san_info.return_value = san_info
        cleanup.return_value.get_sys_bmc.return_value = sys_bmc
        cleanup.return_value.build_sg_names.return_value = sg_names
        cleanup.return_value.get_data_luns.return_value = \
            ['lun1', 'lun2']
        cleanup.return_value.get_fencing_disks.return_value = []

        get_sg.return_value = [sgp1]
        del_sg.return_value = True
        get_luns.return_value = [lun1_obj, lun2_obj]
        cleanup.return_value.delete_unity_luns.return_value = ['2', '4']

        cleanup.return_value.nas_type_name = 'unityxt'
        m_is_env_on_rack.return_value = True

        teardown_san()
        self.assertTrue(cleanup.return_value.delete_unity_pool.called)

        cleanup.return_value.reset_mock()
        teardown_san('excluded_fs')
        self.assertFalse(cleanup.return_value.delete_unity_pool.called)