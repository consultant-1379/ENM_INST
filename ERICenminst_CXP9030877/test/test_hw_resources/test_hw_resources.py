import httplib
import os
from json import dumps
from os.path import join, abspath
from tempfile import gettempdir

import unittest2
from mock import patch
from unittest2 import TestCase

import hw_resources
from h_litp.litp_rest_client import LitpRestClient
from h_xml.xml_utils import load_xml
from hw_resources import HwResources
from test_h_litp.test_h_litp_rest_client import setup_mock as setup_litp_mock

MODEL = """
<litp:root xmlns:litp="http://www.ericsson.com/litp">
    <litp:deployment id="enm">
      <litp:deployment-clusters-collection id="clusters">
        <litp:vcs-cluster id="db_cluster">
          <litp:cluster-nodes-collection id="nodes">
            <litp:node id="db-1">
                <hostname>cloud-db-1</hostname>
            </litp:node>
            <litp:node id="db-2">
                <hostname>cloud-db-2</hostname>
            </litp:node>
          </litp:cluster-nodes-collection>
          <litp:cluster-services-collection id="services">
            <litp:vcs-clustered-service id="elasticsearch_clustered_service">
              <active>1</active>
              <name>elasticsearch</name>
              <node_list>db-2,db-1</node_list>
              <standby>1</standby>
              <litp:clustered-service-applications-collection id="applications">
                <litp:elasticsearch-inherit source_path="/software/services/elasticsearch" id="elasticsearch">
                  <litp:service-packages-collection-inherit source_path="/software/services/elasticsearch_package" id="packages" />
                </litp:elasticsearch-inherit>
              </litp:clustered-service-applications-collection>
            </litp:vcs-clustered-service>
          </litp:cluster-services-collection>
        </litp:vcs-cluster>
        <litp:vcs-cluster id="svc_cluster">
          <litp:cluster-nodes-collection id="nodes">
            <litp:node id="svc-1">
              <hostname>cloud-svc-1</hostname>
            </litp:node>
            <litp:node id="svc-2">
              <hostname>cloud-svc-2</hostname>
            </litp:node>
          </litp:cluster-nodes-collection>
          <dependency_list>db_cluster</dependency_list>
          <litp:cluster-services-collection id="services">
            <litp:vcs-clustered-service id="lvsrouter">
              <active>2</active>
              <name>lvsrouter</name>
              <node_list>svc-1,svc-2</node_list>
              <standby>0</standby>
              <litp:clustered-service-applications-collection id="applications">
                <litp:vm-service-inherit source_path="/software/services/lvsrouter" id="vm-service_lvsrouter" />
              </litp:clustered-service-applications-collection>
            </litp:vcs-clustered-service>
            <litp:vcs-clustered-service id="custom_service">
              <active>2</active>
              <name>custom_service</name>
              <node_list>svc-1,svc-2</node_list>
              <standby>0</standby>
              <litp:clustered-service-applications-collection id="applications">
                <litp:vm-service-inherit source_path="/software/services/custom_service" id="vm-service_custom_service" />
              </litp:clustered-service-applications-collection>
            </litp:vcs-clustered-service>
          </litp:cluster-services-collection>
        </litp:vcs-cluster>
      </litp:deployment-clusters-collection>
    </litp:deployment>
  <litp:software id="software">
    <litp:software-services-collection id="services">
      <litp:vm-service id="lvsrouter">
        <cleanup_command>/sbin/service lvsrouter stop-undefine --stop-timeout=300</cleanup_command>
        <service_name>lvsrouter</service_name>
        <cpus>2</cpus>
        <image_name>rhel7-lsb-image</image_name>
        <internal_status_check>on</internal_status_check>
        <ram>2048M</ram>
        <litp:vm-service-vm_yum_repos-collection id="vm_yum_repos">
          <litp:vm-yum-repo id="common">
            <base_url>http://%%LMS_IP_internal%%/ENM_common_rhel7/</base_url>
            <name>common</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="services">
            <base_url>http://%%LMS_IP_internal%%/ENM_services_rhel7/</base_url>
            <name>services</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="OS">
            <base_url>http://%%LMS_IP_internal%%/7/os/x86_64/Packages/</base_url>
            <name>OS</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="UPDATES">
            <base_url>
              http://%%LMS_IP_internal%%/6/updates/x86_64/Packages/
            </base_url>
            <name>UPDATES</name>
          </litp:vm-yum-repo>
        </litp:vm-service-vm_yum_repos-collection>
      </litp:vm-service>
      <litp:vm-service id="custom_service">
        <cleanup_command>/sbin/service custom_service stop-undefine --stop-timeout=300</cleanup_command>
        <service_name>custom_service</service_name>
        <cpus>2</cpus>
        <image_name>rhel7-lsb-image</image_name>
        <internal_status_check>on</internal_status_check>
        <ram>2048M</ram>
        <litp:vm-service-vm_yum_repos-collection id="vm_yum_repos">
          <litp:vm-yum-repo id="common">
            <base_url>http://%%LMS_IP_internal%%/Custom_service/</base_url>
            <name>common</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="services">
            <base_url>http://%%LMS_IP_internal%%/Custom_service/</base_url>
            <name>services</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="OS">
            <base_url>http://%%LMS_IP_internal%%/7/os/x86_64/Packages/</base_url>
            <name>OS</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="UPDATES">
            <base_url>
              http://%%LMS_IP_internal%%/6/updates/x86_64/Packages/
            </base_url>
            <name>UPDATES</name>
          </litp:vm-yum-repo>
        </litp:vm-service-vm_yum_repos-collection>
      </litp:vm-service>
    </litp:software-services-collection>
  </litp:software>
</litp:root>
"""

