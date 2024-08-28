import unittest2
from mock import patch

from h_litp.litp_rest_client import LitpRestClient
from litpd import LitpIntegration
from vcs_seed_control import GabconfigX, main


class TestVcsSeedControl(unittest2.TestCase):

    @patch('vcs_seed_control.exec_process')
    def test_set_cluster_seed_control(self, ep):
        gabconfig = GabconfigX()
        gabconfig.set_cluster_seed_control('hostA')
        ep.assert_called_with('mco rpc enminst set_cluster_seed_control -I hostA', use_shell=True)


    @patch('h_vcs.vcs_cli.Vcs.get_cluster_system_status')
    def test_get_single_running_node(self, m_gcss):
        gabconfig = GabconfigX()

        headers = ['System', 'State', 'Cluster', 'Frozen']
        data = [{'Frozen': '-', 'Cluster': 'svc_cluster','State': 'EXITED', 'System': 'svc-1'},
                {'Frozen': '-', 'Cluster': 'svc_cluster','State': 'EXITED', 'System': 'svc-2'},
                {'Frozen': '-', 'Cluster': 'svc_cluster','State': 'OFFLINE', 'System': 'svc-3'},
                {'Frozen': '-', 'Cluster': 'svc_cluster','State': 'OFFLINE', 'System': 'svc-4'},
                {'Frozen': '-', 'Cluster': 'svc_cluster','State': 'OFFLINE', 'System': 'svc-5'}
                ]

        m_gcss.side_effect = [(headers, data)]
        self.assertEqual(gabconfig.get_single_running_node('svc_cluster'), 'svc-1')
        data = []
        m_gcss.side_effect = [(headers, data)]
        self.assertEqual(gabconfig.get_single_running_node('evt_cluster'), None)

    @patch('os.path.isfile')
    @patch('h_snapshots.lvm_snapshot.LVMManager.get_nodes_using_local_storage')
    @patch('vcs_seed_control.GabconfigX')
    def test_main(self, m_gabX, m_get_racks, m_isfile):
        m_isfile.return_value = True
        litpd = LitpIntegration()
        litpd.setup_str_cluster_multiple_nodes(['str-1'], state=LitpRestClient.
                                               ITEM_STATE_APPLIED)
        racks = {}
        litp_obj = litpd.get_cluster_nodes().values()[0]['str-1']
        racks[litp_obj] = [u'sda']

        m_get_racks.return_value = racks
        main()
        self.assertEqual(m_gabX.call_count, 1)
        m_isfile.return_value = False
        self.assertRaises(SystemExit, main)
