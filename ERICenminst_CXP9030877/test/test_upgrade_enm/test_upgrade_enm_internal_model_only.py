import os
import shutil

from mock import Mock, patch
from os import environ, makedirs
from os.path import join, exists, isdir
from StringIO import StringIO
from tempfile import gettempdir
from unittest2 import TestCase

import upgrade_enm_internal_model_only as ug_model

from h_litp.litp_utils import LitpException


SED = """
# DB1
db_node1_IP=10.45.225.64
db_node1_hostname=atrcxb2195
db_node1_domain=athtem.eei.ericsson.se
db_node1_IP_storage=10.42.233.29
db_node1_IP_backup=10.248.1.21
db_node1_IP_internal=192.110.0.90
db_node1_IP_jgroups=192.110.1.90
db_node1_iloUsername=root
db_node1_iloPassword=shroot12
db_node1_ilo_IP=10.36.49.170
db_node1_eth0_macaddress=44:1e:a1:45:d2:90
db_node1_eth1_macaddress=44:1e:a1:45:d2:94
db_node1_eth2_macaddress=44:1e:a1:45:d2:91
db_node1_eth3_macaddress=44:1e:a1:45:d2:95
db_node1_WWPN1=50:01:43:80:12:0b:38:64
db_node1_WWPN2=50:01:43:80:12:0b:38:66
db_node1_vcProfile=ENM_ME_db_node
db_node1_serial=CZ3204768D
"""

# LITP value different to SED
PATH_ETH1 = '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth1'
ETH1 = 'FF:FF:FF:FF:FF:ED'
SED_ETH = 'db_node1_eth1_macaddress'
SED_WWPN = 'db_node1_WWPN1'

def get_unchanged_items(path):
    if path == '/infrastructure/systems/db-1_system/controllers/hba1':
        return {u'properties': {u'hba_porta_wwn': '50:01:43:80:12:0b:38:64',
                u'failover_mode': u'std'}}
    elif path == '/infrastructure/systems/db-1_system/controllers/hba2':
        return {u'properties': {u'hba_porta_wwn': '50:01:43:80:12:0b:38:66',
                u'failover_mode': u'std'}}
    elif path == '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth0':
        return {u'properties': {u'macaddress': '44:1e:a1:45:d2:90',
                u'master': u'bond0', u'device_name': u'eth0'}}
    elif path == '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth1':
        return {u'properties': {u'macaddress': '44:1e:a1:45:d2:94',
                u'master': u'bond0', u'device_name': u'eth1'}}
    elif path == '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth2':
        return {u'properties': {u'macaddress': '44:1e:a1:45:d2:91',
                u'master': u'bond0', u'device_name': u'eth2'}}
    elif path == '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth3':
        return {u'properties': {u'macaddress': '44:1e:a1:45:d2:95',
                u'master': u'bond0', u'device_name': u'eth3'}}
    else:
        raise ValueError('invalid property')


def get_changed_items(path):
    if path == '/infrastructure/systems/db-1_system/controllers/hba1':
        return {u'properties': {u'hba_porta_wwn': '50:01:43:80:12:0b:38:aa',
                u'failover_mode': u'std'}}
    elif path == '/infrastructure/systems/db-1_system/controllers/hba2':
        return {u'properties': {u'hba_porta_wwn': '50:01:43:80:12:0b:38:66',
                u'failover_mode': u'std'}}
    elif path == '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth0':
        return {u'properties': {u'macaddress': '44:1e:a1:45:d2:aa',
                u'master': u'bond0', u'device_name': u'eth0'}}
    elif path == '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth1':
        return {u'properties': {u'macaddress': '44:1e:a1:45:d2:94',
                u'master': u'bond0', u'device_name': u'eth1'}}
    elif path == '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth2':
        return {u'properties': {u'macaddress': '44:1e:a1:45:d2:91',
                u'master': u'bond0', u'device_name': u'eth2'}}
    elif path == '/deployments/enm/clusters/db_cluster/nodes/db-1/network_interfaces/eth3':
        return {u'properties': {u'macaddress': '44:1e:a1:45:d2:95',
                u'master': u'bond0', u'device_name': u'eth3'}}
    else:
        raise ValueError('invalid property')


