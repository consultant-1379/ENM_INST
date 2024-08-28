import os
import shutil
from genericpath import exists
from os import remove
from os.path import join
from tempfile import gettempdir

from mock import patch, MagicMock, call
from unittest2 import TestCase

from h_litp.litp_rest_client import LitpObject, LitpRestClient
from h_puppet.mco_agents import McoAgentException
from h_util.h_utils import ExitCodes
from h_vcs.vcs_cli import Vcs, main
from h_vcs.vcs_utils import VCS_GRP_SVS_STATE_ONLINE, \
    VCS_AVAIL_ACTIVE_STANDBY, VCS_AVAIL_PARALLEL, VcsException, \
    filter_groups_by_state, VcsCodes, VcsStates, VCS_GRP_SVS_STATE_OFFLINE, \
    VCS_AVAIL_STANDALONE, VCS_NA
from litpd import LitpIntegration
from test_h_litp.test_h_litp_rest_client import get_node_json

m_clusters = {'c1': ['svc-1', 'svc-2']}
CDATA_GP_PAR_OK = {
    'type': VCS_AVAIL_PARALLEL,
    'global': {'Frozen': '0', 'TFrozen': '0'},
    'systems': {
        'svc-1': {'state': ['ONLINE'], 'uptime': '-1'},
        'svc-2': {'state': ['ONLINE'], 'uptime': '-1'}}
}

CDATA_GP_PAR_3NODES_OK = {
    'type': VCS_AVAIL_PARALLEL,
    'global': {'Frozen': '0', 'TFrozen': '0'},
    'systems': {
        'db-2': {'state': ['ONLINE'], 'uptime': '-1'},
        'db-3': {'state': ['ONLINE'], 'uptime': '-1'},
        'db-4': {'state': ['ONLINE'], 'uptime': '-1'}}
}

CDATA_GP_AS_INVALID = {
    'type': VCS_AVAIL_ACTIVE_STANDBY,
    'global': {'Frozen': '0', 'TFrozen': '0'},
    'systems': {
        'svc-1': {'state': ['OFFLINE'], 'uptime': '-1'},
        'svc-2': {'state': ['OFFLINE'], 'uptime': '-1'}}
}

CDATA_GP_AS_OK = {
    'type': VCS_AVAIL_ACTIVE_STANDBY,
    'global': {'Frozen': '0', 'TFrozen': '0'},
    'systems': {
        'svc-1': {'state': ['ONLINE'], 'uptime': '-1'},
        'svc-2': {'state': ['OFFLINE'], 'uptime': '-1'}}
}

CDATA_GP_PAR_INVALID = {
    'type': VCS_AVAIL_PARALLEL,
    'global': {'Frozen': '0', 'TFrozen': '0'},
    'systems': {
        'svc-1': {'state': ['OFFLINE'], 'uptime': '-1'},
        'svc-2': {'state': ['OFFLINE'], 'uptime': '-1'}}
}

CDATA_GRP_TYPE_INVALID = {
    'type': 'bbbb',
    'global': {'Frozen': '0', 'TFrozen': '0'},
    'systems': {
        'svc-1': {'state': ['OFFLINE'], 'uptime': '-1'},
        'svc-2': {'state': ['OFFLINE'], 'uptime': '-1'}}
}

m_group_hist = {'cluster_group': [
   {"date": "Tue Nov 15 19:42:05 2016",
    "info": "Group Grp_CS_svc_cluster_secserv is offline "
            "on system cloud-svc-3",
    "id": "V-16-1-10446"},
   {"date": "Tue Nov 15 06:48:01 2016",
    "info": "Group Grp_CS_svc_cluster_secserv is online "
            "on system cloud-svc-3",
    "id": "V-16-1-10447"},
   {"date": "Wed Nov 16 20:53:50 2016",
    "info": "Group Grp_CS_svc_cluster_secserv AutoRestart set to 1",
    "id": "V-16-1-10181"},
]}


class ParserError(Exception):
    pass


