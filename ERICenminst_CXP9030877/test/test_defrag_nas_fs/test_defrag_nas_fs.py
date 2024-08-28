import unittest2
from mock import call, MagicMock, patch

from defrag_nas_fs import NasLitpModel, DefragNasFs, NasCommandException, \
    main, disconnect, nas_command

sp1_path = [
    {'path': '/infrastructure/storage/storage_providers/sp1',
     'data': {'item-type-name': 'sfs-service', 'state': 'Applied',
              '_links': {'self': {'href': 'https://localhost:9999/litp/rest/'
                                          'v1/infrastructure/storage/storage'
                                          '_providers/sp1'},
                         'item-type': {'href': 'https://localhost:9999/litp/'
                                               'rest/v1/item-types/sfs-service'
                                       }},
              'id': 'sp1',
              'properties': {'management_ipv4': '192.168.50.19',
                             'user_name': 'support', 'name': 'sfs1',
                             'password_key': 'key-for-sfs'}}}]

fs_path = [
    {'path': '/infrastructure/storage/storage_providers/sp1/pools/pl1/'
             'file_systems/fs1',
     'data': {'item-type-name': 'sfs-filesystem', 'state': 'Applied',
              '_links': {'self': {'href': 'https://localhost:9999/litp/rest/'
                                          'v1/infrastructure/storage/storage_'
                                          'providers/sp1/pools/pl1/'
                                          'file_systems/fs1'},
                         'item-type': {'href': 'https://localhost:9999/litp/'
                                               'rest/v1/item-types/'
                                               'sfs-filesystem'}},
              'id': 'fs1',
              'properties': {'path': '/vx/enm1-00pm', 'size': '10G'}}}]


class TestNasLitpModel(unittest2.TestCase):

    @patch('h_litp.litp_rest_client.LitpRestClient.get_children')
    def test_get_sfs_info(self, rest_mock):
        ni = NasLitpModel()
        rest_mock.side_effect = [sp1_path, fs_path]
        sfs_info = ni.get_nas_info()
        self.assertDictEqual(
                sfs_info, {'sp1': ['192.168.50.19', 'support', 'key-for-sfs',
                                   ['/vx/enm1-00pm']]})


class TestDefragNasFs(unittest2.TestCase):

    def patch_ssh(self, ssh_mock, return_code, stdout, stderr):
        mstdout = MagicMock()
        mstdout.channel.recv_exit_status.return_value = return_code
        mstdout.readlines.return_value = stdout

        mstderr = MagicMock()
        mstderr.stderr.read.return_value = stderr

        ssh_mock.exec_command.return_value = [
            None, mstdout, mstderr]

    @patch('litp.core.base_plugin_api.BasePluginApi.get_password')
    @patch('paramiko.SSHClient')
    def test_connect_to_nas(self, ssh_mock, pass_mock):
        pass_mock.return_value = 'test123'
        dnf = DefragNasFs()
        dnf.connect_to_nas('', '', '')
        ssh_mock.return_value.set_missing_host_key_policy.assert_called_once()
        ssh_mock.return_value.connect.assert_called_once_with(
                '', username='', password='test123', port=22)

        pass_mock.return_value = None
        self.assertRaises(SystemExit, dnf.connect_to_nas, '', '', '')

    def test_disconnect(self):
        m_ssh = MagicMock()
        disconnect(m_ssh)
        m_ssh.close.assert_called_once_with()

    def test_nas_command(self):
        ssh = MagicMock()
        command = 'test command'
        self.patch_ssh(ssh, 0, ['test output'], [])
        rc, output = nas_command(ssh, command)
        self.assertListEqual(output, ['test output'])
        self.assertEquals(rc, 0)

        self.patch_ssh(ssh, 1, ['test output'], ['test error'])
        self.assertRaises(NasCommandException, nas_command, ssh, command)

    def test_get_nas_mounted_fs(self):
        sfsdg = '/dev/vx/dsk/sfsdg'
        sfs_fs_list = ['/dev/sda5 on /opt type ext3 (rw,acl,user_xattr)',
                       sfsdg + '/_nlm_ on /var/lib/nfs/sm type vxfs ()',
                       sfsdg + '/enm1-01pm on /vx/enm1-01pm type vxfs ()',
                       sfsdg + '/enm1-02pm on /vx/enm1-02pm type vxfs ()']
        ssh = MagicMock()
        dnf = DefragNasFs()

        self.patch_ssh(ssh, 0, sfs_fs_list, [])
        mounted_fs = dnf.get_nas_mounted_fs(ssh)
        self.assertTrue(2, len(mounted_fs))
        self.assertIn('/vx/enm1-01pm', mounted_fs)
        self.assertIn('/vx/enm1-02pm', mounted_fs)

        self.patch_ssh(ssh, 1, [], ['Cannot display FS'])
        self.assertRaises(NasCommandException, dnf.get_nas_mounted_fs, ssh)

    @patch('defrag_nas_fs.NasLitpModel.get_nas_info')
    @patch('defrag_nas_fs.disconnect')
    def test_defrag_fs(self, m_disconnect, m_get_nas_info):

        sfsdg = '/dev/vx/dsk/sfsdg'
        sfs_fs_list = ['/dev/sda5 on /opt type ext3 (rw,acl,user_xattr)',
                       sfsdg + '/_nlm_ on /var/lib/nfs/sm type vxfs ()',
                       sfsdg + '/enm1-01pm on /vx/enm1-01pm type vxfs ()',
                       sfsdg + '/enm1-02pm on /vx/enm1-02pm type vxfs ()']

        m_get_nas_info.return_value = {'sp1': ['192.168.50.19',
                                               'support', 'key-for-sfs',
                                               ['/vx/enm1-02pm',
                                                '/vx/enm1-00pm']]}

        dnf = DefragNasFs()
        m_ssh = MagicMock()
        self.patch_ssh(m_ssh, 0, sfs_fs_list, [])

        m_connect_to_nas = MagicMock(return_value=m_ssh)
        dnf.connect_to_nas = m_connect_to_nas

        dnf.disconnect = MagicMock()

        dnf.defrag_fs()
        m_connect_to_nas.assert_called_once_with('192.168.50.19', 'support',
                                                 'key-for-sfs')
        m_ssh.assert_has_calls([
            call.exec_command(
                    '/opt/VRTS/bin/fsadm -t vxfs -T 3600 -d /vx/enm1-02pm')
        ])

        m_ssh.reset_mock()
        self.patch_ssh(m_ssh, 1, sfs_fs_list, [])
        self.assertRaises(NasCommandException, dnf.defrag_fs)

    @patch('defrag_nas_fs.DefragNasFs')
    def test_main(self, m_defragnasfs):
        main()
        m_defragnasfs.assert_called_once_with()


if __name__ == '__main__':
    unittest2.main()
