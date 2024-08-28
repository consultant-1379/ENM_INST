import os
from os.path import join, dirname

import unittest2
from mock import patch, MagicMock

from cleanup_lvm import CleanupLVMSnapshot
from cleanup_lvm import main


class TestLvmCleanup(unittest2.TestCase):
    def setUp(self):
        basepath = dirname(dirname(dirname(__file__.replace(os.sep, '/'))))
        os.environ['ENMINST_CONF'] = join(basepath, 'src/main/resources/conf')

    def test_delete_snapshots(self):
        c = CleanupLVMSnapshot()
        mock_value = ['swi-a-s--:lv_home:litp_lv_home_snapshot:0.00:vg_root']
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = 0
            process.communicate.return_value = mock_value
            c.delete_snapshots()
            self.assertTrue(mock.called)

    def test_main(self):
        mock_value = ['swi-a-s--:lv_home:litp_lv_home_snapshot:0.00:vg_root']
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = 0
            process.communicate.return_value = mock_value
            main()
            self.assertTrue(mock.called)

    def test_delete_no_snapshots(self):
        c = CleanupLVMSnapshot()
        mock_value = ['-wi-a-s--:lv_home:litp_lv_home_snapshot:0.00:vg_root']
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = 0
            process.communicate.return_value = mock_value
            c.delete_snapshots()
            self.assertTrue(mock.called)

    @patch('cleanup_lvm.exec_process')
    def test_delete_snapshots_exception(self, ep):
        ep.side_effect = IOError
        clean_snap = CleanupLVMSnapshot()
        clean_snap.snapshot_list = MagicMock()
        clean_snap.snapshot_list.return_value = \
            'swi-a-s--:lv_home:litp_lv_home_snapshot:0.00:vg_root'
        self.assertRaises(SystemExit, clean_snap.delete_snapshots)


if __name__ == '__main__':
    unittest2.main()
