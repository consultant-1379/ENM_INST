import copy
import json
from io import StringIO

import unittest2
from paramiko import SSHClient, AuthenticationException
from unittest2 import TestCase
from mock import patch

builtin_open = open  # unpatched version

from h_hc.hc_neo4j_cluster import Neo4jClusterOverview, \
    Neo4jClusterOverviewException, Neo4jClusterHCException, \
    InternalNeo4jErrorException, Neo4jClusterDownException, \
    Neo4jServerSideException, Neo4jHCNotSupportedException, \
    Neo4jClusterCriticalRaftIndexLagException, DbNodesSshCredentials, \
    DbNodesSshCredsException, Neo4jUpliftSpaceCheckException
from h_puppet.mco_agents import Neo4jClusterMcoAgent, McoAgentException, \
    Neo4jFilesystemMcoAgent
from h_util.h_collections import ExceptHandlingDict
from h_util.h_ssh.client import SshClient, SuIncorrectPassword
from h_util.h_utils import Sed

from h_vcs.vcs_cli import Vcs
from sanapi import UnityApi, Vnx2Api
#from unityapi import UnityApi
#from vnx2api import  Vnx2Api
from sanapiinfo import LunInfo

CLUSTER_OVERVIEW = {
  "instances": [
    {
      "available": True,
      "addresses": {
        "http": "10.247.246.8:7474",
        "bolt": "10.247.246.8:7687",
        "https": "10.247.246.8:7473"
      },
      "database": "default",
      "lag": 0,
      "ping": True,
      "host": {
        "ip": "10.247.246.8",
        "hostname": "ieatrcxb3529",
        "aliases": [
          "db-2"
        ]
      },
      "version": "3.5.12",
      "role": "FOLLOWER",
      "groups": [],
      "is_behind": False,
      "id": "bc51db75-e09a-48e9-a86e-aa8f03dbeb96"
    },
    {
      "available": True,
      "addresses": {
        "http": "10.247.246.9:7474",
        "bolt": "10.247.246.9:7687",
        "https": "10.247.246.9:7473"
      },
      "database": "default",
      "lag": 0,
      "ping": True,
      "host": {
        "ip": "10.247.246.9",
        "hostname": "ieatrcxb3565",
        "aliases": [
          "db-3"
        ]
      },
      "version": "3.5.12",
      "role": "LEADER",
      "groups": [],
      "is_behind": False,
      "id": "3987dc6c-ec3f-4aa4-99a7-d346805fa963"
    },
    {
      "available": True,
      "addresses": {
        "http": "10.247.246.10:7474",
        "bolt": "10.247.246.10:7687",
        "https": "10.247.246.10:7473"
      },
      "database": "default",
      "lag": 0,
      "ping": True,
      "host": {
        "ip": "10.247.246.10",
        "hostname": "ieatrcxb3566",
        "aliases": [
          "db-4"
        ]
      },
      "version": "3.5.12",
      "role": "FOLLOWER",
      "groups": [],
      "is_behind": False,
      "id": "3d1cba05-a688-42fd-81c8-c6fec3e8b5d3"
    }
  ],
  "cluster": {
    "mode": "cluster",
    "size": 3
  }
}

CLUSTER_OVERVIEW_RACK = {
  "instances": [
    {
      "available": True,
      "addresses": {
        "http": "10.247.246.8:7474",
        "bolt": "10.247.246.8:7687",
        "https": "10.247.246.8:7473"
      },
      "database": "default",
      "lag": 0,
      "ping": True,
      "host": {
        "ip": "10.247.246.8",
        "hostname": "ieatrcxb3529",
        "aliases": [
          "db-1"
        ]
      },
      "version": "4.4.16",
      "role": "FOLLOWER",
      "groups": [],
      "is_behind": False,
      "id": "bc51db75-e09a-48e9-a86e-aa8f03dbeb96"
    },
    {
      "available": True,
      "addresses": {
        "http": "10.247.246.9:7474",
        "bolt": "10.247.246.9:7687",
        "https": "10.247.246.9:7473"
      },
      "database": "default",
      "lag": 0,
      "ping": True,
      "host": {
        "ip": "10.247.246.9",
        "hostname": "ieatrcxb3565",
        "aliases": [
          "db-2"
        ]
      },
      "version": "4.4.16",
      "role": "LEADER",
      "groups": [],
      "is_behind": False,
      "id": "3987dc6c-ec3f-4aa4-99a7-d346805fa963"
    },
    {
      "available": True,
      "addresses": {
        "http": "10.247.246.10:7474",
        "bolt": "10.247.246.10:7687",
        "https": "10.247.246.10:7473"
      },
      "database": "default",
      "lag": 0,
      "ping": True,
      "host": {
        "ip": "10.247.246.10",
        "hostname": "ieatrcxb3566",
        "aliases": [
          "db-3"
        ]
      },
      "version": "4.4.16",
      "role": "FOLLOWER",
      "groups": [],
      "is_behind": False,
      "id": "3d1cba05-a688-42fd-81c8-c6fec3e8b5d3"
    }
  ],
  "cluster": {
    "mode": "cluster",
    "size": 3
  }
}