NON_INHERITED_SERVICES = """
<litp:root xmlns:litp="http://www.ericsson.com/litp">
  <litp:ms id="ms">
    <litp:ms-services-collection id="services">
      <litp:vm-service id="esmon">
        <service_name>esmon</service_name>
        <cpus>2</cpus>
        <image_name>lsb-image</image_name>
        <internal_status_check>off</internal_status_check>
        <ram>4096M</ram>
      </litp:vm-service>
    </litp:ms-services-collection>
  </litp:ms>
</litp:root>
"""

UPGRADE_MODEL = """
<litp:root xmlns:litp="http://www.ericsson.com/litp">
    <litp:deployment id="enm">
      <litp:deployment-clusters-collection id="clusters">
        <litp:vcs-cluster id="db_cluster">
          <litp:cluster-nodes-collection id="nodes">
            <litp:node id="db-1">
                <hostname>cloud-db-1</hostname>
            </litp:node>
            <litp:node id="db-2">
                <hostname>cloud-db-2</hostname>
            </litp:node>
          </litp:cluster-nodes-collection>
          <litp:cluster-services-collection id="services">
            <litp:vcs-clustered-service id="elasticsearch_clustered_service">
              <active>1</active>
              <name>elasticsearch</name>
              <node_list>db-2,db-1</node_list>
              <standby>1</standby>
              <litp:clustered-service-applications-collection
              id="applications">
                <litp:elasticsearch-inherit source_path="/software/services/
                elasticsearch" id="elasticsearch">
                  <litp:service-packages-collection-inherit source_path="
                  /software/services/elasticsearch_package" id="packages" />
                </litp:elasticsearch-inherit>
              </litp:clustered-service-applications-collection>
            </litp:vcs-clustered-service>
          </litp:cluster-services-collection>
        </litp:vcs-cluster>
        <litp:vcs-cluster id="scp_cluster">
          <litp:cluster-nodes-collection id="nodes">
            <litp:node id="scp-1">
              <hostname>cloud-scp-1</hostname>
            </litp:node>
            <litp:node id="scp-2">
              <hostname>cloud-scp-2</hostname>
            </litp:node>
          </litp:cluster-nodes-collection>
          <dependency_list>db_cluster</dependency_list>
          <litp:cluster-services-collection id="services">
            <litp:vcs-clustered-service id="amos">
              <active>2</active>
              <name>amos</name>
              <node_list>scp-1,scp-2</node_list>
              <standby>0</standby>
              <litp:clustered-service-applications-collection
              id="applications">
                <litp:vm-service-inherit source_path="/software/services/amos"
                 id="vm-service_amos" />
              </litp:clustered-service-applications-collection>
            </litp:vcs-clustered-service>
          </litp:cluster-services-collection>
        </litp:vcs-cluster>
        <litp:vcs-cluster id="svc_cluster">
          <litp:cluster-nodes-collection id="nodes">
            <litp:node id="svc-1">
              <hostname>cloud-svc-1</hostname>
            </litp:node>
            <litp:node id="svc-2">
              <hostname>cloud-svc-2</hostname>
            </litp:node>
          </litp:cluster-nodes-collection>
          <dependency_list>db_cluster</dependency_list>
          <litp:cluster-services-collection id="services">
            <litp:vcs-clustered-service id="custom_service_2">
              <active>2</active>
              <name>custom_service_2</name>
              <node_list>svc-1,svc-2</node_list>
              <standby>0</standby>
              <litp:clustered-service-applications-collection
              id="applications">
                <litp:vm-service-inherit
                source_path="/software/services/custom_service_2"
                id="vm-service_custom_service_2" />
              </litp:clustered-service-applications-collection>
            </litp:vcs-clustered-service>
          </litp:cluster-services-collection>
        </litp:vcs-cluster>
      </litp:deployment-clusters-collection>
    </litp:deployment>
  <litp:software id="software">
    <litp:software-services-collection id="services">
      <litp:vm-service id="amos">
        <cleanup_command>/sbin/service amos stop-undefine
        --stop-timeout=300</cleanup_command>
        <service_name>amos</service_name>
        <cpus>16</cpus>
        <image_name>rhel7-lsb-image</image_name>
        <internal_status_check>on</internal_status_check>
        <ram>81920M</ram>
        <litp:vm-service-vm_yum_repos-collection id="vm_yum_repos">
          <litp:vm-yum-repo id="common">
            <base_url>http://%%LMS_IP_internal%%/ENM_common_rhel7/</base_url>
            <name>common</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="services">
            <base_url>http://%%LMS_IP_internal%%/ENM_services_rhel7/</base_url>
            <name>services</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="OS">
            <base_url>http://%%LMS_IP_internal%%/7/os/x86_64/Packages/</base_url>
            <name>OS</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="UPDATES">
            <base_url>
              http://%%LMS_IP_internal%%/6/updates/x86_64/Packages/
            </base_url>
            <name>UPDATES</name>
          </litp:vm-yum-repo>
        </litp:vm-service-vm_yum_repos-collection>
      </litp:vm-service>
      <litp:vm-service id="custom_service_2">
        <cleanup_command>/sbin/service custom_service_2 stop-undefine
        --stop-timeout=300</cleanup_command>
        <service_name>custom_service_2</service_name>
        <cpus>2</cpus>
        <image_name>rhel7-lsb-image</image_name>
        <internal_status_check>on</internal_status_check>
        <ram>2048M</ram>
        <litp:vm-service-vm_yum_repos-collection id="vm_yum_repos">
          <litp:vm-yum-repo id="common">
            <base_url>http://%%LMS_IP_internal%%/Custom_service_2/</base_url>
            <name>common</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="services">
            <base_url>http://%%LMS_IP_internal%%/Custom_service_2/</base_url>
            <name>services</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="OS">
            <base_url>http://%%LMS_IP_internal%%/7/os/x86_64/Packages/</base_url>
            <name>OS</name>
          </litp:vm-yum-repo>
          <litp:vm-yum-repo id="UPDATES">
            <base_url>
              http://%%LMS_IP_internal%%/6/updates/x86_64/Packages/
            </base_url>
            <name>UPDATES</name>
          </litp:vm-yum-repo>
        </litp:vm-service-vm_yum_repos-collection>
      </litp:vm-service>
    </litp:software-services-collection>
  </litp:software>
</litp:root>
"""

