import logging
import os
from os.path import join
from tempfile import gettempdir

import unittest2
from mock import patch

import enm_version
from enm_version import ENMVersion, display, main_exceptions
from h_litp.litp_rest_client import LitpException
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_util.h_utils import ExitCodes
from test_utils import mock_litp_get_requests, assert_exception_raised, \
    load_file_from_path

init_enminst_logging()


class TestEnmVersion(unittest2.TestCase):
    def __init__(self, method_name='runTest'):
        super(TestEnmVersion, self).__init__(method_name)
        self.logger = logging.getLogger('enminst')
        set_logging_level(self.logger, 'DEBUG')


    def log(self, message):
        self.logger.info(message)

    @patch('enm_version.LitpMaintenance.is_maintenance_mode')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('enm_version.exec_process')
    @patch('enm_version.exec_process_via_pipes')
    def test_display(self, exec_process, exec_process_via_pipes, m_litp_get,
                     m_is_maintenance_mode):
        m_is_maintenance_mode.return_value = False
        exec_process.return_value = ""
        exec_process_via_pipes.return_value = ""
        instance = ENMVersion()
        instance.display_enm_versions()
        self.assertTrue(exec_process.called)
        self.assertTrue(exec_process_via_pipes.called)
        self.assertTrue(m_litp_get.called)
        self.assertTrue(m_is_maintenance_mode.called)

    @patch('enm_version.LitpMaintenance.is_maintenance_mode')
    @patch('enm_version.exec_process_via_pipes')
    @patch('enm_version.exec_process')
    def test_display_versions(self, exec_process, exec_process_via_pipes,
                              m_is_maintenance_mode):
        m_is_maintenance_mode.return_value = False
        repolist_result = load_file_from_path(
                '/test_enm_version/output/yum_repolist_output.log')
        repoquery_all_availabe_pkg_info_result = load_file_from_path(
                '/test_enm_version/output/repoquery_all_availabe_pkg_info.log')
        repoquery_package_dependencies_result = load_file_from_path(
                '/test_enm_version/output/repoquery_package_dependencies.log')

        exec_process_via_pipes.side_effect = [repolist_result]

        exec_process.side_effect = [repoquery_all_availabe_pkg_info_result,
                                    repoquery_package_dependencies_result]

        init_enminst_logging()

        self.log("This file path, relative to os.getcwd()")
        self.log(__file__ + "\n")

        current_path = os.path.dirname(__file__)

        mock_litp_get = mock_litp_get_requests(
                current_path,
                ["/software/items",
                 "/software/items/model_package/packages",
                 "/software/services",
                 "/software/services/httpd/vm_packages",
                 "/software/services/httpd/vm_yum_repos",
                 "/software/services/amos/vm_packages",
                 "/software/services/amos/vm_yum_repos",
                 "/software/services/pmserv/vm_packages",
                 "/software/services/pmserv/vm_yum_repos"
                 ])

        instance = ENMVersion()
        instance.litp.get = mock_litp_get
        instance.display_enm_versions()

        self.assertTrue(exec_process.called)
        self.assertTrue(exec_process_via_pipes.called)

    @patch('enm_version.main')
    def test_main_exceptions(self, enm_version_main):
        args = 'enm_version.sh --litpd_host remotehost'.split()

        enm_version_main.side_effect = KeyboardInterrupt(
                'This is an expected error')
        self.assertRaises(SystemExit, main_exceptions, enm_version_main, args)

        enm_version_main.side_effect = LitpException(
                1, 'This is an expected error')
        self.assertRaises(SystemExit, main_exceptions, enm_version_main, args)

        enm_version_main.side_effect = LitpException(
                1, {'a': 'This is an expected error'})
        self.assertRaises(SystemExit, main_exceptions, enm_version_main, args)

        enm_version_main.side_effect = LitpException(
                1, {'messages': {'a': 'This is an expected error'}})
        self.assertRaises(SystemExit, main_exceptions, enm_version_main, args)

    def test_extract_pkg_info(self):
        instance = ENMVersion()
        stdout = load_file_from_path(
                '/test_enm_version/output/repoquery_package_info.log')

        result = instance.extract_pkg_info(stdout)

        self.assertEquals({'ERICenmsguiservice_CXP9031574': (
            '1.0.23', 'R1A23', 'www.ericsson.com')}, result)

        instance.all_available_repo_pkg_info = result
        packages = instance.filter_dependencies_to_packages(
                'ERICenmsguiservice_CXP9031574')
        instance.display_packages_info(packages)

    def test_extract_pkg_info_escape_characters(self):
        instance = ENMVersion()
        stdout = load_file_from_path(
                '/test_enm_version/output/'
                'repoquery_package_info_escape_characters.log')

        result = instance.extract_pkg_info(stdout)

        self.assertEquals(
                {'ERICddc_CXP9030294': ('3.3.5', 'CXP9030294', '"test"'),
                 'ERICenmsguiservice_CXP9031574': (
                     '1.0.23', 'R1A23', 'www.ericsson.com')},
                result)

        instance.all_available_repo_pkg_info = result
        packages = instance.filter_dependencies_to_packages(
                'ERICenmsguiservice_CXP9031574')
        instance.display_packages_info(packages)

    def test_extract_pkg_info_encoding_problems(self):
        instance = ENMVersion()
        stdout = load_file_from_path(
                '/test_enm_version/output/'
                'repoquery_package_info_encoding_problems.log')

        result = instance.extract_pkg_info(stdout)

        self.assertEquals(['hunspell-ca'], result.keys())

        instance.all_available_repo_pkg_info = result
        packages = instance.filter_dependencies_to_packages('hunspell-ca')
        instance.display_packages_info(packages)

    def test_extract_package_dependencies(self):
        instance = ENMVersion()
        stdout = load_file_from_path(
                '/test_enm_version/output/'
                'repoquery_package_dependencies_fixed.log')

        result = instance.extract_package_dependencies(stdout)
        self.assertEquals({
            'ERICenmsglogstash_CXP9031571': ['/bin/sh',
                                             'ERICddc_CXP9030294',
                                             'ERIChyperica_CXP9031241',
                                             'ERIClogstash_CXP9030286']
        }, result)

    @patch('enm_version.exec_process_via_pipes')
    def test_find_current_repos(self, exec_process_via_pipes):
        instance = ENMVersion()
        exec_process_via_pipes.return_value = load_file_from_path(
                '/test_enm_version/output/yum_repolist_output.log')

        result = instance.find_current_repos()
        self.assertEquals(
                ['3PP', 'LITP', 'LITP_PLUGINS', 'OS', 'UPDATES',
                 'common_repo', 'model_repo', 'ms_repo'], result)

        self.assertTrue(exec_process_via_pipes.called)

    @patch('enm_version.exec_process_via_pipes')
    def test_find_current_repos_fails(self, exec_process_via_pipes):
        exec_process_via_pipes.side_effect = IOError
        instance = ENMVersion()
        se = assert_exception_raised(SystemExit, instance.find_current_repos)
        self.assertEquals(se.code, ExitCodes.ERROR)
        self.assertTrue(exec_process_via_pipes.called)

    @patch('enm_version.exec_process')
    def test_process_repoquery_fails(self, exec_process):
        exec_process.side_effect = IOError
        instance = ENMVersion()
        se = assert_exception_raised(SystemExit, instance.process_repoquery,
                                     '/usr/bin/repoquery -q -a'.split())
        self.assertEquals(se.code, ExitCodes.ERROR)
        self.assertTrue(exec_process.called)

    def test_display_release_info(self):
        instance = ENMVersion()

        tmp_filename = join(gettempdir(), 'litp-release')
        with open(tmp_filename, 'a') as tmp_file:
            tmp_file.write('LITP 15.14 CSA 113 110 R2AH08')
        try:
            instance.display_release_info(tmp_filename,
                                          enm_version.LITP_RELEASE_INFO_LABEL)
        finally:
            os.remove(tmp_filename)

    def test_display_release_history(self):
        instance = ENMVersion()

        tmp_filename = join(gettempdir(), 'litp-history-missing')
        with open(tmp_filename, 'a') as tmp_file:
            tmp_file.write('LITP 15.14 CSA 113 110 R2AH08\n')
            tmp_file.write('LITP 15.14 CSA 113 110 R2AH09\n')
        try:
            instance.display_release_history(
                    tmp_filename,
                    'litp-release-missing',
                    enm_version.LITP_HISTORY_INFO_LABEL)
        finally:
            os.remove(tmp_filename)

    def test_display_release_history_missing(self):
        instance = ENMVersion()

        tmp_filename = join(gettempdir(), 'litp-release-missing')
        with open(tmp_filename, 'a') as tmp_file:
            tmp_file.write('LITP 15.14 CSA 113 110 R2AH08\n')
            tmp_file.write('LITP 15.14 CSA 113 110 R2AH09\n')
        try:
            instance.display_release_history(
                    'litp-history-missing',
                    tmp_filename,
                    enm_version.LITP_HISTORY_INFO_LABEL)
        finally:
            os.remove(tmp_filename)

    def test_display_release_history_missing_files(self):
        instance = ENMVersion()
        instance.display_release_history('litp-history-missing',
                                         'litp-release-missing',
                                         enm_version.LITP_HISTORY_INFO_LABEL)

    def test_display_release_info_not_available(self):
        instance = ENMVersion()
        instance.display_release_info("file_not_found", "My Release info : ")

    def test_extractTagValue_wrong_index(self):
        instance = ENMVersion()
        lines = [enm_version.REPOQUERY_TAG_NAME + '=value']
        with self.assertRaises(ValueError) as context:
            instance.extract_pkg_info(self.createStdout(lines))
        print str(context.exception)
        self.assertTrue('Missing line' in str(context.exception))

    def test_extractTagValue_missing_tag(self):
        instance = ENMVersion()
        lines = ['any=value']
        with self.assertRaises(ValueError) as context:
            instance.extract_pkg_info(self.createStdout(lines))
        self.assertTrue('do not define attribute' in str(context.exception))

    def test_extractTagValue_missing_value(self):
        instance = ENMVersion()
        lines = [enm_version.REPOQUERY_TAG_NAME]
        with self.assertRaises(ValueError) as context:
            instance.extract_pkg_info(self.createStdout(lines))
        self.assertTrue('do not define value' in str(context.exception))

    def createStdout(self, lines):
        return '\n'.join(lines)

    @patch('enm_version.display')
    def test_KeyboardInterrupt_handling(self, m_display):
        m_display.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main_exceptions(enm_version.main, [])
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        m_display.reset_mock()
        m_display.side_effect = IOError('This is an expected error')
        self.assertRaises(IOError, main_exceptions, enm_version.main, [])

    @patch('enm_version.display')
    def test_main(self, m_display):
        command = 'enm_version.sh '
        enm_version.main(command.split())
        self.assertTrue(m_display.called)

    @patch.dict('os.environ', {'LOG_LEVEL': 'DEBUG'})
    @patch('enm_version.ENMVersion.display_versions')
    def test_display_log_enminst(self, m_display):
        enm_version.display_log_enminst()
        self.assertTrue(m_display.called)

    @patch('enm_version.ENMVersion.display_versions')
    def test_display_error(self, m_display_versions):
        m_display_versions.side_effect = IOError('This is an expected error')
        self.assertRaises(IOError, display)

    @patch('enm_version.exec_process')
    def test_display_litp_version(self, exec_process):
        litp_version_all_output = load_file_from_path(
                '/test_enm_version/output/litp_version_all.log')
        exec_process.return_value = litp_version_all_output
        instance = ENMVersion()
        instance.display_litp_version()

    @patch('enm_version.exec_process')
    def test_display_litp_version_error(self, exec_process):
        exec_process.side_effect = IOError
        instance = ENMVersion()
        instance.display_litp_version()
        self.assertTrue(exec_process.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.get_children')
    @patch('enm_version.ENMVersion.check_maintenance_mode')
    @patch('enm_version.exec_process_via_pipes')
    @patch('enm_version.exec_process')
    def test_display_versions_mocked(self, m_exec_process,
                                     m_exec_process_via_pipes,
                                     m_check_maintenance_mode,
                                     m_litp_get_children):
        m_check_maintenance_mode.return_value = False
        instance = ENMVersion()
        instance.display_versions()
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_exec_process_via_pipes.called)
        self.assertTrue(m_check_maintenance_mode.called)
        self.assertTrue(m_litp_get_children.called)

    @patch('enm_version.LitpMaintenance.is_maintenance_mode')
    @patch('enm_version.exec_process')
    def test_display_versions_maintenence_mode(self, m_exec_process,
                                               m_is_maintenance_mode):
        m_is_maintenance_mode.return_value = True
        instance = ENMVersion()
        instance.display_versions()
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_is_maintenance_mode.called)
