import os
from os import remove
from os.path import join, dirname, basename
from re import match
from tempfile import gettempdir

import unittest2
from mock import patch, MagicMock, call, mock_open

import sys

sys.modules['naslib.log'] = MagicMock()
sys.modules['naslib.objects'] = MagicMock()
sys.modules['naslib.drivers'] = MagicMock()
sys.modules['naslib.drivers.sfs'] = MagicMock()
sys.modules['naslib.drivers.sfs.utils'] = MagicMock()

import cleanup_sfs
from cleanup_sfs import SfsCleanup, main, teardown_sfs, get_ip_address, \
    get_assigned_ips, plumber, ping_nasconsole, format_msg
from h_util.h_nas_console import NasConsoleException

TC_MODULE = 'cleanup_sfs'
SYSTEMCTL = '/usr/bin/systemctl'

# noinspection PyUnusedLocal
class TestCleanupSfs(unittest2.TestCase):
    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    def test_remove_shares(self, sed, nc):
        nc.return_value.nfs_share_show.return_value = {
            'fs1': [{'client': 'c1'}],
            'fs2': [{'client': 'c1'}]
        }

        deleted = {}

        def se(fs, ex):
            deleted[fs] = ex

        nc.return_value.nfs_share_delete = se

        sfs = SfsCleanup(sed)
        sfs.remove_shares()
        self.assertIn('fs1', deleted)
        self.assertIn('fs2', deleted)
        self.assertTrue('c1', deleted['fs1'])
        self.assertTrue('c1', deleted['fs2'])

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    def test_remove_shares_exclude(self, sed, nc):
        nc.return_value.nfs_share_show.return_value = {
            'fs1': [{'client': 'c1'}],
            'no_rollback': [{'client': 'c2'}]
        }

        deleted = {}

        def se(fs, ex):
            deleted[fs] = ex

        nc.return_value.nfs_share_delete = se

        sfs = SfsCleanup(sed)
        sfs.remove_shares(exclude='no_rollback')

        self.assertNotIn('no_rollback', deleted)
        self.assertIn('fs1', deleted)

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    def test_ensure_filesystems_destroyed(self, sed, nc):
        nc.return_value.storage_fs_list.return_value = {
            'f1': None, 'f2': None
        }
        deleted = []

        def se(fs):
            deleted.append(fs)

        nc.return_value.storage_fs_destroy = se
        sfs = SfsCleanup(sed)
        sfs.ensure_fs_destroyed(filesystem='test')

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    def test_remove_filesystem_snapshots(self, sed, nc):
        nc.return_value.storage_rollback_list.return_value = {
            'rb-fs1': ['fs1'],
            'rb-fs2': ['fs2']
        }

        deleted = {}

        def se(fs, ex):
            deleted[fs] = ex

        nc.return_value.storage_rollback_destroy = se

        sfs = SfsCleanup(sed)
        sfs.remove_filesystem_snapshots()
        self.assertIn('fs1', deleted)
        self.assertIn('fs2', deleted)
        self.assertTrue('rb-fs1', deleted['fs1'])
        self.assertTrue('rb-fs2', deleted['fs2'])

        nc.return_value.storage_rollback_list.return_value = {}
        m_storage_rollback_destroy = MagicMock()
        nc.return_value.storage_rollback_destroy = m_storage_rollback_destroy
        sfs.remove_filesystem_snapshots()
        self.assertFalse(m_storage_rollback_destroy.called)

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    @patch(TC_MODULE + '.os.path')
    def test_remove_filesystems(self, other_path, sed, nc):
        nc.return_value.storage_fs_list.return_value = {
            'f1': None, 'f2': None
        }

        deleted = []
        other_path.isfile.return_value = True

        def se(fs):
            deleted.append(fs)

        nc.return_value.storage_fs_destroy = se

        sfs = SfsCleanup(sed)
        sfs.remove_filesystems()
        self.assertTrue('f1' in deleted)
        self.assertTrue('f2' in deleted)

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    @patch(TC_MODULE + '.os.path')
    def test_remove_filesystems_exclude(self, other_path, sed, nc):
        nc.return_value.storage_fs_list.return_value = {
            'f1': None, 'f2': None, 'no_rollback': None
        }

        deleted = []
        other_path.isfile.return_value = True

        def se(fs):
            deleted.append(fs)

        nc.return_value.storage_fs_destroy = se

        sfs = SfsCleanup(sed)
        sfs.remove_filesystems(exclude='no_rollback')
        self.assertIn('f1', deleted)
        self.assertIn('f2', deleted)
        self.assertNotIn('no_rollback', deleted)

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    @patch(TC_MODULE + '.os.path')
    def test_remove_filesystems_else(self, other_path, sed, nc):
        nc.return_value.storage_fs_list.return_value = {
            'f1': None, 'f2': None
        }

        deleted = []
        other_path.isfile.return_value = False

        def se(fs):
            deleted.append(fs)

        _tmp = nc.return_value.storage_fs_destroy
        nc.return_value.storage_fs_destroy = se

        sfs = SfsCleanup(sed)
        sfs.remove_filesystems()
        nc.return_value.storage_fs_destroy = _tmp
        self.assertTrue('f1' in deleted)
        self.assertTrue('f2' in deleted)

        nc.return_value.storage_fs_destroy.side_effect = NasConsoleException()
        m_ensure_fs_destroyed = MagicMock()
        sfs.ensure_fs_destroyed = m_ensure_fs_destroyed
        sfs.remove_filesystems()
        self.assertEqual(2, m_ensure_fs_destroyed.call_count)

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    def test_remove_filesystems_none(self, m_sed, m_nasconsole):
        m_nasconsole.return_value.storage_fs_list.return_value = {}
        sfs = SfsCleanup(m_sed)
        sfs.remove_filesystems()
        self.assertFalse(m_nasconsole.return_value.storage_fs_destroy.called)

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    def test_remove_rollback_cache(self, sed, nc):
        nc.return_value.storage_rollback_cache_list.return_value = ['c1-cache',
                                                                    'c2_cache',
                                                                    'c2-cache']

        deleted = []

        def se(p):
            deleted.append(p)

        nc.return_value.storage_rollback_cache_destroy = se

        sfs = SfsCleanup(sed)
        sfs.poolname = 'c2'
        sfs.remove_rollback_caches()
        self.assertTrue(2, len(deleted))
        self.assertTrue('c2_cache' in deleted)
        self.assertTrue('c2-cache' in deleted)

        sfs.poolname = 'bbbbbbbbbbbbbbbbbb'
        deleted = []
        sfs.remove_rollback_caches()
        self.assertFalse(deleted)

        nc.return_value.storage_rollback_cache_list.return_value = []
        m_storage_rollback_cache_destroy = MagicMock()
        nc.return_value.storage_rollback_cache_destroy = \
            m_storage_rollback_cache_destroy
        sfs.remove_rollback_caches()
        self.assertFalse(m_storage_rollback_cache_destroy.called)

    # noinspection PyUnresolvedReferences
    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    @patch('cleanup_sfs.get_nas_type_sed')
    def test_clean_all_veritas(self, m_nts, sed, nc):
        m_nts.return_value = 'veritas'
        sfs = SfsCleanup(sed)
        sfs.remove_filesystem_snapshots = MagicMock()
        sfs.remove_shares = MagicMock()
        sfs.remove_filesystems = MagicMock()
        sfs.remove_rollback_caches = MagicMock()

        sfs.clean_all()
        self.assertTrue(sfs.remove_filesystem_snapshots.called)
        self.assertTrue(sfs.remove_shares.called)
        self.assertTrue(sfs.remove_filesystems.called)
        self.assertTrue(sfs.remove_rollback_caches.called)

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    @patch('cleanup_sfs.get_nas_type_sed')
    def test_clean_all_unityxt(self, m_nts, sed, nc):
        m_nts.return_value = 'unityxt'
        sfs = SfsCleanup(sed)
        sfs.remove_filesystem_snapshots = MagicMock()
        sfs.remove_shares = MagicMock()
        sfs.remove_filesystems = MagicMock()
        sfs.remove_rollback_caches = MagicMock()

        sfs.clean_all()
        self.assertTrue(sfs.remove_filesystem_snapshots.called)
        self.assertTrue(sfs.remove_shares.called)
        self.assertTrue(sfs.remove_filesystems.called)
        self.assertFalse(sfs.remove_rollback_caches.called)


    @patch(TC_MODULE + '.clean_lms_mounts')
    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    @patch(TC_MODULE + '.get_env_var')
    @patch(TC_MODULE + '.plumb_lms_storage')
    def test_main(self, pls, gv, sed, nc, clf):
        ntf = join(gettempdir(), 't.log')

        def getvar(name):
            if name == 'LOG_LEVEL':
                return 'INFO'
            elif name == 'ENMINST_LOG':
                return dirname(ntf)
            elif name == 'LOG_FILE':
                return basename(ntf)
            return name

        gv.side_effect = getvar

        try:
            with patch(TC_MODULE + '.SfsCleanup') as snapper:
                snapper.return_value.clean_all.return_value = None
                main(['--sed', 'sed.txt', '--exclude', 'no_rollback,fs1'])
                clean_all = snapper.return_value.clean_all
                self.assertTrue(clean_all.called)
                clean_all.assert_called_with(['no_rollback', 'fs1'])
        finally:
            if os.path.isfile(ntf):
                remove(ntf)

        gv.side_effect = KeyError
        self.assertRaises(SystemExit, main, ['--sed', 'sed.txt'])

    @patch(TC_MODULE + '.clean_lms_mounts')
    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    @patch(TC_MODULE + '.plumb_lms_storage')
    @patch(TC_MODULE + '.SfsCleanup')
    def test_teardown_sfs(self, sfs, pls, sed, nc, clf):
        teardown_sfs('', '', MagicMock())
        self.assertTrue(pls.called)
        self.assertTrue(sfs.called)

    @patch(TC_MODULE + '.exec_process')
    def test_get_ip_address(self, ep):
        ip = '1.1.1.44'
        ep.return_value = 'inet {0}  ' \
                          'Bcast:172.16.30.255  Mask:255.255.255.0'.format(ip)
        aip = get_ip_address('eth2')
        self.assertEqual(ip, aip)

        ep.return_value = ''
        aip = get_ip_address('eth2')
        self.assertIsNone(aip)

    @patch(TC_MODULE + '.listdir')
    @patch(TC_MODULE + '.get_ip_address')
    def test_get_assigned_ips(self, gip, ld):
        mmap = {'eth0': None, 'eth2': '1.1.1.1', 'bonding_masters': None}
        ld.return_value = mmap.keys()

        def side_effect(nic):
            return mmap[nic]

        gip.side_effect = side_effect
        iplist = get_assigned_ips()
        self.assertDictEqual({'1.1.1.1': 'eth2'}, iplist)

    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.wait_detect_link')
    def test_plumber_cleanroom(self, wait_detect_link, ep):
        args = {'DEVICE': 'eth99',
                'BOOTPROTO': 'static',
                'NOZEROCONF': 'no',
                'USERCTL': 'no',
                'NETMASK': '1.1.1.1',
                'HWADDR': '1.1.1.2',
                'IPADDR': '1.1.1.3',
                'BROADCAST': '1.1.1.4'}
        contents = '\n'.join(
                ['%s=%s' % (key, value) for (key, value) in args.items()])

        with patch('{0}.open'.format(TC_MODULE), create=True) as mopen:
            mopen.return_value = MagicMock(spec=file)
            plumber('eth99', args, MagicMock())
            self.assertEqual(4, ep.call_count)
            ecalls = [call(['/sbin/ifdown', 'eth99']),
                      call(['/sbin/ifconfig', 'eth99', 'down']),
                      call(['/sbin/ifconfig', 'eth99', 'up']),
                      call(['/sbin/ifup', 'eth99'])]
            ep.assert_has_calls(ecalls)

            written = ''
            for c in mopen.mock_calls:
                if c[0] == '().__enter__().write':
                    written += '\n'.join(c[1])

            self.assertNotEqual('', written)
            self.assertTrue('HWADDR=1.1.1.2' in written)
            self.assertTrue('DEVICE=eth99' in written)

    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.SfsCleanup.clean_all')
    @patch(TC_MODULE + '.wait_detect_link')
    def test_plumber_ifcfg_with_comments(self, m_wait_detect_link, m_clean_all, m_exec_process):
        args = {'DEVICE': 'eth99',
                'BOOTPROTO': 'static',
                'NOZEROCONF': 'no',
                'USERCTL': 'no',
                'NETMASK': '1.1.1.1',
                'HWADDR': '1.1.1.2',
                'IPADDR': '1.1.1.3',
                'BROADCAST': '1.1.1.4'}
        text = [
            'smth1=smth1',
            '#comment=comment',
            'smth2=smth2'
        ]
        cleanup_sfs.IFCFG = join(gettempdir(), 'ifcfg-eth99')
        mopen = mock_open()
        with patch('{0}.exists'.format(TC_MODULE), create=True) as mexists:
            mexists = MagicMock(return_value=True)
            with patch('cleanup_sfs.open', mopen, create=True):
                mopen.return_value.readlines.return_value = text
                cleanup_sfs.plumber('eth99', args, MagicMock())
                self.assertTrue(mopen.return_value.write.called,
                                'Expected something to get written!')
                handle = mopen()
                mopen.return_value.write.assert_any_call('NOZEROCONF=no\nsmth1=smth1\nsmth2=smth2\nUSERCTL=no\nIPADDR=1.1.1.3\nBROADCAST=1.1.1.4\nDEVICE=eth99\nNETMASK=1.1.1.1\nBOOTPROTO=static\nHWADDR=1.1.1.2')



    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.wait_detect_link')
    def test_plumber_reinstall(self, dl, ep):
        args = {'DEVICE': 'eth99',
                'BOOTPROTO': 'static',
                'NOZEROCONF': 'no',
                'USERCTL': 'no',
                'NETMASK': '1.1.1.1',
                'HWADDR': '1.1.1.2',
                'IPADDR': '1.1.1.3',
                'BROADCAST': '1.1.1.4'}
        cleanup_sfs.IFCFG = join(gettempdir(), 'ifcfg-eth99')
        with open(cleanup_sfs.IFCFG, 'w') as _f:
            for k, v in args.items():
                _f.write('{0}={1}\n'.format(k, v))
        plumber('eth99', args, MagicMock())
        self.assertEqual(2, ep.call_count)
        ecalls = [call(['/sbin/ifconfig', 'eth99', 'up']),
                  call(['/sbin/ifup', 'eth99'])]

    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.wait_detect_link')
    def test_plumber_reinstall_updates(self, dl, ep):
        ifcfg = {'DEVICE': 'eth99',
                 'BOOTPROTO': 'static',
                 'NOZEROCONF': 'no',
                 'USERCTL': 'no',
                 'NETMASK': '1.1.1.1',
                 'HWADDR': '1.1.1.2',
                 'IPADDR': '1.1.1.3',
                 'BROADCAST': '2.1.1.4'}
        cleanup_sfs.IFCFG = join(gettempdir(), 'ifcfg-eth99')
        with open(cleanup_sfs.IFCFG, 'w') as _f:
            for k, v in ifcfg.items():
                _f.write('{0}={1}\n'.format(k, v))

        new_ifcfg = {'DEVICE': 'eth99',
                     'BOOTPROTO': 'static',
                     'NOZEROCONF': 'no',
                     'USERCTL': 'no',
                     'NETMASK': '2.1.1.1',
                     'HWADDR': '2.1.1.2',
                     'IPADDR': '2.1.1.3',
                     'BROADCAST': '2.1.1.4'}
        plumber('eth99', new_ifcfg, MagicMock())
        self.assertEqual(4, ep.call_count)
        ecalls = [call(['/sbin/ifdown', 'eth99']),
                  call(['/sbin/ifconfig', 'eth99', 'down']),
                  call(['/sbin/ifconfig', 'eth99', 'up']),
                  call(['/sbin/ifup', 'eth99'])]
        with open(cleanup_sfs.IFCFG) as _f:
            data = _f.readlines()
        self.assertTrue('IPADDR=2.1.1.3\n' in data)
        self.assertFalse('IPADDR=1.1.1.3\n' in data)

    @patch(TC_MODULE + '.Sed')
    @patch(TC_MODULE + '.get_assigned_ips')
    @patch(TC_MODULE + '.plumber')
    @patch(TC_MODULE + '.ping_nasconsole')
    def test_plumb_lms_storage(self, ping, mario, gip, sed):
        # Test the plumber() isnt called, address already set
        sed.get_value.side_effect = ['blade', '1.1.1.1', '1.1.1.0/24']
        gip.return_value = {'1.1.1.1': 'lo76'}
        cleanup_sfs.plumb_lms_storage('lo67', sed, MagicMock())
        self.assertFalse(mario.called)

        # Test the plumber() gets called, address not set
        sed.get_value.side_effect = ['blade', '1.1.1.1', '1.1.1.0/24', 'aa:aa:aa',
                                     '42.42.42.42']
        gip.side_effect = [{}, {'1.1.1.1': 'lo76'}]
        mario.reset()
        cleanup_sfs.plumb_lms_storage('lo67', sed, MagicMock())
        self.assertTrue(mario.called)

        # Check an error is raised if the address is found even
        # after updating the ifcfg file...
        sed.get_value.side_effect = ['blade', '1.1.1.1', '1.1.1.0/24', 'aa:aa:aa',
                                     '42.42.42.42']
        gip.side_effect = [{}, {}]
        mario.reset()
        self.assertRaises(SystemExit, cleanup_sfs.plumb_lms_storage,
                          'lo67', sed, MagicMock())
        self.assertTrue(mario.called)

    @patch(TC_MODULE + '.Sed')
    @patch(TC_MODULE + '.plumber')
    def test_plumb_lms_storage_skipped(self, mario, sed):
        # Test the plumber is skipped if environment is rack.
        sed.get_value.side_effect = ['Extra_Large_ENM_On_Rack_Servers']
        cleanup_sfs.plumb_lms_storage('lo67', sed, MagicMock())
        self.assertFalse(mario.called)


    @patch(TC_MODULE + '.exec_process')
    def test_wait_detect_link(self, ep):
        l = MagicMock()
        self.assertRaises(IOError, cleanup_sfs.wait_detect_link, 'etc1',
                          l, link_detect_timeout=1)

        ep.reset_mock()
        ep.side_effect = [
            'Link detected: no',
            'Link detected: yes',
            'Link detected: yes'  # This wont get returned/called
        ]
        cleanup_sfs.wait_detect_link('eth9', l, link_detect_timeout=1)
        self.assertEqual(2, ep.call_count)

    @patch(TC_MODULE + '.copy2')
    @patch(TC_MODULE + '.exec_process')
    def test_clean_lms_mounts(self, ep, cp2):
        fstab = [
            '# comment line',
            ''
            '/local     /       ext4    defaults        1       1',
            '1.1.1.1:/vx/p1-fs1    /e     nfs     soft    0       0',
            '1.1.1.1:/vx/p2-fs1    /e     nfs     soft    0       0',
        ]
        # remove the line we want removed in the function to test if it was
        # actually removed ...

        expected_fstab = list(fstab)
        expected_fstab.pop(2)
        expected_wrote = '\n'.join(expected_fstab).strip()
        expected_wrote += '\n'  # mntent warning

        mopen = mock_open()
        with patch('cleanup_sfs.open', mopen, create=True):
            mopen.return_value.readlines.return_value = fstab
            cleanup_sfs.clean_lms_mounts('veritas', 'p1', MagicMock())
            self.assertTrue(mopen.return_value.write.called,
                            'Expected something to get written!')
            handle = mopen()
            handle.write.assert_called_once_with(expected_wrote)
        ep.assert_any_call(['/bin/umount', '-fl', '/e'])
        ep.assert_any_call([SYSTEMCTL, 'stop', 'ddc.service'])

    @patch(TC_MODULE + '.copy2')
    @patch(TC_MODULE + '.exec_process')
    def test_clean_lms_mounts_failed_ddc_stop(self, ep, cpw):
        ep.side_effect = IOError()
        mopen = mock_open()
        with patch('cleanup_sfs.open', mopen, create=True):
            cleanup_sfs.clean_lms_mounts('veritas', 'p1', MagicMock())
        ep.assert_any_call([SYSTEMCTL, 'stop', 'ddc.service'])

    @patch(TC_MODULE + '.copy2')
    @patch(TC_MODULE + '.exec_process')
    def test_clean_lms_mounts_not_mounted(self, ep, cp2):
        ep.side_effect = ['', IOError('not mounted')]
        fstab = [
            '# comment line',
            ''
            '/local     /       ext4    defaults        1       1',
            '1.1.1.1:/vx/p1-fs1    /e     nfs     soft    0       0',
            '1.1.1.1:/vx/p2-fs1    /e     nfs     soft    0       0',
        ]
        expected_fstab = list(fstab)
        expected_fstab.pop(2)
        expected_wrote = '\n'.join(expected_fstab).strip()
        expected_wrote += '\n'  # mntent warning
        mopen = mock_open()
        with patch('cleanup_sfs.open', mopen, create=True):
            mopen.return_value.readlines.return_value = fstab
            cleanup_sfs.clean_lms_mounts('veritas', 'p1', MagicMock())
            handle = mopen()
            self.assertEqual(1, handle.write.call_count)
            handle.write.assert_called_with(expected_wrote)

    @patch(TC_MODULE + '.copy2')
    @patch(TC_MODULE + '.exec_process')
    def test_clean_lms_mounts_not_mounted_error(self, ep, cp2):
        ep.side_effect = ['', IOError('aaaaaaaaaaaaaaaa')]
        fstab = [
            '# comment line',
            ''
            '/local     /       ext4    defaults        1       1',
            '1.1.1.1:/vx/p1-fs1    /e     nfs     soft    0       0',
            '1.1.1.1:/vx/p2-fs1    /e     nfs     soft    0       0',
        ]
        expected_fstab = list(fstab)
        expected_fstab.pop(2)
        expected_wrote = '\n'.join(expected_fstab).strip()
        expected_wrote += '\n'  # mntent warning
        mopen = mock_open()
        with patch('cleanup_sfs.open', mopen, create=True):
            mopen.return_value.readlines.return_value = fstab
            self.assertRaises(IOError, cleanup_sfs.clean_lms_mounts,
                              'veritas', 'p1', MagicMock())

    @patch(TC_MODULE + '.copy2')
    @patch(TC_MODULE + '.exec_process')
    def test_clean_lms_mounts_unityxt(self, ep, cp2):
        fstab = [
            '# comment line',
            ''
            '/local     /       ext4    defaults        1       1',
            '1.1.1.1:/p1-fs1    /e     nfs     soft    0       0',
            '1.1.1.1:/p2-fs1    /e     nfs     soft    0       0',
        ]
        # remove the line we want removed in the function to test if it was
        # actually removed ...

        expected_fstab = list(fstab)
        expected_fstab.pop(2)
        expected_wrote = '\n'.join(expected_fstab).strip()
        expected_wrote += '\n'  # mntent warning

        mopen = mock_open()
        with patch('cleanup_sfs.open', mopen, create=True):
            mopen.return_value.readlines.return_value = fstab
            cleanup_sfs.clean_lms_mounts('unityxt', 'p1', MagicMock())
            self.assertTrue(mopen.return_value.write.called,
                            'Expected something to get written!')
            handle = mopen()
            handle.write.assert_called_once_with(expected_wrote)
        ep.assert_any_call(['/bin/umount', '-fl', '/e'])
        ep.assert_any_call([SYSTEMCTL, 'stop', 'ddc.service'])

    @patch(TC_MODULE + '.copy2')
    @patch(TC_MODULE + '.exec_process')
    def test_clean_lms_mounts_not_mounted_unityxt(self, ep, cp2):
        ep.side_effect = ['', IOError('not mounted')]
        fstab = [
            '# comment line',
            ''
            '/local     /       ext4    defaults        1       1',
            '1.1.1.1:/p1-fs1    /e     nfs     soft    0       0',
            '1.1.1.1:/p2-fs1    /e     nfs     soft    0       0',
        ]
        expected_fstab = list(fstab)
        expected_fstab.pop(2)
        expected_wrote = '\n'.join(expected_fstab).strip()
        expected_wrote += '\n'  # mntent warning
        mopen = mock_open()
        with patch('cleanup_sfs.open', mopen, create=True):
            mopen.return_value.readlines.return_value = fstab
            cleanup_sfs.clean_lms_mounts('unityxt', 'p1', MagicMock())
            handle = mopen()
            self.assertEqual(1, handle.write.call_count)
            handle.write.assert_called_with(expected_wrote)

    @patch(TC_MODULE + '.NasConsole')
    @patch(TC_MODULE + '.Sed')
    def test_check_sfs(self, sed, nc):
        sfs = SfsCleanup(sed)
        nc.return_value.rollback_check.return_value = True
        self.assertRaises(SystemExit, sfs.check_sfs)

    @patch(TC_MODULE + '.exec_process')
    def test_ping_nasconsole(self, m_exec_process):
        nasc_ip = '1.2.4.6'
        snic = 'eth42'

        m_logger = MagicMock()
        ping_nasconsole(snic, nasc_ip, m_logger)
        m_exec_process.assert_any_call(['/bin/ping', '-c', '5', '-I',
                                        snic, nasc_ip])

        m_exec_process.reset_mock()
        m_exec_process.side_effect = IOError
        self.assertRaises(IOError, ping_nasconsole, snic, nasc_ip, m_logger)

    def test_format_msg(self):
        _str = format_msg('INFO', '_msg_')
        self.assertIsNotNone(match(r'.*\sINFO.*:\s_msg_$', _str))
