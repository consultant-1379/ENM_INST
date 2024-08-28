from mock import patch
import mock
import unittest2

from h_snapshots.snap_agent import SnapAgents


class TestSnapAgent(unittest2.TestCase):
    def setUp(self):
        self.san_cred = {'san_login_scope': 'global', 'san_user': 'admin',
                         'san_spb_ip': '10.32.236.189',
                         'san_spa_ip': '10.32.236.188', 'san_psw':
                             'passw0rd',
                         'san_pool': 'Fargo9'}

    @patch('h_snapshots.snap_agent.SnapAgents.mco_exec')
    def test_create_versant_snapshot(self, mco_exec):
        snapper = SnapAgents()
        snapper.create_versant_snapshot('versant', '55',
                                        'vnx2',
                                        self.san_cred['san_spa_ip'],
                                        self.san_cred['san_spb_ip'],
                                        'node_1',
                                        self.san_cred['san_user'],
                                        self.san_cred['san_psw'],
                                        self.san_cred['san_login_scope'],
                                        'Snapshot', 'ENM_Upgrade_Snapshot')
        expected_args = ['dbtype=versant',
                         'array_type=vnx2',
                         'spa_ip=10.32.236.188',
                         'spb_ip=10.32.236.189',
                         'spa_username=admin',
                         'Password=passw0rd',
                         'Scope=global',
                         'dblun_id=55',
                         'snap_name=Snapshot_55',
                         'descr=ENM_Upgrade_Snapshot']

        mco_exec.assert_called_with('create_snapshot', expected_args, 'node_1')

    @patch('h_snapshots.snap_agent.SnapAgents.mco_exec')
    def test_create_mysql_snapshot(self, mco_exec):
        snapper = SnapAgents()
        snapper.create_mysql_snapshot('mysql', '56',
                                      'vnx2',
                                      self.san_cred['san_spa_ip'],
                                      self.san_cred['san_spb_ip'],
                                      'node_2',
                                      self.san_cred['san_user'],
                                      self.san_cred['san_psw'],
                                      self.san_cred['san_login_scope'],
                                      'Snapshot',
                                      'ENM_Upgrade_Snapshot',
                                      'root')
        expected_args = [
            'dbtype=mysql',
            'array_type=vnx2',
            'spa_ip=10.32.236.188',
            'spb_ip=10.32.236.189',
            'spa_username=admin',
            'Password=passw0rd',
            'Scope=global',
            'dblun_id=56',
            'snap_name=Snapshot_56',
            'descr=ENM_Upgrade_Snapshot',
            'mysql_user=root'
        ]

        mco_exec.assert_called_with('create_snapshot', expected_args,
                                    'node_2')

    @patch('h_snapshots.snap_agent.SnapAgents.mco_exec')
    def test_backup_opendj(self, mco_exec):
        node_list = ['node_1', 'node_2']
        opendj_backup_cmd = '/opt/ericsson/com.ericsson.oss.security/' \
                            'idenmgmt/opendj/bin/opendj_backup.sh'
        opendj_backup_dir = '/var/tmp/opendj_backup'
        opendj_log_dir = '/var/tmp/opendj_backup_log'
        snapper = SnapAgents()
        snapper.backup_opendj(node_list, opendj_backup_cmd, opendj_backup_dir,
                              opendj_log_dir)
        expected_args = ['opendj_backup_cmd={0}'.format(opendj_backup_cmd),
                         'opendj_backup_dir={0}'.format(opendj_backup_dir),
                         'opendj_log_dir={0}'.format(opendj_log_dir)]
        for node in node_list:
            mco_exec.assert_has_calls([mock.call('opendj_backup',
                                                 expected_args,
                                                 node,
                                                 rpc_command_timeout=210)],
                                                       any_order=False)

    @patch('h_snapshots.snap_agent.SnapAgents.mco_exec')
    def test_cleanup_opendj(self, mco_exec):
        node_list = ['node_1', 'node_2']
        opendj_backup_dir = '/var/tmp/opendj_backup'
        opendj_log_dir = '/var/tmp/opendj_backup_log'
        snapper = SnapAgents()
        snapper.cleanup_opendj(node_list, opendj_backup_dir, opendj_log_dir)
        expected_args = ['opendj_backup_dir={0}'.format(opendj_backup_dir),
                         'opendj_log_dir={0}'.format(opendj_log_dir)]
        for node in node_list:
            mco_exec.assert_has_calls([mock.call('opendj_cleanup',
                                                 expected_args,
                                                 node)], any_order=False)

    @patch('h_snapshots.snap_agent.SnapAgents.mco_exec')
    def test_ensure_installed(self, m_mco_exec):
        snapper = SnapAgents()
        snapper.ensure_installed('packagename', 'node1')
        m_mco_exec.assert_called_with('ensure_installed',
                                      ['package=packagename'],
                                      'node1')
