from copy import deepcopy
from json import dumps
from socket import gethostname

from mock import patch, call
from unittest2 import TestCase

from agent.enminst_snapshots import EnminstRemoteSnapshot, logging


class TestEnminstRemoteSnapshot(TestCase):
    def __init__(self, method_name='runTest'):
        super(TestEnminstRemoteSnapshot, self).__init__(method_name)
        self.snap_snap_name = 'test_snap'
        self.snap_lv_path = '/dev/vg_root/test_lv'
        self.snap_fs_snap_size = 10
        self.snap_tag = 'test_tag'
        self.snap_data = {
            gethostname(): [{
                'fs_snap_size': self.snap_fs_snap_size,
                'snap_name': self.snap_snap_name,
                'lv_path': self.snap_lv_path
            }],
            'host-2': [{
                'fs_snap_size': '10',
                'snap_name': 'other_snap',
                'lv_path': '/dev/vg_root/other_lv'
            }],
            'snap_tag': self.snap_tag}

    @patch('agent.enminst_snapshots.logging.getLogger')
    def test_enable_debug(self, m_getlogger):
        EnminstRemoteSnapshot.enable_debug({'verbose': 'true'})
        m_getlogger.assert_has_call(call().setLevel(logging.DEBUG))

        m_getlogger.reset_mock()
        EnminstRemoteSnapshot.enable_debug({'verbose': 'false'})
        self.assertEqual(0, m_getlogger.call_count)

    @patch('logging.config.fileConfig')
    @patch('agent.base_agent.Popen')
    def test_create_lv_snapshots(self, m_popen, m_fileconfig):
        args = {
            'snap_info': dumps(self.snap_data)
        }
        m_popen.return_value.communicate.side_effect = [
            ('Snapped volume', '')
        ]
        m_popen.return_value.returncode = 0

        snapper = EnminstRemoteSnapshot()
        results = snapper.create_lv_snapshots(args)
        self.assertEqual(1, m_popen.call_count)
        m_popen.assert_called_once_with(
                ['/sbin/lvcreate', '--snapshot',
                 '--addtag', self.snap_tag,
                 '--extents', '{0}%ORIGIN'.format(self.snap_fs_snap_size),
                 '--name', self.snap_snap_name,
                 self.snap_lv_path], shell=False, stderr=-1, env=None,
                stdout=-1
        )
        self.assertEqual(0, results['retcode'])
        self.assertEqual('Snapped volume', results['out'])

    @patch('logging.config.fileConfig')
    @patch('agent.base_agent.Popen')
    def test_create_lv_snapshots_notag(self, m_popen, m_fileconfig):
        data = deepcopy(self.snap_data)
        del data['snap_tag']
        args = {
            'snap_info': dumps(data)
        }
        m_popen.return_value.communicate.side_effect = [
            ('Snapped volume', '')
        ]
        m_popen.return_value.returncode = 0

        snapper = EnminstRemoteSnapshot()
        results = snapper.create_lv_snapshots(args)
        self.assertEqual(1, m_popen.call_count)
        m_popen.assert_called_once_with(
                ['/sbin/lvcreate', '--snapshot',
                 '--extents', '{0}%ORIGIN'.format(self.snap_fs_snap_size),
                 '--name', self.snap_snap_name,
                 self.snap_lv_path], shell=False, stderr=-1, env=None,
                stdout=-1
        )
        self.assertEqual(0, results['retcode'])
        self.assertEqual('Snapped volume', results['out'])

    @patch('logging.config.fileConfig')
    @patch('agent.base_agent.Popen')
    def test_create_lv_snapshots_errors(self, m_popen, m_fileconfig):
        args = {
            'snap_info': dumps(self.snap_data)
        }
        m_popen.return_value.communicate.side_effect = [
            ('Snapped volume', 'Snap error')
        ]
        m_popen.return_value.returncode = 1

        snapper = EnminstRemoteSnapshot()
        results = snapper.create_lv_snapshots(args)
        self.assertEqual(1, m_popen.call_count)
        m_popen.assert_called_once_with(
                ['/sbin/lvcreate', '--snapshot',
                 '--addtag', self.snap_tag,
                 '--extents', '{0}%ORIGIN'.format(self.snap_fs_snap_size),
                 '--name', self.snap_snap_name,
                 self.snap_lv_path], shell=False, stderr=-1, env=None,
                stdout=-1
        )
        self.assertEqual(1, results['retcode'])
        self.assertEqual('Snap error', results['err'])

    @patch('logging.config.fileConfig')
    @patch('agent.base_agent.Popen')
    def test_create_lv_snapshots_diffhost(self, m_popen, m_fileconfig):
        data = deepcopy(self.snap_data)
        del data[gethostname()]
        args = {
            'snap_info': dumps(data)
        }
        snapper = EnminstRemoteSnapshot()
        results = snapper.create_lv_snapshots(args)
        self.assertEqual(0, m_popen.call_count)
        self.assertEqual(0, results['retcode'])

    @patch('agent.base_agent.Popen')
    def test_delete_lv_snapshots(self, m_popen):
        snapper = EnminstRemoteSnapshot()
        m_popen.return_value.communicate.side_effect = [
            ('Snapped volume', 'Delete error')
        ]
        m_popen.return_value.returncode = 1

        results = snapper.delete_lv_snapshots({'tag_name': self.snap_tag})
        self.assertEqual(1, results['retcode'])
        self.assertEqual('Delete error', results['err'])

        m_popen.reset_mock()
        m_popen.return_value.communicate.side_effect = [
            ('Removed volume', '')
        ]
        m_popen.return_value.returncode = 0
        results = snapper.delete_lv_snapshots({'tag_name': self.snap_tag})
        self.assertEqual(0, results['retcode'])
        self.assertEqual('Removed volume', results['out'])
        m_popen.assert_called_once_with(
                ['/sbin/lvremove', '--force', '@' + self.snap_tag],
                shell=False, stderr=-1, env=None, stdout=-1)

    @patch('agent.base_agent.Popen')
    def test_restore_lv_snapshots(self, m_popen):
        snapper = EnminstRemoteSnapshot()
        m_popen.return_value.communicate.side_effect = [
            ('volume', 'Merge error')
        ]
        m_popen.return_value.returncode = 1

        results = snapper.restore_lv_snapshots({'tag_name': self.snap_tag})
        self.assertEqual(1, results['retcode'])
        self.assertEqual('Merge error', results['err'])

        m_popen.reset_mock()
        m_popen.return_value.communicate.side_effect = [
            ('Merged volume', '')
        ]
        m_popen.return_value.returncode = 0

        results = snapper.restore_lv_snapshots({'tag_name': self.snap_tag})
        self.assertEqual(0, results['retcode'])
        self.assertEqual('Merged volume', results['out'])
        m_popen.assert_called_once_with(
                ['/sbin/lvconvert', '--merge', '@' + self.snap_tag],
                shell=False, stderr=-1, env=None, stdout=-1)

    @patch('agent.base_agent.Popen')
    def test_execute_sync_command(self, m_popen):
        # error case
        snapper = EnminstRemoteSnapshot()
        # we don't actually expect any error message as per
        # info coreutils 'sync invocation' but log any stderr just in case
        m_popen.return_value.communicate.side_effect = [
            ('', 'error')
        ]
        m_popen.return_value.returncode = 1

        results = snapper.execute_sync_command({})
        self.assertEqual(1, results['retcode'])
        self.assertEqual('error', results['err'])

        # no error case
        m_popen.reset_mock()
        m_popen.return_value.communicate.side_effect = [
            ('', '')
        ]
        m_popen.return_value.returncode = 0

        results = snapper.execute_sync_command({})
        self.assertEqual(0, results['retcode'])
        self.assertEqual('', results['out'])
        m_popen.assert_called_once_with(
                ['/bin/sync'],
                shell=False, stderr=-1, env=None, stdout=-1)
