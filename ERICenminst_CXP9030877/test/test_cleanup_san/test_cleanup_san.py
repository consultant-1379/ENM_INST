import sys

from mock import MagicMock

try:
    import yum
except ImportError:
    sys.modules['yum'] = MagicMock()

import shutil
from genericpath import exists
from logging import INFO
from os import makedirs, remove
from os.path import join, expanduser
from tempfile import gettempdir

import unittest2
from mock import patch, Mock

import cleanup_san
import cleanup_sfs
from cleanup_san import main, NAVI_RPM

from sanapi import api_builder, Vnx2Api
from sanapiinfo import SnapshotInfo, LunInfo, StoragePoolInfo


sed = '''san_systemName=atvnx-14
san_spaIP=10.45.233.117
san_spbIP=10.45.233.118
san_user=ciadmin
san_password=ciadm57
san_type=vnx2
san_loginScope=global
san_siteId=TOR176
san_poolId=3
san_poolName=TOR176'''

san1_path = [
    {'path': '/infrastructure/storage/storage_providers/san1',
     'data': {'item-type-name': 'san-emc', 'state': 'Applied',
              '_links': {'self': {'href': 'https://localhost:9999/litp/rest/'
                                          'v1/infrastructure/storage/storage'
                                          '_providers/san1'},
                         'item-type': {'href': 'https://localhost:9999/litp/'
                                               'rest/v1/item-types/san-emc'
                                       }},
              'id': 'san1',
              'properties': {'management_ipv4': '192.168.50.19',
                             'user_name': 'support', 'name': 'san1',
                             'password_key': 'key-for-san'}}}]


