from os.path import join
import shutil
from tempfile import gettempdir
from os.path import exists, realpath
from os import makedirs
import time

import unittest2
from mock import patch, MagicMock

from h_util import h_utils
import import_iso_version
from import_iso_version import HISTORY_ACTION_INSTALLED, \
    HISTORY_ACTION_UPGRADED, HISTORY_ACTION_TIME_FORMAT


class TestImportIsoVersion(unittest2.TestCase):
    def __init__(self, method_name='runTest'):
        super(TestImportIsoVersion, self).__init__(method_name)
        self.test_dir = join(gettempdir(), 'TestImportIsoVersion')
        self.test_var_tmp_dir = join(self.test_dir, 'var/tmp')
        self.test_etc_version_dir = join(self.test_dir, 'etc')
        self.test_mnt_dir = join(self.test_dir, 'mnt')

        self.TEST_ENM_RELEASE_TMP = realpath(
            join(self.test_var_tmp_dir, 'enm-version-temp'))
        self.TEST_ENM_VERSION_FILENAME = realpath(
            join(self.test_etc_version_dir, 'enm-version'))
        self.TEST_ENM_HISTORY_FILENAME = realpath(
            join(self.test_etc_version_dir, 'enm-history'))
        self.TEST_COPIED_ENM_VERSION_FILE = realpath(
                    join(self.test_etc_version_dir, '.enm-version'))

        self.TEST_LITP_RELEASE_FILENAME = \
            realpath(join(self.test_etc_version_dir, 'litp-release'))
        self.TEST_LITP_HISTORY_FILENAME = \
            realpath(join(self.test_etc_version_dir, 'litp-release-history'))

        self.TEST_RHEL7_VERSION_FILENAME = \
            realpath(join(self.test_etc_version_dir, 'rhel7_patch_set-version'))
        self.TEST_RHEL7_HISTORY_FILENAME = \
            realpath(join(self.test_etc_version_dir, 'rhel7_patch_set-history'))
        self.RHEL7_JSON_FILENAME = join(self.test_mnt_dir, 'ericrhel7-release')
        self.RHEL7_JSON_FILENAME_RSTATE = join(self.test_mnt_dir, 'ericrhel7-release-json')
        self.RHEL7_JSON_FILENAME_RSTATE_MISSING = join(self.test_mnt_dir, 'ericrhel7-release-json-missing')

        self.ISO_VERSION_FILENAME = join(self.test_mnt_dir, '.version')

        self.VERSION_1 = 'Version1'
        self.VERSION_2 = 'Version2'
        self.VERSION_3 = 'Version3'

    def setUp(self):
        if not exists(self.test_var_tmp_dir):
            makedirs(self.test_var_tmp_dir)
        if not exists(self.test_etc_version_dir):
            makedirs(self.test_etc_version_dir)
        if not exists(self.test_mnt_dir):
            makedirs(self.test_mnt_dir)
        if not exists(self.RHEL7_JSON_FILENAME):
            with open(self.RHEL7_JSON_FILENAME, 'w') as json_setup:
                json_setup.write('''
                    {
                        "cxp": "9041797",
                        "rhel_version": "7.9",
                        "parent_cxp": "9029081",
                        "gask_candidate": "B",
                        "nexus_version": "1.0.2"
                    }
                    ''')
        if not exists(self.RHEL7_JSON_FILENAME_RSTATE):
            with open(self.RHEL7_JSON_FILENAME_RSTATE, 'w') as json_setup:
                json_setup.write('''
                    {
                        "cxp": "9041797",
                        "rhel_version": "7.9",
                        "parent_cxp": "9029081",
                        "R-state" : "R1B01",
                        "nexus_version": "1.0.2"
                    }
                    ''')
        if not exists(self.RHEL7_JSON_FILENAME_RSTATE_MISSING):
            with open(self.RHEL7_JSON_FILENAME_RSTATE_MISSING, 'w') as json_setup:
                json_setup.write('''
                    {
                        "cxp": "9041797",
                        "rhel_version": "7.9",
                        "parent_cxp": "9029081",
                        "nexus_version": "1.0.2"
                    }
                    ''')

    def tearDown(self):
        shutil.rmtree(join(gettempdir(), 'TestImportIsoVersion'))

    @patch('import_iso_version.exists')
    @patch('shutil.copy')
    def test_import_version(self, m_copy_version, m_exists):
        m_exists.return_value = True
        mnt_pnt = '/temp/mnt'
        m_copy_version.return_code = 0
        import_iso_version.import_enm_version(mnt_pnt)
        self.assertTrue(m_copy_version.called)

    @patch('import_iso_version.exists')
    @patch('shutil.copy')
    def test_import_version_fails(self, m_copy_version, m_exists):
        m_exists.return_value = True
        mnt_pnt = '/temp/mnt'
        m_copy_version.side_effect = IOError
        import_iso_version.import_enm_version(mnt_pnt)
        self.assertTrue(m_copy_version.called)

    @patch('import_iso_version.exists')
    def test_import_version_no_version_file(self, m_exists):
        mnt_pnt = '/temp/mnt'
        m_exists.return_value = False
        self.assertRaises(SystemExit, import_iso_version.import_enm_version,
                          mnt_pnt)

    def test_update_enm_version_and_history_missing_temp_version_file(self):
        import_iso_version.update_enm_version_and_history(
            temp_version_file='enm-version-temp-missing')

    @patch('import_iso_version.update_copied_enm_version')
    def test_update_enm_version_and_history(self, m_update_copied):

        history_file = self.TEST_ENM_HISTORY_FILENAME
        version_file = self.TEST_ENM_VERSION_FILENAME
        temp_version_file = self.TEST_ENM_RELEASE_TMP

        self.create_file_with_content(self.ISO_VERSION_FILENAME,
                                      self.VERSION_1)

        import_iso_version.import_enm_version(
            self.test_mnt_dir, temp_version_file)
        import_iso_version.update_enm_version_and_history(
            temp_version_file=temp_version_file,
            version_file=version_file,
            history_file=history_file)
        self.assertTrue(m_update_copied.called)

        self.check_history_entry(0, [self.VERSION_1],
                                 [HISTORY_ACTION_INSTALLED],
                                 history_file=history_file,
                                 version_file=version_file)

        self.create_file_with_content(self.ISO_VERSION_FILENAME,
                                      self.VERSION_2)
        import_iso_version.import_enm_version(
            self.test_mnt_dir, temp_version_file)
        import_iso_version.update_enm_version_and_history(
            temp_version_file=temp_version_file,
            version_file=version_file,
            history_file=history_file)

        self.check_history_entry(1, [self.VERSION_1, self.VERSION_2],
                                 [HISTORY_ACTION_UPGRADED],
                                 history_file=history_file,
                                 version_file=version_file)

        self.create_file_with_content(self.ISO_VERSION_FILENAME,
                                      self.VERSION_3)
        import_iso_version.import_enm_version(
            self.test_mnt_dir, temp_version_file)
        import_iso_version.update_enm_version_and_history(
            temp_version_file=temp_version_file,
            version_file=version_file,
            history_file=history_file)

        self.check_history_entry(2, [self.VERSION_1, self.VERSION_2,
                                     self.VERSION_3],
                                 [HISTORY_ACTION_UPGRADED],
                                 history_file=history_file,
                                 version_file=version_file)

    def check_history_entry(self, index, versions, static_words,
                            history_file, version_file):

        time_format_short = HISTORY_ACTION_TIME_FORMAT[:-2]

        history_lines = self.read_lines(history_file)
        operation_time = h_utils.file_modification_date(history_file)
        words = static_words + [versions[index], 'on',
                                time.strftime(time_format_short,
                                              operation_time.timetuple())]
        for word in words:
            self.assertIn(word, history_lines[index])

        self.assertEquals(len(versions), len(history_lines))
        for version_index in range(len(versions)):
            self.assertIn(versions[version_index],
                          history_lines[version_index])

    def test_update_litp_version_and_history(self):

        history_file = self.TEST_LITP_HISTORY_FILENAME
        version_file = self.TEST_LITP_RELEASE_FILENAME

        self.create_file_with_content(
            version_file, self.VERSION_1)

        self.create_file_with_content(self.ISO_VERSION_FILENAME,
                                      self.VERSION_2)
        import_iso_version.handle_litp_version_history(
            self.test_mnt_dir,
            version_file=version_file,
            history_file=history_file)

        self.check_history_entry(0, [self.VERSION_1, self.VERSION_2],
                                 [HISTORY_ACTION_INSTALLED],
                                 history_file=history_file,
                                 version_file=version_file)

        self.check_history_entry(1, [self.VERSION_1, self.VERSION_2],
                                 [HISTORY_ACTION_UPGRADED],
                                 history_file=history_file,
                                 version_file=version_file)
        self.create_file_with_content(self.ISO_VERSION_FILENAME,
                                      self.VERSION_3)
        import_iso_version.handle_litp_version_history(
            self.test_mnt_dir,
            version_file=version_file,
            history_file=history_file)

        self.check_history_entry(2, [self.VERSION_1, self.VERSION_2,
                                     self.VERSION_3],
                                 [HISTORY_ACTION_UPGRADED],
                                 history_file=history_file,
                                 version_file=version_file)

    @patch('import_iso_version.import_version')
    def test_handle_litp_version_history_import_version_error(
            self, m_import_version):
        self.create_file_with_content(self.ISO_VERSION_FILENAME,
                                      self.VERSION_1)
        m_import_version.side_effect = IOError
        self.assertRaises(IOError,
                          import_iso_version.handle_litp_version_history,
                          self.test_mnt_dir,
                          version_file=self.TEST_LITP_RELEASE_FILENAME,
                          history_file=self.TEST_LITP_HISTORY_FILENAME)

    def create_file_with_content(self, file_path, content):
        with open(file_path, 'w') as f:
            f.write(content)

    def read_lines(self, path):
        with open(path, 'r') as r:
            return r.read().splitlines()

    def read_line(self, path):
        with open(path, 'r') as r:
            return r.read().splitlines()[0]

    @patch('os.remove')
    @patch('import_iso_version.update_copied_enm_version')
    def test_update_enm_version_and_history_temp_version_file_remove_error(
            self, m_update_copied, m_remove):
        self.create_file_with_content(self.TEST_ENM_RELEASE_TMP,
                                      self.VERSION_1)
        m_remove.side_effect = OSError
        import_iso_version.LOG = MagicMock()
        import_iso_version.update_enm_version_and_history(
            temp_version_file=self.TEST_ENM_RELEASE_TMP,
            version_file=self.TEST_ENM_VERSION_FILENAME,
            history_file=self.TEST_ENM_HISTORY_FILENAME)
        self.assertTrue(m_remove.called)
        self.assertTrue(import_iso_version.LOG.error.called)
        self.assertTrue(exists(self.TEST_ENM_VERSION_FILENAME))
        self.assertTrue(exists(self.TEST_ENM_HISTORY_FILENAME))
        self.assertTrue(m_update_copied.called)

    @patch('shutil.copyfile')
    def test_update_enm_version_and_history_temp_version_file_copy_error(
            self, m_copy_temp_version):
        self.create_file_with_content(self.TEST_ENM_RELEASE_TMP,
                                      self.VERSION_1)
        m_copy_temp_version.side_effect = IOError
        import_iso_version.LOG = MagicMock()
        self.assertRaises(IOError,
                          import_iso_version.update_enm_version_and_history,
                          temp_version_file=self.TEST_ENM_RELEASE_TMP,
                          version_file=self.TEST_ENM_VERSION_FILENAME,
                          history_file=self.TEST_ENM_HISTORY_FILENAME)
        self.assertTrue(m_copy_temp_version.called)
        self.assertTrue(import_iso_version.LOG.exception.called)
        self.assertFalse(exists(self.TEST_ENM_VERSION_FILENAME))
        self.assertFalse(exists(self.TEST_ENM_HISTORY_FILENAME))

    @patch('import_iso_version.update_copied_enm_version')
    @patch('import_iso_version.create_history_entry')
    def test_update_enm_version_and_history_update_history_file_error(
            self, m_create_history_entry, m_update_copied):
        self.create_file_with_content(self.TEST_ENM_RELEASE_TMP,
                                      self.VERSION_1)
        m_create_history_entry.side_effect = IOError
        import_iso_version.LOG = MagicMock()
        self.assertRaises(IOError,
                          import_iso_version.update_enm_version_and_history,
                          temp_version_file=self.TEST_ENM_RELEASE_TMP,
                          version_file=self.TEST_ENM_VERSION_FILENAME,
                          history_file=self.TEST_ENM_HISTORY_FILENAME)
        self.assertTrue(m_create_history_entry.called)
        self.assertTrue(m_update_copied.called)
        self.assertTrue(import_iso_version.LOG.exception.called)
        self.assertTrue(exists(self.TEST_ENM_VERSION_FILENAME))
        self.assertFalse(exists(self.TEST_ENM_HISTORY_FILENAME))

    def test_update_rhel7_version_and_history_gask(self):
        self.assertFalse(exists(self.TEST_RHEL7_HISTORY_FILENAME))
        import_iso_version.update_rhel_version_and_history(
            self.RHEL7_JSON_FILENAME, self.TEST_RHEL7_VERSION_FILENAME,
            self.TEST_RHEL7_HISTORY_FILENAME, create_empty_hist=True)
        self.assertTrue(exists(self.TEST_RHEL7_HISTORY_FILENAME))
        import_iso_version.update_rhel_version_and_history(
            self.RHEL7_JSON_FILENAME, self.TEST_RHEL7_VERSION_FILENAME,
            self.TEST_RHEL7_HISTORY_FILENAME)
        with open(self.TEST_RHEL7_VERSION_FILENAME, 'r') as version_file:
            self.assertTrue('B' in
                            version_file.readline())

        with open(self.TEST_RHEL7_HISTORY_FILENAME, 'r') as history_file:
            self.assertTrue('Upgraded to    RHEL version 7.9 CXP 9041797 '
                            'Revision B on' in history_file.readline())

    def test_update_rhel7_version_and_history_rstate(self):
        self.assertFalse(exists(self.TEST_RHEL7_HISTORY_FILENAME))
        import_iso_version.update_rhel_version_and_history(
            self.RHEL7_JSON_FILENAME_RSTATE, self.TEST_RHEL7_VERSION_FILENAME,
            self.TEST_RHEL7_HISTORY_FILENAME, create_empty_hist=True)
        self.assertTrue(exists(self.TEST_RHEL7_HISTORY_FILENAME))
        import_iso_version.update_rhel_version_and_history(
            self.RHEL7_JSON_FILENAME_RSTATE, self.TEST_RHEL7_VERSION_FILENAME,
            self.TEST_RHEL7_HISTORY_FILENAME)
        with open(self.TEST_RHEL7_VERSION_FILENAME, 'r') as version_file:
            self.assertTrue('R1B01' in
                            version_file.readline())

        with open(self.TEST_RHEL7_HISTORY_FILENAME, 'r') as history_file:
            self.assertTrue('Upgraded to    RHEL version 7.9 CXP 9041797 '
                            'R-state R1B01 on' in history_file.readline())

    def test_update_rhel7_version_and_history_rstate_missing(self):
        self.assertFalse(exists(self.TEST_RHEL7_HISTORY_FILENAME))
        self.assertRaises(ValueError,
                          import_iso_version.update_rhel_version_and_history,
                          self.RHEL7_JSON_FILENAME_RSTATE_MISSING,
                          self.TEST_RHEL7_VERSION_FILENAME,
                          self.TEST_RHEL7_HISTORY_FILENAME,
                          create_empty_hist=True)

    def test_failed_update_copied_enm_version(self):
        with open(self.TEST_ENM_VERSION_FILENAME, 'w') as enm_setup:
            enm_setup.write('')
        self.assertRaises(KeyError,
                          import_iso_version.update_copied_enm_version,
                              version_file=self.TEST_ENM_VERSION_FILENAME,
                              copied_file=self.TEST_COPIED_ENM_VERSION_FILE)

    def test_update_copied_enm_version(self):
        test_version = 'ENM 16.7 (ISO Version: 1.22.52) AOM901151 R1AA\n'
        with open(self.TEST_ENM_VERSION_FILENAME, 'w') as enm_setup:
            enm_setup.write(test_version)
        import_iso_version.update_copied_enm_version(
            self.TEST_ENM_VERSION_FILENAME,
            self.TEST_COPIED_ENM_VERSION_FILE)
        self.assertTrue(exists(self.TEST_COPIED_ENM_VERSION_FILE))
        with open(self.TEST_COPIED_ENM_VERSION_FILE, 'r') as test_f:
            example = test_f.readline()
        self.assertTrue(example in test_version)