MCO_RESP_ERR = {'retcode': 1,
                'err': '',
                'out': 'Internal error: please check /var/log/messages'}

MCO_FAILED_ERR = {'ieatrcxb6399': {'errors': u'No answer from node ieatrcxb6399',
                                   'data': {}}}

VCS_NEO_SG_GRP_OUT = [
    {
        'ServiceState': 'ONLINE',
        'Cluster': 'db_cluster',
        'ServiceType': 'lsb',
        'Group': 'Grp_CS_db_cluster_sg_neo4j_clustered_service',
        'GroupState': 'OK',
        'HAType': 'parallel',
        'Frozen': '-',
        'System': 'ieatrcxb6399'
    }
]

VCS_SG_KEYS = ['Cluster', 'Group', 'System', 'HAType', 'ServiceType',
               'ServiceState', 'GroupState', 'Frozen']

FILE_SYSTEM_STATUS = {
            "enough_space": True,
            "avail_space": 1000,
            "can_free": {
                "labels_scan": 30,
                "transactions": 50,
                "logs": 30,
                "schema": 100,
                "cluster_state": 30,
                "total": 240
            },
            "extension": 300,
            "required": 1300,
            "reserved": 50,
        }


class TestNeo4jClusterOverview(TestCase):

    def setUp(self):
        self.cluster_overview = Neo4jClusterOverview()

    def tearDown(self):
        self.cluster_overview = None

    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_sgs_offline(self, get_cluster_group_status):
        neo_sg_grp = copy.deepcopy(VCS_NEO_SG_GRP_OUT)
        for i in neo_sg_grp:
            i['ServiceState'] = 'OFFLINE'
        get_cluster_group_status.return_value = neo_sg_grp, VCS_SG_KEYS

        with self.assertRaises(Neo4jClusterDownException):
            self.cluster_overview.is_single_mode()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_health_check_not_supported(self, get_cluster_group_status,
                                        get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        mco_resp_err = copy.deepcopy(MCO_RESP_ERR)
        mco_resp_err['retcode'] = 77

        with self.assertRaises(Neo4jHCNotSupportedException):
            get_cluster_overview.side_effect = McoAgentException(mco_resp_err)
            self.cluster_overview.is_single_mode()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_cluster_overview_resp_status_1(self, get_cluster_group_status,
                                            get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS

        with self.assertRaises(InternalNeo4jErrorException):
            get_cluster_overview.side_effect = McoAgentException(MCO_RESP_ERR)
            self.cluster_overview.is_single_mode()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_cluster_overview_resp_status_2(self, get_cluster_group_status,
                                            get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        mco_resp_err = copy.deepcopy(MCO_RESP_ERR)
        mco_resp_err['retcode'] = 2

        with self.assertRaises(Neo4jClusterDownException):
            get_cluster_overview.side_effect = McoAgentException(mco_resp_err)
            self.cluster_overview.is_single_mode()

    @patch("time.sleep")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_cluster_overview_mco_failed(self, get_cluster_group_status,
                                         get_cluster_overview, sleep):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        mco_failed_err = copy.deepcopy(MCO_FAILED_ERR)
        get_cluster_overview.side_effect = McoAgentException(mco_failed_err)
        with self.assertRaises(Neo4jClusterHCException):
            self.cluster_overview.is_single_mode()

    @patch("json.loads")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_cluster_overview_broken_resp(self, get_cluster_group_status,
                                          get_cluster_overview, loads):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = "Something not json loadable"

        with self.assertRaises(Neo4jClusterOverviewException):
            loads.side_effect = ValueError("Failed")
            self.cluster_overview.is_single_mode()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_unexpected_neo4j_server_side_err(self, get_cluster_group_status,
                                              get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS

        with self.assertRaises(Neo4jServerSideException):
            get_cluster_overview.side_effect = McoAgentException("Failed")
            self.cluster_overview.is_single_mode()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_is_single_mode(self, get_cluster_group_status,
                            get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        self.assertIs(type(self.cluster_overview.is_single_mode()), bool)

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_instances(self, get_cluster_group_status, get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        self.assertIs(type(self.cluster_overview.instances), list)
        self.assertEquals(self.cluster_overview.instances,
                          CLUSTER_OVERVIEW['instances'])

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_expected_cluster_size_causal(self, get_cluster_group_status,
                                          get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        self.assertIs(type(self.cluster_overview.expected_cluster_size), int)
        self.assertGreaterEqual(self.cluster_overview.expected_cluster_size, 0)

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_expected_cluster_size_single(self, get_cluster_group_status,
                                          get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)

        cluster_overview['cluster']['mode'] = 'single'
        cluster_overview['cluster']['size'] = 1
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        self.assertEquals(self.cluster_overview.expected_cluster_size, 1)

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_is_cluster_fully_formed_true(self, get_cluster_group_status,
                                          get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        self.assertTrue(self.cluster_overview.is_cluster_fully_formed())

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_is_cluster_fully_formed_false(self, get_cluster_group_status,
                                           get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'] = cluster_overview['instances'][0:2]
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        self.assertFalse(self.cluster_overview.is_cluster_fully_formed())

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_single_is_healthy(self, get_cluster_group_status,
                                     get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'] = cluster_overview['instances'][0:1]
        cluster_overview['cluster']['mode'] = 'single'
        cluster_overview['cluster']['size'] = 1

        get_cluster_overview.return_value = json.dumps(cluster_overview)

        self.cluster_overview.health_check()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_single_is_offline(self, get_cluster_group_status,
                                     get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'] = []
        cluster_overview['cluster']['mode'] = 'single'
        cluster_overview['cluster']['size'] = 1
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        with self.assertRaises(Neo4jClusterHCException):
            self.cluster_overview.health_check()

    @patch("time.sleep")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_single_is_offline2(self, get_cluster_group_status,
                                      get_cluster_overview, sleep):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'] = cluster_overview['instances'][0:1]
        cluster_overview['instances'][0]['available'] = False
        cluster_overview['cluster']['mode'] = 'single'
        cluster_overview['cluster']['size'] = 1
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        with self.assertRaises(Neo4jClusterHCException):
            self.cluster_overview.health_check()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_causal_is_healthy(self, get_cluster_group_status,
                                     get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        self.cluster_overview.health_check()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_causal_raft_index_no_lag(self, get_cluster_group_status,
                                     get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)
        try:
            self.cluster_overview.raft_index_lag_check()
        except Neo4jClusterCriticalRaftIndexLagException:
            self.fail("raft_index_lag_check raised Neo4jClusterCriticalRaftIndexLagException unexpectedly!")

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_causal_raft_index_lag(self, get_cluster_group_status,
                                     get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)

        cluster_overview['instances'][0]["lag"] = 100000
        cluster_overview['instances'][1]["lag"] = -600
        cluster_overview['instances'][2]["lag"] = 170000
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        self.assertIs(type(self.cluster_overview.raft_index_lagging_instances), list)
        with self.assertRaises(Neo4jClusterCriticalRaftIndexLagException):
            self.cluster_overview.raft_index_lag_check()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_causal_raft_index_lag_not_supported(self, get_cluster_group_status, get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        del cluster_overview['instances'][0]['lag']
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        with self.assertRaises(Neo4jHCNotSupportedException):
            self.cluster_overview.raft_index_lag_check()

    @patch("time.sleep")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_causal_is_not_formed(self, get_cluster_group_status,
                                        get_cluster_overview, sleep):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'] = cluster_overview['instances'][0:1]
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        with self.assertRaises(Neo4jClusterHCException):
            self.cluster_overview.health_check()

    @patch("time.sleep")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_neo4j_causal_is_not_available(self, get_cluster_group_status,
                                           get_cluster_overview, sleep):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'][0]['available'] = False
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        with self.assertRaises(Neo4jClusterHCException):
            self.cluster_overview.health_check()

    @patch("time.sleep")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_co_exception_during_health_check(self, get_cluster_group_status,
                                              get_cluster_overview, sleep):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        del cluster_overview['cluster']['mode']
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        with self.assertRaises(Neo4jClusterOverviewException):
            self.cluster_overview.health_check()

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_need_uplift(self, get_cluster_group_status, get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)
        self.assertTrue(self.cluster_overview.need_uplift())

    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_no_need_uplift(self, get_cluster_group_status, get_cluster_overview):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'][0]['version'] = "4.0.4"
        get_cluster_overview.return_value = json.dumps(cluster_overview)
        self.assertFalse(self.cluster_overview.need_uplift())

    @patch('h_hc.hc_neo4j_cluster.exec_process')
    def test_is_neo4j_4_in_dd_true(self, ep):
        stdout = '<package_name>ERICneo4j4server_CXP9038634'
        ep.return_value = stdout
        class Args(object):
            model_xml = "/software/autoDeploy/AAA.xml"

        cfg = Args()
        self.assertTrue(self.cluster_overview.is_neo4j_4_in_dd(cfg))

    @patch('h_hc.hc_neo4j_cluster.exec_process')
    def test_is_neo4j_4_in_dd_false(self, ep):
        ep.side_effect = IOError
        class Args(object):
            model_xml = "/software/autoDeploy/AAA.xml"

        cfg = Args()
        self.assertFalse(self.cluster_overview.is_neo4j_4_in_dd(cfg))

    @patch('h_hc.hc_neo4j_cluster.load_xml')
    @patch('h_hc.hc_neo4j_cluster.xpath')
    @patch('h_hc.hc_neo4j_cluster.Neo4jClusterOverview._get_neo4j_version_from_dd')
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_need_uplift_4x(self, get_cluster_group_status, get_cluster_overview,
                                                    m_dd_ver, m_xpath, m_load):
        m_dd_ver.return_value = '4.5.11'
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW_RACK)
        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.assertTrue(self.cluster_overview.need_uplift_4x(cfg))

    @patch('h_hc.hc_neo4j_cluster.load_xml')
    @patch('h_hc.hc_neo4j_cluster.xpath')
    @patch('h_hc.hc_neo4j_cluster.Neo4jClusterOverview._get_neo4j_version_from_dd')
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_no_need_uplift_4x(self, get_cluster_group_status, get_cluster_overview,
                                                            m_dd_ver, m_xpath, m_load):
        m_dd_ver.return_value = '4.4.16'
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW_RACK)
        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.assertFalse(self.cluster_overview.need_uplift_4x(cfg))

    @patch('h_hc.hc_neo4j_cluster.load_xml')
    @patch('h_hc.hc_neo4j_cluster.xpath')
    @patch('h_hc.hc_neo4j_cluster.Neo4jClusterOverview._get_neo4j_version_from_dd')
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_no_need_uplift_4x_small_uplift(self, get_cluster_group_status, get_cluster_overview,
                                                            m_dd_ver, m_xpath, m_load):
        m_dd_ver.return_value = '4.4.18'
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW_RACK)
        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.assertFalse(self.cluster_overview.need_uplift_4x(cfg))

    @patch("h_util.h_utils.Sed.__init__", autospec=True, return_value=None)
    @patch.object(Sed, "get_value")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_check_sed_credentials_blade(self, get_cluster_group_status, get_cluster_overview, rack, sed_get_val, sed):
        sed_get_val.return_value = "shroot"
        rack.return_value = False
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'][0]['version'] = "3.5.12"
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        class Args(object):
            sed_file = "/software/autoDeploy/sed"
        cfg = Args()
        nodes_user_cred = {
            'db-2':
                {"litp-admin": "shroot",
                 'root': "shroot"},
            'db-3':
                {"litp-admin": "shroot",
                 'root': "shroot"},
            'db-4':
                {"litp-admin": "shroot",
                 'root': "shroot"}}
        creds = self.cluster_overview.check_sed_credentials(cfg)
        self.assertDictEqual(nodes_user_cred, creds)

    @patch("h_util.h_utils.Sed.__init__", autospec=True, return_value=None)
    @patch.object(Sed, "get_value")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_check_sed_credentials_rack(self, get_cluster_group_status, get_cluster_overview, rack, sed_get_val, sed):
        sed_get_val.return_value = "shroot"
        rack.return_value = True
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW_RACK)
        cluster_overview['instances'][0]['version'] = "4.0.11"
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        class Args(object):
            sed_file = "/software/autoDeploy/sed"
        cfg = Args()
        nodes_user_cred = {
            'db-1':
                {"litp-admin": "shroot",
                 'root': "shroot"},
            'db-2':
                {"litp-admin": "shroot",
                 'root': "shroot"},
            'db-3':
                {"litp-admin": "shroot",
                 'root': "shroot"}}
        creds = self.cluster_overview.check_sed_credentials(cfg)
        self.assertDictEqual(nodes_user_cred, creds)

    @patch("h_util.h_utils.Sed.__init__", autospec=True, return_value=None)
    @patch.object(Sed, "get_value")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_fail_check_sed_credentials(self, get_cluster_group_status, get_cluster_overview, rack, sed_get_val, sed):
        sed_get_val.side_effect = KeyError
        rack.return_value = False
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)
        cluster_overview['instances'][0]['version'] = "3.5.12"
        get_cluster_overview.return_value = json.dumps(cluster_overview)
        class Args(object):
            sed_file = "/software/autoDeploy/sed"
        cfg = Args()
        with self.assertRaises(SystemExit) as sysexit:
            creds = self.cluster_overview.check_sed_credentials(cfg)
            self.assertFalse(creds)

    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_get_fs_status_return_type(self, get_cluster_group_status, get_filesystem_status):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.return_value = FILE_SYSTEM_STATUS
        fs_status = self.cluster_overview._get_fs_status("1.1.1.1", ["san1=arg1", "san2=arg2"])
        self.assertIsInstance(fs_status, dict)
        self.assertIsInstance(fs_status, ExceptHandlingDict)

    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_get_fs_status_handles_mco_exception(self, get_cluster_group_status, get_filesystem_status):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.side_effect = McoAgentException
        with self.assertRaises(Neo4jUpliftSpaceCheckException):
            fs_status = self.cluster_overview._get_fs_status("1.1.1.1",
                                                             ["san1=arg1",
                                                              "san2=arg2"])

    @patch.object(UnityApi, "get_lun")
    @patch.object(Sed, "_load")
    @patch.object(Sed, "get_value")
    @patch.object(Sed, "get_last_applied_sed")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_fs_status_property_neo4j_single_mode(self, get_cluster_group_status, get_filesystem_status,
                                                  get_cluster_overview, get_last_applied_sed, get_sed_value,
                                                  _load, get_lun):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.return_value = FILE_SYSTEM_STATUS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)

        cluster_overview['cluster']['mode'] = 'single'
        cluster_overview['cluster']['size'] = 1
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        get_last_applied_sed.return_value = "/path/to/sed"
        get_sed_value.side_effect = ["EMM_665", "user", "admin", "1.1.1.1", "unity"]

        neo4j_lun = LunInfo('5', 'LITP2_enm1_neo4jlun', 'uid', 'pool1', '300', 'StoragePool', '5')
        get_lun.return_value = neo4j_lun

        fs_status = self.cluster_overview._fs_status

        self.assertEqual(fs_status["enough_space"], True)
        self.assertEqual(fs_status["avail_space"], 1000)
        self.assertEqual(fs_status["can_free"]["labels_scan"], 30)
        self.assertEqual(fs_status["can_free"]["transactions"], 50)
        self.assertEqual(fs_status["can_free"]["logs"], 30)
        self.assertEqual(fs_status["can_free"]["cluster_state"], 30)
        self.assertEqual(fs_status["can_free"]["total"], 240)
        self.assertEqual(fs_status["extension"], 300)
        self.assertEqual(fs_status["required"], 1300)
        self.assertEqual(fs_status["reserved"], 50)

    @patch.object(Vnx2Api, "get_lun")
    @patch.object(Sed, "_load")
    @patch.object(Sed, "get_value")
    @patch.object(Sed, "get_last_applied_sed")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_fs_status_property_neo4j_cluster_mode(self, get_cluster_group_status, get_filesystem_status,
                                                   get_cluster_overview, get_last_applied_sed, get_sed_value,
                                                   _load, get_lun):

        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.return_value = FILE_SYSTEM_STATUS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        get_last_applied_sed.return_value = "/path/to/sed"
        get_sed_value.side_effect = ["EMM_665", "user", "admin", "1.1.1.1", "vnx2"]

        neo4j_lun = LunInfo('5', 'LITP2_enm1_neo4jlun', 'uid', 'pool1', '300', 'StoragePool', '5')
        get_lun.return_value = neo4j_lun

        fs_status = self.cluster_overview._fs_status
        self.assertIsInstance(fs_status, dict)

    @patch.object(Sed, "get_last_applied_sed")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_fs_status_property_files_not_found(self, get_cluster_group_status, get_filesystem_status,
                                                         get_cluster_overview, get_last_applied_sed):

        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.return_value = FILE_SYSTEM_STATUS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        get_last_applied_sed.side_effect = IOError("Cmd args log not found or sed file not found")

        with self.assertRaises(Neo4jUpliftSpaceCheckException):
            fs_status = self.cluster_overview._fs_status

    @patch.object(Sed, "get_last_applied_sed")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_fs_status_property_sed_param_not_found(self, get_cluster_group_status, get_filesystem_status,
                                                         get_cluster_overview, get_last_applied_sed):

        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.return_value = FILE_SYSTEM_STATUS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        get_last_applied_sed.side_effect = ValueError("Unable to find sed paramater in command")

        with self.assertRaises(Neo4jUpliftSpaceCheckException):
            fs_status = self.cluster_overview._fs_status

    @patch.object(Sed, "_load")
    @patch.object(Sed, "get_value")
    @patch.object(Sed, "get_last_applied_sed")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_fs_status_property_sed_key_error(self, get_cluster_group_status, get_filesystem_status,
                                              get_cluster_overview, get_last_applied_sed, get_sed_value, _load):

        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.return_value = FILE_SYSTEM_STATUS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        get_last_applied_sed.return_value = "/path/to/sed"
        get_sed_value.side_effect = KeyError

        with self.assertRaises(Neo4jUpliftSpaceCheckException):
            fs_status = self.cluster_overview._fs_status

    @patch.object(Sed, "_load")
    @patch.object(Sed, "get_value")
    @patch.object(Sed, "get_last_applied_sed")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_fs_status_property_sed_value_error(self, get_cluster_group_status, get_filesystem_status,
                                                get_cluster_overview, get_last_applied_sed, get_sed_value, _load):

        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.return_value = FILE_SYSTEM_STATUS
        get_cluster_overview.return_value = json.dumps(CLUSTER_OVERVIEW)

        get_last_applied_sed.return_value = "/path/to/sed"
        get_sed_value.side_effect = ValueError

        with self.assertRaises(Neo4jUpliftSpaceCheckException):
            fs_status = self.cluster_overview._fs_status

    @patch.object(UnityApi, "get_lun")
    @patch.object(Sed, "_load")
    @patch.object(Sed, "get_value")
    @patch.object(Sed, "get_last_applied_sed")
    @patch.object(Neo4jClusterMcoAgent, "get_cluster_overview")
    @patch.object(Neo4jFilesystemMcoAgent, "get_filesystem_status")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_pre_uplift_space_report(self, get_cluster_group_status, get_filesystem_status,
                                     get_cluster_overview, get_last_applied_sed, get_sed_value,
                                     _load, get_lun):
        get_cluster_group_status.return_value = VCS_NEO_SG_GRP_OUT, VCS_SG_KEYS
        get_filesystem_status.return_value = FILE_SYSTEM_STATUS
        cluster_overview = copy.deepcopy(CLUSTER_OVERVIEW)

        cluster_overview['cluster']['mode'] = 'single'
        cluster_overview['cluster']['size'] = 1
        get_cluster_overview.return_value = json.dumps(cluster_overview)

        get_last_applied_sed.return_value = "/path/to/sed"

        get_sed_value.side_effect = ["EMM_665", "user", "admin", "1.1.1.1", "unity"]

        neo4j_lun = LunInfo('5', 'LITP2_enm1_neo4jlun', 'uid', 'pool1', '300', 'StoragePool', '5')
        get_lun.return_value = neo4j_lun

        fs_report = self.cluster_overview.get_pre_uplift_space_report()
        self.assertEqual(fs_report["enough_space"], True)
        self.assertEqual(fs_report["avail_space"].num_bytes, 1000)
        self.assertEqual(fs_report["can_free"]["labels_scan"].num_bytes, 30)
        self.assertEqual(fs_report["can_free"]["transactions"].num_bytes, 50)
        self.assertEqual(fs_report["can_free"]["logs"].num_bytes, 30)
        self.assertEqual(fs_report["can_free"]["cluster_state"].num_bytes, 30)
        self.assertEqual(fs_report["can_free"]["total"].num_bytes, 240)
        self.assertEqual(fs_report["extension"].num_bytes, 300)
        self.assertEqual(fs_report["required"].num_bytes, 1300)
        self.assertEqual(fs_report["reserved"].num_bytes, 50)


DB_CREDENTIALS = u"""
db-2:
    litp-admin: "passw0rd"
    root: "litpc0b6lEr"

db-3:
    litp-admin: "passw0rd"
    root: "litpc0b6lEr"

db-4:
    litp-admin: "passw0rd"
    root: "litpc0b6lEr"
"""

DB_CREDENTIALS_RACK = u"""
db-1:
    litp-admin: "passw0rd"
    root: "litpc0b6lEr"

db-2:
    litp-admin: "passw0rd"
    root: "litpc0b6lEr"

db-3:
    litp-admin: "passw0rd"
    root: "litpc0b6lEr"
"""

DB_CREDENTIALS_INVALID_FORMAT = u"""
db-2:
 litp-admin: "passw0rd"
  root: "litpc0b6lEr"
"""

DB_CREDENTIALS_KEYS = u"""
db-2:
    litp-admin: /path/to/key.pem

db-3:
    litp-admin: /path/to/key.pem

db-4:
    litp-admin: /path/to/key.pem
"""


class TestDbNodesSshCredentials(TestCase):
    def setUp(self):
        self.db_credentials = DbNodesSshCredentials()

    def tearDown(self):
        self.db_credentials = None

    @patch("os.path.exists")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    def test_credentials_file_not_found(self, is_rack, exists):
        is_rack.return_value = False
        with self.assertRaises(DbNodesSshCredsException):
            exists.return_value = False
            self.db_credentials.validate_credentials()

    @patch.object(SSHClient, "close")
    @patch.object(SshClient, "_run")
    @patch.object(SSHClient, "connect")
    @patch.object(SSHClient, "load_system_host_keys")
    @patch("__builtin__.open")
    @patch("os.path.exists")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    def test_validate_credentials_blade_success(self, is_rack, exists, _open,
                           load_system_host_keys, connect, _run, c_close):
        is_rack.return_value = False
        exists.return_value = True
        _open.return_value = StringIO(DB_CREDENTIALS)
        self.db_credentials.validate_credentials()
        self.assertTrue(c_close.called)

    @patch.object(SSHClient, "close")
    @patch.object(SshClient, "_run")
    @patch.object(SSHClient, "connect")
    @patch.object(SSHClient, "load_system_host_keys")
    @patch("__builtin__.open")
    @patch("os.path.exists")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    def test_validate_credentials_rack_success(self, is_rack, exists, _open,
                           load_system_host_keys, connect, _run, c_close):
        is_rack.return_value = True
        exists.return_value = True
        _open.return_value = StringIO(DB_CREDENTIALS_RACK)
        self.db_credentials.validate_credentials()
        self.assertTrue(c_close.called)

    @patch("__builtin__.open")
    @patch("os.path.exists")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    def test_credentials_file_invalid_format(self, is_rack, exists, _open):
        with self.assertRaises(DbNodesSshCredsException):
            exists.return_value = True
            _open.return_value = StringIO(DB_CREDENTIALS_INVALID_FORMAT)
            self.db_credentials.validate_credentials()

    @patch("socket.gethostbyaddr")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    def test_db_hostnames_map(self, is_env_on_rack, gethostbyaddr):
        dbs = ['db-2', 'db-3', 'db-4']
        is_env_on_rack.return_value = False
        gethostbyaddr.side_effect = [(d,) for d in dbs]
        ret = self.db_credentials._db_hostnames_map
        self.assertTrue(isinstance(ret, dict), ret)
        self.assertTrue(all([d in ret for d in dbs]), ret)
        self.assertTrue(all([ret[d] == d for d in dbs]), ret)

    @patch("socket.gethostbyaddr")
    @patch("__builtin__.open")
    @patch("os.path.exists")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jFilesystemMcoAgent, "check_ssh_connectivity")
    def test_validate_credentials_for_key_access_via_db_creds(self,
            check_ssh_connectivity, is_env_on_rack, exists, _open,
            gethostbyaddr):

        def mocked_open(path, *args, **kwargs):
            if 'dbcreds.yaml' in path:
                return StringIO(DB_CREDENTIALS_KEYS)
            else:
                return builtin_open(path, *args, **kwargs)

        exists.return_value = True
        _open.side_effect = mocked_open
        gethostbyaddr.side_effect = [('db-2',), ('db-3',), ('db-4',)]
        is_env_on_rack.return_value = False
        ret = self.db_credentials.validate_credentials_for_key_access()
        self.assertEquals(ret, None)

    @patch("socket.gethostbyaddr")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jFilesystemMcoAgent, "check_ssh_connectivity")
    @patch.object(Neo4jFilesystemMcoAgent, "has_file")
    def test_validate_credentials_for_key_access(self, has_file,
                                                 check_ssh_connectivity,
                                                 is_env_on_rack,
                                                 gethostbyaddr):
        has_file.return_value = 'true'
        gethostbyaddr.side_effect = [('db-2',), ('db-3',), ('db-4',)]
        is_env_on_rack.return_value = False
        ret = self.db_credentials.validate_credentials_for_key_access()
        self.assertEquals(ret, None)

    @patch("socket.gethostbyaddr")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jFilesystemMcoAgent, "check_ssh_connectivity")
    @patch.object(Neo4jFilesystemMcoAgent, "has_file")
    def test_validate_credentials_for_key_access_no_key(self, has_file,
                                                        check_ssh_connectivity,
                                                        is_env_on_rack,
                                                        gethostbyaddr):
        has_file.side_effect = ['true', 'false', 'true']
        gethostbyaddr.side_effect = [('db-2',), ('db-3',), ('db-4',)]
        is_env_on_rack.return_value = False
        exc = None
        try:
            self.db_credentials.validate_credentials_for_key_access()
        except Exception as exc:
            pass
        self.assertTrue(exc is not None)
        self.assertTrue(isinstance(exc, DbNodesSshCredsException))
        self.assertTrue('Credentials file /ericsson/tor/data/neo4j/'
                        'dbcreds.yaml not found' in str(exc))

    @patch("socket.gethostbyaddr")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jFilesystemMcoAgent, "check_ssh_connectivity")
    @patch.object(Neo4jFilesystemMcoAgent, "has_file")
    def test_validate_credentials_for_key_access_connectivity_failure(self,
          has_file, check_ssh_connectivity, is_env_on_rack, gethostbyaddr):
        dbs = ['db-2', 'db-3', 'db-4']
        has_file.return_value = 'true'
        gethostbyaddr.side_effect = [(d,) for d in dbs]
        check_ssh_connectivity.side_effect = McoAgentException('SSH CONNECTION FAILED')
        is_env_on_rack.return_value = False
        exc = None
        try:
            self.db_credentials.validate_credentials_for_key_access()
        except Exception as exc:
            pass
        self.assertTrue(exc is not None)
        self.assertTrue(isinstance(exc, DbNodesSshCredsException), exc)
        msg = "SSH connectivity check failed from %s to %s with key " \
              "/home/litp-admin/.ssh/id_rsa. Details: SSH CONNECTION FAILED"
        for from_db in dbs:
            for to_db in dbs:
                if from_db == to_db:
                    continue
                self.assertTrue((msg % (from_db, to_db)) in str(exc), str(exc))

    @patch("socket.gethostbyaddr")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jFilesystemMcoAgent, "check_ssh_connectivity")
    @patch.object(Neo4jFilesystemMcoAgent, "has_file")
    def test_validate_credentials_for_key_access_connectivity_one_failure(self,
          has_file, check_ssh_connectivity, is_env_on_rack, gethostbyaddr):
        dbs = ['db-2', 'db-3', 'db-4']
        has_file.return_value = 'true'
        gethostbyaddr.side_effect = [(d,) for d in dbs]
        check_ssh_connectivity.side_effect = [None,
                                              McoAgentException('FAILED'),
                                              None,
                                              None,
                                              None,
                                              None]
        is_env_on_rack.return_value = False
        exc = None
        try:
            self.db_credentials.validate_credentials_for_key_access()
        except Exception as exc:
            pass
        self.assertTrue(exc is not None)
        self.assertTrue(isinstance(exc, DbNodesSshCredsException), exc)
        msg = "SSH connectivity check failed from %s to %s with key " \
              "/home/litp-admin/.ssh/id_rsa. Details: FAILED"
        for from_db in dbs:
            for to_db in dbs:
                if from_db == to_db:
                    continue
                if from_db == 'db-3' and to_db == 'db-4':
                    self.assertTrue((msg % (from_db, to_db)) in str(exc),
                                    str(exc))
                else:
                    self.assertFalse((msg % (from_db, to_db)) in str(exc),
                                     str(exc))


    @patch("os.remove")
    @patch("os.path.exists")
    def test_remove_cred_file(self, exists, remove):
        exists.return_value = True
        self.db_credentials.remove_cred_file()

    @patch.object(SSHClient, "connect")
    @patch.object(SSHClient, "load_system_host_keys")
    @patch("__builtin__.open")
    @patch("os.path.exists")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    def test_invalid_litp_password(self, is_rack, exists, _open, load_system_host_keys, connect):
        exists.return_value = True
        _open.return_value = StringIO(DB_CREDENTIALS)

        with self.assertRaises(DbNodesSshCredsException):
            connect.side_effect = AuthenticationException("Auth Failed")
            self.db_credentials.validate_credentials()

    @patch.object(SshClient, "_run")
    @patch.object(SSHClient, "connect")
    @patch.object(SSHClient, "load_system_host_keys")
    @patch("__builtin__.open")
    @patch("os.path.exists")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    def test_invalid_root_password(self, is_rack, exists, _open, load_system_host_keys, connect, _run):
        exists.return_value = True
        _open.return_value = StringIO(DB_CREDENTIALS)

        with self.assertRaises(DbNodesSshCredsException):
            _run.side_effect = SuIncorrectPassword("Invalid root password")
            self.db_credentials.validate_credentials()


if __name__ == '__main__':
    unittest2.main()
