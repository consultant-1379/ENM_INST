import unittest2

from enm_upgrade_prechecks import EnmPreChecks
from reinstall_peer_nodes import ReinstallPeerNodes, main
from h_util.h_utils import get_enable_cron_on_expiry_cmd, \
                            cmd_DISABLE_CRON_ON_EXPIRY
from h_litp.litp_utils import LitpException
from mock import patch, call
import tempfile
from os import remove, path
from json import dump


class MockLitpObject(object):
    def __init__(self, path, state, properties, item_id):
        self.path = path
        self.state = state
        self.properties = properties
        self.item_id = item_id

    def get_property(self, key):
        return self.properties[key]

class TestReinstallPeerNodes(unittest2.TestCase):

    @patch('reinstall_peer_nodes.ReinstallPeerNodes.update_kickstart_template')
    @patch('enm_upgrade_prechecks.EnmPreChecks.check_litp_model_synchronized')
    @patch('reinstall_peer_nodes.ReinstallPeerNodes.create_run_plan')
    @patch('reinstall_peer_nodes.ReinstallPeerNodes.set_nodes_to_initial')
    @patch('reinstall_peer_nodes.ReinstallPeerNodes.get_hostname_details')
    @patch('reinstall_peer_nodes.ReinstallPeerNodes.load_list_from_file')
    @patch('__builtin__.raw_input')
    @patch('os.path.isfile')
    def test_reinstall(self, m_isfile, m_raw_input, m_load_list,
                       m_get_hostname_details, m_set_nodes_to_initial,
                       m_create_run_plan, m_check_litp_model_synchronized,
                       m_update_kickstart_template):
        m_check_litp_model_synchronized.return_value = True
        rpn = ReinstallPeerNodes()
        m_raw_input.return_value = 'YeS'
        m_isfile.side_effect = [False, True]
        self.assertRaises(SystemExit, rpn.reinstall)
        m_isfile.side_effect = [True, True]
        m_load_list.return_value = ['ieatebs1', 'ieatebs2']
        m_get_hostname_details.return_value = {'str-1':'str_cluster',
                                               'str-2':'str-cluster'}
        rpn.reinstall()
        m_get_hostname_details.assert_called_with(m_load_list.return_value)
        m_set_nodes_to_initial.assert_called_with \
            (m_get_hostname_details.return_value)
        self.assertTrue(m_create_run_plan.called)
        expected_calls= [call(get_enable_cron_on_expiry_cmd(
            ReinstallPeerNodes.RHEL7_SYSTEM_AUTH)),
                         call(cmd_DISABLE_CRON_ON_EXPIRY)]
        m_update_kickstart_template.assert_has_calls(expected_calls)

    @patch('reinstall_peer_nodes.ReinstallPeerNodes.update_kickstart_template')
    @patch('reinstall_peer_nodes.ReinstallPeerNodes.set_nodes_to_initial')
    @patch('reinstall_peer_nodes.ReinstallPeerNodes.create_run_plan')
    @patch('reinstall_peer_nodes.ReinstallPeerNodes.get_hostname_details')
    @patch('reinstall_peer_nodes.ReinstallPeerNodes.load_list_from_file')
    @patch('__builtin__.raw_input')
    @patch('os.path.isfile')
    def test_reinstall_litp_exception(self, m_isfile, m_raw_input, m_load_list,
                                      m_get_hostname_details, m_create_run_plan,
                                      m_set_nodes_to_intial,
                                      m_update_kickstart_template):
        rpn = ReinstallPeerNodes()
        m_raw_input.return_value = 'YeS'
        m_isfile.side_effect = [True, True]
        m_load_list.return_value = ['ieatebs1', 'ieatebs2']
        m_get_hostname_details.return_value = {'str-1':'str_cluster',
                                               'str-2':'str-cluster'}
        m_set_nodes_to_intial.called
        m_create_run_plan.side_effect = LitpException
        self.assertRaises(SystemExit, rpn.reinstall)

    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    def test_get_hostname_details(self, m_get_cluster_nodes):
        rpn = ReinstallPeerNodes()
        node_list = ['ieatstr1', 'ieatstr2']

        str1_object  =  MockLitpObject("/deployments/enm/clusters/"
                                       "str_cluster/nodes/str-1" ,'Applied',
                                       {'is_locked': 'false',
                                        'hostname': 'ieatstr1'},'str-1')

        str2_object  =  MockLitpObject("/deployments/enm/clusters/"
                                       "str_cluster/nodes/str-2" ,'Applied',
                                       {'is_locked': 'false',
                                        'hostname': 'ieatstr2'},'str-2')

        svc1_object  =  MockLitpObject("/deployments/enm/clusters/"
                                       "svc_cluster/nodes/svc-1" ,'Applied',
                                       {'is_locked': 'false',
                                        'hostname': 'ieatsvc1'},'svc-1')

        svc2_object  =  MockLitpObject("/deployments/enm/clusters/"
                                       "svc_cluster/nodes/svc-2" ,'Applied',
                                       {'is_locked': 'false',
                                        'hostname': 'ieatsvc2'},'svc-2')

        SVC_CLUSTER = 'svc_cluster'
        STR_CLUSTER = 'str_cluster'
        SVC_CLUSTER_NODES = {'svc-1':svc1_object,
                             'svc-2':svc2_object}
        STR_CLUSTER_NODES = {'str-1':str1_object,
                             'str-2':str2_object}

        MOCK_CLUSTER_NODES = {STR_CLUSTER: STR_CLUSTER_NODES,
                              SVC_CLUSTER: SVC_CLUSTER_NODES}

        m_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES

        self.assertEqual(rpn.get_hostname_details(node_list),
                         {'str-1':'str_cluster', 'str-2':'str_cluster'})

    @patch('reinstall_peer_nodes.exec_process')
    def test_set_nodes_to_initial(self, m_exec_process):
        rpn = ReinstallPeerNodes()
        hostname_details = {'str-1':'str_cluster', 'str-2':'str_cluster'}
        str1_cmd = ['/usr/bin/litp', 'prepare_restore', '-p',
                    '/deployments/enm/clusters/str_cluster/nodes/str-1/']
        str2_cmd = ['/usr/bin/litp', 'prepare_restore', '-p',
                    '/deployments/enm/clusters/str_cluster/nodes/str-2/']
        rpn.set_nodes_to_initial(hostname_details)

        m_exec_process.assert_has_calls(
            [call(str1_cmd)])
        m_exec_process.assert_has_calls(
            [call(str2_cmd)])

        m_exec_process.side_effect = IOError
        self.assertRaises(SystemExit, rpn.set_nodes_to_initial,
                          hostname_details)

    @patch('h_litp.litp_rest_client.LitpRestClient.create_plan')
    @patch('h_litp.litp_rest_client.LitpRestClient.set_plan_state')
    @patch('h_litp.litp_rest_client.LitpRestClient.monitor_plan')
    def test_create_run_plan(self, m_mp, m_sps, m_cp):
        rpn = ReinstallPeerNodes()
        rpn.create_run_plan()
        self.assertTrue(m_cp.called)
        self.assertTrue(m_sps.called)
        self.assertTrue(m_mp.called)
        m_mp.side_effect = LitpException
        self.assertRaises(SystemExit, rpn.create_run_plan)
        m_sps.side_effect = LitpException
        self.assertRaises(SystemExit, rpn.create_run_plan)
        m_cp.side_effect = LitpException
        self.assertRaises(SystemExit, rpn.create_run_plan)

    @patch('os.path.exists')
    def test_load_list(self, m_exists):
        rpn = ReinstallPeerNodes()
        m_exists.return_value = True
        lost_nodes = ['ieatstr1', 'ieatstr2']
        node_list_file = tempfile.mktemp()

        with open(node_list_file, 'w+') as _writer:
            dump(lost_nodes, _writer)

        self.assertEqual(rpn.load_list_from_file(node_list_file), lost_nodes)

        if path.exists(node_list_file):
            remove(node_list_file)

        self.assertEqual(rpn.load_list_from_file(node_list_file), None)


    @patch('reinstall_peer_nodes.ReinstallPeerNodes')
    def test_main(self, m_rpn):
        main()
        m_rpn.assert_called_once_with()
