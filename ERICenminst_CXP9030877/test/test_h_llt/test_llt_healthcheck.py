import unittest2
from mock import patch
from h_llt.llt_healthcheck import LltHealthCheck


class TestLltHealthCheck(unittest2.TestCase):

    def get_lltstat_mco_output(self, svc1_eth6_status='UP', svc2_eth6_status='UP'):
        output = {}
        output['cloud-db-1'] = ('LLT node information:\n'
                                '       Node      State Link  Status  Address\n'
                                '  * 0 cloud-db-1 OPEN\n'
                                '                       eth6   UP    00:50:56:00:00:F3\n'
                                '                       eth5   UP    00:50:56:00:00:F2\n'
                                '                       eth4   UP    00:50:56:00:00:F1\n')
        output['cloud-svc-1'] = ('LLT node information:\n'
                                 '       Node       State Link  Status  Address\n'
                                 '  * 0 cloud-svc-1 OPEN\n'
                                 '                       eth6   {0}    00:50:56:00:00:E1\n'
                                 '                       eth5   UP    00:50:56:00:00:E0\n'
                                 '                       br1    UP    00:50:56:00:00:DF\n'
                                 '    1 cloud-svc-2 OPEN\n'
                                 '                       eth6   {1}    00:50:56:00:00:EA\n'
                                 '                       eth5   UP    00:50:56:00:00:E9\n'
                                 '                       br1    UP    00:50:56:00:00:E8\n'
                                 .format(svc1_eth6_status,
                                        svc2_eth6_status))
        output['cloud-svc-2'] = ('LLT node information:\n'
                                 '       Node       State Link  Status  Address\n'
                                 '    0 cloud-svc-1 OPEN\n'
                                 '                       eth6   {0}    00:50:56:00:00:E1\n'
                                 '                       eth5   UP    00:50:56:00:00:E0\n'
                                 '                       br1    UP    00:50:56:00:00:DF\n'
                                 '  * 1 cloud-svc-2 OPEN\n'
                                 '                       eth6   UP    00:50:56:00:00:EA\n'
                                 '                       eth5   UP    00:50:56:00:00:E9\n'
                                 '                       br1    UP    00:50:56:00:00:E8\n'
                                 .format(svc1_eth6_status))
        return output

    def get_cluster_ids_mco_output(self):
        return {'cloud-db-1': 'db_cluster',
                'cloud-svc-1': 'svc_cluster',
                'cloud-svc-2': 'svc_cluster'}

    def test_LltHealthCheck_subclasses(self):
        class McoAgentReturnNothing(object):
            def get_lltstat_data(self):
                return {}

            def get_cluster_list(self):
                return {}

        class McoAgentReturnFullData(object):
            def __init__(self, testcase, svc1_eth6_status='UP',
                         svc2_eth6_status='UP'):
                self.testcase = testcase
                self.svc1_eth6_status = svc1_eth6_status
                self.svc2_eth6_status = svc2_eth6_status

            def get_lltstat_data(self):
                return self.testcase.get_lltstat_mco_output(
                    self.svc1_eth6_status, self.svc2_eth6_status)

            def get_cluster_list(self):
                return self.testcase.get_cluster_ids_mco_output()

        nic1 = LltHealthCheck.LltNic('eth1', 'UP', '00:50:56:00:00:E0')
        nic2 = LltHealthCheck.LltNic('eth2', 'UP', '00:60:56:00:00:E0')

        node1 = LltHealthCheck.LltNode('cloud-svc-1', [nic1, nic2])

        self.assertTrue(node1.is_healthy())
        nic2.status = 'NOT-UP'
        self.assertFalse(node1.is_healthy())

        deployment1 = LltHealthCheck.LltDeployment(McoAgentReturnNothing())
        self.assertFalse(deployment1.is_healthy())

        deployment2 = LltHealthCheck.LltDeployment(McoAgentReturnFullData(self))
        self.assertTrue(deployment2.is_healthy())

        deployment3 = LltHealthCheck.LltDeployment(McoAgentReturnFullData(self,
                                                    svc1_eth6_status='DOWN'))
        self.assertFalse(deployment3.is_healthy())

        representation = "%s" % (deployment3)

        # TORF-334377
        deployment4 = LltHealthCheck.LltDeployment(McoAgentReturnFullData(self,
                                                    svc2_eth6_status='DOWN'))
        self.assertFalse(deployment4.is_healthy())

    @patch('h_llt.llt_healthcheck.LltStatAgent.get_lltstat_data')
    def test_LltHealthCheck_sysexit(self, get_lltstat_data):
        get_lltstat_data.side_effect = [{}]
        self.assertRaises(SystemExit, LltHealthCheck().verify_health)

    @patch('h_llt.llt_healthcheck.LltStatAgent.get_lltstat_data')
    def test_LltHealthCheck(self, get_lltstat_data):
        get_lltstat_data.side_effect = [self.get_lltstat_mco_output()]
        self.assertTrue(LltHealthCheck().verify_health())


if __name__ == '__main__':
    unittest2.main()