class TestCleanupSanSnap(unittest2.TestCase):
    @patch('sanapi.api_builder')
    def setUp(self, m_sanapi):
        self.tmpdir = join(gettempdir(), 'TestSed')
        if not exists(self.tmpdir):
            makedirs(self.tmpdir)
        self.tmp_sed = join(self.tmpdir, 'tmp_sed')
        self.write_file(self.tmp_sed, sed)
        self.sed = cleanup_sfs.Sed(self.tmp_sed)
        self.sanSnapCleanupObj = cleanup_san.SanSnapCleanup(self.sed)
        self.sanSnapCleanupObj._navi_sleep = 1
        self.spa = self.sanSnapCleanupObj.sed.get_value('san_spaIP')
        self.sanuser = self.sanSnapCleanupObj.sed.get_value('san_user')
        self.sanpasswd = self.sanSnapCleanupObj.sed.get_value('san_password')
        self.scope = self.sanSnapCleanupObj.sed.get_value('san_loginScope')
        self.navi_subcmd = "getlun 5"

        self.vnx_mock = MagicMock(spec=Vnx2Api)
        m_sanapi.return_value = self.vnx_mock

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def write_file(self, location, contents):
        with open(location, 'w') as _f:
            _f.writelines(contents)

    @patch('sanapi.Vnx2Api.get_luns')
    def test_get_lunids_for_snap_greenfield(self, get_luns):
        lun = LunInfo(lun_id='34',
                      name='test_lun',
                      uid='sadasd',
                      container='pool1',
                      size='100Gb',
                      container_type='StoragePool',
                      raid='5')

        get_luns.return_value = []
        lun_list = self.sanSnapCleanupObj.get_lunids_for_snap()
        self.assertListEqual([], lun_list)

        get_luns.return_value = [lun]
        lun_list = self.sanSnapCleanupObj.get_lunids_for_snap()
        self.assertListEqual(['34'], lun_list)

    @patch('sanapi.Vnx2Api.get_luns')
    def test_get_lunids_for_snap_exclude_luns(self, get_luns):
        exclude_lun_name = 'LITP2_TOR176_appvg_SVC2'
        exclude_lun_id = '5'
        exclude_lun = LunInfo(lun_id='5',
                              name=exclude_lun_name,
                              uid='sadasd',
                              container='pool1',
                              size='100Gb',
                              container_type='StoragePool',
                              raid='5')

        include_lun_name = 'LITP2_TOR176_rootvg_DB2'
        include_lun_id = '28'
        include_lun = LunInfo(lun_id=include_lun_id,
                              name=include_lun_name,
                              uid='sadasd',
                              container='pool1',
                              size='100Gb',
                              container_type='StoragePool',
                              raid='5')

        get_luns.return_value = [exclude_lun, include_lun]

        ret = self.sanSnapCleanupObj.get_lunids_for_snap(excludeluns=exclude_lun_name)
        self.assertEquals(ret, [include_lun_id])

    @patch('sanapi.Vnx2Api.get_snapshots')
    def test_do_check_vnx_snap_feature_ok(self, get_snaps):
        ret = self.sanSnapCleanupObj.do_check_vnx_snap_feature()
        get_snaps.assert_called_with()
        self.assertTrue(ret)

    @patch('sanapi.Vnx2Api.get_snapshots')
    def test_do_check_vnx_snap_feature_nok(self, get_snaps):
        self.sanSnapCleanupObj.do_check_vnx_snap_feature()
        get_snaps.side_effect = Exception
        self.assertFalse(self.sanSnapCleanupObj.do_check_vnx_snap_feature())

    @patch('cleanup_san.exec_process')
    def test_check_navisec_feature_ok(self, exec_process):
        self.sanSnapCleanupObj.check_navisec_feature()
        exec_process.assert_called_with(
                ['yum', 'info', NAVI_RPM])
        self.assertTrue(self.sanSnapCleanupObj.check_navisec_feature())

    @patch('cleanup_san.exec_process')
    def test_check_navisec_feature_nok(self, exec_process):
        exec_process.side_effect = IOError
        self.assertFalse(self.sanSnapCleanupObj.check_navisec_feature())

    @patch('cleanup_san.SanSnapCleanup.check_navisec_feature')
    @patch('cleanup_san.exec_process')
    def test_install_navisec(self, exec_process, check_nav):
        check_nav.return_value = True
        self.sanSnapCleanupObj.install_navisec()
        exec_process.side_effect = IOError
        exec_process.assert_called_with(
                ['yum', 'install', NAVI_RPM, '-y'])
        self.assertRaises(SystemExit, self.sanSnapCleanupObj.install_navisec)
        check_nav.return_value = False
        self.assertRaises(SystemExit, self.sanSnapCleanupObj.install_navisec)

    @patch('cleanup_san.SanSnapCleanup.check_san_info')
    @patch('cleanup_san.SanSnapCleanup.do_destroy_snapshots')
    @patch('cleanup_san.SanSnapCleanup.do_check_vnx_snap_feature')
    @patch('h_logging.enminst_logger.init_enminst_logging')
    def test_teardown_san(self, logger, check_snap_feat,
                          destroy_snaps, saninfo):
        saninfo.return_value = True
        check_snap_feat.return_value = True
        cleanup_san.teardown_san(self.tmp_sed, logger)
        self.assertTrue(destroy_snaps.called)
        logger.info.assert_called_with("SAN Snapshot cleanup completed.")

        saninfo.return_value = False
        cleanup_san.teardown_san(self.tmp_sed, logger)
        logger.info.assert_called_with("Removal of SAN Snapshots not "
                                       "required. Continuing ...")

    @patch('sanapi.Vnx2Api.get_snapshots')
    @patch('cleanup_san.SanSnapCleanup.get_lunids_for_snap')
    def test_do_list_snapshots(self, get_lunids_for_snap, get_snaps):
        snap_info1 = SnapshotInfo(resource_lun_id='40',
                                  snapshot_name='CI-Snapshot_40',
                                  created_time='just a moment ago',
                                  snap_state='Available',
                                  resource_lun_name='lun40',
                                  description=None)

        snap_info2 = SnapshotInfo(resource_lun_id='83',
                                  snapshot_name='CI-Snapshot_83',
                                  created_time='just a moment ago',
                                  snap_state='Available',
                                  resource_lun_name='lun83',
                                  description=None)

        get_snaps.return_value = [snap_info1, snap_info2]
        get_lunids_for_snap.return_value = ['40']

        ret = self.sanSnapCleanupObj.do_list_snapshots(['40'])

        self.assertEqual(ret, [snap_info1])
        get_snaps.assert_called_with()



    @patch('sanapi.Vnx2Api.get_snapshots')
    @patch('cleanup_san.SanSnapCleanup.install_navisec')
    @patch('cleanup_san.LitpRestClient.get_items_by_type')
    def test_check_san_info(self, m_litp, m_install_navi, m_get_snaps):
        m_litp.return_value = 'san1'
        snap_name = 'CI-Snapshot_45'
        snap_info = SnapshotInfo(resource_lun_id='45',
                                 snapshot_name=snap_name,
                                 created_time='just a moment ago',
                                 snap_state='Available',
                                 resource_lun_name='lun45',
                                 description=None)
        m_get_snaps.return_value = [snap_info]

        result = self.sanSnapCleanupObj.check_san_info()
        self.assertEqual(result, True)

    @patch('sanapi.Vnx2Api.delete_snapshot')
    @patch('cleanup_san.SanSnapCleanup.do_list_snapshots')
    @patch('cleanup_san.SanSnapCleanup.get_lunids_for_snap')
    def test_do_destroy_snapshots_nomock(self, get_lunids_for_snap,
                                         do_list_snapshots, del_snap):
        snap_name = 'CI-Snapshot_45'
        snap_info = SnapshotInfo(resource_lun_id='45',
                                 snapshot_name=snap_name,
                                 created_time='just a moment ago',
                                 snap_state='Available',
                                 resource_lun_name='lun45',
                                 description=None)
        do_list_snapshots.return_value = [snap_info]
        get_lunids_for_snap.return_value = ['45']

        self.sanSnapCleanupObj.do_destroy_snapshots()

        del_snap.assert_called_with(snap_name)

    @patch('cleanup_san.teardown_san')
    @patch('cleanup_san.get_env_var')
    def test_main(self, get_env_var, teardown_san):
        get_env_var['LOG_LEVEL'].return_value = INFO
        main(['--sed', self.tmp_sed])
        teardown_san.assert_called_with(self.tmp_sed,
                                        self.sanSnapCleanupObj.logger)

    @patch('h_logging.enminst_logger.init_enminst_logging')
    def test_main_key_error(self, init_log):
        init_log.side_effect = KeyError
        self.assertRaises(SystemExit, main, ['--sed', self.tmp_sed])


if __name__ == '__main__':
    unittest2.main()
