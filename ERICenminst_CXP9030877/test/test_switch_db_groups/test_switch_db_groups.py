import sys
import unittest2
from mock import patch, MagicMock, call

if sys.platform.lower().startswith('win'):
    sys.modules['pwd'] = MagicMock()

from switch_db_groups import switch_dbcluster_groups, \
    _is_sg_failover_supported

ONE_SYSTEM = (['System', 'State', 'Cluster', 'Frozen'],
              [{'Frozen': '-', 'Cluster': u'db_cluster',
                'State': 'RUNNING',
                'System': u'ieatrcxb3808-1'}])

TWO_SYSTEMS = (['System', 'State', 'Cluster', 'Frozen'],
               [{'Frozen': '-', 'Cluster': u'db_cluster',
                 'State': 'RUNNING', 'System': u'ieatrcxb3808-1'},
                {'Frozen': '-', 'Cluster': u'db_cluster',
                 'State': 'RUNNING', 'System': u'ieatrcxb3809-1'}])

VERSANT_SWITCH_GROUPS = \
    ([{'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_jms_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_jms_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_opendj_clustered_service',
       'GroupState': 'Invalid', 'HAType': 'parallel',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_postgres_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_postgres_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_elasticsearch_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_elasticsearch_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_versant_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_versant_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'}], [])

NEO4J_SWITCH_GROUPS = \
    ([{'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_jms_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_jms_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_opendj_clustered_service',
       'GroupState': 'Invalid', 'HAType': 'parallel',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_postgres_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_postgres_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_elasticsearch_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_elasticsearch_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_versant_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3808-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_versant_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'},
      {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
       'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
       'GroupState': 'OK', 'HAType': 'active-standby',
       'System': 'ieatrcxb3809-1'}], [])

VERSANT_OFFLINE = ([{'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
                     'Group': 'Grp_CS_db_cluster_versant_clustered_service',
                     'GroupState': 'OK', 'HAType': 'active-standby',
                     'System': 'ieatrcxb3808-1'},
                    {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
                     'Group': 'Grp_CS_db_cluster_versant_clustered_service',
                     'GroupState': 'OK', 'HAType': 'active-standby',
                     'System': 'ieatrcxb3809-1'}], [])

VERSANT_ONLINE = ([{'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
                    'Group': 'Grp_CS_db_cluster_versant_clustered_service',
                    'GroupState': 'OK', 'HAType': 'active-standby',
                    'System': 'ieatrcxb3808-1'},
                   {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
                    'Group': 'Grp_CS_db_cluster_versant_clustered_service',
                    'GroupState': 'OK', 'HAType': 'active-standby',
                    'System': 'ieatrcxb3809-1'}], [])

NEO4J_ONLINE = ([{'ServiceState': 'ONLINE', 'Cluster': u'db_cluster',
                  'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
                  'GroupState': 'OK', 'HAType': 'active-standby',
                  'System': 'ieatrcxb3808-1'},
                 {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
                  'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
                  'GroupState': 'OK', 'HAType': 'active-standby',
                  'System': 'ieatrcxb3809-1'}], [])


NEO4J_OFFLINE = ([{'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
                   'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
                   'GroupState': 'OK', 'HAType': 'active-standby',
                   'System': 'ieatrcxb3808-1'},
                  {'ServiceState': 'OFFLINE', 'Cluster': u'db_cluster',
                   'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
                   'GroupState': 'OK', 'HAType': 'active-standby',
                   'System': 'ieatrcxb3809-1'}], [])


class TestDBClusterSGDistribution(unittest2.TestCase):

    @patch('switch_db_groups.Vcs')
    @patch('switch_db_groups.is_env_on_rack')
    def test_failover_not_supported(self, is_rack, vcs):
        is_rack.return_value = False
        vcs.return_value.get_cluster_system_status.return_value = ONE_SYSTEM

        res = _is_sg_failover_supported(vcs.return_value)
        self.assertEquals(res, False)
        switch_dbcluster_groups()
        vcs.return_value.get_cluster_system_status.assert_called_with(
            'db_cluster')

    @patch('switch_db_groups.Vcs')
    @patch('switch_db_groups.is_env_on_rack')
    def test_versant_offline_on_all_nodes(self, is_rack, vcs):
        is_rack.return_value = False
        vcs.H_SERVICE_STATE = 'ServiceState'
        vcs.H_SYSTEM = 'System'
        vcs.H_GROUP = 'Group'
        vcs.H_TYPE = 'HAType'
        vcs.return_value.get_cluster_system_status.return_value = TWO_SYSTEMS
        vcs.return_value.get_cluster_group_status.return_value = \
            VERSANT_OFFLINE

        self.assertRaises(SystemExit, switch_dbcluster_groups)

    @patch('switch_db_groups.Vcs')
    @patch('switch_db_groups.is_env_on_rack')
    def test_switch_dbcluster_groups(self, is_rack, vcs):
        is_rack.return_value = False
        vcs.H_SERVICE_STATE = 'ServiceState'
        vcs.H_SYSTEM = 'System'
        vcs.H_GROUP = 'Group'
        vcs.H_TYPE = 'HAType'
        vcs.return_value.get_cluster_system_status.return_value = TWO_SYSTEMS
        vcs.return_value.get_cluster_group_status.side_effect = [
            VERSANT_ONLINE, VERSANT_SWITCH_GROUPS]

        switch_dbcluster_groups()
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_jms_clustered_service',
            'ieatrcxb3809-1', 'db_cluster', timeout=-1)

    @patch('switch_db_groups.Vcs')
    @patch('switch_db_groups.is_env_on_rack')
    def test_alphabetic_switch_dbcluster_groups(self, is_rack, vcs):
        is_rack.return_value = False
        vcs.H_SERVICE_STATE = 'ServiceState'
        vcs.H_SYSTEM = 'System'
        vcs.H_GROUP = 'Group'
        vcs.H_TYPE = 'HAType'
        vcs.return_value.get_cluster_system_status.return_value = TWO_SYSTEMS
        vcs.return_value.get_cluster_group_status.side_effect = [
            VERSANT_ONLINE, VERSANT_SWITCH_GROUPS]

        switch_dbcluster_groups()
        expected_calls = [
            call(),
            call().get_cluster_system_status('db_cluster'),
            call().get_cluster_group_status(
                verbose=False,
                group_filter='sg_neo4j_clustered_service',
                cluster_filter='db_cluster'),
            call().get_cluster_group_status(
                verbose=False,
                cluster_filter='db_cluster'),
            call(),
            call().hagrp_switch(
                'Grp_CS_db_cluster_elasticsearch_clustered_service',
                'ieatrcxb3809-1',
                'db_cluster',
                timeout=-1),
            call().hagrp_switch(
                'Grp_CS_db_cluster_jms_clustered_service',
                'ieatrcxb3809-1',
                'db_cluster',
                timeout=-1),
            call().hagrp_switch(
                'Grp_CS_db_cluster_postgres_clustered_service',
                'ieatrcxb3809-1',
                'db_cluster',
                timeout=-1)
        ]

    @patch('switch_db_groups.Vcs')
    @patch('switch_db_groups.is_env_on_rack')
    def test_switch_dbcluster_groups_failure(self, is_rack, vcs):
        is_rack.return_value = False
        vcs.H_SERVICE_STATE = 'ServiceState'
        vcs.H_SYSTEM = 'System'
        vcs.H_GROUP = 'Group'
        vcs.H_TYPE = 'HAType'
        vcs.return_value.get_cluster_system_status.return_value = TWO_SYSTEMS
        vcs.return_value.get_cluster_group_status.side_effect = [
            VERSANT_ONLINE, VERSANT_SWITCH_GROUPS]

        vcs.return_value.hagrp_switch.side_effect = SystemExit()
        self.assertRaises(SystemExit, switch_dbcluster_groups)

    @patch('switch_db_groups.Vcs')
    @patch('switch_db_groups.is_env_on_rack')
    def test_neo4j_switch_dbcluster_groups(self, is_rack, vcs):
        is_rack.return_value = False
        vcs.H_SERVICE_STATE = 'ServiceState'
        vcs.H_SYSTEM = 'System'
        vcs.H_GROUP = 'Group'
        vcs.H_TYPE = 'HAType'
        vcs.return_value.get_cluster_system_status.return_value = TWO_SYSTEMS
        vcs.return_value.get_cluster_group_status.side_effect = [
            NEO4J_ONLINE, NEO4J_SWITCH_GROUPS]

        switch_dbcluster_groups()
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_jms_clustered_service',
            'ieatrcxb3809-1', 'db_cluster', timeout=-1)
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_postgres_clustered_service',
            'ieatrcxb3809-1', 'db_cluster', timeout=-1)

    @patch('switch_db_groups.Vcs')
    @patch('switch_db_groups.is_env_on_rack')
    def test_neo4j_offline_on_all_nodes(self, is_rack, vcs):
        is_rack.return_value = False
        vcs.H_SERVICE_STATE = 'ServiceState'
        vcs.H_SYSTEM = 'System'
        vcs.H_GROUP = 'Group'
        vcs.H_TYPE = 'HAType'
        vcs.return_value.get_cluster_system_status.return_value = TWO_SYSTEMS
        vcs.return_value.get_cluster_group_status.return_value = \
            NEO4J_OFFLINE

        self.assertRaises(SystemExit, switch_dbcluster_groups)

    @patch('switch_db_groups.Vcs')
    @patch('switch_db_groups.is_env_on_rack')
    def test_switch_dbcluster_groups_on_rack_updated(self, is_rack, vcs):
        is_rack.return_value = True
        vcs.return_value.node_name_to_vcs_system.side_effect = ['ieatrcxb3808-1', 'ieatrcxb3809-1', 'ieatrcxb3810-1']
        switch_dbcluster_groups()
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_eshistory_clustered_service',
            'ieatrcxb3810-1', 'db_cluster', timeout=-1)
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_modeldeployment_cluster_service_1',
            'ieatrcxb3808-1', 'db_cluster', timeout=-1)
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_elasticsearch_clustered_service',
            'ieatrcxb3809-1', 'db_cluster', timeout=-1)
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_jms_clustered_service',
            'ieatrcxb3810-1', 'db_cluster', timeout=-1)
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_postgres_clustered_service',
            'ieatrcxb3810-1', 'db_cluster', timeout=-1)
        vcs.return_value.hagrp_switch.assert_any_call(
            'Grp_CS_db_cluster_sg_neo4jbur_clustered_service',
            'ieatrcxb3808-1', 'db_cluster', timeout=-1)

if __name__ == '__main__':
    unittest2.main()