XML_NODES = """
<litp:root xmlns:litp="http://www.ericsson.com/litp" id="root">
  <litp:node id="svc-1">
    <hostname>ieatrcxb6035</hostname>
  </litp:node>
  <litp:node id="svc-2">
    <hostname>ieatrcxb6036</hostname>
  </litp:node>
</litp:root>
"""


class TestHwResources(TestCase):
    def setUp(self):
        self.reported_data = []

    def setup_for_main_args(self, m_litp):
        stubbed_litp = LitpRestClient()
        deployments = {'_embedded': {'item': [{'id': 'enm'}]}}
        clusters = {'_embedded': {'item': [
            {'id': 'db_cluster'},
            {'id': 'svc_cluster'}
        ]}}
        db_cluster_nodes = {'_embedded': {'item': [
            {'id': 'db-1',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-db-1'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}},
            {'id': 'db-2',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-db-2'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}}
        ]}}
        svc_cluster_nodes = {'_embedded': {'item': [
            {'id': 'svc-1',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-svc-1'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}},
            {'id': 'svc-2',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-svc-2'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}}
        ]}}
        get_lms = {'id': 'ms',
                   'state': 'Applied',
                   'item-type-name': 'node',
                   'properties': {'hostname': 'cloud-ms-1'},
                   '_links': {'self': {'href': '/litp/rest/v1/'}}}

        setup_litp_mock(stubbed_litp, [
            ['GET', dumps({}), httplib.OK],
            ['GET', MODEL, httplib.OK],
            ['GET', dumps(deployments), httplib.OK],
            ['GET', dumps(clusters), httplib.OK],
            ['GET', dumps(db_cluster_nodes), httplib.OK],
            ['GET', dumps(svc_cluster_nodes), httplib.OK],
            ['GET', dumps(get_lms), httplib.OK]
        ])
        m_litp.return_value = stubbed_litp

        upgrade_xml_path = join(gettempdir(), 'upgrade_model.xml')
        with open(upgrade_xml_path, 'w') as ofile:
            ofile.write(UPGRADE_MODEL)

        runtime_model_path = join(gettempdir(), 'runtime_model.xml')
        with open(runtime_model_path, 'w') as ofile:
            ofile.write(MODEL)
        return upgrade_xml_path, runtime_model_path

    def assert_resource_usage(self, expected_reported, actual_reported):
        self.assertEqual(len(expected_reported), len(actual_reported))
        for row in actual_reported:
            node = row[HwResources.H_NODE]
            self.assertEqual(
                    expected_reported[node][HwResources.H_CPUU],
                    row[HwResources.H_CPUU],
                    msg='CPU usage calculated incorrectly!'
            )
            self.assertEqual(
                    expected_reported[node][HwResources.H_RAMU],
                    row[HwResources.H_RAMU],
                    msg='RAM usage calculated incorrectly!'
            )

    @patch('h_litp.litp_utils.get_xml_deployment_file')
    @patch('h_litp.litp_utils.get_dd_xml_file')
    @patch('h_litp.litp_utils.is_custom_service')
    def test_get_modeled_vm_resources(self, m_custom, m_dd, m_xml):
        hw = HwResources()
        model = join(gettempdir(), 'model_test.xml')
        ug_model = join(gettempdir(), 'upgrade_test.xml')

        try:
            with open(model, 'w') as ofile:
                ofile.write(MODEL)
            model_xml = load_xml(model)
            m_custom.side_effect = [False, True]
            get_model_data = hw.get_modeled_vm_resources(model_xml)
            model_result = {'svc_cluster':
                                {'custom_service':
                                     {'custom': True, 'ram': 2048, 'cpus': 2, 'node_list': ['svc-1', 'svc-2']},
                                 'lvsrouter':
                                     {'custom': False, 'ram': 2048, 'cpus': 2, 'node_list': ['svc-1', 'svc-2']}}}

            self.assertDictEqual(get_model_data, model_result)

            with open(ug_model, 'w') as ofile:
                ofile.write(UPGRADE_MODEL)
            ug_model_xml = load_xml(ug_model)
            get_with_current_usage = hw. \
                get_modeled_vm_resources(ug_model_xml, get_model_data)
            custom_result = {'scp_cluster':
                                 {'amos': {'custom': False, 'ram': 81920, 'cpus': 16, 'node_list': ['scp-1', 'scp-2']}},
                             'svc_cluster':
                                 {'custom_service_2': {'custom': False, 'ram': 2048, 'cpus': 2, 'node_list': ['svc-1', 'svc-2']},
                                  'custom_service': {'custom': True, 'ram': 2048, 'cpus': 2, 'node_list': ['svc-1', 'svc-2']}}}

            self.assertDictEqual(get_with_current_usage, custom_result)

        finally:
            os.remove(model)
            os.remove(ug_model)

    @patch('h_litp.litp_utils.get_xml_deployment_file')
    @patch('h_litp.litp_utils.get_dd_xml_file')
    def test_get_non_inheritted_vm_resources(self, m_dd, m_xml):
        hw = HwResources()
        model_ms_service = join(gettempdir(), 'non_inherited_service_test.xml')
        try:
            with open(model_ms_service, 'w') as ofile:
                ofile.write(NON_INHERITED_SERVICES)
            model_xml = load_xml(model_ms_service)
            get_model_data = hw.get_modeled_vm_resources(model_xml)
            not_inherited = {}
            self.assertDictEqual(get_model_data, not_inherited)
        finally:
            os.remove(model_ms_service)

    def test_get_blade_vm_resources(self):
        hw = HwResources()
        get_usage = {'svc_cluster': {
            'cmrules':
                {'cpus': 2,
                 'node_list': ['svc-1'],
                 'ram': 4096},
            'fmx':
                {'cpus': 4,
                 'node_list': ['svc-1', 'svc-2'],
                 'ram': 12288}}}

        blade_usage = hw.get_blade_vm_resources(get_usage)
        result = {'svc_cluster': {'svc-1': {'ram': 16384, 'cpus': 6},
                                  'svc-2': {'ram': 12288, 'cpus': 4}}}
        self.assertDictEqual(blade_usage, result)

    @patch('hw_resources.report_tab_data')
    def test_show_layout(self, m_report_tab_data):
        hw = HwResources()
        get_usage = {'svc_cluster': {
            'cmrules':
                {'cpus': 2,
                 'node_list': ['svc-1'],
                 'ram': 4096},
            'fmx':
                {'cpus': 4,
                 'node_list': ['svc-1', 'svc-2'],
                 'ram': 12288}}
        }

        self.reported_data = []

        def stubbed_report_tab_data(report_type, headers,
                                    table_data, verbose=True):
            self.reported_data.append(table_data)

        m_report_tab_data.side_effect = stubbed_report_tab_data

        hw.show_layout(get_usage)

        expected_report_1 = {
            'svc-1': {
                'fmx': {'RAM used (MB)': 12288, 'CPUs used': 4},
                'cmrules': {'RAM used (MB)': 4096, 'CPUs used': 2}
            },
            'svc-2': {
                'fmx': {'RAM used (MB)': 12288, 'CPUs used': 4}
            }
        }

        expected_report_2 = {
            'svc-1': {'RAM used (MB)': 16384, 'CPUs used': 6},
            'svc-2': {'RAM used (MB)': 12288, 'CPUs used': 4},
        }
        print self.reported_data
        self.assertEqual(2, len(self.reported_data))

        for row in self.reported_data[0]:
            act_node = row[HwResources.H_NODE]
            act_service = row[HwResources.H_SERVICE]

            self.assertIn(act_node, expected_report_1)
            self.assertIn(act_service, expected_report_1[act_node])

            exp_data = expected_report_1[act_node][act_service]
            self.assertEqual(
                    exp_data[HwResources.H_CPUU],
                    row[HwResources.H_CPUU],
                    msg='CPU usage calculated incorrectly!'
            )
            self.assertEqual(
                    exp_data[HwResources.H_RAMU],
                    row[HwResources.H_RAMU],
                    msg='RAM usage calculated incorrectly!'
            )

        for row in self.reported_data[1]:
            act_node = row[HwResources.H_NODE]
            self.assertIn(act_node, expected_report_2)

            exp_data = expected_report_2[act_node]
            self.assertEqual(
                    exp_data[HwResources.H_CPUU],
                    row[HwResources.H_CPUU],
                    msg='CPU usage calculated incorrectly!'
            )
            self.assertEqual(
                    exp_data[HwResources.H_RAMU],
                    row[HwResources.H_RAMU],
                    msg='RAM usage calculated incorrectly!'
            )

    @patch('hw_resources.HwResources.get_actual_cpus')
    @patch('hw_resources.HwResources.get_actual_mem')
    @patch('hw_resources.report_tab_data')
    def test_show_blade_vm_usage(self, rtd, mem, cpu):
        hw = HwResources()
        mem.return_value = {'ieatrcxb2539-1': 258208, 'ieatrcxb2540-1': 258208}
        cpu.return_value = {'ieatrcxb2539-1': 40, 'ieatrcxb2540-1': 40}

        modeled_usage = {'svc_cluster': {'svc-1': {'ram': 16384, 'cpus': 6},
                                         'svc-2': {'ram': 12288, 'cpus': 4}}}

        data = [dict(zip(HwResources.B_HEADER, ['svc_cluster', 'svc-2', 4,
                                                '0.1', 12288, 245920, 'OK'])),
                dict(zip(HwResources.B_HEADER, ['svc_cluster', 'svc-1', 6,
                                                '0.15', 16384, 241824, 'OK']))]
        hostidmappings = {'svc-1': 'ieatrcxb2539-1', 'svc-2': 'ieatrcxb2540-1'}
        node_states = {
            'ieatrcxb2539-1': LitpRestClient.ITEM_STATE_APPLIED,
            'ieatrcxb2540-1': LitpRestClient.ITEM_STATE_APPLIED
        }
        hw.show_blade_vm_usage(modeled_usage, hostidmappings, node_states)
        rtd.assert_called_with(None, HwResources.B_HEADER, data)

        mem.return_value = {'ieatrcxb2539-1': 16000, 'ieatrcxb2540-1': 12000}
        cpu.return_value = {'ieatrcxb2539-1': 5, 'ieatrcxb2540-1': 3}

        self.assertRaises(SystemExit, hw.show_blade_vm_usage, modeled_usage,
                          hostidmappings, node_states)

    def test_get_modeled_hosts(self):
        hw = HwResources()
        model = join(gettempdir(), 'get_modeled_hosts_test.xml')
        try:
            with open(model, 'w') as ofile:
                ofile.write(XML_NODES)
            model_xml = load_xml(model)
            result = {'svc-1': 'ieatrcxb6035', 'svc-2': 'ieatrcxb6036'}
            get_hostnames_dict = hw.get_modeled_hosts(model_xml)
            self.assertDictEqual(get_hostnames_dict, result)
        finally:
            os.remove(model)

    @patch('h_puppet.mco_agents.EnminstAgent.get_mem')
    def test_get_actual_mem(self, agent):
        hw = HwResources()
        model = join(gettempdir(), 'get_actual_mem_test.xml')
        try:
            with open(model, 'w') as ofile:
                ofile.write(XML_NODES)

            agent.return_value = {'ieatrcxb6035': 1024, 'ieatrcxb6036': 1024}

            result = {'ieatrcxb6035': 1, 'ieatrcxb6036': 1}
            get_actual_mem = hw.get_actual_mem()
            self.assertDictEqual(get_actual_mem, result)
        finally:
            os.remove(model)

    @patch('h_puppet.mco_agents.EnminstAgent.get_cores')
    def test_get_actual_cpus(self, agent):
        hw = HwResources()
        model = join(gettempdir(), 'get_actual_mem_test.xml')
        try:
            with open(model, 'w') as ofile:
                ofile.write(XML_NODES)

            agent.return_value = {'ieatrcxb6035': 40, 'ieatrcxb6036': 40}

            result = {'ieatrcxb6035': 40, 'ieatrcxb6036': 40}
            get_actual_cpus = hw.get_actual_cpus()
            self.assertDictEqual(get_actual_cpus, result)
        finally:
            os.remove(model)

    def test_main_no_args(self):
        self.assertRaises(SystemExit, hw_resources.main, [])

    def test_main_wrong_args(self):
        self.assertRaises(SystemExit, hw_resources.main, '-r -s'.split())

    @patch('h_litp.litp_utils.get_xml_deployment_file')
    @patch('h_litp.litp_utils.get_dd_xml_file')
    @patch('hw_resources.report_tab_data')
    @patch('hw_resources.HwResources.litp')
    @patch('h_litp.litp_utils.is_custom_service')
    def test_main_args(self, m_custom, m_litp, m_report_tab_data, m_dd, m_xml):
        upgrade_xml_path, runtime_model_path = self.setup_for_main_args(
                m_litp)

        self.reported_data = None

        def stubbed_report_tab_data(report_type, headers,
                                    table_data, verbose=True):
            self.reported_data = table_data

        m_report_tab_data.side_effect = stubbed_report_tab_data

        expected_svc = {
            'svc-1': {
                HwResources.H_STATE: HwResources.STATE_NOK,
                HwResources.H_CPUU: 6,
                HwResources.H_RAMU: 6144
            },
            'svc-2': {
                HwResources.H_STATE: HwResources.STATE_NOK,
                HwResources.H_CPUU: 6,
                HwResources.H_RAMU: 6144
            }
        }
        expected_svc_2 = {
            'svc-1': {
                HwResources.H_STATE: HwResources.STATE_NOK,
                HwResources.H_CPUU: 4,
                HwResources.H_RAMU: 4096
            },
            'svc-2': {
                HwResources.H_STATE: HwResources.STATE_NOK,
                HwResources.H_CPUU: 4,
                HwResources.H_RAMU: 4096
            }
        }
        expected_scp = {
            'scp-1': {
                HwResources.H_STATE: LitpRestClient.ITEM_STATE_INITIAL,
                HwResources.H_CPUU: 16,
                HwResources.H_RAMU: 81920
            },
            'scp-2': {
                HwResources.H_STATE: LitpRestClient.ITEM_STATE_INITIAL,
                HwResources.H_CPUU: 16,
                HwResources.H_RAMU: 81920
            }
        }

        try:
            args = '-r -um {0}'.format(upgrade_xml_path)
            m_custom = [False, True, False, True,
                        False, True, False, True]
            with self.assertRaises(SystemExit) as sysexit:
                hw_resources.main(args.split())
            self.assertEqual(sysexit.exception.code, 1)
            expected_reported = dict()
            expected_reported.update(expected_svc)
            expected_reported.update(expected_scp)
            self.assert_resource_usage(expected_reported, self.reported_data)

            args = '-r -m {0} -um {1}'.format(runtime_model_path,
                                              upgrade_xml_path)

            self.reported_data = None
            hw_resources.main(args.split())
            self.assert_resource_usage(expected_reported, self.reported_data)

            args = '-r -m {0}'.format(runtime_model_path)
            self.reported_data = None
            hw_resources.main(args.split())
            self.assert_resource_usage(expected_svc_2, self.reported_data)

            args = '-s -m {0}'.format(abspath(runtime_model_path))
            self.reported_data = None
            hw_resources.main(args.split())
            print self.reported_data
            self.assert_resource_usage(expected_svc_2, self.reported_data)
        finally:
            os.remove(runtime_model_path)
            os.remove(upgrade_xml_path)


if __name__ == '__main__':
    unittest2.main()
