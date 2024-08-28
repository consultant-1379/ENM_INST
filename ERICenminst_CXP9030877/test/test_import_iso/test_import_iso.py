import sys
from os import makedirs
from shutil import rmtree

from mock import MagicMock

try:
    import yum
except ImportError:
    sys.modules['yum'] = MagicMock()

import os
import shutil
from datetime import datetime
from os.path import exists, join, dirname
from platform import node
from tempfile import gettempdir, mktemp

import unittest2
from argparse import Namespace
from mock import patch

import import_iso
from h_util.h_utils import ExitCodes, touch
from import_iso import main_flow
from test_utils import assert_exception_raised


class TestImportIso(unittest2.TestCase):
    def setUp(self):
        import_iso.IMPORT_TIMEOUT = 1
        import_iso.MONITORING_SLEEP_SECONDS = 1.0 / 10.0
        import_iso.WAIT_AFTER_IMPORT_ISO_STARTED = 1
        import_iso.MAINTENANCE_READ_WAIT_SECONDS = 1

        self.tmpdir = join(gettempdir(), 'TestImportIso')
        if exists(self.tmpdir):
            rmtree(self.tmpdir)
        makedirs(self.tmpdir)

    def tearDown(self):
        if exists(self.tmpdir):
            rmtree(self.tmpdir)

    def test_create_mnt_dir(self):
        # Test 1
        mnt = import_iso.create_mnt_dir()
        self.assertTrue(os.path.exists(mnt))

        # Test 2
        with patch('os.makedirs') as os_mkdir:
            import_iso.create_mnt_dir()
            self.assertFalse(os_mkdir.called)

        # Clean up
        os.removedirs(mnt)

        # Test 3
        with patch('os.makedirs') as os_mkdir:
            os_mkdir.side_effect = IOError
            self.assertRaises(IOError, import_iso.create_mnt_dir)

    @patch('import_iso.exec_process')
    def test_mount(self, ep):
        # Test 1
        ep.return_code = 0
        iso_file = 'erictor.iso'
        mnt_pnt = '/tmp/mnt'
        import_iso.mount(mnt_pnt, iso_file)
        cmd = 'mount -o loop {0} {1}'.format(iso_file, mnt_pnt)
        ep.assert_called_with(cmd.split())

        # Test 2
        ep.side_effect = IOError
        self.assertRaises(SystemExit, import_iso.mount, mnt_pnt, iso_file)

    @patch('import_iso.LitpMaintenance.is_maintenance_mode')
    @patch('import_iso.LitpMaintenance.get_status')
    @patch('import_iso.run_litp')
    def test_litp_import_iso(self, run_litp, m_get_job_state, m_is_m_m_1):
        # Test 1
        m_get_job_state.side_effect = ['Starting', 'Running',
                                       None, 'Done', 'Done']
        m_is_m_m_1.return_value = False
        mnt_pnt = '/tmp/mnt'
        import_iso.litp_import_iso(mnt_pnt)
        cmd = 'import_iso {0}'.format(mnt_pnt)
        run_litp.assert_called_with(cmd)
        self.assertTrue(m_is_m_m_1.called)

        # Test 2
        run_litp.side_effect = Exception
        self.assertRaises(SystemExit, import_iso.litp_import_iso,
                          mnt_pnt)
        print datetime.now()

    @patch('import_iso.LitpMaintenance.is_maintenance_mode')
    @patch('import_iso.LitpMaintenance.get_status')
    def test_monitor_import_progress(self, m_get_job_state, m_is_m_m):
        states = ['Starting', 'Running', 'Done', 'Done']
        m_get_job_state.side_effect = states
        m_is_m_m.side_effect = [True, False]
        monitoring_time = 4 * import_iso.MONITORING_SLEEP_SECONDS
        import_iso.monitor_import_progress(monitoring_time)
        self.assertEqual(m_get_job_state.call_count, len(states))
        assert m_is_m_m.call_count == 2

    @patch('import_iso.LitpMaintenance.is_maintenance_mode')
    @patch('import_iso.LitpMaintenance.get_status')
    def test_monitor_import_progress_timeout(self, m_get_job_state, m_is_m_m):
        m_get_job_state.return_value = 'Running'
        se = assert_exception_raised(
            SystemExit, import_iso.monitor_import_progress, 1)
        self.assertEquals(se.code, ExitCodes.TIMEOUT)
        m_is_m_m.assert_not_called()

    @patch('import_iso.LitpMaintenance.is_maintenance_mode')
    @patch('import_iso.LitpMaintenance.get_status')
    def test_monitor_import_progress_job_failed(self, m_get_job_state,
                                                m_is_m_m):
        m_get_job_state.return_value = 'Failed'
        se = assert_exception_raised(
            SystemExit, import_iso.monitor_import_progress, 1)
        self.assertEquals(se.code, ExitCodes.ERROR)
        m_is_m_m.assert_not_called()

    @patch('import_iso.LitpMaintenance.is_maintenance_mode')
    @patch('import_iso.LitpMaintenance.get_status')
    def test_monitor_import_progress_get_status_problem(self, m_get_job_state,
                                                        m_is_m_m):
        m_is_m_m.return_value = False
        states = ['Running', None, 'Done']

        local_values = {'index': 0}

        def side_effect():
            result = states[local_values['index']]
            local_values['index'] += 1
            if result is None:
                raise ValueError

            return result

        m_get_job_state.side_effect = side_effect
        monitoring_time = 4 * import_iso. \
            MONITORING_SLEEP_SECONDS + import_iso.MAINTENANCE_READ_WAIT_SECONDS
        import_iso.monitor_import_progress(monitoring_time)
        self.assertEquals(local_values['index'], len(states))
        self.assertTrue(m_is_m_m.called)

    @patch('import_iso.LitpMaintenance.is_maintenance_mode')
    @patch('import_iso.LitpMaintenance.get_status')
    def test_monitor_import_progress_not_available(self, m_get_job_state,
                                                   is_m_m):
        is_m_m.return_value = False
        m_get_job_state.side_effect = [ValueError('Status not available'),
                                       'Done']
        monitoring_time = import_iso.MAINTENANCE_READ_WAIT_SECONDS
        import_iso.monitor_import_progress(monitoring_time)
        self.assertEqual(2, m_get_job_state.call_count)
        self.assertEqual(1, is_m_m.call_count)

    @patch('import_iso.litp_import_iso')
    @patch('import_iso.run_litp')
    def test_import_products(self, run_litp, iso):
        mnt_pnt = '/temp/mnt'
        import_iso.import_products(mnt_pnt)
        cmd = 'update -p /ms -o hostname={0}'.format(node())
        run_litp.assert_called_with(cmd)
        self.assertTrue(iso.called)

    @patch('import_iso.get_config')
    @patch('import_iso.cleanup_redundant_images')
    @patch('import_iso.listdir')
    def test_update_images(self, list_dir, cleanup,
                           m_get_config):

        wp_cfg_filename = join(mktemp(), 'cfg.ini')

        img_list = self.configure_import_update_images(list_dir,
                                                       wp_cfg_filename,
                                                       m_get_config)

        # Test 1
        mnt_pnt = '/temp/mnt'
        import_iso.update_images(mnt_pnt)
        enminst_working_parameters = import_iso.get_config()[
            'enminst_working_parameters']
        self.assertTrue(exists(dirname(enminst_working_parameters)))
        search_string = "_image"
        cleanup.assert_called_with(wp_cfg_filename, search_string)
        with open(enminst_working_parameters, 'r') as _reader:
            _lines = ''.join(_reader.readlines())

        for _img in img_list:
            self.assertTrue('{0}={1}'.format(_img.split('_')[0], _img), _lines)



    def configure_import_update_images(self, list_dir, wp_cfg_filename,
                                       m_get_config):
        img_list = ['ERICimg1_CXP1111111.qcow2',
                    'ERICimg2_CXP2222222.qcow2']
        list_dir.return_value = img_list

        m_get_config.return_value = {
            'enminst_working_parameters': wp_cfg_filename
        }
        return img_list

    @patch('import_iso.get_config')
    @patch('import_iso.cleanup_redundant_images')
    @patch('import_iso.update_working_params')
    @patch('import_iso.listdir')
    def test_update_images_makedirs(self, list_dir, m_update_working_params,
                                    m_cleanup_redundant_images,
                                    m_get_config):
        tmpdir = join(gettempdir(), 'temptest')
        if exists(tmpdir):
            shutil.rmtree(tmpdir)

        wp_cfg_filename = join(tmpdir, 'cfg.ini')
        try:
            self.configure_import_update_images(list_dir, wp_cfg_filename,
                                                m_get_config)
            mnt_pnt = '/temp/mnt'
            import_iso.update_images(mnt_pnt)
            self.assertTrue(exists(tmpdir))
        finally:
            if exists(tmpdir):
                shutil.rmtree(tmpdir)

    def test_varify(self):
        img = 'ERICrhel45myimage_CXP123-1.2.3.qcow2'
        res = import_iso.create_image_var(img)
        self.assertIn('ERICrhel45myimage', res)
        self.assertEqual(res['ERICrhel45myimage'], img)

    def test_update_working_params(self):
        img_list = ['ERICrhel45myimage_CXP123-1.2.3.qcow2',
                    'ERICrhel6yourimage_CXP123-1.2.3.qcow2',
                    'ERICrhel7ourimage_CXP123-1.2.3.qcow2']

        lines_list = ['ERICrhel45myimage='
                      'ERICrhel45myimage_CXP123-1.2.3.qcow2\n',
                      'ERICrhel6yourimage='
                      'ERICrhel6yourimage_CXP123-1.2.3.qcow2\n',
                      'ERICrhel7ourimage='
                      'ERICrhel7ourimage_CXP123-1.2.3.qcow2\n']

        params_file = os.path.join(gettempdir(), 'params.cfg')
        try:
            import_iso.update_working_params(params_file, img_list)
            with open(params_file, 'r') as pf:
                lines = pf.readlines()

            for line in lines_list:
                self.assertIn(line, lines)
        finally:
            if exists(params_file):
                os.remove(params_file)

    @patch('os.path.ismount')
    @patch('import_iso.exec_process')
    def test_umount(self, ep, ismount):
        mp = '/tmp/mnt'
        # Test 1
        iso_file = 'erictor.iso'
        ismount.return_value = False
        import_iso.umount(mp, iso_file)
        self.assertFalse(ep.called)

        ismount.return_value = True
        import_iso.umount(mp, iso_file)
        ep.assert_called_with(['umount', mp])

        # Test 2
        ep.side_effect = IOError
        self.assertRaises(IOError, import_iso.umount, mp)

    @patch('import_iso.exec_process')
    def test_run_litp(self, ep):
        cmd = 'show_plan'
        import_iso.run_litp(cmd)
        ep.assert_called_with('litp {0}'.format(cmd).split())

    @patch('os.path.ismount')
    @patch('shutil.rmtree')
    @patch('import_iso.exec_process')
    @patch('import_iso.glob')
    def test_cleanup_mnt_point(self, m_glob, exec_process, rm_mock,
                               ismount):
        rm_mock.side_effect = [OSError()]
        m_glob.side_effect = [['i_dont_exist!']]
        ismount.return_value = True
        import_iso.cleanup_mnt_points()
        self.assertTrue(exec_process.called)

    @patch('import_iso.get_iso_contents')
    @patch('import_iso.umount')
    @patch('import_iso.update_images')
    @patch('import_iso.import_products')
    @patch('import_iso.import_enm_version')
    @patch('import_iso.mount')
    @patch('import_iso.check_litp_mode')
    def test_main(self, m_check_litp_mode, mnt, imp_v, imp_p, upd_i, umnt,
                  m_get_iso_contents):
        cmd_args = 'import_iso.py --iso /var/tmp/ENM.iso --verbose'

        import_iso.main(cmd_args.split())
        self.assertTrue(m_check_litp_mode.called)
        self.assertTrue(mnt.called)
        self.assertTrue(imp_v.called)
        self.assertTrue(imp_p.called)
        self.assertTrue(upd_i.called)
        self.assertTrue(umnt.called)
        self.assertTrue(m_get_iso_contents.called)

    @patch('import_iso.get_iso_contents')
    @patch('import_iso.umount')
    @patch('import_iso.update_images')
    @patch('import_iso.LitpMaintenance.get_status')
    @patch('import_iso.run_litp')
    @patch('import_iso.import_enm_version')
    @patch('import_iso.mount')
    @patch('import_iso.check_litp_mode')
    def test_main_import_timeout(self, m_check_litp_mode, mnt, imp_v,
                                 m_run_litp, m_get_status, upd_i, umnt,
                                 m_get_iso_contents):
        cmd_args = 'import_iso.py --iso /var/tmp/ENM.iso --verbose'

        m_get_status.return_value = 'Running'

        se = assert_exception_raised(
            SystemExit, import_iso.main, cmd_args.split())
        self.assertEquals(se.code, ExitCodes.TIMEOUT)
        self.assertTrue(m_check_litp_mode.called)
        self.assertTrue(mnt.called)
        self.assertTrue(imp_v.called)
        self.assertTrue(m_run_litp.called)
        self.assertFalse(upd_i.called)
        self.assertTrue(umnt.called)
        self.assertTrue(m_get_iso_contents.called)

    @patch('import_iso.LitpMaintenance.is_maintenance_mode')
    def test_main_maintenance_mode(self, m_is_maintenance_mode):
        m_is_maintenance_mode.return_value = True

        cmd_args = 'import_iso.py --iso /var/tmp/ENM.iso --verbose'

        se = assert_exception_raised(
            SystemExit, import_iso.main, cmd_args.split())
        self.assertEquals(se.code, ExitCodes.LITP_MAINT_MODE)
        self.assertTrue(m_is_maintenance_mode.called)

    @patch('import_iso.get_iso_contents')
    @patch('import_iso.create_mnt_dir')
    @patch('import_iso.cleanup_mnt_points')
    @patch('import_iso.mount')
    @patch('import_iso.import_enm_version')
    @patch('import_iso.import_products')
    @patch('import_iso.update_images')
    @patch('import_iso.check_litp_mode')
    def test_KeyboardInterrupt_handling(self,
                                        m_check_litp_mode,
                                        m_update_images,
                                        m_import_products,
                                        m_import_version,
                                        m_mount,
                                        m_cleanup_mnt_points,
                                        m_create_mount_dir,
                                        m_get_iso_contents):
        cmd_args = 'import_iso.py --iso /var/tmp/ENM.iso --verbose'.split()

        m_import_products.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            import_iso.main(cmd_args)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)
        self.assertTrue(m_check_litp_mode.called)
        self.assertTrue(m_cleanup_mnt_points.called)
        self.assertEquals(1, m_cleanup_mnt_points.call_count)
        self.assertTrue(m_create_mount_dir.called)
        self.assertTrue(m_mount.called)
        self.assertTrue(m_import_version.called)
        self.assertTrue(m_import_products.called)
        self.assertFalse(m_update_images.called)
        self.assertTrue(m_get_iso_contents.called)

        m_import_products.reset_mock()
        m_import_products.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            import_iso.main(cmd_args)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        m_import_products.reset_mock()
        m_import_products.side_effect = IOError()
        self.assertRaises(IOError, import_iso.main, cmd_args)

    @patch('import_iso.get_iso_contents')
    @patch('import_iso.cleanup_mnt_points')
    @patch('import_iso.create_mnt_dir')
    @patch('import_iso.mount')
    @patch('import_iso.import_enm_version')
    @patch('import_iso.import_products')
    @patch('import_iso.update_images')
    @patch('import_iso.check_litp_mode')
    def test_cleanup_on_error(self,
                              m_check_litp_mode,
                              m_update_images,
                              m_import_products,
                              m_import_version,
                              m_mount,
                              m_create_mnt_dir,
                              m_cleanup_mnt_points,
                              m_get_iso_contents):
        m_get_iso_contents.return_value = {}

        m_create_mnt_dir.return_value = 'mp'
        cfg = Namespace(verbose=False,
                        iso=None)
        # 2 cleanup_mnt_points should be called
        m_import_products.side_effect = IOError
        self.assertRaises(IOError, main_flow, cfg)
        self.assertEqual(2, m_cleanup_mnt_points.call_count)
        self.assertTrue(m_check_litp_mode)
        self.assertTrue(m_mount.called)
        self.assertTrue(m_import_version.called)

        # Only one cleanup_mnt_points call should be made as
        # the import is still running in the background and a
        # ctrl-c is stopping the script
        m_import_products.reset_mock()
        m_cleanup_mnt_points.reset_mock()
        m_import_products.side_effect = KeyboardInterrupt
        try:
            main_flow(cfg)
            self.fail('Epected SystemExit')
        except SystemExit as se:
            self.assertEquals(se.code, ExitCodes.INTERRUPTED)
            system_exit_raised = True
        self.assertTrue(system_exit_raised)
        self.assertEqual(1, m_cleanup_mnt_points.call_count)

        # 2 cleanup_mnt_points call should be made, the monitoring is
        # running and it's throwing some error
        m_import_products.reset_mock()
        m_cleanup_mnt_points.reset_mock()
        m_import_products.side_effect = IOError
        self.assertRaises(IOError, main_flow, cfg)
        self.assertEqual(2, m_cleanup_mnt_points.call_count)

        # 2 cleanup_mnt_points call should be made as
        # the import is not being monitored anymore (it failed|finished).
        m_import_products.reset_mock()
        m_cleanup_mnt_points.reset_mock()
        m_import_products.side_effect = None
        m_update_images.side_effect = Exception
        self.assertRaises(Exception, main_flow, cfg)
        self.assertEqual(2, m_cleanup_mnt_points.call_count)

    def test_get_iso_contents(self):
        makedirs(join(self.tmpdir, 'images'))
        makedirs(join(self.tmpdir, 'images/ENM'))
        touch(join(self.tmpdir, 'images/ENM', 'testimage.qcow2'))
        touch(join(self.tmpdir, 'images/ENM', 'some.file'))

        makedirs(join(self.tmpdir, 'repos'))
        makedirs(join(self.tmpdir, 'repos/ENM'))
        makedirs(join(self.tmpdir, 'repos/ENM/db'))
        touch(join(self.tmpdir, 'repos/ENM/db', 'rpm_db1.rpm'))
        touch(join(self.tmpdir, 'repos/ENM/db', 'rpm_db2.rpm'))
        touch(join(self.tmpdir, 'repos/ENM/db', 'repo.xml'))

        makedirs(join(self.tmpdir, 'repos/ENM/str'))
        touch(join(self.tmpdir, 'repos/ENM/str', 'rpm_str1.rpm'))
        touch(join(self.tmpdir, 'repos/ENM/str', 'blaaaa.txt'))

        iso_contents = import_iso.get_iso_contents(self.tmpdir)

        self.assertIn('ENM', iso_contents[import_iso.ISO_CONTENTS_IMAGES])
        self.assertEqual(['testimage.qcow2'],
                         iso_contents[import_iso.ISO_CONTENTS_IMAGES]['ENM'])

        self.assertIn('ENM_db_rhel7', iso_contents[import_iso.ISO_CONTENTS_YUM])
        self.assertEqual(2, len(
            iso_contents[import_iso.ISO_CONTENTS_YUM]['ENM_db_rhel7']))
        self.assertIn('rpm_db1.rpm',
                      iso_contents[import_iso.ISO_CONTENTS_YUM]['ENM_db_rhel7'])
        self.assertIn('rpm_db2.rpm',
                      iso_contents[import_iso.ISO_CONTENTS_YUM]['ENM_db_rhel7'])

        self.assertEqual(1, len(
            iso_contents[import_iso.ISO_CONTENTS_YUM]['ENM_str_rhel7']))
        self.assertIn('rpm_str1.rpm',
                      iso_contents[import_iso.ISO_CONTENTS_YUM]['ENM_str_rhel7'])