class TestVcsCli(TestCase):
    def test_write_csv(self):
        ofile = join(gettempdir(), 'ofile.csv')
        if exists(ofile):
            remove(ofile)

        headers = ['h1', 'h2']
        data = [
            {'h1': 'z', 'h2': 'a'},
            {'h1': 'a', 'h2': 'a'}
        ]
        try:
            Vcs.write_csv(ofile, headers, data)
            self.assertTrue(exists(ofile))
            with open(ofile, 'r') as _of:
                contents = ''.join(_of.readlines())
            self.assertTrue('h1,h2' in contents)
            self.assertTrue('z,a' in contents)
            self.assertTrue('a,a' in contents)
        finally:
            if exists(ofile):
                remove(ofile)

        orig_home = None
        if 'HOME' in os.environ:
            orig_home = os.environ['HOME']

        tmp_home = join(gettempdir(), 'ff')
        os.environ['HOME'] = tmp_home
        output_file = 'ofile.csv'
        try:
            rfile = join(os.environ['HOME'], output_file)
            Vcs.write_csv(output_file, headers, data)
            self.assertTrue(exists(rfile))
        finally:
            shutil.rmtree(tmp_home)
            if orig_home:
                os.environ['HOME'] = orig_home

    def test__get_group_struct(self):
        struct = Vcs._get_group_struct('cn', 'gn', 'sn', 'av', 'srvs', 'gps',
                                       False, False, 'vm')
        self.assertEqual('cn', struct[Vcs.H_CLUSTER])
        self.assertEqual('gn', struct[Vcs.H_GROUP])
        self.assertEqual('sn', struct[Vcs.H_SYSTEM])
        self.assertEqual('av', struct[Vcs.H_TYPE])
        self.assertEqual('srvs', struct[Vcs.H_SERVICE_STATE])
        self.assertEqual('-', struct[Vcs.H_FROZEN])
        self.assertEqual('vm', struct[Vcs.H_LITP_SERVICE_TYPE])

    def test__get_system_struct(self):
        struct = Vcs._get_system_struct('s', 'on', 'c', False, False)
        self.assertEqual('s', struct[Vcs.H_SYSTEM])
        self.assertEqual('on', struct[Vcs.H_SYSTEM_STATE])
        self.assertEqual('c', struct[Vcs.H_CLUSTER])
        self.assertEqual('-', struct[Vcs.H_FROZEN])

    @patch('h_vcs.vcs_cli.LitpRestClient.get_children')
    def test__get_modeled_groups(self, m_get_children):
        c_json = get_node_json('cluster', 'c1', 'Applied', '/d/d1/c/c1')
        s_json = get_node_json('service', 's-1', 'Applied', '/d/d1/c/c1/s/s1')
        m_get_children.side_effect = [
            [{'path': '/d/d1', 'data': {}}],
            [{'path': '/d/d1/c/c1', 'data': c_json}],
            [{'path': '/d/d1/c/c1/n1/s/b1', 'data': s_json}]
        ]
        by_model, by_vcs = Vcs._get_modeled_groups()
        self.assertIn('c1', by_model)
        self.assertIn('s_1', by_model['c1'])
        self.assertIn('c1', by_vcs)
        self.assertIn('Grp_CS_c1_s_1', by_vcs['c1'])

    @patch('h_vcs.vcs_cli.LitpRestClient.get_children')
    def test_get_modeled_group_timeouts(self, m_get_children):
        d_json = get_node_json('deployment', 'd1', 'Applied', '/d/d1')
        gp1_json = get_node_json('service', 'gp1', 'Applied',
                                 '/d/d1/c/c1/s/s1/gp1',
                                 properties={Vcs.H_ONLINE_TIMEOUT: '1',
                                             Vcs.H_OFFLINE_TIMEOUT: '2'})
        gp2_json = get_node_json('service', 'gp2', 'Applied',
                                 '/d/d1/c/c1/s/s1/gp2',
                                 properties={Vcs.H_ONLINE_TIMEOUT: '3',
                                             Vcs.H_OFFLINE_TIMEOUT: '4'})

        side_effect = [
            [{'path': '/d/d1', 'data': d_json}],
            [
                {'path': '/d/d1/c/c1/s/s1/gp1', 'data': gp1_json},
                {'path': '/d/d1/c/c1/s/s1/gp2', 'data': gp2_json}
            ]
        ]

        m_get_children.side_effect = side_effect
        timeouts = Vcs._get_modeled_group_timeouts('c', 'gp2')
        self.assertIn(Vcs.H_ONLINE_TIMEOUT, timeouts)
        self.assertEqual('3', timeouts[Vcs.H_ONLINE_TIMEOUT])
        self.assertIn(Vcs.H_OFFLINE_TIMEOUT, timeouts)
        self.assertEqual('4', timeouts[Vcs.H_OFFLINE_TIMEOUT])

        m_get_children.reset_mock()
        m_get_children.side_effect = side_effect

        timeouts = Vcs._get_modeled_group_timeouts('c', 'aaaaa')
        self.assertIn(Vcs.H_ONLINE_TIMEOUT, timeouts)
        self.assertEqual('600', timeouts[Vcs.H_ONLINE_TIMEOUT])
        self.assertIn(Vcs.H_OFFLINE_TIMEOUT, timeouts)
        self.assertEqual('600', timeouts[Vcs.H_OFFLINE_TIMEOUT])

    def test_get_modeled_group_retry_limit(self):
        retries = Vcs._get_modeled_group_retry_limit()
        self.assertIn(Vcs.H_ONLINE_RETRY, retries)
        self.assertEqual('3', retries[Vcs.H_ONLINE_RETRY])
        self.assertIn(Vcs.H_OFFLINE_RETRY, retries)
        self.assertEqual('3', retries[Vcs.H_OFFLINE_RETRY])

    def setup_get_cluster_group_status(self,
                                       cluster_name,
                                       vcs_group_name,
                                       litp_group_state,
                                       vcs_group_data,
                                       m_get_modeled_groups,
                                       m_get_hostname_vcs_aliases,
                                       m_get_modeled_group_types,
                                       m_get_vcs_group_info,
                                       m_discover_peer_nodes):
        vcs_name = cluster_name + '_' + vcs_group_name
        node_list = ['svc-1', 'svc-2']
        hostname_list = ['atrcxb1', 'atrcxb2']
        m_discover_peer_nodes.return_value = hostname_list
        mock_object = LitpObject(None, {}, None)
        mock_object._id = vcs_group_name
        mock_object._properties = {'node_list': ','.join(node_list)}
        mock_object._state = litp_group_state

        m_get_modeled_groups.return_value = (
            {},
            {cluster_name: {vcs_name: mock_object}}
        )
        m_get_hostname_vcs_aliases.return_value = (
            {'atrcxb1': 'svc-1', 'atrcbx2': 'svc-2'},
            {'svc-1': 'atrcxb1', 'svc-2': 'atrcxb2'}
        )
        m_get_modeled_group_types.return_value = {
            vcs_group_name: {'type': 'vm', 'node_list': node_list}}

        m_get_vcs_group_info.return_value = {vcs_name: vcs_group_data}

    def setup_get_3nodes_cluster_group_status(self,
                                       cluster_name,
                                       vcs_group_name,
                                       litp_group_state,
                                       vcs_group_data,
                                       m_get_modeled_groups,
                                       m_get_hostname_vcs_aliases,
                                       m_get_modeled_group_types,
                                       m_get_vcs_group_info,
                                       m_discover_peer_nodes):
        vcs_name = cluster_name + '_' + vcs_group_name
        node_list = ['db-2', 'db-3', 'db-4']
        hostname_list = ['atrcxb2', 'atrcxb3', 'atrcxb4']
        m_discover_peer_nodes.return_value = hostname_list
        mock_object = LitpObject(None, {}, None)
        mock_object._id = vcs_group_name
        mock_object._properties = {'node_list': ','.join(node_list)}
        mock_object._state = litp_group_state

        m_get_modeled_groups.return_value = (
            {},
            {cluster_name: {vcs_name: mock_object}}
        )
        m_get_hostname_vcs_aliases.return_value = (
            {'atrcxb2': 'db-2', 'atrcbx3': 'db-3', 'atrcbx4': 'db-4'},
            {'db-2': 'atrcxb2', 'db-3': 'atrcxb3', 'db-4': 'atrcxb4'}
        )
        m_get_modeled_group_types.return_value = {
            vcs_group_name: {'type': 'lsb', 'node_list': node_list}}

        m_get_vcs_group_info.return_value = {vcs_name: vcs_group_data}

    @patch('commands.getstatusoutput')
    @patch('h_vcs.vcs_cli.Vcs.get_cluster_group_status')
    @patch('h_vcs.vcs_cli.Vcs.get_neo4j_cluster_information')
    @patch('h_vcs.vcs_cli.Vcs.neo4j_offline_freeze')
    def test_neo4j_pre_check_neoj4_not_in_use(
            self, m_neo4j_offline_freeze,
            m_get_neo4j_cluster_information,
            m_get_cluster_group_status,
            m_getstatusoutput):

        m_getstatusoutput.return_value = 0, 'dps_persistence_provider=neo4j'
        instance = Vcs()
        instance.neo4j_set_state()
        self.assertTrue(m_get_neo4j_cluster_information.called)
        self.assertTrue(m_neo4j_offline_freeze.called)

    @patch('h_puppet.mco_agents.EnminstAgent.hagrp_freeze')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_offline')
    def test_neo4j_offline_freeze(
            self, m_hagrp_offline, m_hagrp_freeze):

        neo4j_cluster_information = ([{ \
            'ServiceState': u'ONLINE', 'Cluster': u'db_cluster', \
            'ServiceType': 'lsb', 'Group': \
            u'Grp_CS_db_cluster_sg_neo4j_clustered_service', \
            'GroupState': 'OK', 'HAType': 'parallel', 'Frozen': '-', \
            'System': u'ieatrcxb4750-1'}, {'ServiceState': u'ONLINE', \
            'Cluster': u'db_cluster', 'ServiceType': 'lsb', 'Group': \
            u'Grp_CS_db_cluster_sg_neo4j_clustered_service', 'GroupState': \
            'OK', 'HAType': 'parallel', 'Frozen': '-', 'System': u'ieatrcxb4752-1'}, \
            {'ServiceState': u'ONLINE', 'Cluster': u'db_cluster', 'ServiceType': \
            'lsb', 'Group': u'Grp_CS_db_cluster_sg_neo4j_clustered_service', \
            'GroupState': 'OK', 'HAType': 'parallel', 'Frozen': '-', \
            'System': u'ieatrcxb4736-1'}],)
        instance = Vcs()
        instance.neo4j_offline_freeze(neo4j_cluster_information)
        self.assertTrue(m_hagrp_offline.called)
        self.assertTrue(m_hagrp_freeze.called)

    @patch('h_puppet.mco_agents.EnminstAgent.hagrp_unfreeze')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_online')
    def test_neo4j_unfreeze_online(
            self, m_hagrp_online, m_hagrp_unfreeze):

        neo4j_cluster_information = ([{ \
            'ServiceState': u'OFFLINE', 'Cluster': u'db_cluster', \
            'ServiceType': 'lsb', 'Group': \
            u'Grp_CS_db_cluster_sg_neo4j_clustered_service', \
            'GroupState': 'OK', 'HAType': 'parallel', 'Frozen': 'Perm', \
            'System': u'ieatrcxb4750-1'}, {'ServiceState': u'OFFLINE', \
            'Cluster': u'db_cluster', 'ServiceType': 'lsb', 'Group': \
            u'Grp_CS_db_cluster_sg_neo4j_clustered_service', 'GroupState': \
            'OK', 'HAType': 'parallel', 'Frozen': 'Perm',  \
            'System': u'ieatrcxb4752-1'}, \
            {'ServiceState': u'OFFLINE', 'Cluster': u'db_cluster', 'ServiceType': \
            'lsb', 'Group': u'Grp_CS_db_cluster_sg_neo4j_clustered_service', \
            'GroupState': 'OK', 'HAType': 'parallel', 'Frozen': 'Perm', \
            'System': u'ieatrcxb4736-1'}],)
        instance = Vcs()
        instance.neo4j_unfreeze_online(neo4j_cluster_information)
        self.assertTrue(m_hagrp_unfreeze.called)
        self.assertTrue(m_hagrp_online.called)

    def assert_get_cluster_group_status(self,
                                        cluster_name,
                                        vcs_group_name,
                                        litp_group_state,
                                        vcs_group_data,
                                        m_get_modeled_groups,
                                        m_get_hostname_vcs_aliases,
                                        m_get_modeled_group_types,
                                        m_get_vcs_group_info,
                                        m_discover_peer_nodes,
                                        assert_data):
        self.setup_get_cluster_group_status(cluster_name, vcs_group_name,
                                            litp_group_state,
                                            vcs_group_data,
                                            m_get_modeled_groups,
                                            m_get_hostname_vcs_aliases,
                                            m_get_modeled_group_types,
                                            m_get_vcs_group_info,
                                            m_discover_peer_nodes)

        _filter = '.*{0}.*'.format(vcs_group_name)
        data, _h = Vcs.get_cluster_group_status(cluster_filter=cluster_name,
                                                group_filter=_filter,
                                                uptimes=True)

        vcs_name = cluster_name + '_' + vcs_group_name
        self.assertEqual(assert_data['len'], len(data))
        for index in xrange(0, assert_data['len']):
            self.assertEqual(vcs_name, data[index]['Group'])
            self.assertEqual(assert_data['group_state'][index],
                             data[index]['GroupState'])
            self.assertEqual(assert_data['service_state'][index],
                             data[index]['ServiceState'])

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_NWAY_OK(self, m_get_modeled_groups,
                                              m_get_hostname_vcs_aliases,
                                              m_get_modeled_group_types,
                                              m_get_vcs_group_info,
                                              m_discover_peer_nodes):
        self.assert_get_cluster_group_status(
                'c1', 'gp_par_ok', 'Applied', CDATA_GP_PAR_OK,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes,
                {'len': 2,
                 'group_state': [Vcs.STATE_OK, Vcs.STATE_OK],
                 'service_state': [VCS_GRP_SVS_STATE_ONLINE,
                                   VCS_GRP_SVS_STATE_ONLINE]}
        )

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_INITIAL(self, m_get_modeled_groups,
                                              m_get_hostname_vcs_aliases,
                                              m_get_modeled_group_types,
                                              m_get_vcs_group_info,
                                              m_discover_peer_nodes):
        self.assert_get_cluster_group_status(
                'c1', 'gp_par_ok', 'Initial', CDATA_GP_PAR_OK,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes,
                {'len': 2,
                 'group_state': [Vcs.STATE_UNDEFINED, Vcs.STATE_UNDEFINED],
                 'service_state': ['N/A', 'N/A']}
        )

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_NWAY_INVALID(self,
                                                   m_get_modeled_groups,
                                                   m_get_hostname_vcs_aliases,
                                                   m_get_modeled_group_types,
                                                   m_get_vcs_group_info,
                                                   m_discover_peer_nodes):
        self.assert_get_cluster_group_status(
                'c1', 'gp_par_invalid', 'Applied', CDATA_GP_PAR_INVALID,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes,
                {'len': 2,
                 'group_state': [Vcs.STATE_INVALID, Vcs.STATE_INVALID],
                 'service_state': [VCS_GRP_SVS_STATE_OFFLINE,
                                   VCS_GRP_SVS_STATE_OFFLINE]}
        )

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_2N_INVALID(self, m_get_modeled_groups,
                                                 m_get_hostname_vcs_aliases,
                                                 m_get_modeled_group_types,
                                                 m_get_vcs_group_info,
                                                 m_discover_peer_nodes):
        self.assert_get_cluster_group_status(
                'c1', 'gp_as_invalid', 'Applied', CDATA_GP_AS_INVALID,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes,
                {'len': 2,
                 'group_state': [Vcs.STATE_INVALID, Vcs.STATE_INVALID],
                 'service_state': [VCS_GRP_SVS_STATE_OFFLINE,
                                   VCS_GRP_SVS_STATE_OFFLINE]}
        )

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_POWEREDOFF(self,
                                                 m_get_modeled_groups,
                                                 m_get_hostname_vcs_aliases,
                                                 m_get_modeled_group_types,
                                                 m_get_vcs_group_info,
                                                 m_discover_peer_nodes):
        cluster_name = 'c1'
        vcs_group_name = 'gp_par_ok'
        vcs_name = cluster_name + '_' + vcs_group_name

        mock_object = LitpObject(None, {}, None)
        mock_object._id = vcs_group_name
        mock_object._properties = {'node_list': 'svc-1,svc-2'}

        m_get_modeled_groups.return_value = (
            {},
            {cluster_name: {vcs_name: mock_object}}
        )
        m_get_hostname_vcs_aliases.return_value = (
            {'atrcxb1': 'svc-1', 'atrcbx2': 'svc-2'},
            {'svc-1': 'atrcxb1', 'svc-2': 'atrcxb2'}
        )
        m_discover_peer_nodes.return_value = ['atrcxb1', 'atrcbx2']
        m_get_modeled_group_types.return_value = {
            vcs_group_name: {'type': 'vm', 'node_list': ['svc-1', 'svc-2']}}

        m_get_vcs_group_info.side_effect = [
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10011)),
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10011))
        ]
        data, _ = Vcs.get_cluster_group_status()
        self.assertEqual(2, len(data))
        for row in data:
            self.assertEqual('-', row[Vcs.H_GROUP])
            self.assertEqual(Vcs.STATE_INVALID, row[Vcs.H_GROUP_STATE])
            self.assertEqual(VCS_NA, row[Vcs.H_TYPE])

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_2N_OK(self, m_get_modeled_groups,
                                            m_get_hostname_vcs_aliases,
                                            m_get_modeled_group_types,
                                            m_get_vcs_group_info,
                                            m_discover_peer_nodes):
        self.assert_get_cluster_group_status(
                'c1', 'gp_as_ok', 'Applied', CDATA_GP_AS_OK,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes,
                {'len': 2,
                 'group_state': [Vcs.STATE_OK, Vcs.STATE_OK],
                 'service_state': [VCS_GRP_SVS_STATE_ONLINE,
                                   VCS_GRP_SVS_STATE_OFFLINE]}
        )

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_invalid_type(self,
                                                   m_get_modeled_groups,
                                                   m_get_hostname_vcs_aliases,
                                                   m_get_modeled_group_types,
                                                   m_get_vcs_group_info,
                                                   m_discover_peer_nodes):
        with self.assertRaises(VcsException) as ve:
            self.assert_get_cluster_group_status(
                    'c1', 'grp_type_invalid', 'Applied',
                    CDATA_GRP_TYPE_INVALID,
                    m_get_modeled_groups,
                    m_get_hostname_vcs_aliases,
                    m_get_modeled_group_types,
                    m_get_vcs_group_info,
                    m_discover_peer_nodes,
                    {'len': 2,
                     'group_state': [Vcs.STATE_OK, Vcs.STATE_OK],
                     'service_state': [VCS_GRP_SVS_STATE_ONLINE,
                                       VCS_GRP_SVS_STATE_OFFLINE]}
            )
        self.assertTrue('Unknown mode bbbb' in str(ve.exception))

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_verify_cluster_group_status_frozen(self,
                                                  m_get_modeled_groups,
                                                  m_get_hostname_vcs_aliases,
                                                  m_get_modeled_group_types,
                                                  m_get_vcs_group_info,
                                                  m_discover_peer_nodes):
        gdata = {
            'type': VCS_AVAIL_PARALLEL,
            'global': {'Frozen': '0', 'TFrozen': '1'},
            'systems': {
                'svc-1': {'state': ['ONLINE'], 'uptime': '-1'},
                'svc-2': {'state': ['ONLINE'], 'uptime': '-1'}}
        }
        self.setup_get_cluster_group_status(
                'c1', 'gp_par_ok', 'Applied', gdata,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes
        )

        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_group_status(
                    cluster_filter=None,
                    group_filter='gp_par_ok',
                    group_type=None,
                    system_filter=None,
                    groupstate_filter=None,
                    systemstate_filter=None,
                    sort_keys=None)
        self.assertNotEqual(sysexit.exception, ExitCodes.VCS_INVALID_STATE)

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_verify_cluster_group_status_frozen_versant(self,
                                                  m_get_modeled_groups,
                                                  m_get_hostname_vcs_aliases,
                                                  m_get_modeled_group_types,
                                                  m_get_vcs_group_info,
                                                  m_discover_peer_nodes):
        gdata = {
            'type': VCS_AVAIL_PARALLEL,
            'global': {'Frozen': '0', 'TFrozen': '1'},
            'systems': {
                'svc-1': {'state': ['ONLINE'], 'uptime': '-1'},
                'svc-2': {'state': ['ONLINE'], 'uptime': '-1'}}
        }
        self.setup_get_cluster_group_status(
                'c1', 'versant_clustered_service', 'Applied', gdata,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes
        )
        ofile = join(gettempdir(), 'ofile.csv')
        if exists(ofile):
            remove(ofile)
        try:
            Vcs.verify_cluster_group_status(cluster_filter=None,
                                            group_filter='versant_clustered_service',
                                            group_type=None,
                                            system_filter=None,
                                            groupstate_filter=None,
                                            systemstate_filter=None,
                                            sort_keys=None,
                                            csvfile=ofile,
                                            show_uptime=True)
            self.assertTrue(exists(ofile))
            with open(ofile, 'r') as _infile:
                lines = _infile.readlines()
            self.assertEqual(3, len(lines))
            lines = ''.join(lines)
            self.assertIn('c1,c1_versant_clustered_service,svc-1,parallel,vm,ONLINE,OK,Temp,-1',
                          lines)
            self.assertIn('c1,c1_versant_clustered_service,svc-2,parallel,vm,ONLINE,OK,Temp,-1',
                          lines)
        finally:
            if exists(ofile):
                remove(ofile)

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_verify_cluster_group_status_NWAY_INV(self,
                                                  m_get_modeled_groups,
                                                  m_get_hostname_vcs_aliases,
                                                  m_get_modeled_group_types,
                                                  m_get_vcs_group_info,
                                                  m_discover_peer_nodes):

        self.setup_get_cluster_group_status(
                'c1', 'gp_par_invalid', 'Applied', CDATA_GP_PAR_INVALID,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes
        )

        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_group_status(
                    cluster_filter=None,
                    group_filter='gp_par_invalid',
                    group_type=None,
                    system_filter=None,
                    groupstate_filter=None,
                    systemstate_filter=None,
                    sort_keys=None)
        self.assertNotEqual(sysexit.exception, ExitCodes.VCS_INVALID_STATE)

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_verify_cluster_group_status_2N_INV(self,
                                                m_get_modeled_groups,
                                                m_get_hostname_vcs_aliases,
                                                m_get_modeled_group_types,
                                                m_get_vcs_group_info,
                                                m_discover_peer_nodes):

        self.setup_get_cluster_group_status(
                'c1', 'gp_par_invalid', 'Applied', CDATA_GP_PAR_INVALID,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes
        )

        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_group_status(
                    cluster_filter=None,
                    group_filter='gp_par_invalid',
                    group_type=None,
                    system_filter=None,
                    groupstate_filter=None,
                    systemstate_filter=None,
                    sort_keys=Vcs.H_SYSTEM)
        self.assertNotEqual(sysexit.exception, ExitCodes.VCS_INVALID_STATE)

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_verify_cluster_group_status_CSV(self,
                                             m_get_modeled_groups,
                                             m_get_hostname_vcs_aliases,
                                             m_get_modeled_group_types,
                                             m_get_vcs_group_info,
                                             m_discover_peer_nodes):
        ofile = join(gettempdir(), 'ofile.csv')
        if exists(ofile):
            remove(ofile)

        self.setup_get_cluster_group_status(
                'c1', 'gp_par_ok', 'Applied', CDATA_GP_PAR_OK,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes
        )
        try:
            Vcs.verify_cluster_group_status(cluster_filter=None,
                                            group_filter='gp_par_ok',
                                            group_type=None,
                                            system_filter=None,
                                            groupstate_filter=None,
                                            systemstate_filter=None,
                                            sort_keys=None,
                                            csvfile=ofile,
                                            show_uptime=True)
            self.assertTrue(exists(ofile))
            with open(ofile, 'r') as _infile:
                lines = _infile.readlines()
            self.assertEqual(3, len(lines))
            lines = ''.join(lines)
            print lines
            self.assertIn('c1,c1_gp_par_ok,svc-1,parallel,vm,ONLINE,OK,-,-1',
                          lines)
            self.assertIn('c1,c1_gp_par_ok,svc-2,parallel,vm,ONLINE,OK,-,-1',
                          lines)
        finally:
            if exists(ofile):
                remove(ofile)

    @patch('commands.getstatusoutput')
    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_verify_cluster_group_status_3nodes_OK(self,
                                                m_get_modeled_groups,
                                                m_get_hostname_vcs_aliases,
                                                m_get_modeled_group_types,
                                                m_get_vcs_group_info,
                                                m_discover_peer_nodes,
                                                m_getstatusoutput):

        m_getstatusoutput.return_value = 0
        self.setup_get_3nodes_cluster_group_status(
                'db_cluster', 'neo4j_clustered_service', 'Applied',
                CDATA_GP_PAR_3NODES_OK,
                m_get_modeled_groups,
                m_get_hostname_vcs_aliases,
                m_get_modeled_group_types,
                m_get_vcs_group_info,
                m_discover_peer_nodes
        )

        try:
            Vcs.verify_cluster_group_status(
                    cluster_filter=None,
                    group_filter='neo4j_clustered_service',
                    group_type=None,
                    system_filter=None,
                    groupstate_filter=None,
                    systemstate_filter=None,
                    sort_keys=Vcs.H_SYSTEM)
        except sysexit.exception:
            self.fail("verify_cluster_group_status_3nodes failed.")

    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_history')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.screen')
    def test_show_history(self, m_screen,
                          m_get_hostname_vcs_aliases,
                          m_get_modeled_groups,
                          m_hagrp_history):
        cluster_name = 'cluster'
        vcs_group_name = 'group'
        vcs_name = cluster_name + '_' + vcs_group_name

        mock_object = LitpObject(None, {}, None)
        mock_object._id = vcs_group_name
        mock_object._properties = {'node_list': 'svc-1,svc-2'}

        m_get_modeled_groups.return_value = (
            {},
            {cluster_name: {vcs_name: mock_object}}
        )
        m_get_hostname_vcs_aliases.return_value = ({}, {
            'svc-1': 'n1', 'svc-2': 'n2'
        })

        m_hagrp_history.return_value = {
            vcs_name: [{'date': 'ddd', 'info': ' iii'}]}

        vcs = Vcs()
        vcs.show_history(cluster_name, vcs_name)
        # No too worried about what gets printed just that something was.
        self.assertEqual(1, m_screen.call_count)

        m_screen.reset_mock()
        m_hagrp_history.reset_mock()
        vcs.show_history('hjhjhjh', vcs_name)
        self.assertEqual(0, m_hagrp_history.call_count)

        m_screen.reset_mock()
        m_hagrp_history.reset_mock()
        vcs.show_history(cluster_name, 'dfgdfgdfgd')
        self.assertEqual(0, m_hagrp_history.call_count)

        m_screen.reset_mock()
        m_hagrp_history.reset_mock()
        m_hagrp_history.return_value = []
        vcs.show_history(cluster_name, vcs_name)
        self.assertEqual(1, m_hagrp_history.call_count)

        m_screen.reset_mock()
        m_hagrp_history.reset_mock()
        m_hagrp_history.return_value = m_group_hist
        vcs.show_history()
        first = call('Tue Nov 15 06:48:01 2016 Group Grp_CS_svc_cluster_'
                     'secserv is online on system cloud-svc-3')
        second = call('Tue Nov 15 19:42:05 2016 Group Grp_CS_svc_cluster_'
                      'secserv is offline on system cloud-svc-3')
        third = call('Wed Nov 16 20:53:50 2016 Group Grp_CS_svc_cluster_'
                     'secserv AutoRestart set to 1')
        # default, no order
        m_screen.assert_has_calls([second, first, third])
        # and now, sorted
        vcs.show_history(sort_by_date=True)
        m_screen.assert_has_calls([first, second, third])

    @patch('h_vcs.vcs_cli.Vcs.verify_cluster_group_status')
    @patch('h_vcs.vcs_cli.Vcs.show_history')
    def test_main(self, history, verify_cluster):
        self.assertRaises(SystemExit, main, [])
        self.assertRaises(SystemExit, main, ['ad'])

        main(['--groups'])
        self.assertTrue(verify_cluster.called)
        self.assertFalse(history.called)

        verify_cluster.reset_mock()
        history.reset_mock()
        main(['--history', '-g', 'group_name', '-c', 'some_cluster'])
        self.assertFalse(verify_cluster.called)
        self.assertTrue(history.called)

    @patch('h_vcs.vcs_cli.Vcs.hagrp_online')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_offline')
    def test_main_restart(self, m_online, m_offline):
        main(['--restart', '-g=g', '-s=s'])
        self.assertTrue(m_offline.called)
        self.assertTrue(m_online.called)

        m_offline.reset_mock()
        m_online.reset_mock()
        main(['--restart', '-g=g'])
        self.assertTrue(m_offline.called)
        self.assertTrue(m_online.called)

        m_offline.reset_mock()
        m_online.reset_mock()
        main(['--restart', '-s=s'])
        self.assertTrue(m_offline.called)
        self.assertTrue(m_online.called)

        m_offline.reset_mock()
        m_online.reset_mock()
        main(['--restart', '-g', 'gp1'])
        self.assertTrue(m_offline.called)
        self.assertTrue(m_online.called)

        m_offline.reset_mock()
        m_online.reset_mock()
        main(['--restart', '-s', 's1'])
        self.assertTrue(m_offline.called)
        self.assertTrue(m_online.called)

    @patch('h_vcs.vcs_cli.Vcs.hagrp_online')
    def test_main_online(self, m_hagrp_online):
        main(['--online', '-g=g', '-s=s'])
        self.assertTrue(m_hagrp_online.called)

        m_hagrp_online.reset_mock()
        main(['--online', '-g', 'gp1'])
        self.assertTrue(m_hagrp_online.called)

        m_hagrp_online.reset_mock()
        main(['--online', '-s', 's1'])
        self.assertTrue(m_hagrp_online.called)

        m_hagrp_online.reset_mock()
        main(['--online', '-g', 'gp1'])
        self.assertTrue(m_hagrp_online.called)

        m_hagrp_online.reset_mock()
        main(['--online', '-s', 's1'])
        self.assertTrue(m_hagrp_online.called)

    @patch('h_vcs.vcs_cli.Vcs.hagrp_offline')
    def test_main_offline(self, m_hagrp_offline):
        main(['--offline', '-g=g', '-s=s'])
        self.assertTrue(m_hagrp_offline.called)

        m_hagrp_offline.reset_mock()
        main(['--offline', '-g', 'gp1'])
        self.assertTrue(m_hagrp_offline.called)

        m_hagrp_offline.reset_mock()
        main(['--offline', '-s', 's1'])
        self.assertTrue(m_hagrp_offline.called)

        m_hagrp_offline.reset_mock()
        main(['--offline', '-s', 's1'])
        self.assertTrue(m_hagrp_offline.called)

    @patch('h_vcs.vcs_cli.Vcs.show_history')
    def test_main_history(self, show_history):
        main(['--history', '-g', 'group1'])
        show_history.assert_called_with(cluster_filter=None,
                                        group_filter='^group1$',
                                        sort_by_date=False)
        main(['--history', '-c', 'cluster1'])
        show_history.assert_called_with(cluster_filter='^cluster1$',
                                        group_filter='Grp_CS_.*',
                                        sort_by_date=False)
        main(['--history', '--by-date', '-c', 'cluster1'])
        show_history.assert_called_with(cluster_filter='^cluster1$',
                                        group_filter='Grp_CS_.*',
                                        sort_by_date=True)

    @patch('argparse.ArgumentParser.error')
    def test_main_history_error(self, arg_error):
        arg_error.side_effect = ParserError('')
        self.assertRaises(ParserError, main, ['--history', '-s', 'sys1'])
        self.assertRaises(ParserError, main, ['--history', '-t', 'a_type'])
        self.assertRaises(ParserError, main, ['--history', '-a', 'state'])
        self.assertRaises(ParserError, main, ['--history', '-a', 'state'])
        self.assertRaises(ParserError, main, ['--history', '-g', 'group',
                                              '-vt', 'x'])
        self.assertRaises(ParserError, main, ['--history', '-c', 'clu',
                                              '-b', 'group_state'])

    def test_filter_state(self):
        states = [
            {'group': 'g1', 'State': 'ONLINE'},
            {'group': 'g2', 'State': 'OFFLINE'}
        ]
        filtered = filter_groups_by_state(states, None)
        self.assertListEqual(states, filtered)
        filtered = filter_groups_by_state(states, 'ONLINE')
        self.assertEqual(1, len(filtered))
        self.assertEqual('g1', filtered[0]['group'])
        filtered = filter_groups_by_state(states, 'ONLINE,OFFLINE')
        self.assertEqual(2, len(filtered))

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_clear')
    def test_hagrp_clear(self, m_hagrp_clear, m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED]
            }
        ]
        vcs = Vcs()
        vcs.hagrp_clear('somename', 'cname', 'somesys')
        m_hagrp_clear.assert_has_calls([
            call('somename', 'somesys')
        ], any_order=True)

        m_hagrp_clear.reset_mock()
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE]
            }
        ]
        vcs.hagrp_clear('somename', 'cname', 'somesys')
        self.assertFalse(m_hagrp_clear.called)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_clear')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_online')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    def test_hagrp_online(self,
                          m_hagrp_wait,
                          m_hagrp_online,
                          m_hagrp_clear,
                          m_get_action_groups):
        group_name = 'group_name'
        group_system = 'system_name'
        group_cluster = 'cluster_name'
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: group_name,
                Vcs.H_SYSTEM: group_system,
                Vcs.H_CLUSTER: group_cluster,
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED],
                Vcs.H_TYPE: VCS_AVAIL_STANDALONE,
                Vcs.H_ONLINE_TIMEOUT: '30',
                Vcs.H_OFFLINE_TIMEOUT: '30',
                Vcs.H_ONLINE_RETRY: '3',
                Vcs.H_OFFLINE_RETRY: '3',
                Vcs.H_DEPS: []
            }
        ]
        vcs = Vcs()

        vcs.hagrp_online(group_name, group_system, group_cluster, -1,
                         autoclear=True)

        m_hagrp_clear.assert_has_calls([
            call(group_name, group_system)
        ], any_order=True)

        m_hagrp_online.assert_has_calls([
            call(group_name, group_system, propagate=False)
        ], any_order=True)

        m_hagrp_wait.assert_has_calls([
            call(group_name, group_system, 'ONLINE', timeout=90)
        ], any_order=True)

        m_hagrp_clear.reset_mock()
        m_hagrp_online.reset_mock()
        m_hagrp_wait.reset_mock()
        self.assertRaises(SystemExit, vcs.hagrp_online,
                          group_name, group_system, group_cluster, 3)

    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_online')
    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    def test_hagrp_online_1(self, m_get_action_groups, m_hagrp_online):
        m_get_action_groups.return_value = []
        vcs = Vcs()
        vcs.hagrp_online('group', 'system', 'cluster', 3, autoclear=True)
        self.assertEqual(0, m_hagrp_online.call_count)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_clear')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_online')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    def test_hagrp_online_2(self,
                            m_hagrp_wait,
                            m_hagrp_online,
                            m_hagrp_clear,
                            m_get_action_groups):
        group_name = 'group_name'
        group_system = 'system_name'
        group_cluster = 'cluster_name'
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: group_name,
                Vcs.H_SYSTEM: group_system,
                Vcs.H_CLUSTER: group_cluster,
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_STANDALONE,
                Vcs.H_DEPS: ['dep1']
            }
        ]
        vcs = Vcs()

        vcs.hagrp_online(group_name, group_system, group_cluster, 3,
                         autoclear=True)
        self.assertEqual(0, m_hagrp_clear.call_count)

        m_hagrp_online.assert_has_calls([call(group_name, group_system,
                                              propagate=True)],
                                        any_order=True)

        m_hagrp_wait.assert_has_calls([call(group_name, group_system, 'ONLINE',
                                            timeout=3)], any_order=True)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_clear')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_online')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    def test_hagrp_online_3(self,
                            m_hagrp_wait,
                            m_hagrp_online,
                            m_hagrp_clear,
                            m_get_action_groups):
        group_name = 'group_name'
        group_system = 'system_name'
        group_cluster = 'cluster_name'
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: group_name,
                Vcs.H_SYSTEM: group_system,
                Vcs.H_CLUSTER: group_cluster,
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_STANDALONE,
                Vcs.H_DEPS: []
            }
        ]
        m_hagrp_online.side_effect = McoAgentException(VcsCodes.V_16_1_40229)
        vcs = Vcs()
        vcs.hagrp_online(group_name, group_system, group_cluster, 3,
                         autoclear=True)
        self.assertFalse(m_hagrp_wait.called)

        m_hagrp_online.side_effect = McoAgentException(VcsCodes.V_16_1_10446)
        self.assertRaises(McoAgentException, vcs.hagrp_online,
                          group_name, group_system, group_cluster, 3,
                          autoclear=True)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_online')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    def test_hagrp_online_4(self,
                            m_hagrp_wait,
                            m_hagrp_online,
                            m_get_action_groups):
        group_name = 'group_name'
        group_system = 'system_name'
        group_cluster = 'cluster_name'

        mco_data = [
            {
                Vcs.H_NAME: group_name,
                Vcs.H_SYSTEM: group_system,
                Vcs.H_CLUSTER: group_cluster,
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_ACTIVE_STANDBY,
                Vcs.H_DEPS: []
            },
            {
                Vcs.H_NAME: group_name,
                Vcs.H_SYSTEM: group_system + '_1',
                Vcs.H_CLUSTER: group_cluster,
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_ACTIVE_STANDBY,
                Vcs.H_DEPS: []
            }
        ]

        m_get_action_groups.return_value = mco_data
        vcs = Vcs()
        vcs.hagrp_online(group_name, '^{0}$'.format(group_system),
                         group_cluster, 3)
        m_hagrp_online.assert_has_calls([call(group_name, group_system,
                                              propagate=False)],
                                        any_order=True)

        mco_data[1][Vcs.H_SYSTEM_STATE] = [VcsStates.ONLINE]
        # No online call should be made as one side of the active-standy
        # group is already online even though the system_filter is targeting
        # the OFFLINE side/system
        m_hagrp_online.reset_mock()
        vcs.hagrp_online(group_name, '^{0}$'.format(group_system),
                         group_cluster, 3)
        self.assertFalse(m_hagrp_online.called)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_online')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    def test_hagrp_online_error(self,
                                m_hagrp_wait,
                                m_hagrp_online,
                                m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_STANDALONE,
                Vcs.H_DEPS: []
            }
        ]
        m_hagrp_wait.side_effect = McoAgentException('timedout')
        vcs = Vcs()
        self.assertRaises(SystemExit, vcs.hagrp_online, 'somename', 'somesys',
                          'cname', 3, autoclear=False)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_offline')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    def test_hagrp_offline(self, m_hagrp_wait, m_hagrp_offline,
                           m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED],
                Vcs.H_TYPE: VCS_AVAIL_STANDALONE,
                Vcs.H_ONLINE_TIMEOUT: '30',
                Vcs.H_OFFLINE_TIMEOUT: '30',
                Vcs.H_ONLINE_RETRY: '3',
                Vcs.H_OFFLINE_RETRY: '3'
            }
        ]
        vcs = Vcs()
        vcs.hagrp_offline('somename', 'somesys', 'cname', -1)
        m_hagrp_offline.assert_has_calls([
            call('somename', 'somesys')
        ], any_order=True)

        m_hagrp_wait.assert_has_calls([
            call('somename', 'somesys', 'OFFLINE', timeout=90)
        ], any_order=True)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_offline')
    def test_hagrp_offline_1(self, m_hagrp_offline,
                             m_get_action_groups):
        m_get_action_groups.return_value = []
        vcs = Vcs()
        vcs.hagrp_offline('somename', 'somesys', 'cname', 3)
        self.assertEqual(0, m_hagrp_offline.call_count)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_offline')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    def test_hagrp_offline_2(self, m_hagrp_wait, m_hagrp_offline,
                             m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED],
                Vcs.H_TYPE: VCS_AVAIL_STANDALONE,
                Vcs.H_ONLINE_TIMEOUT: '30',
                Vcs.H_OFFLINE_TIMEOUT: '30',
                Vcs.H_ONLINE_RETRY: '3',
                Vcs.H_OFFLINE_RETRY: '3'
            }
        ]

        vcs = Vcs()
        m_hagrp_wait.side_effect = McoAgentException('')
        self.assertRaises(SystemExit, vcs.hagrp_offline,
                          'somename', 'somesys', 'cname', -1)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_switch')
    def test_hagrp_switch(self, m_hagrp_switch, m_hagrp_wait,
                          m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_ACTIVE_STANDBY,
                Vcs.H_ONLINE_TIMEOUT: '30',
                Vcs.H_OFFLINE_TIMEOUT: '30',
                Vcs.H_ONLINE_RETRY: '3',
                Vcs.H_OFFLINE_RETRY: '3'
            }
        ]
        vcs = Vcs()
        vcs.hagrp_switch('somename', 'somesys', 'cname', 3)

        m_hagrp_switch.assert_has_calls([
            call('somename', 'somesys', 'somesys')
        ], any_order=True)

        m_hagrp_wait.assert_has_calls([
            call('somename', 'somesys', 'ONLINE', timeout=3)
        ], any_order=True)

        vcs.hagrp_switch('somename', 'somesys', 'cname', -1)

        m_hagrp_switch.assert_has_calls([
            call('somename', 'somesys', 'somesys')
        ], any_order=True)

        m_hagrp_wait.assert_has_calls([
            call('somename', 'somesys', 'ONLINE', timeout=180)
        ], any_order=True)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_switch')
    def test_hagrp_switch_1(self, m_hagrp_switch,
                            m_get_action_groups):
        m_get_action_groups.return_value = []
        vcs = Vcs()
        vcs.hagrp_switch('somename', 'somesys', 'cname', 3)
        self.assertEqual(0, m_hagrp_switch.call_count)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_switch')
    def test_hagrp_switch_2(self, m_hagrp_switch,
                            m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_ACTIVE_STANDBY
            },
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys-2',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_ACTIVE_STANDBY
            }
        ]
        vcs = Vcs()
        # Both side are offline, no switch will happen
        vcs.hagrp_switch('somename', 'somesys', 'cname', -1)
        self.assertFalse(m_hagrp_switch.called)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_switch')
    def test_hagrp_switch_3(self, m_hagrp_switch,
                            m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'somename',
                Vcs.H_SYSTEM: 'somesys',
                Vcs.H_CLUSTER: 'cname',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE],
                Vcs.H_TYPE: VCS_AVAIL_ACTIVE_STANDBY
            }
        ]
        m_hagrp_switch.side_effect = McoAgentException()
        vcs = Vcs()
        self.assertRaises(SystemExit, vcs.hagrp_switch,
                          'somename', 'somesys', 'cname', -1)

    @patch('h_vcs.vcs_cli.LitpRestClient')
    def test__get_hostname_vcs_aliases(self, litp):

        node_json = get_node_json('node', 'node_id', 'Applied',
                                  '/d/d1/c/c1/nodes/n1',
                                  properties={'hostname': 'h1'})

        litp.return_value.get_children.side_effect = [
            [{'path': '/d/d1', 'data': {}}],
            [{'path': '/d/d1/c/c1', 'data': {}}],
            [{'path': '/d/d1/c/c1/nodes/n1', 'data': node_json}]
        ]
        aliases_key_hostname, aliased_key_modelid = \
            Vcs._get_hostname_vcs_aliases()

        self.assertEqual(len(aliases_key_hostname), len(aliased_key_modelid))

        self.assertEqual(1, len(aliases_key_hostname))
        self.assertIn('h1', aliases_key_hostname)
        self.assertEqual('node_id', aliases_key_hostname['h1'])

        self.assertEqual(1, len(aliased_key_modelid))
        self.assertIn('node_id', aliased_key_modelid)
        self.assertEqual('h1', aliased_key_modelid['node_id'])

    def test__get_view_string(self):
        self.assertEqual('alias', Vcs._get_view_string('real', 'alias', 'm'))
        self.assertEqual('real', Vcs._get_view_string('real', 'alias', 'v'))
        self.assertEqual('real/alias',
                         Vcs._get_view_string('real', 'alias', 'x'))

        self.assertEqual('real',
                         Vcs._get_view_string('real', {}, 'm'))
        self.assertEqual('real',
                         Vcs._get_view_string('real', {}, 'v'))
        self.assertEqual('real/real',
                         Vcs._get_view_string('real', {}, 'x'))

        self.assertEqual('alias',
                         Vcs._get_view_string('real',
                                              {'real': 'alias'}, 'm'))
        self.assertEqual('real',
                         Vcs._get_view_string('real',
                                              {'real': 'alias'}, 'v'))
        self.assertEqual('real/alias',
                         Vcs._get_view_string('real',
                                              {'real': 'alias'}, 'x'))

    def test__get_service_resource_type(self):
        litp_path_parser = MagicMock()
        litp_path_parser.return_value.path_parser.return_value = '/p'
        app_type = Vcs._get_service_resource_type([], ['type1'],
                                                  litp_path_parser)
        self.assertIsNone(app_type)

        obj1_path = '/d/d1/c/c1/nodes/n1'
        obj2_path = '/d/d1/c/c1/nodes/n2'

        data_list = [
            {'path': obj1_path, 'data':
                get_node_json('vm', 'n1', 'Applied', obj1_path)},
            {'path': obj2_path, 'data':
                get_node_json('mysql', 'n2', 'Applied', obj2_path)}
        ]
        app_type = Vcs._get_service_resource_type(data_list, ['vm'],
                                                  litp_path_parser)
        self.assertEqual('mixed', app_type)

        app_type = Vcs._get_service_resource_type(data_list, ['vm', 'mysql'],
                                                  litp_path_parser)
        self.assertEqual('mixed', app_type)

        data_list = [
            {'path': obj1_path, 'data':
                get_node_json('vm', 'n1', 'Applied', obj1_path)}
        ]
        app_type = Vcs._get_service_resource_type(data_list, ['vm'],
                                                  litp_path_parser)
        self.assertEqual('vm', app_type)

        data_list = [
            {'path': obj1_path, 'data':
                get_node_json('mysql', 'n1', 'Applied', obj1_path)}
        ]
        app_type = Vcs._get_service_resource_type(data_list, ['vm'],
                                                  litp_path_parser)
        self.assertEqual('lsb', app_type)

    def test__get_frozen_type(self):
        self.assertEqual('-', Vcs._get_frozen_type(False, False))
        self.assertEqual('Temp', Vcs._get_frozen_type(True, False))
        self.assertEqual('Perm', Vcs._get_frozen_type(False, True))
        self.assertEqual('Temp', Vcs._get_frozen_type(True, True))

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.Vcs._filter_clusters')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_deactivated(self,
                                                  m_model_groups,
                                                  m_vcs_aliases,
                                                  m_group_types,
                                                  m_filter_clusters,
                                                  m_peer_nodes):

        m_model_groups.return_value = MagicMock, MagicMock
        m_vcs_aliases.return_value = MagicMock, MagicMock

        sg_deactivated = MagicMock(path='/d/e/c/v_1', state='Applied',
                                   properties={u'name': u'v_1',
                                               u'node_list': u'db',
                                               u'deactivated': u'true'})
        m_filter_clusters.return_value = {u'db_cluster':
                                          {'systems': [u'aaa'],
                                           'groups': {'v_1': sg_deactivated}}}
        vcs = Vcs()
        cluster_data, _ = vcs.get_cluster_group_status()
        self.assertEquals(cluster_data, [])

    @patch('h_vcs.vcs_cli.LitpRestClient')
    def test__get_modeled_group_types(self, litp):
        services = [
            {'path': 's1', 'data': get_node_json(
                    'service', 's1', 'Applied', '/d1/c1/n1',
                    properties={'node_list': 'n1,n2',
                                'name': 'service1'}
            )}
        ]
        applications = [
            {'path': 'app1', 'data': get_node_json(
                    'vm-service', 'app1', 'Applied', 'app1')}
        ]
        runtimes = [
            {'path': 'rt1', 'data': get_node_json(
                    'vm-service', 'rt1', 'Applied', 'rt1')}
        ]
        litp.return_value.get_children.side_effect = [
            [{'path': 'deploy1'}],
            [{'path': 'cluster1'}],
            services, applications
        ]

        group_types = Vcs._get_modeled_group_types()
        self.assertIn('s1', group_types)
        self.assertEqual('vm', group_types['s1']['type'])
        self.assertListEqual(['n1', 'n2'], group_types['s1']['node_list'])
        self.assertIn('service1', group_types)
        self.assertEqual('vm', group_types['service1']['type'])
        self.assertListEqual(['n1', 'n2'],
                             group_types['service1']['node_list'])

        litp.reset_mock()
        litp.return_value.get_children.side_effect = [
            [{'path': 'deploy1'}],
            [{'path': 'cluster1'}],
            services, [], runtimes
        ]
        group_types = Vcs._get_modeled_group_types()
        self.assertIn('s1', group_types)
        self.assertEqual('vm', group_types['s1']['type'])
        self.assertListEqual(['n1', 'n2'], group_types['s1']['node_list'])

    @patch('h_vcs.vcs_cli.LitpRestClient')
    def test__get_modeled_clusters(self, m_litp):
        m_get_children = MagicMock()
        m_litp.return_value.get_children = m_get_children

        get_deployments = [
            {'path': '/deployments/enm', 'data':
                get_node_json('deployments', 'enm', 'Applied',
                              '/deployments/enm')}]

        get_clusters = [
            {'path': '/deployments/enm/clusters/db', 'data':
                get_node_json('deployment', 'db', 'Applied',
                              '/deployments/enm/clusters/db')},
            {'path': '/deployments/enm/clusters/svc', 'data':
                get_node_json('deployment', 'svc', 'Applied',
                              '/deployments/enm/clusters/svc')}
        ]

        get_dbnodes = [
            {'path': '/deployments/enm/clusters/db/nodes/dbn1', 'data':
                get_node_json('node', 'dbn1', 'Applied',
                              '/deployments/enm/clusters/db/nodes/dbn1',
                              properties={'hostname': 'hdbn1'})},
            {'path': '/deployments/enm/clusters/db/nodes/dbn2', 'data':
                get_node_json('node', 'dbn2', 'Applied',
                              '/deployments/enm/clusters/db/nodes/dbn2',
                              properties={'hostname': 'hdbn2'})}
        ]

        get_svcnodes = [
            {'path': '/deployments/enm/clusters/svc/nodes/svcn1', 'data':
                get_node_json('node', 'svcn1', 'Applied',
                              '/deployments/enm/clusters/svc/nodes/svcn1',
                              properties={'hostname': 'hsvcn1'})}
        ]

        mock_model = {
            '/deployments': get_deployments,
            '/deployments/enm/clusters': get_clusters,
            '/deployments/enm/clusters/db/nodes': get_dbnodes,
            '/deployments/enm/clusters/svc/nodes': get_svcnodes
        }

        def mock_get_children(path):
            return mock_model[path]

        m_get_children.side_effect = mock_get_children

        clusters = Vcs._get_modeled_clusters()
        self.assertEqual(2, len(clusters))
        self.assertIn('db', clusters)
        self.assertListEqual(['hdbn1', 'hdbn2'], clusters['db'])
        self.assertIn('svc', clusters)
        self.assertListEqual(['hsvcn1'], clusters['svc'])

        clusters = Vcs._get_modeled_clusters(cluster_filter='svc')
        self.assertEqual(1, len(clusters))
        self.assertNotIn('db', clusters)
        self.assertIn('svc', clusters)
        self.assertListEqual(['hsvcn1'], clusters['svc'])

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.EnminstAgent.hasys_display')
    @patch('h_vcs.vcs_cli.EnminstAgent.hasys_state')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_node_states')
    def test_get_cluster_system_status_running(self,
                                               m_get_modeled_node_states,
                                               m_get_modeled_clusters,
                                               m_get_hostname_vcs_aliases,
                                               m_hasys_state,
                                               m_hasys_display,
                                               m_discover_peer_nodes):
        m_discover_peer_nodes.return_value = ['node1', 'node2']

        m_get_modeled_node_states.return_value = {
            'node1': LitpRestClient.ITEM_STATE_APPLIED,
            'node2': LitpRestClient.ITEM_STATE_APPLIED
        }
        m_get_modeled_clusters.side_effect = [{'cluster': ['node1', 'node2']}]
        m_get_hostname_vcs_aliases.return_value = ({}, {})

        m_hasys_state.return_value = (
            [],
            [{Vcs.H_NAME: 'node1', Vcs.H_SYSTEM_STATE: ['RUNNING']},
             {Vcs.H_NAME: 'node2', Vcs.H_SYSTEM_STATE: ['RUNNING']}]
        )

        m_hasys_display.return_value = {
            'node1': {'Frozen': '0', 'TFrozen': '0'},
            'node2': {'Frozen': '0', 'TFrozen': '0'}
        }

        _, data = Vcs.get_cluster_system_status()
        self.assertEqual(2, len(data))

        def assert_in_equal(key, datamap, value):
            self.assertIn(key, datamap)
            self.assertEqual(value, datamap[key])

        def assert_system(sysdata, sysname):
            assert_in_equal('Frozen', sysdata, '-')
            assert_in_equal('Cluster', sysdata, 'cluster')
            assert_in_equal('State', sysdata, VcsStates.RUNNING)
            assert_in_equal('System', sysdata, sysname)

        assert_system(data[0], 'node1')
        assert_system(data[1], 'node2')

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.EnminstAgent.hasys_display')
    @patch('h_vcs.vcs_cli.EnminstAgent.hasys_state')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_node_states')
    def test_get_cluster_system_status_exited(self,
                                              m_get_modeled_node_states,
                                              m_get_modeled_clusters,
                                              m_get_hostname_vcs_aliases,
                                              m_hasys_state,
                                              m_hasys_display,
                                              m_discover_peer_nodes):
        m_discover_peer_nodes.return_value = ['node1', 'node2']

        m_get_modeled_node_states.return_value = {
            'node1': LitpRestClient.ITEM_STATE_APPLIED,
            'node2': LitpRestClient.ITEM_STATE_APPLIED
        }
        m_get_modeled_clusters.side_effect = [{'cluster': ['node1', 'node2']}]
        m_get_hostname_vcs_aliases.return_value = ({}, {})

        m_hasys_state.return_value = (
            [],
            [{Vcs.H_NAME: 'node1', Vcs.H_SYSTEM_STATE: ['RUNNING']},
             {Vcs.H_NAME: 'node2', Vcs.H_SYSTEM_STATE: ['EXITED']}]
        )

        m_hasys_display.return_value = {
            'node1': {'Frozen': '0', 'TFrozen': '0'},
            'node2': {'Frozen': '0', 'TFrozen': '0'}
        }

        _, data = Vcs.get_cluster_system_status()
        self.assertEqual(2, len(data))

        def assert_in_equal(key, datamap, value):
            self.assertIn(key, datamap)
            self.assertEqual(value, datamap[key])

        def assert_system(sysdata, sysname, state):
            assert_in_equal('Frozen', sysdata, '-')
            assert_in_equal('Cluster', sysdata, 'cluster')
            assert_in_equal('State', sysdata, state)
            assert_in_equal('System', sysdata, sysname)

        assert_system(data[0], 'node1', VcsStates.RUNNING)
        assert_system(data[1], 'node2', VcsStates.EXITED)

    @patch('h_vcs.vcs_cli.report_tab_data')
    @patch('h_vcs.vcs_cli.Vcs.write_csv')
    @patch('h_vcs.vcs_cli.Vcs.get_cluster_system_status')
    def test_verify_cluster_system_status(self,
                                          m_get_cluster_system_status,
                                          m_write_csv,
                                          m_report_tab_data):
        headers = ['System', 'State', 'Cluster', 'Frozen']
        data = [{
            'Frozen': '-', 'Cluster': 'c1',
            'State': 'RUNNING', 'System': 's1'}]

        m_get_cluster_system_status.side_effect = [
            (headers, data)
        ]
        Vcs.verify_cluster_system_status(None, None, sort_keys=Vcs.H_SYSTEM)
        self.assertTrue(m_report_tab_data.called)

        m_get_cluster_system_status.reset_mock()
        m_get_cluster_system_status.side_effect = [
            (headers, [{
                'Frozen': '-', 'Cluster': 'c1',
                'State': 'Undefined', 'System': 's1'}])
        ]
        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_system_status(None, None)
        self.assertEqual(ExitCodes.VCS_INVALID_STATE, sysexit.exception.code)

        m_get_cluster_system_status.reset_mock()
        m_report_tab_data.reset_mock()
        m_write_csv.reset_mock()
        m_get_cluster_system_status.side_effect = [
            (headers, data)
        ]
        Vcs.verify_cluster_system_status(None, None, csvfile='cc')
        self.assertFalse(m_report_tab_data.called)
        self.assertTrue(m_write_csv.called)

        data = [{
            'Frozen': '-', 'Cluster': 'c2',
            'State': 'LEAVING', 'System': 's1'}]
        m_get_cluster_system_status.reset_mock()
        m_report_tab_data.reset_mock()
        m_write_csv.reset_mock()
        m_get_cluster_system_status.side_effect = [
            (headers, data)
        ]
        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_system_status(None, None)
        self.assertNotEqual(sysexit.exception,
                            ExitCodes.VCS_INVALID_STATE)

    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch('h_util.h_utils.Popen')
    @patch('h_vcs.vcs_cli.Vcs.get_litp_client')
    def test_vcs_locked_systems(self, m_get_litp_client,
                                m_popen,
                                m_run_rpc_command):
        m_popen.return_value.returncode = 0
        m_popen.return_value.communicate.return_value = \
            ('svc-1\nsvc-2\ntest-ms-1', None)

        svc_1_frozen = 0
        svc_1_tfrozen = 0
        svc_2_frozen = 0
        svc_2_tfrozen = 0

        def stubbed_run_rpc_command(nodes, agent, action,
                                    action_kwargs=None,
                                    timeout=None, retries=0):
            if 'hasys_state' == action:
                return {
                    'svc-1': {'errors': '', 'data': {
                        'retcode': 0, 'err': '',
                        'out': '#System    Attribute             Value\n'
                               'svc-1 SysState              {0}\n'
                               'svc-2 SysState              {0}'.format(
                                Vcs.SYSTEM_STATE_RUNNING)
                    }},
                    'svc-2': {'errors': '', 'data': {
                        'retcode': 0, 'err': '',
                        'out': '#System    Attribute             Value\n'
                               'svc-1 SysState              {0}\n'
                               'svc-2 SysState              {0}'.format(
                                Vcs.SYSTEM_STATE_RUNNING)
                    }}
                }
            elif 'hasys_display' == action:
                return {'svc-1': {
                    'errors': '',
                    'data': {
                        'retcode': 0,
                        'err': '',
                        'out': {
                            'svc-1':
                                '#System    Attribute             Value\n'
                                'svc-1 Frozen                {0}\n'
                                'svc-1 TFrozen               {1}'.format(
                                        svc_1_frozen, svc_1_tfrozen),
                            'svc-2':
                                '#System    Attribute             Value\n'
                                'svc-2 Frozen                {0}\n'
                                'svc-2 TFrozen               {1}'.format(
                                        svc_2_frozen, svc_2_tfrozen)
                        }
                    }
                }}
            raise Exception('Missed implementation!!!!')

        m_run_rpc_command.side_effect = stubbed_run_rpc_command

        litpd = LitpIntegration()
        cluster_path = litpd.setup_svc_cluster()
        litpd.setup_cluster_node(cluster_path, 'svc-2')

        m_get_litp_client.return_value = litpd

        Vcs.verify_cluster_system_status(None, None, sort_keys=Vcs.H_SYSTEM)

        svc_1_frozen = 1
        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_system_status(None, None,
                                             sort_keys=Vcs.H_SYSTEM)
        self.assertEqual(ExitCodes.VCS_INVALID_STATE, sysexit.exception.code)

        svc_1_frozen = 0
        svc_1_tfrozen = 1
        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_system_status(None, None,
                                             sort_keys=Vcs.H_SYSTEM)
        self.assertEqual(ExitCodes.VCS_INVALID_STATE, sysexit.exception.code)

        svc_1_tfrozen = 0
        svc_2_frozen = 1
        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_system_status(None, None,
                                             sort_keys=Vcs.H_SYSTEM)
        self.assertEqual(ExitCodes.VCS_INVALID_STATE, sysexit.exception.code)

        svc_2_frozen = 0
        svc_2_tfrozen = 1
        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_system_status(None, None,
                                             sort_keys=Vcs.H_SYSTEM)
        self.assertEqual(ExitCodes.VCS_INVALID_STATE, sysexit.exception.code)

        svc_2_tfrozen = 0
        litpd.setup_cluster_node(cluster_path, 'ebs-1',
                                 state=LitpRestClient.ITEM_STATE_INITIAL)
        with self.assertRaises(SystemExit) as sysexit:
            Vcs.verify_cluster_system_status(None, None,
                                             sort_keys=Vcs.H_SYSTEM)
        self.assertEqual(ExitCodes.VCS_INVALID_STATE, sysexit.exception.code)


    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_freeze')
    def test_freeze_group(self, m_hagrp_freeze, m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'msap',
                Vcs.H_SYSTEM: 'atrcxb1234',
                Vcs.H_CLUSTER: 'c1',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED]
            }
        ]

        vcs = Vcs()
        vcs.freeze_group('msap', False, group_system='atrcxb1234')
        m_hagrp_freeze.assert_has_calls([
            call('msap', 'atrcxb1234', persistent=False)],
                any_order=True)

        m_hagrp_freeze.reset_mock()
        vcs.freeze_group('msap', True, group_system='atrcxb1234')
        m_hagrp_freeze.assert_has_calls([
            call('msap', 'atrcxb1234', persistent=True)],
                any_order=True)

    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_freeze')
    def test_freeze_group_no_system(self, m_hagrp_freeze, m_get_action_groups,
                                    m_get_hostname_vcs_aliases):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'msap',
                Vcs.H_SYSTEM: 'atrcxb1234',
                Vcs.H_CLUSTER: 'c1',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED]
            }
        ]

        mock_object = LitpObject(None, {}, None)
        mock_object._id = 'msap'
        mock_object._properties = {'node_list': 'svc-1'}
        m_get_hostname_vcs_aliases.return_value = ({}, {'svc-1': 'atrcxb1234'})

        vcs = Vcs()
        vcs.freeze_group('msap', False)
        m_hagrp_freeze.assert_has_calls([
            call('msap', 'atrcxb1234', persistent=False)],
                any_order=True)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_freeze')
    def test_freeze_group_mco_error(self, m_hagrp_freeze, m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'msap',
                Vcs.H_SYSTEM: 'atrcxb1234',
                Vcs.H_CLUSTER: 'c1',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED]
            }
        ]
        m_hagrp_freeze.side_effect = McoAgentException()

        vcs = Vcs()
        self.assertRaises(McoAgentException, vcs.freeze_group, 'group',
                          False, 'atrcxb1234')

        m_hagrp_freeze.reset_mock()
        m_hagrp_freeze.side_effect = McoAgentException(
                str(VcsCodes.V_16_1_40200))
        try:
            vcs.freeze_group('group', False, 'atrcxb1234')
        except Exception:
            self.fail('No exception expected!')

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_unfreeze')
    def test_unfreeze_group(self, m_hagrp_unfreeze, m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'msap',
                Vcs.H_SYSTEM: 'atrcxb1234',
                Vcs.H_CLUSTER: 'c1',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED]
            }
        ]

        vcs = Vcs()
        vcs.unfreeze_group('msap', False, group_system='atrcxb1234')
        m_hagrp_unfreeze.assert_has_calls([
            call('msap', 'atrcxb1234', persistent=False)],
                any_order=True)

        m_hagrp_unfreeze.reset_mock()
        vcs.unfreeze_group('msap', True, group_system='atrcxb1234')
        m_hagrp_unfreeze.assert_has_calls([
            call('msap', 'atrcxb1234', persistent=True)],
                any_order=True)

    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_unfreeze')
    def test_unfreeze_group_no_system(self, m_hagrp_unfreeze,
                                      m_get_action_groups,
                                      m_get_hostname_vcs_aliases):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'msap',
                Vcs.H_SYSTEM: 'atrcxb1234',
                Vcs.H_CLUSTER: 'c1',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED]
            }
        ]

        mock_object = LitpObject(None, {}, None)
        mock_object._id = 'msap'
        mock_object._properties = {'node_list': 'svc-1'}
        m_get_hostname_vcs_aliases.return_value = ({}, {'svc-1': 'atrcxb1234'})

        vcs = Vcs()
        vcs.unfreeze_group('msap', False)
        m_hagrp_unfreeze.assert_has_calls([
            call('msap', 'atrcxb1234', persistent=False)],
                any_order=True)

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.EnminstAgent.hagrp_unfreeze')
    def test_unfreeze_group_mco_error(self, m_unhagrp_freeze,
                                      m_get_action_groups):
        m_get_action_groups.return_value = [
            {
                Vcs.H_NAME: 'msap',
                Vcs.H_SYSTEM: 'atrcxb1234',
                Vcs.H_CLUSTER: 'c1',
                Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE, VcsStates.FAULTED]
            }
        ]

        m_unhagrp_freeze.side_effect = McoAgentException()
        vcs = Vcs()
        self.assertRaises(McoAgentException, vcs.unfreeze_group, 'group',
                          False, 'atrcxb1234')

        m_unhagrp_freeze.reset_mock()
        m_unhagrp_freeze.side_effect = McoAgentException(
                str(VcsCodes.V_16_1_40201))
        try:
            vcs.unfreeze_group('group', False, 'atrcxb1234')
        except Exception:
            self.fail('No exception expected!')

    @patch('h_vcs.vcs_cli.Vcs._get_action_systems')
    def test_lock_bad_filter(self, m_get_action_systems):
        m_get_action_systems.return_value = []
        vcs = Vcs()
        self.assertRaises(VcsException, vcs.lock, 'sys1', 1)

    @patch('h_vcs.vcs_cli.Vcs.get_cluster_system_status')
    @patch('h_vcs.vcs_cli.Vcs._get_action_systems')
    def test_lock_sys_frozen(self, m_get_action_systems,
                             m_get_cluster_system_status):
        test_system = 'sys1'
        vcs = Vcs()

        m_get_action_systems.return_value = [test_system]
        headers = ['System', 'State', 'Cluster', 'Frozen']
        data = [{
            'Frozen': 'Perm', 'Cluster': 'c1', 'State':
                'RUNNING', 'System': test_system}]

        m_get_cluster_system_status.side_effect = [
            (headers, data)
        ]
        self.assertRaises(SystemExit, vcs.lock, test_system, 300)

    @patch('h_vcs.vcs_cli.Vcs.get_cluster_system_status')
    @patch('h_vcs.vcs_cli.Vcs._get_action_systems')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.mco_exec')
    def test_lock(self, m_mco_exec, m_get_action_systems,
                  m_get_cluster_system_status):
        test_system = 'sys1'
        vcs = Vcs()

        m_get_action_systems.return_value = [test_system]
        headers = ['System', 'State', 'Cluster', 'Frozen']
        data = [{
            'Frozen': '-', 'Cluster': 'c1', 'State':
                'RUNNING', 'System': test_system}]

        m_get_cluster_system_status.side_effect = [
            (headers, data)
        ]
        vcs.lock(test_system, 300)

        m_mco_exec.assert_has_calls([
            call('lock', ['sys=sys1', 'switch_timeout=300'], 'sys1')
        ])

    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_timeouts')
    @patch('h_vcs.vcs_cli.Vcs.get_cluster_group_status')
    @patch('h_vcs.vcs_cli.Vcs.get_cluster_system_status')
    @patch('h_vcs.vcs_cli.Vcs._get_action_systems')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.mco_exec')
    def test_lock_no_timeout(self, m_mco_exec, m_get_action_systems,
                             m_get_cluster_system_status,
                             m_get_cluster_group_status,
                             m_get_modeled_group_timeouts):
        test_system = 'sys1'
        vcs = Vcs()

        m_get_action_systems.return_value = [test_system]
        headers = ['System', 'State', 'Cluster', 'Frozen']
        data = [{
            'Frozen': '-', 'Cluster': 'c1', 'State':
                'RUNNING', 'System': test_system}]

        m_get_cluster_system_status.side_effect = [
            (headers, data)
        ]

        m_get_cluster_group_status.side_effect = [
            [(
                [Vcs._get_group_struct('c1',
                                       'gp_as_1',
                                       test_system,
                                       VCS_AVAIL_ACTIVE_STANDBY,
                                       VCS_GRP_SVS_STATE_ONLINE,
                                       Vcs.STATE_OK,
                                       False,
                                       False,
                                       '-'),
                 Vcs._get_group_struct('c1',
                                       'gp_as_2',
                                       test_system,
                                       VCS_AVAIL_ACTIVE_STANDBY,
                                       VCS_GRP_SVS_STATE_ONLINE,
                                       Vcs.STATE_OK,
                                       False,
                                       False,
                                       '-'),
                 Vcs._get_group_struct('c1',
                                       'gp_p',
                                       test_system,
                                       VCS_AVAIL_PARALLEL,
                                       VCS_GRP_SVS_STATE_ONLINE,
                                       Vcs.STATE_OK,
                                       False,
                                       False,
                                       '-')]
            ), []]]

        m_get_modeled_group_timeouts.return_value = {
            Vcs.H_ONLINE_TIMEOUT: '3', Vcs.H_OFFLINE_TIMEOUT: '5'}

        vcs.lock(test_system, -1)

        m_mco_exec.assert_has_calls([
            call('lock', ['sys=sys1', 'switch_timeout=10'], 'sys1')
        ])

    @patch('h_vcs.vcs_cli.Vcs._get_action_systems')
    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.mco_exec')
    def test_unlock(self, m_mco_exec, m_get_action_systems):
        test_system = 'sys1'
        m_get_action_systems.return_value = [test_system]
        vcs = Vcs()

        vcs.unlock(test_system, 30)

        m_mco_exec.assert_has_calls([
            call('unlock', ['sys=sys1', 'nic_wait_timeout=30'], 'sys1')
        ])

    @patch('h_vcs.vcs_cli.Vcs.verify_cluster_system_status')
    def test_main_systems(self, m_verify_cluster_system_status):
        main(['--systems'])
        self.assertTrue(m_verify_cluster_system_status.called)

    @patch('h_vcs.vcs_cli.Vcs.unfreeze_group')
    @patch('h_vcs.vcs_cli.Vcs.unfreeze_system')
    def test_main_unfreeze(self, m_unfreeze_system, m_unfreeze_group):
        main(['--unfreeze', '-g', 'g1'])
        self.assertTrue(m_unfreeze_group.called)
        self.assertFalse(m_unfreeze_system.called)

        m_unfreeze_group.reset_mock()
        m_unfreeze_system.reset_mock()
        main(['--unfreeze', '-s', 's1'])
        self.assertFalse(m_unfreeze_group.called)
        self.assertTrue(m_unfreeze_system.called)

        m_unfreeze_group.reset_mock()
        m_unfreeze_system.reset_mock()
        self.assertRaises(SystemExit, main, ['--unfreeze'])

    @patch('h_vcs.vcs_cli.Vcs.freeze_group')
    @patch('h_vcs.vcs_cli.Vcs.freeze_system')
    def test_main_freeze(self, m_freeze_system, m_freeze_group):
        main(['--freeze', '-g', 'g1'])
        self.assertTrue(m_freeze_group.called)
        self.assertFalse(m_freeze_system.called)

        m_freeze_group.reset_mock()
        m_freeze_system.reset_mock()
        main(['--freeze', '-s', 's1'])
        self.assertFalse(m_freeze_group.called)
        self.assertTrue(m_freeze_system.called)

        m_freeze_group.reset_mock()
        m_freeze_system.reset_mock()
        self.assertRaises(SystemExit, main, ['--freeze'])

    @patch('h_vcs.vcs_cli.Vcs.lock')
    def test_main_lock(self, m_lock):
        main(['--lock', '-s', 's1'])
        self.assertTrue(m_lock.called)

        m_lock.reset_mock()
        self.assertRaises(SystemExit, main, ['--lock'])

    @patch('h_vcs.vcs_cli.Vcs.unlock')
    def test_main_unlock(self, m_unlock):
        main(['--unlock', '-s', 's1'])
        self.assertTrue(m_unlock.called)

        m_unlock.reset_mock()
        self.assertRaises(SystemExit, main, ['--unlock'])

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    def test_get_cluster_group_status_SYS_EXIITED(self,
                                                  m_get_modeled_groups,
                                                  m_get_hostname_vcs_aliases,
                                                  m_get_modeled_group_types,
                                                  m_get_vcs_group_info,
                                                  m_discover_peer_nodes):
        cluster_name = 'c1'
        vcs_group_name = 'gp_par_ok'
        vcs_name = cluster_name + '_' + vcs_group_name

        mock_object = LitpObject(None, {}, None)
        mock_object._id = vcs_group_name
        mock_object._properties = {'node_list': 'svc-1,svc-2'}

        m_get_modeled_groups.return_value = (
            {},
            {cluster_name: {vcs_name: mock_object}}
        )
        m_get_hostname_vcs_aliases.return_value = (
            {'atrcxb1': 'svc-1', 'atrcbx2': 'svc-2'},
            {'svc-1': 'atrcxb1', 'svc-2': 'atrcxb2'}
        )
        m_discover_peer_nodes.return_value = ['atrcxb1', 'atrcxb2']
        m_get_modeled_group_types.return_value = {
            vcs_group_name: {'type': 'vm', 'node_list': ['svc-1', 'svc-2']}}

        m_get_vcs_group_info.side_effect = [
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10600)),
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10600))
        ]
        data, _ = Vcs.get_cluster_group_status()
        self.assertEqual(2, len(data))
        for row in data:
            self.assertEqual('-', row[Vcs.H_GROUP])
            self.assertEqual(Vcs.STATE_INVALID, row[Vcs.H_GROUP_STATE])
            self.assertEqual(VCS_NA, row[Vcs.H_TYPE])

        m_get_vcs_group_info.reset_mock()
        m_get_vcs_group_info.side_effect = [McoAgentException()]
        self.assertRaises(McoAgentException, Vcs.get_cluster_group_status)

        m_get_vcs_group_info.reset_mock()
        m_get_vcs_group_info.side_effect = [
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10600)),
            {vcs_name: CDATA_GP_PAR_INVALID}
        ]
        data, _ = Vcs.get_cluster_group_status(group_filter='c1_gp_par_ok')
        self.assertEqual(2, len(data))
        self.assertEqual('c1_gp_par_ok', data[0]['Group'])
        self.assertEqual('c1_gp_par_ok', data[1]['Group'])

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.EnminstAgent.hasys_state')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_node_states')
    def test_get_cluster_system_status_SYS_EXISTED(self,
                                                   m_get_modeled_node_states,
                                                   m_get_modeled_clusters,
                                                   m_get_hostname_vcs_aliases,
                                                   m_hasys_state,
                                                   m_discover_peer_nodes):
        m_get_modeled_clusters.return_value = m_clusters
        m_get_hostname_vcs_aliases.return_value = ({}, {})
        m_discover_peer_nodes.return_value = ['svc-1', 'svc-2']
        m_get_modeled_node_states.return_value = {
            'svc-1': LitpRestClient.ITEM_STATE_APPLIED,
            'svc-2': LitpRestClient.ITEM_STATE_APPLIED
        }

        m_hasys_state.side_effect = [
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10446)),
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10446))
        ]
        self.assertRaises(McoAgentException, Vcs.get_cluster_system_status)

        m_hasys_state.side_effect = [
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10600)),
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10600))
        ]
        _, data = Vcs.get_cluster_system_status()
        self.assertEqual(VcsStates.EXITED, data[0][Vcs.H_SYSTEM_STATE])
        self.assertEqual(VcsStates.EXITED, data[1][Vcs.H_SYSTEM_STATE])

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.EnminstAgent.hasys_state')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_node_states')
    def test_get_cluster_system_status_SYS_OFF(self,
                                               m_get_modeled_node_states,
                                               m_get_modeled_clusters,
                                               m_get_hostname_vcs_aliases,
                                               m_hasys_state,
                                               m_discover_peer_nodes):
        m_discover_peer_nodes.return_value = ['svc-1', 'svc-2']
        m_get_modeled_node_states.return_value = {
            'svc-1': LitpRestClient.ITEM_STATE_APPLIED,
            'svc-2': LitpRestClient.ITEM_STATE_APPLIED
        }
        m_get_modeled_clusters.return_value = m_clusters
        m_get_hostname_vcs_aliases.return_value = ({}, {})

        m_hasys_state.side_effect = [
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10011)),
            McoAgentException(VcsCodes.to_string(VcsCodes.V_16_1_10011))
        ]
        _, data = Vcs.get_cluster_system_status()
        self.assertEqual(VcsStates.POWERED_OFF, data[0][Vcs.H_SYSTEM_STATE])
        self.assertEqual(VcsStates.POWERED_OFF, data[1][Vcs.H_SYSTEM_STATE])

    @patch('h_vcs.vcs_cli.screen')
    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_node_states')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    def test_get_cluster_system_status_empty(self,
                                             m_get_hostname_vcs_aliases,
                                             m_get_modeled_node_states,
                                             m_get_modeled_clusters,
                                             m_discover_peer_nodes,
                                             m_screen):

        m_get_hostname_vcs_aliases.return_value = [{'a': 0}, {'b': 0}]

        m_discover_peer_nodes.return_value = []

        m_get_modeled_node_states.return_value = {
            'node1': LitpRestClient.ITEM_STATE_APPLIED,
            'node2': LitpRestClient.ITEM_STATE_APPLIED,
            'node3': LitpRestClient.ITEM_STATE_APPLIED,
            'node4': LitpRestClient.ITEM_STATE_APPLIED,
        }

        m_get_modeled_clusters.return_value = {'c1': ['node1', 'node2'],
                                               'c2': ['node3', 'node4']}

        _, data = Vcs().get_cluster_system_status()

        calls = [call('WARNING: 0 peer nodes found.'),
                 call('WARNING: MCO undiscovered cluster host node3'),
                 call('WARNING: MCO undiscovered cluster host node4'),
                 call('WARNING: Could not get any system information '
                      'from any systems belonging to the cluster c2: node3, node4'),
                 call('WARNING: MCO undiscovered cluster host node1'),
                 call('WARNING: MCO undiscovered cluster host node2'),
                 call('WARNING: Could not get any system information '
                      'from any systems belonging to the cluster c1: node1, node2')]

        # check if the correct messages are outputed by the screen() function
        m_screen.assert_has_calls(calls, any_order=True)
        # check the number of nodes in in the cluster
        self.assertEqual(4, len(data))
        # check the correct number of calls to the screen() function
        self.assertEqual(7, m_screen.call_count)
        # check the correct node['State'] of the nodes in the cluster
        self.assertEqual(['N/A', 'N/A', 'N/A', 'N/A'],
                         [node['State'] for node in data])

        m_get_modeled_clusters.reset_mock()
        m_get_modeled_clusters.return_value = {'c1': ['node1'],
                                               'c2': ['node3', 'node4']}

        m_screen.reset_mock()

        _, data = Vcs().get_cluster_system_status()

        # check number of calls if a node is skipped
        calls = [call('WARNING: 0 peer nodes found.'),
                 call('WARNING: MCO undiscovered cluster host node3'),
                 call('WARNING: MCO undiscovered cluster host node4'),
                 call('WARNING: Could not get any system information '
                      'from any systems belonging to the cluster c2: node3, node4'),
                 call('WARNING: MCO undiscovered cluster host node1'),
                 # call('WARNING: MCO undiscovered cluster host node2'),
                 call('WARNING: Could not get any system information '
                      'from any systems belonging to the cluster c1: node1')]

        # check if the correct messages are outputed by the screen() function
        m_screen.assert_has_calls(calls, any_order=True)
        # # check the number of nodes in in the cluster
        self.assertEqual(3, len(data))
        # check the correct number of calls to the screen() function
        self.assertEqual(6, m_screen.call_count)
        # check the correct node['State'] of the nodes in the cluster
        self.assertEqual(['N/A', 'N/A', 'N/A'],
                         [node['State'] for node in data])

    @patch('h_vcs.vcs_cli.Vcs.get_cluster_group_status')
    def test_is_sg_persistently_frozen(
            self, m_vcs_group_status):

        neo4j_cluster_information = [{'ServiceState': u'OFFLINE', \
                                      'Cluster': u'db_cluster', 'ServiceType': 'lsb', \
                                      'Group': u'Grp_CS_db_cluster_sg_neo4j_clustered_service', \
                                      'GroupState': 'Invalid', \
                                      'HAType': 'active-standby', 'Frozen': 'Perm', 'Uptime': '-', \
                                      'System': u'ieatrcxb1111'}, \
                                     {'ServiceState': u'OFFLINE', 'Cluster': u'db_cluster', 'ServiceType': 'lsb', \
                                      'Group': u'Grp_CS_db_cluster_sg_neo4j_clustered_service', \
                                      'GroupState': 'Invalid', \
                                      'HAType': 'active-standby', 'Frozen': 'Perm', 'Uptime': '-', \
                                      'System': u'ieatrcxb2222'}]

        headers = list(Vcs.VCS_GROUP_TABLE_HEADERS)
        m_vcs_group_status.return_value = neo4j_cluster_information, headers
        isFrozen = Vcs.is_sg_persistently_frozen(Vcs.ENM_DB_CLUSTER_NAME,
                                      '.*neo4j_clustered_service')
        self.assertTrue(isFrozen)

    def test_to_model_name(self):

        def assert_name(cluster, group):
            vname = '{0}{1}_{2}'.format(Vcs.VCS_GROUPNAME_PREFIX, cluster,
                                        group)
            self.assertEqual(group, Vcs._to_model_name(cluster, vname))

        assert_name('cluster', 'gp1')
        assert_name('cluster', 'gp1-nb')

    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_timeouts')
    @patch('h_vcs.vcs_utils.EnminstAgent.hagrp_state')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    def test_get_action_groups(self, m_get_modeled_clusters,
                               m_get_modeled_groups,
                               m_hagrp_state,
                               m_timeouts):
        m_timeouts.return_value = {Vcs.H_ONLINE_TIMEOUT: '600',
                                   Vcs.H_OFFLINE_TIMEOUT: '600'}
        node_list = ['svc-1', 'svc-2']
        cluster_name = 'svc_cluster'
        model_name = 'msap'
        vcs_name = 'Grp_CS_{0}_{1}'.format(cluster_name, model_name)
        clusters = {cluster_name: node_list}

        def proxy_get_modeled_clusters(cname):
            if 'non' == cname:
                return {}
            else:
                return clusters

        # m_get_modeled_clusters.return_value = {cluster_name: node_list}
        m_get_modeled_clusters.side_effect = proxy_get_modeled_clusters

        mock_object = LitpObject(None, {}, None)
        mock_object._id = model_name
        mock_object._properties = {'node_list': ','.join(node_list),
                                   'active': '1', 'standby': '1'}
        all_groups_modelid = {cluster_name: {model_name: mock_object}}
        all_groups_vcsid = {
            cluster_name: {vcs_name: mock_object}}
        m_get_modeled_groups.return_value = (all_groups_modelid,
                                             all_groups_vcsid)

        def proxy_m_get_group_info(mco_host):
            return {}, [
                {'State': ['ONLINE'], 'Name': vcs_name, 'System': 'svc-1'},
                {'State': ['ONLINE'], 'Name': vcs_name, 'System': 'svc-2'}
            ]

        m_hagrp_state.side_effect = proxy_m_get_group_info

        vcs = Vcs()
        groups = vcs._get_action_groups(vcs_name, 'svc-1', cluster_name)
        self.assertEqual(1, len(groups))
        self.assertEqual(cluster_name, groups[0][Vcs.H_CLUSTER])
        self.assertEqual(vcs_name, groups[0][Vcs.H_NAME])
        self.assertEqual('svc-1', groups[0][Vcs.H_SYSTEM])
        self.assertEqual(['ONLINE'], groups[0][Vcs.H_SYSTEM_STATE])

        mock_object._properties['active'] = '2'
        mock_object._properties['standby'] = '0'
        groups = vcs._get_action_groups(vcs_name, None, cluster_name)
        self.assertEqual(2, len(groups))

        mock_object._properties['active'] = '2'
        mock_object._properties['standby'] = '0'
        mock_object._properties['dependency'] = '2'
        groups = vcs._get_action_groups(vcs_name, 'svc-2', cluster_name)
        self.assertEqual(1, len(groups))

        self.assertRaises(SystemExit, vcs._get_action_groups, vcs_name,
                          'svc-2', 'non')

        self.assertRaises(SystemExit, vcs._get_action_groups, vcs_name,
                          'svc-3', cluster_name)

        m_search_for_groups = MagicMock()
        m_search_for_groups.return_value = []
        vcs._search_for_groups = m_search_for_groups
        self.assertRaises(SystemExit, vcs._get_action_groups, vcs_name,
                          'svc-2', cluster_name)

    def test__search_for_groups_notfound(self):
        vcs = Vcs()
        mco_cluster_data = [
            {'State': ['ONLINE'], 'Name': 'vcsname', 'System': 'svc-1'},
            {'State': ['ONLINE'], 'Name': 'vcsname', 'System': 'svc-2'}
        ]
        self.assertRaises(VcsException, vcs._search_for_groups,
                          'cluster1', 'vcsname', ['svc-1'], {'cluster1': []},
                          mco_cluster_data)

    def test_filter_activestandby(self):
        check_group1 = {
            Vcs.H_NAME: 'cg',
            Vcs.H_SYSTEM: 'cg-s1',
            Vcs.H_TYPE: VCS_AVAIL_ACTIVE_STANDBY,
            Vcs.H_SYSTEM_STATE: [VcsStates.ONLINE]
        }
        check_group2 = {
            Vcs.H_NAME: 'cg',
            Vcs.H_SYSTEM: 'cg-s2',
            Vcs.H_TYPE: VCS_AVAIL_ACTIVE_STANDBY,
            Vcs.H_SYSTEM_STATE: [VcsStates.OFFLINE]
        }
        self.assertFalse(Vcs.filter_activestandby([check_group2],
                                                  check_group1))
        self.assertFalse(Vcs.filter_activestandby([check_group1],
                                                  check_group1))

    @patch('h_vcs.vcs_cli.Vcs._get_action_groups')
    @patch('h_vcs.vcs_cli.Vcs.wait_vcs_state')
    def test_online_wait(self, m_wait_vcs_state, m_get_action_groups):
        m_wait_vcs_state.return_value = (True, None)
        m_get_action_groups.return_value = []

        vcs = Vcs()

        self.assertEqual((True, None), vcs.online_wait('', '', '', 1, ''))

        e = McoAgentException(str(VcsCodes.V_16_1_40156))
        m_wait_vcs_state.side_effect = e
        self.assertEqual((False, str(e)),
                         vcs.online_wait('', '',
                                         VCS_AVAIL_ACTIVE_STANDBY, 1, ''))

        m_get_action_groups.return_value = [
            {Vcs.H_SYSTEM: 's1'},
            {Vcs.H_SYSTEM: 's2'}
        ]
        e = McoAgentException(str(VcsCodes.V_16_1_40156))
        m_wait_vcs_state.side_effect = e
        self.assertEqual((True, None),
                         vcs.online_wait('', 's1',
                                         VCS_AVAIL_ACTIVE_STANDBY, 1,
                                         ''))

        e = McoAgentException(str(VcsCodes.V_16_1_40156))
        m_wait_vcs_state.side_effect = e
        self.assertEqual((False, str(e)),
                         vcs.online_wait('', '',
                                         VCS_AVAIL_PARALLEL, 1, ''))

        e = McoAgentException(str(VcsCodes.V_16_1_40201))
        m_wait_vcs_state.side_effect = e
        self.assertEqual((False, str(e)),
                         vcs.online_wait('', '',
                                         VCS_AVAIL_PARALLEL, 1, ''))

    @patch('h_vcs.vcs_cli.VcsCmdApiAgent.hagrp_wait')
    def test_wait_vcs_state(self, m_hagrp_wait):
        vcs = Vcs()
        ok, error = vcs.wait_vcs_state('group', 'system', 'ONLINE', 1)
        self.assertEqual((True, None), (ok, error))

        m_hagrp_wait.side_effect = McoAgentException(VcsCodes.V_16_1_10805)
        ok, error = vcs.wait_vcs_state('group', 'system', 'ONLINE', 1)
        self.assertFalse(ok)
        self.assertTrue('Timedout' in error)

        m_hagrp_wait.side_effect = McoAgentException(VcsCodes.V_16_1_10191)
        ok, error = vcs.wait_vcs_state('group', 'system', 'ONLINE', 1)
        self.assertEqual((False, str), (ok, type(error)))

        m_hagrp_wait.side_effect = IOError('')
        ok, error = vcs.wait_vcs_state('group', 'system', 'ONLINE', 1)
        self.assertEqual((False, str), (ok, type(error)))

    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    @patch('h_vcs.vcs_cli.EnminstAgent.hasys_freeze')
    def test_freeze_system(self, m_hasys_freeze, m_get_modeled_clusters):
        m_get_modeled_clusters.return_value = {'cluster': ['node1', 'node2']}
        vcs = Vcs()

        vcs.freeze_system('node1', False)
        self.assertEqual(1, m_hasys_freeze.call_count)
        m_hasys_freeze.assert_has_calls([
            call('node1', False, False)
        ], any_order=True)

        m_hasys_freeze.reset_mock()
        vcs.freeze_system('node1', True)
        self.assertEqual(1, m_hasys_freeze.call_count)
        m_hasys_freeze.assert_has_calls([
            call('node1', True, False)
        ], any_order=True)

        m_hasys_freeze.reset_mock()
        vcs.freeze_system('node1', True, True)
        self.assertEqual(1, m_hasys_freeze.call_count)
        m_hasys_freeze.assert_has_calls([
            call('node1', True, True)
        ], any_order=True)

        m_hasys_freeze.reset_mock()
        vcs.freeze_system('node*', True)
        self.assertEqual(2, m_hasys_freeze.call_count)
        m_hasys_freeze.assert_has_calls([
            call('node1', True, False),
            call('node2', True, False),
        ], any_order=True)

        m_hasys_freeze.reset_mock()
        m_hasys_freeze.side_effect = McoAgentException(
                str(VcsCodes.V_16_1_40206))
        try:
            vcs.freeze_system('node*', True)
        except McoAgentException as e:
            self.fail('No exception expected {0}'.format(e))

        m_hasys_freeze.reset_mock()
        m_hasys_freeze.side_effect = McoAgentException('gooooooo')
        self.assertRaises(McoAgentException, vcs.freeze_system,
                          'node*', True)

    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    @patch('h_vcs.vcs_cli.EnminstAgent.hasys_unfreeze')
    def test_unfreeze_system(self, m_hasys_unfreeze, m_get_modeled_clusters):
        m_get_modeled_clusters.return_value = {'cluster': ['node1', 'node2']}
        vcs = Vcs()

        vcs.unfreeze_system('node1', False)
        self.assertEqual(1, m_hasys_unfreeze.call_count)
        m_hasys_unfreeze.assert_has_calls([
            call('node1', False)
        ], any_order=True)

        m_hasys_unfreeze.reset_mock()
        vcs.unfreeze_system('node1', True)
        self.assertEqual(1, m_hasys_unfreeze.call_count)
        m_hasys_unfreeze.assert_has_calls([
            call('node1', True)
        ], any_order=True)

        m_hasys_unfreeze.reset_mock()
        vcs.unfreeze_system('node*', True)
        self.assertEqual(2, m_hasys_unfreeze.call_count)
        m_hasys_unfreeze.assert_has_calls([
            call('node1', True),
            call('node2', True),
        ], any_order=True)

        m_hasys_unfreeze.reset_mock()
        m_hasys_unfreeze.side_effect = McoAgentException(
                str(VcsCodes.V_16_1_40204))
        try:
            vcs.unfreeze_system('node*', True)
        except McoAgentException as e:
            self.fail('No exception expected {0}'.format(e))

        m_hasys_unfreeze.reset_mock()
        m_hasys_unfreeze.side_effect = McoAgentException('gooooooo')
        self.assertRaises(McoAgentException, vcs.unfreeze_system,
                          'node*', True)

    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    def test_node_name_to_vcs_system(self,
                                     m_get_hostname_vcs_aliases):
        m_get_hostname_vcs_aliases.return_value = (
            {"system": "db-2"}, {"db-2": "system"})

        system = Vcs.node_name_to_vcs_system('db-2')

        self.assertEqual('system', system)

    def test_add_regex_filter(self):
        vcs = Vcs()
        self.assertEqual(['^svc1$', '^svc10$', '^svc2$', '^svc3$'],
            vcs._add_regex_filter(['svc1', '^svc10$', '^svc2', 'svc3$']))

    @patch('h_vcs.vcs_cli.Vcs._get_modeled_clusters')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    @patch('h_vcs.vcs_cli.get_group_info')
    def test_search_for_groups_regex_delimiters(self, ggi, gmg, gmc):
        gmc.return_value = {'cluster': ['node1', 'node2']}

        def side_effect(something, something_else=None):
            if something == 'active' or something == 'standby':
                return 1
            elif something == 'node_list':
                return 'node1,node2'

        mock_object = LitpObject(MagicMock(), MagicMock(), MagicMock())
        mock_object._id = 'Grp_CS_cluster_Vcs_Group'
        mock_object._properties = {'node_list': ','.join(['node1', 'node2'])}
        mock_object.get_property = MagicMock(side_effect=side_effect)
        gmg.return_value = ({'cluster': {'Vcs_Group': mock_object}}, {})

        ggi.return_value = ({}, [
                {'State': ['ONLINE'],
                 'Name': 'Grp_CS_cluster_Vcs_Group',
                 'System': 'node1'},
                {'State': ['ONLINE'],
                 'Name': 'Grp_CS_cluster_Vcs_Group',
                 'System': 'node2'}]
        )

        self.assertEqual([{'Cluster': 'cluster',
                           'Dependencies': [],
                           'HAType': 'active-standby',
                           'Name': 'Grp_CS_cluster_Vcs_Group',
                           'State': ['ONLINE'],
                           'System': 'node1',
                           'offline_retry': None,
                           'offline_timeout': None,
                           'online_retry': None,
                           'online_timeout': None
                           }],
            Vcs()._get_action_groups(
                'Grp_CS_cluster_Vcs_Group', '^node1$', 'cluster'
            )
        )