class TestENMUpgradeInternalModelOnly(TestCase):
    def write_file(self, location, contents):
        with open(location, 'w') as _f:
            _f.writelines(contents)

    def setUp(self):
        self.tmpdir = join(gettempdir(), 'TestSed')
        if not exists(self.tmpdir):
            makedirs(self.tmpdir)
        self.tmp_sed = join(self.tmpdir, 'tmp_sed')
        self.write_file(self.tmp_sed, SED)
        environ['ENMINST_RUNTIME'] = gettempdir()

        wwpn_filter = ug_model.WWPN_FILTER
        wwpn_path = ug_model.WWPN_PATH
        mac_filter = ug_model.MAC_FILTER
        mac_path = ug_model.MAC_PATH

        self.wwpn_rule = ug_model.SedLitpMappingRule(
            wwpn_filter, wwpn_path, 'hba_porta_wwn', ignore_case=True)
        self.mac_rule = ug_model.SedLitpMappingRule(
            mac_filter, mac_path, 'macaddress', ignore_case=True)
        self.filter_rules = (self.wwpn_rule, self.mac_rule)

    def tearDown(self):
        del os.environ['ENMINST_RUNTIME']
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    @patch('sys.stdout', new_callable=StringIO)
    def test_upgrade_enm_internal_model_no_sed_arg(self, mock_print):
        msg = 'Usage:  blah <path to SED>\n'

        self.assertRaises(SystemExit, ug_model.update_litp, ['blah'])
        self.assertEquals(mock_print.getvalue(), msg)

    @patch('upgrade_enm_internal_model_only.init_enminst_logging')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_upgrade_enm_internal_model_no_updates_necessary(self,
                                                             rest_get,
                                                             iel):
        # setup
        info_mock = Mock()
        log_mock = Mock()
        iel.return_value = log_mock
        log_mock.info = info_mock
        script_name = "upgrade_enm_internal_model_only.py"
        args = [script_name, self.tmp_sed]
        rest_get.side_effect = get_unchanged_items

        # test
        self.assertRaises(SystemExit, ug_model.update_litp, args)

        # verify
        info_mock.assert_called_with('No items require updating.  Exiting')

    @patch('upgrade_enm_internal_model_only.init_enminst_logging')
    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_upgrade_enm_internal_model_updates_necessary(self,
                                                          rest_get,
                                                          rest_update,
                                                          iel):
        # setup
        info_mock = Mock()
        log_mock = Mock()
        iel.return_value = log_mock
        log_mock.info = info_mock
        script_name = "upgrade_enm_internal_model_only.py"
        args = [script_name, self.tmp_sed]
        rest_get.side_effect = get_changed_items

        # test
        self.assertRaises(SystemExit, ug_model.update_litp, args)

        # verify
        info_mock.assert_called_with("Script %s completed successfully", script_name)

    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_check_litp_updater_rollback(self,
                                            rest_get,
                                            rest_update):
        # setup
        rollback1 = ('litp update -p /infrastructure/systems/db-1_system/'
                    'controllers/hba1 -o hba_porta_wwn=50:01:43:80:12:0b:38:aa')
        rollback2 = ('litp update -p /deployments/enm/clusters/db_cluster/'
                    'nodes/db-1/network_interfaces/eth0'
                    ' -o macaddress=44:1e:a1:45:d2:aa')
        rollback_values = [rollback1, rollback2]

        rest_get.side_effect = get_changed_items

        # test
        litp_updater = ug_model.LitpUpdater(self.tmp_sed, self.filter_rules)
        litp_updater.check_litp_for_updates()
        litp_updater.update_litp_items()

        # verify
        self.assertEquals(len(litp_updater.rollback), len(rollback_values))
        self.assertEquals(litp_updater.rollback.sort(), rollback_values.sort())

    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_check_litp_for_updates_failure(self, rest_get):
        rest_get.side_effect = LitpException('not found')
        litp_updater = ug_model.LitpUpdater(self.tmp_sed, self.filter_rules)
        self.assertRaises(LitpException, litp_updater.check_litp_for_updates)

    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_update_litp_items_success(self, rest_get, rest_update):
        # setup
        rest_get.side_effect = get_changed_items

        # test
        litp_updater = ug_model.LitpUpdater(self.tmp_sed,
                                            self.filter_rules)
        litp_updater.check_litp_for_updates()
        for_update = litp_updater.get_items_by_states(
                                ug_model.LitpPropertyItem.STATE_FOR_UPDATE)

        litp_updater.update_litp_items()

        # verify
        updates = litp_updater.get_items_by_states(
                                ug_model.LitpPropertyItem.STATE_UPDATED)
        unchanged = litp_updater.get_items_by_states(
                                ug_model.LitpPropertyItem.STATE_IDENTICAL)

        self.assertEquals(for_update, updates)
        # 2 updates out of 6, both successful
        self.assertEquals(len(updates), 2)
        self.assertEquals(len(unchanged), 4)
        self.assertEquals(len(litp_updater.rollback), 2)

    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_update_litp_items_failure(self, rest_get, rest_update):
        # setup
        rest_get.side_effect = get_changed_items
        rest_update.side_effect = [None, LitpException]

        # test
        litp_updater = ug_model.LitpUpdater(self.tmp_sed, self.filter_rules)
        litp_updater.check_litp_for_updates()
        self.assertRaises(LitpException, litp_updater.update_litp_items)

        # verify
        updates = litp_updater.get_items_by_states(
                                    ug_model.LitpPropertyItem.STATE_UPDATED)
        unchanged = litp_updater.get_items_by_states(
                                    ug_model.LitpPropertyItem.STATE_IDENTICAL)

        # 1 of 2 updates ok out of 6 candidates.   So only one to rollback
        self.assertEquals(len(updates), 1)
        self.assertEquals(len(unchanged), 4)
        self.assertEquals(len(litp_updater.rollback), 1)

    def test_sed_litp_mapping_rule_wwpns(self):
        expected_path = '/infrastructure/systems/db-1_system/controllers/hba1'

        wwpn_path = self.wwpn_rule.get_litp_path(SED_WWPN)
        self.assertEquals(wwpn_path, expected_path)

    def test_sed_litp_mapping_rule_mac(self):
        mac_path = self.mac_rule.get_litp_path(SED_ETH)
        self.assertEquals(mac_path, PATH_ETH1)

    def test_sed_litp_mapping_rule_incorrect_key(self):
        self.assertRaises(ValueError, self.wwpn_rule.get_litp_path, 'blah')

    def test_litp_property_item_ignore_case(self):
        item = ug_model.LitpPropertyItem(SED_ETH,
                                         PATH_ETH1,
                                         'macaddress',
                                         ETH1.upper(),
                                         ignore_case=True)
        comp = ETH1.lower()
        self.assertTrue(item.equals(comp))

    def test_litp_property_item__case_senstive(self):
        item = ug_model.LitpPropertyItem(SED_ETH,
                                         PATH_ETH1,
                                         'macaddress',
                                         ETH1.upper(),
                                         ignore_case=False)
        comp = ETH1.lower()
        self.assertFalse(item.equals(comp))
