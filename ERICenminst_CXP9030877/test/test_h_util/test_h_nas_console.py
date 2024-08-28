from mock import MagicMock, patch
from unittest2 import TestCase

import sys

sys.modules['naslib.log'] = MagicMock()
sys.modules['naslib.objects'] = MagicMock()
sys.modules['naslib.drivers'] = MagicMock()
sys.modules['naslib.drivers.sfs'] = MagicMock()
sys.modules['naslib.drivers.sfs.utils'] = MagicMock()

from h_util.h_nas_console import get_pool_prefix, is_fs_in_pool, \
    get_rollback_cache_name, NasConsole, NasConsoleException, normalize_size, \
    get_rollback_name, get_litp_rollback_cache_name, map_tabbed_data


class TestNasConsole(TestCase):
    def setUp(self):
        super(TestNasConsole, self).setUp()

    def test_get_pool_prefix(self):
        gen = get_pool_prefix('abc')
        self.assertEqual('abc-', gen)

    def test_normalize_size(self):
        self.assertEquals(50.0, normalize_size('50m'))
        self.assertEquals(51200.0, normalize_size('50g'))
        self.assertNotEqual(50, normalize_size('50g'))
        self.assertEqual(1048576.0, normalize_size('1t'))
        self.assertEqual(2485125.12, normalize_size('2.37t'))

    def test_is_fs_in_pool(self):
        self.assertFalse(is_fs_in_pool('fs', 'somepool'))
        self.assertTrue(is_fs_in_pool('somepool-fs', 'somepool'))
        self.assertFalse(is_fs_in_pool('fs-somepool', 'somepool'))

    def test_get_rollback_cache_name(self):
        self.assertEqual('pool-cache', get_rollback_cache_name('pool'))

    def test_get_litp_rollback_cache_name(self):
        self.assertEqual('pool_cache', get_litp_rollback_cache_name('pool'))

    def test_get_rollback_name(self):
        self.assertEquals('Snapshot-enm-brsadm_home',
                          get_rollback_name('Snapshot', 'enm-brsadm_home'))

    def test_nfs_share_show(self):
        nc = NasConsole('', '', '')
        sharelist = nc.nfs_share_show('enm')
        self.assertTrue(1, len(sharelist))
        self.assertIn('enm-batch', sharelist)
        self.assertNotIn('pool-hcdumps', sharelist)

    def test_nfs_share_show_faulted_fs_in_pool(self):
        nc = NasConsole('', '', '')
        self.assertRaises(NasConsoleException, nc.nfs_share_show, 'FAULTED')

    def test_nfs_share_show_fauted_fs_in_other_pool(self):
        nc = NasConsole('', '', '')
        sharelist = nc.nfs_share_show('enm')
        self.assertTrue(1, len(sharelist))
        self.assertIn('enm-batch', sharelist)
        self.assertNotIn('FAULTED-FS', sharelist)

    def test_nfs_share_delete(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_fs_list(self):
        nc = NasConsole('', '', '')
        fslist = nc.storage_fs_list('ENM')
        self.assertEqual(1, len(fslist))
        self.assertIn('ENM-FS1', fslist)
        self.assertNotIn('NOTENM_FS1', fslist)

    def test_nas_fs_usage(self):
        """
        Action handled by naslib
        Testing in naslib tests
        """
        pass

    def test_storage_fs_offline(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_support_fs_destroy(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_rollback_list(self):
        nc = NasConsole('', '', '')
        rbacks = nc.storage_rollback_list('enm', '*')
        self.assertEqual(1, len(rbacks))
        self.assertIn('enm-batch', rbacks)
        self.assertIn('cirb-enm-batch', rbacks['enm-batch'])

        self.assertNotIn('test-batch', rbacks)
        self.assertNotIn('cirb-test-batch', rbacks['enm-batch'])

        rbacks = nc.storage_rollback_list('enm', 'cirb')
        self.assertEqual(1, len(rbacks))
        self.assertIn('enm-batch', rbacks)
        self.assertNotIn('cirb-test-batch', rbacks)

    def test_storage_rollback_list_multi(self):
        nc = NasConsole('', '', '')
        rbacks = nc.storage_rollback_list('multi', '*')
        self.assertEqual(1, len(rbacks))
        self.assertEqual(2, len(rbacks['multi-data']))

    def test_storage_rollback_destroy(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_rollback_cache_list(self):
        nc = NasConsole('', '', '')
        rbacks = nc.storage_rollback_cache_list()
        self.assertEqual(2, len(rbacks))
        self.assertIn('enm-cache', rbacks)
        self.assertIn('TORD1234-cache', rbacks)

    def test_storage_rollback_cache_destroy(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_rollback_cache_destroy_ioerror5(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_rollback_cache_destroy_ioerror1(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_rollback_cache_create(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_rollback_create(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_rollback_restore(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_storage_fs_online(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_nfs_share_add(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    @patch('naslib.connection.NasConnection.sh.create')
    def test_nfs_share_add_check_command(self, con):
        nc = NasConsole('', '', '')
        fs, cl, op = ('fs', 'cl', 'op')
        nc.nfs_share_add(fs, cl, op)
        con.assert_called_with('/vx/fs', 'cl', 'op')

        nc = NasConsole('', '', '', '', 'unityxt')
        fs, cl, op = ('fs', 'cl', 'op')
        nc.nfs_share_add(fs, cl, op)
        con.assert_called_with('fs', 'cl', 'op')

    def test_ip_route_show(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_rollback_check(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_rollback_check_false(self):
        """test_rollback_check_false"""
        nas_con = NasConsole('', '', '', "", "unityxt")
        self.assertFalse(nas_con.rollback_check("storage_pool_name"),
                         "False not returned for rollback_check on unityxt")

    @patch('h_util.h_nas_console.is_fs_in_pool')
    def test_rollback_check_raise_exception_v49310(self, m_is_fs_in_pool):
        """test_rollback_check_raise_exception_v49310"""
        nas_con = NasConsole('', '', '', "")
        m_is_fs_in_pool.side_effect = NasConsoleException('ERROR V-493-10')
        m_logger = MagicMock()
        nas_con.logger = m_logger
        nas_con.logger.return_value = m_logger

        self.assertRaises(
            Exception, nas_con.rollback_check, 'storage_pool_name')
        m_logger.error.assert_called_once_with(
            "Connection to the FS is lost due to FS being down/unreachable "
            "with message: ERROR V-493-10")

    def test_storage_fs_list_details(self):
        nc = NasConsole('', '', '')
        results = nc.storage_fs_list_details('ENM-FS1')
        self.assertEqual(['layout: simple',
                          'name: ENM-FS1',
                          'pool: ENM_pool',
                          'size: 3221225472B'], results)

    def test_storage_fs_destroy(self):
        """
        Action now handled by naslib
        Testing now in naslib tests
        """
        pass

    def test_nas_server_list(self):
        """
        Action handled by naslib
        Testing in naslib tests
        """
        pass

    def test_nas_server_create(self):
        """
        Action handled by naslib
        Testing in naslib tests
        """
        pass

    def test_nas_server_destroy(self):
        """
        Action handled by naslib
        Testing in naslib tests
        """
        pass

    def test_nas_server_list_details(self):
        """
        Action handled by naslib
        Testing in naslib tests
        """
        pass

    def test_map_tabbed_data(self):
        raw_data = [
            'a       b        c  d',
            'aaaaa   bbbbbbbb c  dddddd',
            'xx      yyy      zz '
        ]
        data = map_tabbed_data(raw_data, 'a')
        self.assertEqual(2, len(data))

        self.assertIn('aaaaa', data)
        self.assertEqual('aaaaa', data['aaaaa']['a'])
        self.assertEqual('bbbbbbbb', data['aaaaa']['b'])
        self.assertEqual('c', data['aaaaa']['c'])
        self.assertEqual('dddddd', data['aaaaa']['d'])

        self.assertIn('xx', data)
        self.assertEqual('xx', data['xx']['a'])
        self.assertEqual('yyy', data['xx']['b'])
        self.assertEqual('zz', data['xx']['c'])
        self.assertEqual('', data['xx']['d'])

    def test_mapped_data_lengths(self):
        snap_name = 'Snapshot-ENM425-upgrade_ind'
        raw_data = ['NAME                     TYPE           SNAPDATE'
                    '            CHANGED_DATA   SYNCED_DATA',
                    snap_name + 'spaceopt       2017/01/30 12:27    '
                                '256K(0.1%)     256K(0.1%)']
        data = map_tabbed_data(raw_data, 'NAME', len(snap_name))
        self.assertEqual(1, len(data))

        self.assertIn(snap_name, data)
        self.assertEqual(snap_name, data[snap_name]['NAME'])
        self.assertEqual('spaceopt', data[snap_name]['TYPE'])
        self.assertEqual('2017/01/30 12:27', data[snap_name]['SNAPDATE'])
        self.assertEqual('256K(0.1%)', data[snap_name]['CHANGED_DATA'])
        self.assertEqual('256K(0.1%)', data[snap_name]['SYNCED_DATA'])
