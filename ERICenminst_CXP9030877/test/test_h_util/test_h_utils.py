import StringIO
import datetime
import os
import shutil
import sys
import stat
import unittest2
from mock import patch, call, MagicMock, Mock

import h_util.h_utils

if sys.platform.lower().startswith('win'):
    sys.modules['pwd'] = MagicMock()
    sys.modules['yum'] = MagicMock()
from test_utils import assert_exception_raised, read_file
from os import remove
from os.path import exists, join, isfile
from tempfile import gettempdir, NamedTemporaryFile
from h_util.h_utils import (exec_process, delete_file, exec_process_via_pipes,
                            read_enminst_config, Formatter, Sed,
                            get_env_var, get_sed_nodetypes, format_sed_key,
                            switch_user, query_strong_yes_no,
                            strong_confirmation_or_exit, ExitCodes, touch,
                            time_delta, exec_process_retry, copy_file,
                            litp_backup_state_cron, install_rpm,
                            cleanup_java_core_dumps_cron, sanitize,
                            get_removed_nodes, db_node_removed, remove_rpm,
                            kill_processes_dir, RHELUtil, to_ordinal,
                            create_san_fault_check_cron, _handle_exec_process,
                            ping, _pexpect_execute_remote_command,
                            _handle_pexpect_response,
                            _parse_pexpect_return_code,
                            InvalidCredentialsError,
                            _exec_curl_command, get_removed_clusters,
                            create_nasaudit_errorcheck_cron,
                            get_edp_generated_sed, is_exist_edp_sed_file,
                            get_nas_type_sed, get_nas_type, is_env_on_rack,
                            migrate_cleanup_cmd, compare_versions,
                            get_enable_cron_on_expiry_cmd, _copy_as_template,
                            copy_custom_banners, LITP_ERB_TEMPLATES,
                            KICKSTART_ERB)
from pexpect import EOF, TIMEOUT, ExceptionPexpect
from yum.Errors import RemoveError

MS_HOSTS_FILE = ['10.247.246.214\tscp-1-scripting\tscripting-1-internal\t# Created by LITP. Please do not edit\n',
                 '10.247.246.214\tscp-2-scripting\tscripting-1-internal\t# Created by LITP. Please do not edit\n',
                 '10.247.246.177\tsvc-4-lvsrouter\tlvsrouter-4-internal\t# Created by LITP. Please do not edit\n']

def mock_sed(seddata):
    with patch('h_litp.sed_password_encrypter.Sed._load'):
        sed = Sed('mock')
    sed.sed = seddata
    return sed


class MockPexpectChild(object):

    def __init__(self, expect_return, before_return, sendline_return=None):
        self.set_expect_return = expect_return
        self.before = before_return
        self.set_sendline_side_effect = sendline_return

    def expect(self, *args, **kwargs):
        return self.set_expect_return

    def sendline(self, arg):
        if self.set_sendline_side_effect:
            raise self.set_sendline_side_effect


class TestHutils(unittest2.TestCase):
    def __init__(self, method_name='runTest'):
        super(TestHutils, self).__init__(method_name)
        self.test_rpm = 'RHEL_OS_Patch_Set_CXP9041797'
        self.rpm_list = ['kde-l10n-Polish-4.10.5-2.el7.noarch',
                         'python-enum34-1.0.4-1.el7.noarch',
                         'libidn-1.28-4.el7.i686',
                         'RHEL_OS_Patch_Set_CXP9041797-1.16-1.el7.i686']

    def setUp(self):
        self.exec_cmd = 'ls'
        self.faulty_cmd = 'mockcmd'
        self.tmp_file = NamedTemporaryFile().name
        self.cron_file = NamedTemporaryFile().name
        self.cleanup_cron_file = NamedTemporaryFile().name
        self.backup_dir = join(gettempdir(), 'Testbackup')
        self.scp_values = {
                    "password" : "pass123",
                    "source" : "/opt/ericsson/enminst/bin/test.sh",
                    "destination" : "/tmp",
                    "user" : "administrator",
                    "hostname" : "vm1"
        }
        self.ssh_values = {
                    "hostname" : "vm1",
                    "user" : "administrator",
                    "command" : "/usr/bin/touch file.txt",
                    "password" : "pass123",
                    "port": 123,
        }

    def tearDown(self):
        if exists(self.cron_file):
            remove(self.cron_file)

        if exists(self.backup_dir):
            shutil.rmtree(self.backup_dir)

        if exists(self.cleanup_cron_file):
            remove(self.cleanup_cron_file)

        if exists(self.tmp_file):
            remove(self.tmp_file)

    @patch('h_util.h_utils.yum.YumBase')
    @patch('h_util.h_utils.yum.YumBase.closeRpmDB')
    def test_install_rpm(self, m_closedb, m_yum):
        rpm_list = ['kde-l10n-Polish-4.3.4-5.el6.noarch',
                    'python-formencode-1.2.2-2.1.el6.noarch',
                    'libidn-devel-1.18-2.el6.i686']
        m_yum.return_value.pkgSack.returnPackages.return_value = rpm_list
        self.assertRaises(KeyError, install_rpm, self.test_rpm)


    @patch('h_util.h_utils.exec_process_via_pipes')
    def test_kill_process_dir(self, m_exec_process_via_pipes):
        command_lsof = ['lsof']
        command_grep_path = ['grep', '/some/path']
        command_awk = ['awk', '{print $2}']
        command_xargs = ['xargs', 'kill', '-9']

        kill_processes_dir('/some/path')
        self.assertTrue(m_exec_process_via_pipes.called)
        m_exec_process_via_pipes.assert_called_with(command_lsof, command_grep_path, command_awk, command_xargs)
        self.assertEqual(m_exec_process_via_pipes.call_count, 1)

    @patch('h_util.h_utils.yum.YumBase')
    def test_install_rpm_not_already_installed(self, m_pkg):
        m_pkg.return_value.pkgSack.returnPackages.return_value = self.rpm_list
        m_pkg.return_value.isPackageInstalled.side_effect = [False, True]
        install_rpm(self.test_rpm)
        self.assertTrue(m_pkg.return_value.pkgSack.returnPackages.called)
        self.assertEqual(m_pkg.return_value.isPackageInstalled.call_count, 2)

    @patch('h_util.h_utils.yum.YumBase')
    def test_install_rpm_already_installed(self, m_pkg):
        m_pkg.return_value.pkgSack.returnPackages.return_value = self.rpm_list
        m_pkg.return_value.isPackageInstalled.side_effect = [True]
        install_rpm(self.test_rpm)
        self.assertTrue(m_pkg.return_value.pkgSack.returnPackages.called)
        self.assertTrue(m_pkg.return_value.isPackageInstalled.call_count == 1)

    def test_compare_versions(self):
        version1 = "10.5.2"
        version2 = "101.3.1"
        result = compare_versions(version1, version2)
        self.assertTrue(result == "smaller")

        version1 = "102.5.2"
        version2 = "102.3.1"
        result = compare_versions(version1, version2)
        self.assertTrue(result == "bigger")

        version1 = "102.5.0"
        version2 = "102.5.0"
        result = compare_versions(version1, version2)
        self.assertTrue(result == "equal")

        # ---   ---   ---
        # TORF-685196: Added three tests.
        version1 = "2.6.21"
        version2 = "2.31.4"
        result = compare_versions(version1, version2)
        self.assertTrue(result == "smaller")

        version1 = "2.6.21"
        version2 = "2.1.999"
        result = compare_versions(version1, version2)
        self.assertTrue(result == "bigger")

        version1 = "2.6.21"
        version2 = "2.006.020"
        result = compare_versions(version1, version2)
        self.assertTrue(result == "bigger")

    @patch('h_util.h_utils.yum.YumBase')
    def test_install_rpm_failed(self, m_pkg):
        m_pkg.return_value.pkgSack.returnPackages.return_value = self.rpm_list
        m_pkg.return_value.isPackageInstalled.side_effect = [False, False]
        self.assertRaises(Exception,
                         install_rpm, self.test_rpm)

    @patch('h_util.h_utils.yum.YumBase')
    def test_remove_rpm(self, m_pkg):
        m_pkg.return_value.isPackageInstalled.return_value = True
        remove_rpm(self.test_rpm)
        self.assertTrue(m_pkg.remove.isCalled())

    @patch('h_util.h_utils.yum.YumBase')
    def test_remove_rpm_failed(self, m_pkg):
        m_pkg.return_value.isPackageInstalled.return_value = True
        m_pkg.return_value.processTransaction.side_effect = \
            RemoveError
        self.assertRaises(RemoveError, remove_rpm, self.test_rpm)

    def test_delete_file(self):
        test_file = 'testYUIhjkbnm.txt'
        touch(test_file)
        self.assertTrue(os.path.isfile(test_file))
        delete_file(test_file)
        self.assertFalse(os.path.isfile(test_file))

    @patch('h_util.h_utils.os.remove')
    def test_delete_file_with_exception(self, os_remove):
        test_file = 'testYUIhjkbnm.txt'
        touch(test_file)
        os_remove.side_effect = OSError
        self.assertRaises(OSError, delete_file(test_file))
        os.unlink(test_file)

    @patch('h_util.h_utils.shutil.copy2')
    def test_copy_file(self, cp):
        file1 = 'file1'
        file2 = 'file2'
        copy_file(file1, file2)
        cp.side_effect = IOError
        self.assertRaises(IOError, copy_file, file1, file2)


    def test_exec_process_exception(self):
        self.assertRaises(OSError, exec_process, [self.faulty_cmd])

    def test_exec_process_command(self):
        mock_value = ['Standard output', 'of command']
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = 0
            process.communicate.return_value = mock_value
            result = exec_process([self.exec_cmd])
            self.assertEquals(result, mock_value[0])

    def some_possible_retry_error_messages(self):
        return [
            '.*Error: no response from RAKP [0-9]+ message.*',
            '.*Error: Received an Unexpected RAKP [0-9] message.*'
        ]

    @patch('h_util.h_utils.exec_process')
    def test_exec_process_retry(self, ep):
        exec_process_retry(['some', 'command'],
                           retry_count=1,
                           retry_errors=self.
                           some_possible_retry_error_messages())
        ep.assert_called_with(['some command'], use_shell=True)

    @patch('h_util.h_utils.exec_process')
    def test_exec_process_retry_expected_error(self, ep):
        ep.side_effect = [IOError('Error: no response from RAKP 1 message'),
                          IOError('Error: Received an Unexpected RAKP 1'
                                  ' message'), 'command_worked_on_retry']
        std_out = exec_process_retry(
            'cmd',
            retry_count=5,
            retry_errors=self.some_possible_retry_error_messages())
        self.assertEqual(std_out, 'command_worked_on_retry')

    @patch('h_util.h_utils.exec_process')
    def test_exec_process_retry_limit_reached(self, ep):
        ep.side_effect = [IOError('Error: no response from RAKP 1 message'),
                          IOError('Error: no response from RAKP 1 message')]
        self.assertRaises(IOError,
                          exec_process_retry, 'cmd',
                          retry_count=1,
                          retry_errors=self.
                          some_possible_retry_error_messages())

    @patch('h_util.h_utils.exec_process')
    def test_exec_process_retry_unexpected_error(self, ep):
        ep.side_effect = [IOError('Error: no response from RAKP 1 message'),
                          IOError('Error: some other unknown error')]
        self.assertRaises(IOError,
                          exec_process_retry, 'cmd',
                          retry_count=1,
                          retry_errors=self.
                          some_possible_retry_error_messages())

    def test_exec_process_via_pipes_0(self):
        self.assertRaises(ValueError, exec_process_via_pipes)

    @patch('h_util.h_utils.Popen')
    def test_exec_process_via_pipes(self, popen):
        self.assertRaises(ValueError, exec_process_via_pipes)

        cmd1 = MagicMock()
        cmd1.stdout = StringIO.StringIO('')
        cmd1.returncode = 0
        cmd1.communicate.return_value = ('stdout_cmd1', 'stderr_cmd1')

        cmd2 = MagicMock()
        cmd2.stdout = StringIO.StringIO('')
        cmd2.returncode = 0
        cmd2.communicate.return_value = ('stdout_cmd2', 'stderr_cmd2')

        popen.side_effect = [
            cmd1, cmd2
        ]

        command_parts_dmesg = ['/bin/dmesg']
        command_parts_grep_cpu = ['/bin/grep', 'cpu']

        result = exec_process_via_pipes(command_parts_dmesg,
                                        command_parts_grep_cpu)
        self.assertEqual('stdout_cmd2', result)

        popen.reset_mock()
        popen.side_effect = [
            cmd1, cmd2
        ]
        cmd1.reset_mock()
        cmd2.reset_mock()
        cmd2.returncode = 1
        self.assertRaises(IOError, exec_process_via_pipes,
                          command_parts_dmesg,
                          command_parts_grep_cpu)

    def test_exec_process_exception_retc(self):
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = 5
            self.assertRaises(IOError, exec_process, [self.exec_cmd])

    def test_read_enminst_config_second(self):
        os.environ['ENMINST_HOME'] = '/opt/ericsson/notenminst'
        d = read_enminst_config()
        self.assertEqual(d['enminst_home'], '/opt/ericsson/notenminst')

        self.assertRaises(SystemExit, read_enminst_config,
                          '/opt/ericsson/notenminst')

    def test_get_env_var(self):
        varname = 'tvar'
        os.environ[varname] = 'value--'
        self.assertEqual(os.environ[varname],
                         get_env_var(varname))
        del os.environ[varname]
        self.assertRaises(KeyError, get_env_var, varname)

    def test_get_sed_nodetypes(self):
        sed = mock_sed({
            'db_node1_hostname': 'db1',
            'db_node2_hostname': 'db2',
            'svc_node1_hostname': 'svc1',
            'svc_node2_hostname': 'svc2',
            'db_node3_hostname': '',
            'db_node4_hostname': None,
            'abc_node2_hostname': None,
            'efg_node2_hostname': 'efg1',
            'scp_node1_hostname': '',
            'scp_node2_hostname': '',
        })
        nodetypes = get_sed_nodetypes(sed)

        self.assertIn('db', nodetypes)
        self.assertEqual(2, nodetypes['db'])

        self.assertIn('svc', nodetypes)
        self.assertEqual(2, nodetypes['svc'])

        self.assertNotIn('abc', nodetypes)
        self.assertNotIn('scp', nodetypes)

        self.assertIn('efg', nodetypes)
        self.assertEqual(1, nodetypes['efg'])

    def test_format_sed_key(self):
        self.assertEqual('zxc_node2_akey', format_sed_key('zxc', 2, 'akey'))

    def test_switch_user_no_user_provided(self):
        res = switch_user(None)
        self.assertEqual(res, None)

    def test_switch_user(self):
        res = switch_user('no_user')
        self.assertTrue(callable(res))

    @patch('h_util.h_utils.pwd')
    def test_switch_user_no_user_exists(self, pwd):
        pwd.getpwnam.side_effect = KeyError
        func = switch_user('no_user')
        self.assertRaises(NameError, func)

    @patch('h_util.h_utils.os')
    @patch('h_util.h_utils.pwd')
    def test_switch_user_existing_user(self, pwd, m_os):
        uid = 501
        gid = 501

        class existing_user(object):
            pw_uid = uid
            pw_gid = gid

        pwd.getpwnam.return_value = existing_user
        func = switch_user('existing_user')
        func()
        m_os.setregid.assert_called_with(gid, gid)
        m_os.setreuid.assert_called_with(uid, uid)

    @patch('__builtin__.raw_input')
    def test_query_strong_yes_no_case_sensitive(self, m_raw_input):
        user_inputs = ["y", "yes", "YeS"]
        m_raw_input.side_effect = user_inputs
        answer = query_strong_yes_no("Do you want to continue?")
        self.assertTrue(answer)
        self.assertEqual(m_raw_input.call_count, len(user_inputs))

    @patch('__builtin__.raw_input')
    def test_query_strong_yes_no_repeat(self, m_raw_input):
        m_raw_input.side_effect = ['maybe', 'no']
        answer = query_strong_yes_no("Do you want to continue?")
        self.assertFalse(answer)

    @patch('__builtin__.raw_input')
    def test_strong_confirmation_or_exit_do_not_confirm(self, m_raw_input):
        m_raw_input.return_value = 'no'
        se = assert_exception_raised(SystemExit, strong_confirmation_or_exit,
                                     False, "Blaaa", "Test operation")
        self.assertEquals(se.code, ExitCodes.OK)
        self.assertTrue(m_raw_input.called)

    @patch('__builtin__.raw_input')
    def test_strong_confirmation_or_exit(self, m_raw_input):
        m_raw_input.return_value = 'YeS'
        strong_confirmation_or_exit(False, 'Blaaaaaaaaaaa', "Test operation")
        self.assertTrue(m_raw_input.called)

    def test_time_delta(self):
        ts1 = datetime.datetime(1000, 3, 4, 5, 30, 30).replace(microsecond=0)
        ts2 = ts1 + datetime.timedelta(hours=2)
        h, m, s = time_delta(ts1, ts2)
        self.assertEqual(2, h)
        self.assertEqual(0, m)
        self.assertEqual(0, s)

        # now try several days
        ts2 = ts1 + datetime.timedelta(hours=49)
        h, m, s = time_delta(ts1, ts2)
        self.assertEqual(49, h)
        self.assertEqual(0, m)
        self.assertEqual(0, s)

        ts2 = ts1 + datetime.timedelta(seconds=63)
        h, m, s = time_delta(ts1, ts2)
        self.assertEqual(0, h)
        self.assertEqual(1, m)
        self.assertEqual(3, s)

        ts1 = datetime.datetime.now().replace(microsecond=0)
        ts2 = ts1 + datetime.timedelta(seconds=2)
        with patch('h_util.h_utils.datetime') as m_datetime:
            m_datetime.now.return_value = ts2
            h, m, s = time_delta(ts1)
            self.assertEqual(0, h)
            self.assertEqual(0, m)
            self.assertEqual(2, s)

    def test_litp_backup_state_cron(self):
        litp_backup_state_cron(self.cron_file, self.backup_dir)
        self.assertTrue(os.path.isfile(self.cron_file))
        self.assertTrue(os.path.isdir(self.backup_dir))
        cron_str = '*/10 * * * * root ' \
                   '[ -f /opt/ericsson/nms/litp/bin/litp_state_backup.sh ] && ' \
                   '/opt/ericsson/nms/litp/bin/litp_state_backup.sh ' + \
                   self.backup_dir + '\n'
        cron_entry = open(self.cron_file).read()
        self.assertEqual(cron_str, cron_entry)

    def test_cleanup_java_core_dumps_cron(self):
        cleanup_java_core_dumps_cron(self.cleanup_cron_file)
        self.assertTrue(os.path.isfile(self.cleanup_cron_file))
        cron_str = '#!/bin/sh\n' \
                   'find /ericsson/enm/dumps -type f -mtime +30 ' \
                   r'\( -name \*.hprof -o -name core.\* \) -exec rm -f {} \; ' + '\n'
        cron_entry = open(self.cleanup_cron_file).read()
        self.assertEqual(cron_str, cron_entry)
        mode = oct(stat.S_IMODE(os.stat(self.cleanup_cron_file).st_mode))
        self.assertEqual(mode, oct(0755))

    def test_create_san_fault_check_cron(self):
        create_san_fault_check_cron(self.cleanup_cron_file)
        self.assertTrue(os.path.isfile(self.cleanup_cron_file))
        cron_str = "*/15 * * * * root /opt/ericsson/enminst/bin/san_fault_check.sh \n"
        cron_entry = open(self.cleanup_cron_file).read()
        self.assertEqual(cron_str, cron_entry)

    def test_create_nasaudit_errorcheck_cron(self):
        create_nasaudit_errorcheck_cron(self.cleanup_cron_file)
        self.assertTrue(os.path.isfile(self.cleanup_cron_file))
        cron_str = "0 */4 * * * root /opt/ericsson/enminst/bin/nasaudit_error_check.sh \n"
        cron_entry = open(self.cleanup_cron_file).read()
        self.assertEqual(cron_str, cron_entry)

    @patch('h_util.h_utils.os.makedirs')
    def test_litp_backup_state_cron_exception(self, m_makedirs):
        m_makedirs.side_effect = OSError
        self.assertRaises(OSError, litp_backup_state_cron, self.cron_file,
                          self.backup_dir)

    def test_sanitize(self):
        raw_string = r"K9$y$tem"
        sanitized_string = sanitize(raw_string)
        self.assertEquals(sanitized_string, r"K9\$y\$tem")

    def test_get_removed_nodes(self):
        tmp_model_diff_file = join(gettempdir(), 'xml_model.diff')
        if os.path.exists(tmp_model_diff_file):
            os.remove(tmp_model_diff_file)
        os.environ['DEPLOYMENT_DIFF_OUTPUT'] = tmp_model_diff_file

        removed_nodes = get_removed_nodes()
        self.assertEquals(removed_nodes, [])

        try:
            with open(tmp_model_diff_file, 'w') as _writer:
                _writer.writelines([
                    '# This file contains a list of paths ..\n'
                    'y /deployments/enm/clusters/cluster/configs/aliases\n'
                    'y /deployments/enm/clusters/cluster/nodes/db-1/items/t1\n'
                    'y /deployments/enm/clusters/cluster/nodes/svc-2\n'
                    'y /infrastructure/systems/svc-2_system\n'])
            removed_nodes = get_removed_nodes()
            self.assertEquals(removed_nodes,
                    ['/deployments/enm/clusters/cluster/nodes/svc-2'])
        finally:
            os.remove(tmp_model_diff_file)

    def test_get_removed_clusters(self):
        tmp_model_diff_file = join(gettempdir(), 'xml_model.diff')
        if os.path.exists(tmp_model_diff_file):
            os.remove(tmp_model_diff_file)
        os.environ['DEPLOYMENT_DIFF_OUTPUT'] = tmp_model_diff_file

        removed_clusters = get_removed_clusters()
        self.assertEquals(removed_clusters, [])
        try:
            with open(tmp_model_diff_file, 'w') as _writer:
                _writer.writelines([
                    '# This file contains a list of paths ..\n'
                    'y /deployments/enm/clusters/aut_cluster/configs/aliases\n'
                    'y /deployments/enm/clusters/aut_cluster/nodes/db-1\n'
                    'y /deployments/enm/clusters/aut_cluster\n'])
            removed_clusters = get_removed_clusters()
            self.assertEquals(removed_clusters,
                              ['/deployments/enm/clusters/aut_cluster'])
        finally:
            os.remove(tmp_model_diff_file)

    @patch('h_util.h_utils.delete_file')
    def test_delete_matching_files(self, delete):
        c = h_util.h_utils
        gp_file = join(gettempdir(), 'hostname.ks')
        open(gp_file, 'w').close()
        c.delete_matching_files(gettempdir(), 'hostname.ks')
        expected = join(gettempdir(), 'hostname.ks')
        delete.assert_called_with(expected)
        if exists(expected):
            os.remove(expected)

    def test_db_node_removed(self):
        tmp_model_diff_file = join(gettempdir(), 'xml_model.diff')
        if os.path.exists(tmp_model_diff_file):
            os.remove(tmp_model_diff_file)
        os.environ['DEPLOYMENT_DIFF_OUTPUT'] = tmp_model_diff_file

        self.assertEquals(db_node_removed(), False)

        try:
            with open(tmp_model_diff_file, 'w') as _writer:
                _writer.writelines([
                        '# This file contains a list of paths ..\n'
                        'y /deployments/enm/clusters/cluster/configs/aliases\n'
                        'y /deployments/enm/clusters/db_cluster/nodes/db-1\n'
                        'y /infrastructure/systems/db-1_system\n'])
            self.assertEquals(db_node_removed(), True)

            with open(tmp_model_diff_file, 'w') as _writer:
                _writer.writelines([
                    '# This file contains a list of paths ..\n'
                    'y /deployments/enm/clusters/db_cluster/configs/aliases\n'
                    'y /deployments/enm/clusters/svc_cluster/nodes/svc-1\n'
                    'y /infrastructure/systems/svc-1_system\n'])
            self.assertEquals(db_node_removed(), False)
        finally:
            os.remove(tmp_model_diff_file)

    @patch('os.system')
    def test__exec_curl_command(self, m_os_system):
        m_os_system.return_value = "OK"
        self.assertEquals("OK", _exec_curl_command("curlcommand"))
        m_os_system.assert_called_with("curlcommand")

    @patch('os.system')
    def test__exec_curl_command_OSError_no_try(self, m_os_system):
        m_os_system.return_value = "OK"
        self.assertRaises(SystemExit, _exec_curl_command, "curlcommand", 0)

    @patch('os.system')
    def test__exec_curl_command_IOError_retry(self, m_os_system):
        m_os_system.side_effect = [IOError(), "OK"]
        self.assertEquals("OK", _exec_curl_command("curlcommand"))

    @patch('os.system')
    def test__exec_curl_command_retry_failure(self, m_os_system):
        m_os_system.side_effect = [IOError(), OSError()]
        self.assertRaises(SystemExit, _exec_curl_command, "curlcommand")


    @patch('h_util.h_utils._parse_pexpect_return_code')
    def test__handle_pexpect_response(self, m_parse_pexpect_return_code):
        m_child = MockPexpectChild(0, "stdout")
        m_parse_pexpect_return_code.return_value = "stdout"
        self.assertEquals(_handle_pexpect_response(m_child), "stdout")

    def test__handle_pexpect_response_InvalidCredentialsError(self):
        m_child = MockPexpectChild(1, "stdout")
        self.assertRaises(InvalidCredentialsError, _handle_pexpect_response, m_child)

    def test__parse_pexpect_return_code(self):
        response = "\r\n[u'', u'Provide a Ne Type value from this list:"\
                   " [5GRadioNode, AFG, BGF]']\r\nReturn Code: 0\r\n"
        expected_return = "[u'', u'Provide a Ne Type value from this list:"\
                   " [5GRadioNode, AFG, BGF]']"
        self.assertEquals(_parse_pexpect_return_code(response), expected_return)

    def test__parse_pexpect_return_code_CR_LF_put_back(self):
        response = "\r\n[u'', u'Provide\r\n a Ne Type value from\r\n this list:"\
                   " [5GRadioNode, \r\nAFG, BGF]']\r\nReturn Code: 0\r\n"
        expected_return = "[u'', u'Provide\r\n a Ne Type value from\r\n this list:"\
                   " [5GRadioNode, \r\nAFG, BGF]']"
        self.assertEquals(_parse_pexpect_return_code(response), expected_return)

    def test__parse_pexpect_return_code_IOError(self):
        response = "\r\nReturn Code: 2\r\npython: can't open file"\
                   " '/home/shared/administrator/h_enmscripting_administrator_20190717151030592788.py':"\
                   " [Errno 2] No such file or directory\r\n"
        self.assertRaises(IOError, _parse_pexpect_return_code, response)

    def test__parse_pexpect_return_code_10_IOError(self):
        response = "\r\nReturn Code: 10\r\npython: can't open file"\
                   " '/home/shared/administrator/h_enmscripting_administrator_20190717151030592788.py':"\
                   " [Errno 2] No such file or directory\r\n"
        self.assertRaises(IOError, _parse_pexpect_return_code, response)

    def test__parse_pexpect_return_code_01_IOError(self):
        response = "\r\nReturn Code: 01\r\npython: can't open file"\
                   " '/home/shared/administrator/h_enmscripting_administrator_20190717151030592788.py':"\
                   " [Errno 2] No such file or directory\r\n"
        self.assertRaises(IOError, _parse_pexpect_return_code, response)

    def test__parse_pexpect_return_code_no_return_code(self):
        response = "\r\n[u'', u'Provide a Ne Type value from this list:"\
                   " [5GRadioNode, AFG, BGF]']\r\n"
        expected_return = "[u'', u'Provide a Ne Type value from this list:"\
                   " [5GRadioNode, AFG, BGF]']"
        self.assertEquals(_parse_pexpect_return_code(response), expected_return)

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(0, "")
        m_spawn.return_value = m_child
        m_pex_resp.return_value = "stdout"
        self.assertEquals(_pexpect_execute_remote_command(self.ssh_values['command'],
                                                          self.ssh_values['password']),
                                                            "stdout")

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command_IOError_success(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(0, "")
        m_spawn.return_value = m_child
        m_pex_resp.side_effect = [IOError, "stdout"]
        self.assertEquals(_pexpect_execute_remote_command(self.ssh_values['command'],
                                                          self.ssh_values['password']),
                                                            "stdout")

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command_OSError_EOF(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(0, "")
        m_spawn.return_value = m_child
        m_pex_resp.side_effect = [OSError, EOF("")]
        self.assertRaises(IOError, _pexpect_execute_remote_command, self.ssh_values['command'],
                          self.ssh_values['password'])

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command_TIMEOUT_success(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(0, "")
        m_spawn.return_value = m_child
        m_pex_resp.side_effect = [TIMEOUT(""), "stdout"]
        self.assertEquals(_pexpect_execute_remote_command(self.ssh_values['command'],
                                                          self.ssh_values['password']),
                                                            "stdout")

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command_TIMEOUT_success_unkown_hosts(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(1, "")
        m_spawn.return_value = m_child
        m_pex_resp.side_effect = [TIMEOUT(""), "stdout"]
        self.assertEquals(_pexpect_execute_remote_command(self.ssh_values['command'],
                                                          self.ssh_values['password']),
                                                            "stdout")

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command_OSError_EOF_unkown_hosts(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(1, "")
        m_spawn.return_value = m_child
        m_pex_resp.side_effect = [TIMEOUT(""), EOF("")]
        self.assertRaises(IOError, _pexpect_execute_remote_command, self.ssh_values['command'],
                          self.ssh_values['password'])

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command_InvalidCredentialsError(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(0, "")
        m_spawn.return_value = m_child
        m_pex_resp.side_effect = [InvalidCredentialsError, "stdout"]
        self.assertRaises(InvalidCredentialsError, _pexpect_execute_remote_command, self.ssh_values['command'],
                          self.ssh_values['password'])

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command_ExceptionPexpect(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(0, "")
        m_spawn.return_value = m_child
        m_pex_resp.side_effect = [ExceptionPexpect(""), "stdout"]
        self.assertRaises(IOError, _pexpect_execute_remote_command, self.ssh_values['command'],
                          self.ssh_values['password'])

    def test__pexpect_execute_remote_command_TypeError(self):
        self.assertRaises(TypeError, _pexpect_execute_remote_command, self.ssh_values['command'],
                          self.ssh_values['password'], "", "")

    @patch('h_util.h_utils.pexpect.spawn')
    @patch('h_util.h_utils._handle_pexpect_response')
    def test__pexpect_execute_remote_command_No_TypeError(self, m_pex_resp, m_spawn):
        m_child = MockPexpectChild(0, "")
        m_spawn.return_value = m_child
        m_pex_resp.return_value = "stdout"
        _pexpect_execute_remote_command(self.ssh_values['command'],
                          self.ssh_values['password'], 1, 1)

    @patch('h_util.h_utils.exec_process')
    def test_ping(self, m_exec_process):
        m_exec_process.return_value = ""
        self.assertEquals(True, ping("scp-1-scripting"))

    @patch('h_util.h_utils.exec_process')
    def test_ping_IOError(self, m_exec_process):
        m_exec_process.side_effect = IOError()
        self.assertEquals(False, ping("scp-1-scripting"))

    @patch('h_util.h_utils.LOG')
    @patch('h_util.h_utils.is_exist_edp_sed_file')
    def test_get_edp_sed_none(self,
                              m_sed_exist,
                              m_log):

        edp_sed_dir = '/software/vol1'
        mock_sed_file = 'ansible_tmp_sed.txt'
        sed_filepath = '{0}/{1}'.format(edp_sed_dir, mock_sed_file)
        regex = '.*_ilo_IP'
        m_sed_exist.return_value = False
        res = get_edp_generated_sed(regex)
        m_sed_exist.assert_called_once()
        m_log.assert_called_once()
        self.assertEqual({}, res)

    @patch('h_util.h_utils.exists')
    @patch('h_util.h_utils.is_exist_edp_sed_file')
    def test_get_edp_sed_from_key(self,
                                   m_sed_exist,
                                   m_os_path_exists):
        regex = '.*_ilo_IP'
        expect_res = {'LMS_ilo_IP': '1.2.3.4'}
        m_sed_exist.return_value = True
        m_os_path_exists.return_value = True
        sed_file_content = """LMS_ilo_IP=1.2.3.4\nLMS_hostname='hello_world'\nLMS_IP=2.3.4.5"""
        with patch('__builtin__.open') as mock_open:
            mock_open.return_value.__enter__.return_value = StringIO.StringIO(sed_file_content)
            res = get_edp_generated_sed(regex)
        self.assertEqual(expect_res, res)

    @patch('h_util.h_utils.Sed._load')
    @patch('h_util.h_utils.Sed.get_value')
    @patch('h_util.h_utils.Sed.find_keys')
    @patch('h_util.h_utils.is_exist_edp_sed_file')
    def test_get_whole_edp_sed(self,
                               m_sed_exist,
                               m_sed_find_keys,
                               m_sed_get_val,
                               m_sed_load):
        edp_sed_dir = '/software/vol1'
        mock_sed_file = 'ansible_tmp_sed.txt'
        sed_filepath = '{0}/{1}'.format(edp_sed_dir, mock_sed_file)
        m_sed_exist.return_value = True
        get_edp_generated_sed()
        m_sed_load.assert_called_once_with(sed_filepath)
        m_sed_find_keys.assert_not_called()
        m_sed_get_val.assert_not_called()


class TestSed(unittest2.TestCase):
    def __init__(self, method_name='runTest'):
        super(TestSed, self).__init__(method_name)
        self.sedfilename = join(gettempdir(), 'test.sed')

    def tearDown(self):
        super(TestSed, self).tearDown()
        if exists(self.sedfilename):
            remove(self.sedfilename)

    def test_init(self):
        self.assertRaises(IOError, Sed, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')

    def test_get_value(self):
        sed = mock_sed({'a': None, '1': '2'})
        self.assertIsNone(sed.get_value('a'))
        self.assertRaises(ValueError, sed.get_value, 'a',
                          error_if_not_set=True)
        self.assertEqual('2', sed.get_value('1'))
        self.assertEqual('default', sed.get_value('not_defined', 'default'))
        self.assertRaises(KeyError, sed.get_value, 'not_defined')

    def test_find_keys(self):
        sed = mock_sed({'k1': '', 'k2': 'v2', '2k2': '2v2'})
        keys = sed.find_keys('.*')
        self.assertEqual(3, len(keys))
        self.assertEqual(['k2', 'k1', '2k2'], keys)

        keys = sed.find_keys('k2')
        self.assertEqual(1, len(keys))
        self.assertEqual(['k2'], keys)

        keys = sed.find_keys('.*k2')
        self.assertEqual(2, len(keys))
        keys = sed.find_keys('k2')
        self.assertEqual(1, len(keys))
        self.assertEqual(['k2'], keys)

        keys = sed.find_keys('.*k2')
        self.assertEqual(2, len(keys))
        self.assertEqual(['k2', '2k2'], keys)

        keys = sed.find_keys('k.*')
        self.assertEqual(2, len(keys))
        self.assertEqual(['k2', 'k1'], keys)

    def test_has_site_key(self):
        sed = mock_sed({'k2': 'v2', '2k2': '2v2'})
        self.assertFalse(sed.has_site_key('sdflkda;lsdka;ldk'))
        self.assertTrue(sed.has_site_key('k2'))

    def test_get_network_key(self):
        self.assertEqual('IP_test', Sed.get_network_key('teST'))
        self.assertEqual('IP', Sed.get_network_key('services'))

    def testmodelid_to_sedid(self):
        self.assertEqual('str_node2', Sed.modelid_to_sedid('str-2'))

    def test_subset(self):
        sed = Sed(None)
        sed.sed = {
            'aa_1': 'a',
            'aa_2': 'a',
            'bb_1': 'b',
            'bb_2': 'b'
        }
        subset = sed.subset('aa_(.*)')
        self.assertIn('1', subset)
        self.assertEqual('a', subset['1'])
        self.assertIn('1', subset)
        self.assertEqual('a', subset['2'])

    def test_get_node_config(self):
        sed = Sed(None)
        sed.sed = {
            'svc_node1_IP': 'ipsvc',
            'svc_node1_eth0_macaddress': 'macsvc',
            'str_node1_IP': 'ipstr',
            'srt_node1_eth0_macaddress': 'macstr'
        }
        data = sed.get_node_config('svc_node1')
        self.assertIn('IP', data)
        self.assertEqual('ipsvc', data['IP'])
        self.assertIn('eth0_macaddress', data)
        self.assertEqual('macsvc', data['eth0_macaddress'])

    @patch('h_util.h_utils.exec_process')
    @patch("os.path.exists")
    def test_get_last_applied_sed_s_param(self, _exists, _exec_process):
        ug_cmd = "./upgrade_enm.sh %s /path/toSED/sed.cfg -e /other/param"
        _exists.return_value = True
        _exec_process.return_value = ug_cmd % "-s"
        sed_path = Sed.get_last_applied_sed()
        self.assertEqual(sed_path, "/path/toSED/sed.cfg")

    @patch('h_util.h_utils.exec_process')
    @patch("os.path.exists")
    def test_get_last_applied_sed_param(self, _exists, _exec_process):
        ug_cmd = "./upgrade_enm.sh %s /path/toSED/sed.cfg -e /other/param"
        _exists.return_value = True
        _exec_process.return_value = ug_cmd % "--sed"
        sed_path = Sed.get_last_applied_sed()
        self.assertEqual(sed_path, "/path/toSED/sed.cfg")

    @patch('h_util.h_utils.exec_process')
    @patch("os.path.exists")
    def test_no_sed_param_in_cmd(self, _exists, _exec_process):
        ug_cmd = "./upgrade_enm.sh %s /path/toSED/sed.cfg -e /other/param"
        _exists.return_value = True
        _exec_process.return_value = ug_cmd % "--no"
        with self.assertRaises(ValueError):
            Sed.get_last_applied_sed()

    @patch("os.path.exists")
    def test_cmd_log_does_not_exists(self, _exists):
        _exists.return_value = False
        with self.assertRaises(IOError):
            Sed.get_last_applied_sed()

    @patch('h_util.h_utils.exec_process')
    @patch("os.path.exists")
    def test_sed_file_does_not_exists(self, _exists, _exec_process):
        ug_cmd = "./upgrade_enm.sh %s /path/toSED/sed.cfg -e /other/param"
        _exists.side_effect = (True, False)
        _exec_process.return_value = ug_cmd % "--sed"
        with self.assertRaises(IOError):
            Sed.get_last_applied_sed()

    @patch('h_litp.litp_rest_client.LitpRestClient.get_auth_header')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_is_env_on_rack(self, litp, litp_header):
        header = {'Authorization': 'Basic litp-admin:password'}
        litp_header.return_value = header

        litp.return_value = {'properties': {'key': 'enm_deployment_type'}}
        for pval in ('Extra_Large_ENM_On_Rack_Servers',
                     'vLITP_ENM_On_Rack_Servers',
                     'Anything_ENM_On_Rack_Servers'):
            litp.return_value['properties']['value'] = pval
            self.assertTrue(is_env_on_rack())

    @patch('h_litp.litp_rest_client.LitpRestClient.get_auth_header')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_is_env_not_on_rack(self, litp, litp_header):
        header = {
            'Authorization': 'Basic litp-admin:password'
        }
        litp_header.return_value = header
        litp.return_value = {'properties': {'key': 'enm_deployment_type',
                                            'value': 'Test_ENM_Servers'}}
        self.assertFalse(is_env_on_rack())

class TestFormatter(unittest2.TestCase):
    def setUp(self):
        self.formatter = Formatter()

    def test_init_formatter(self):
        self.assertIsInstance(self.formatter, Formatter)

    def test_format_color(self):
        color, text = self.formatter.BG_GRAY, 'sometext'
        fc = self.formatter.format_color(text, color)
        self.assertEquals(fc, color + text + self.formatter.ENDC)


class TestRHELUtil(unittest2.TestCase):
    def setUp(self):
        web_root = '/var/www/html'
        self.rhel_ver = '6.10'
        self.instance = RHELUtil(web_root)
        self.pp_man = ['file { ["/var/www/html/6.6",' \
                            '"/var/www/html/6.6/os",' \
                            '"/var/www/html/6.6/os/x86_64",' \
                            '"/var/www/html/6.6/os/x86_64/Packages",' \
                            '"/var/www/html/6.6/updates",' \
                            '"/var/www/html/6.6/updates/x86_64",' \
                            '"/var/www/html/6.6/updates/x86_64/Packages",' \
                            '"/var/www/html/litp_plugins",' \
                            '"/var/www/html/vm_scripts"]:' \
                            'ensure      => directory,' \
                          '}' \
                      'file {\'/var/www/html/6/\':' \
                        'ensure      => \'link\',' \
                        'target      => \'/var/www/html/6.6/\',' \
                        'require     => File["/var/www/html/6.6/updates"],'\
                      '}',
                      '{"target":"File[/var/www/html/6.6]","source":"Class[Litp::Ms_node]"},{"target":"File[/var/www/html/6.6/os]","source":"Class[Litp::Ms_node]"},{"target":"File[/var/www/html/6.6/os/x86_64/Packages]","source":"Class[Litp::Ms_node]"}'
                       ]

    def test_get_current_version(self):
        with patch('h_util.h_utils.open', create=True) as m_open:
            m_open.return_value.__enter__.return_value.readline.return_value \
                = 'Red Hat Enterprise Linux Server release 7.10 (Maipo)'
            self.assertEqual('7.10', self.instance.get_current_version())

            m_open.return_value.__enter__.return_value.readline.return_value \
                = 'Red Hat Enterprise Linux Server release 7.9 (Maipo)'
            self.assertEqual('7.9', self.instance.get_current_version())

            m_open.return_value.__enter__.return_value.readline.return_value \
                = 'CentOS Linux release 7.9.2009 (Core)'
            self.assertEqual('7.9.2009', self.instance.get_current_version())

            m_open.return_value.__enter__.return_value.readline.return_value \
                = 'Red Hat Enterprise Linux Server release 7.10 (Maipo)'
            self.assertNotEqual('7.9', self.instance.get_current_version())

            m_open.return_value.__enter__.return_value.readline.return_value \
                = 'Red Hat Enterprise Linux Server release 7.9 (Maipo)'
            self.assertNotEqual('7.10', self.instance.get_current_version())

    @patch('os.path.isdir')
    def test_is_latest_version(self, m_isdir):
        with patch('h_util.h_utils.open', create=True) as m_open:
            m_isdir.return_value = True
            m_open.return_value.__enter__.return_value.readline.return_value \
                = 'Red Hat Enterprise Linux Server release 7.9 (Maipo)'
            self.assertTrue(self.instance.is_latest_version())

            m_open.return_value.__enter__.return_value.readline.return_value \
                = 'Red Hat Enterprise Linux Server release 6.6 (Santiago)'
            self.assertFalse(self.instance.is_latest_version())

            m_isdir.return_value = False
            m_open.return_value.__enter__.return_value.readline.return_value \
                = 'Red Hat Enterprise Linux Server release 6.10 (Santiago)'
            self.assertFalse(self.instance.is_latest_version())

    @patch('h_util.h_utils.exec_process')
    @patch('os.unlink')
    @patch('os.path.isdir')
    def test_ensure_version_symlink(self, m_isdir, m_unlink, m_exec):
        m_isdir.return_value = True
        self.instance.ensure_version_symlink(self.rhel_ver)
        m_exec.assert_has_calls(
            [call(['ln', '-sf', '/var/www/html/6.10', '/var/www/html/6'])])

    @patch('h_util.h_utils.exec_process')
    @patch('socket.gethostname')
    def test_ensure_version_manifest(self, m_hostname, m_exec):
        with patch('h_util.h_utils.open', create=True) as m_open:
            m_hostname.return_value = 'ms_hostname'
            m_open.return_value.__enter__.return_value.read.side_effect \
                    = [self.pp_man[0], self.pp_man[1]]
            self.instance.ensure_version_manifest(self.rhel_ver)
            m_exec.assert_has_calls(
                [call(['sed', '-i', 's/\\/var\\/www\\/html\\/6.6/\\/var\\/www\\/html\\/6.10/g',
                       '/opt/ericsson/nms/litp/etc/puppet/modules/litp/manifests/ms_node.pp']),
                 call(['sed', '-i', 's/\\/var\\/www\\/html\\/6.6/\\/var\\/www\\/html\\/6.10/g',
                       '/var/lib/puppet/client_data/catalog/ms_hostname.json'])
                 ], any_order=True)

    @patch('h_util.h_utils.shutil.rmtree')
    @patch('glob.glob')
    @patch('os.path.isdir')
    def test_clean_repos(self, m_isdir, m_glob, m_rmtree):
        m_isdir.side_effect = [True, True]
        m_glob.return_value = ['/var/www/html/6.6']
        self.instance.clean_repos()
        self.assertTrue(m_rmtree.called)
        m_rmtree.assert_called_with('/var/www/html/6.6')

    def test_to_ordinal(self):
        test_vals = ((1, '1st'), (2, '2nd'), (3, '3rd'),
                     (4, '4th'), (11, '11th'), (12, '12th'),
                     (13, '13th'), (20, '20th'), (21, '21st'),
                     (22, '22nd'), (23, '23rd'), (100, '100th'),
                     (101, '101st'), (102, '102nd'), (103, '103rd'),
                     (111, '111th'), (112, '112th'), (113, '113th'),
                     (121, '121st'), (122, '122nd'), (123, '123rd'))

        for val, expected in test_vals:
            res = to_ordinal(val)
            self.assertEquals(res, expected)

    def test_get_nas_type_sed_unityxt(self):
        sed_nas_type = Mock()
        sed_nas_type.get_value = Mock(return_value='unityxt')
        self.assertEquals(get_nas_type_sed(sed_nas_type), 'unityxt')

    def test_get_nas_type_sed_veritas(self):
        sed_nas_type = Mock()
        sed_nas_type.get_value = Mock(return_value='veritas')
        self.assertEquals(get_nas_type_sed(sed_nas_type), 'veritas')

    def test_get_nas_type_sed_none(self):
        sed_nas_type = Mock()
        sed_nas_type.get_value.side_effect = KeyError
        self.assertEquals(get_nas_type_sed(sed_nas_type), 'veritas')

    def test_get_nas_value_veritas(self):
        model_data = [{'path': '/infrastructure/storage/storage_providers//sfs',
                       'data': {u'id': u'sfs',
                                u'item-type-name': u'sfs-service',
                                u'applied_properties_determinable': True,
                                u'state': u'Applied', u'_links': {u'self': {
                               u'href': u'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/sfs'},
                                                                  u'item-type': {
                                                                      u'href': u'http://127.0.0.1/litp/rest/v1/item-types/sfs-service'}},
                                u'properties': {u'nas_type': u'veritas',
                                                u'management_ipv4': u'172.16.30.18',
                                                u'user_name': u'support',
                                                u'name': u'cloud-sfs',
                                                u'password_key': u'key-for-sfs'}}}]
        mock_litp_get = Mock()
        mock_litp_get.get_all_items_by_type = Mock(return_value=model_data)

        self.assertEquals(get_nas_type(mock_litp_get), 'veritas')

    def test_get_nas_value_unityxt(self):
        model_data = [{'path': '/infrastructure/storage/storage_providers//sfs',
                       'data': {u'id': u'sfs',
                                u'item-type-name': u'sfs-service',
                                u'applied_properties_determinable': True,
                                u'state': u'Applied', u'_links': {u'self': {
                               u'href': u'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/sfs'},
                                                                  u'item-type': {
                                                                      u'href': u'http://127.0.0.1/litp/rest/v1/item-types/sfs-service'}},
                                u'properties': {u'nas_type': u'unityxt',
                                                u'management_ipv4': u'10.150.29.165',
                                                u'user_name': u'admin',
                                                u'name': u'ieatunity-32',
                                                u'password_key': u'key-for-sfs'}}}]
        mock_litp_get = Mock()
        mock_litp_get.get_all_items_by_type = Mock(return_value=model_data)

        self.assertEquals(get_nas_type(mock_litp_get), 'unityxt')

    def test_get_nas_value_no_nastype(self):
        model_data = [{'path': '/infrastructure/storage/storage_providers//sfs',
                       'data': {u'id': u'sfs',
                                u'item-type-name': u'sfs-service',
                                u'applied_properties_determinable': True,
                                u'state': u'Applied', u'_links': {u'self': {
                               u'href': u'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/sfs'},
                                                                  u'item-type': {
                                                                      u'href': u'http://127.0.0.1/litp/rest/v1/item-types/sfs-service'}},
                                u'properties': {
                                    u'management_ipv4': u'172.16.30.18',
                                    u'user_name': u'support',
                                    u'name': u'cloud-sfs',
                                    u'password_key': u'key-for-sfs'}}}]
        mock_litp_get = Mock()
        mock_litp_get.get_all_items_by_type = Mock(return_value=model_data)

        self.assertEquals(get_nas_type(mock_litp_get), 'veritas')

    def test_get_nas_value_no_model_entry(self):
        mock_litp_get = Mock()
        mock_litp_get.get_all_items_by_type = Mock(return_value=[])

        self.assertEquals(get_nas_type(mock_litp_get), 'veritas')

    @patch('h_litp.litp_utils.is_custom_service')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_all_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    def test_migrate_cleanup_cmd(self, mock_update, mock_get_items,
                                 mock_is_custom_svc):
        mock_is_custom_svc.return_value = True
        vm_utils = '/usr/share/litp_libvirt/vm_utils'

        cmd1 = '/sbin/service foo stop'
        cmd2 = '/sbin/service bar stop-undef'
        cmd3 = '/sbin/service baz force-stop'
        cmd4 = '/sbin/service bam make-stop -timeout=30'
        cmd5 = 'service dam do-stop --timeout=300'
        cmd6 = 'systemctl stop ram.service'
        cmd7 = vm_utils + ' cam stop'
        tdata = [{'data': {'id': 'svc_name',
                           'properties': {'cleanup_command': cmd}},
                 'path': '/software/services/svc{0}'.format(idx)}
                 for idx, cmd in enumerate([cmd1, cmd2, cmd3, cmd4,
                                            cmd5, cmd6, cmd7])]

        mock_get_items.return_value = tdata

        migrate_cleanup_cmd()

        expected = [call('/software/services/svc1',
                         {'cleanup_command': vm_utils + ' bar stop-undefine'}),
                    call('/software/services/svc2',
                         {'cleanup_command': vm_utils + ' baz stop-undefine'}),
                    call('/software/services/svc3',
            {'cleanup_command': vm_utils + ' bam stop-undefine -timeout=30'})]

        mock_update.assert_has_calls(expected)

    def test_get_enable_cron_on_expiry_cmd(self):
        m_pam_auth_file = '/etc/pam.d/password_auth'
        expected_cmd = 'grep pam_unix.so {0}; if [ $? -ne 0 ]; then '\
        'sed -i.bak \'$i grep pam_access.so {1}; if [ $? -ne 0 ]; then '\
        'sed -i.bak '\
        '\'\\\'\'s/account     required      pam_unix.so/account'\
        '     required      pam_access.so\\\\n'\
        'account  [success=1 default=ignore] pam_succeed_if.so'\
        ' service in crond quiet use_uid\\\\n'\
        'account     required      pam_unix.so /g\'\\\'\' {1}; fi\''\
        ' {0}; fi'.format(KICKSTART_ERB, m_pam_auth_file)
        self.assertEquals(get_enable_cron_on_expiry_cmd(m_pam_auth_file), expected_cmd)

    @patch('h_util.h_utils.Sed.get_value', return_value='file:///path/to/banner.txt')
    @patch('h_util.h_utils.exists', return_value=True)
    @patch('filecmp.cmp', return_value=False)
    @patch('h_util.h_utils.shutil.copyfile')
    def test_copy_as_template_with_file_path(self, _copyfile, _cmp, _exists, _get_value):

        sed = mock_sed({
            'custom_login_banner': 'file:///path/to/banner.txt',
        })

        banner_key = "custom_login_banner"
        target = "issue.net.custom"

        result = _copy_as_template(sed, banner_key, target)

        _get_value.assert_called_with(banner_key)
        _cmp.assert_called_with("/path/to/banner.txt", join(LITP_ERB_TEMPLATES, target), False)
        _copyfile.assert_not_called()
        self.assertFalse(result)

        _exists.return_value = False
        result = _copy_as_template(sed, banner_key, target)
        _get_value.assert_called_with(banner_key)
        _copyfile.assert_called_with("/path/to/banner.txt", join(LITP_ERB_TEMPLATES, target))
        self.assertTrue(result)

    @patch('h_util.h_utils._copy_as_template')
    @patch('h_util.h_utils.Sed')
    def test_copy_custom_banners(self, _sed_class, _copy_as_template):
        _sed_instance = MagicMock()
        _sed_instance.get_value.side_effect = lambda key: {
            'custom_login_banner': 'Custom Banner Content',
            'custom_motd_banner': 'Custom MOTD Content'
        }.get(key, None)
        _sed_class.return_value = _sed_instance

        class Args(object):
            sed_file = "/software/autoDeploy/sed"
        cfg = Args()

        copy_custom_banners(cfg)

        _copy_as_template.assert_any_call(_sed_instance,
                                              'custom_login_banner',
                                              'issue.net.custom')
        _copy_as_template.assert_any_call(_sed_instance,
                                              'custom_motd_banner',
                                              'motd.custom')


if __name__ == '__main__':
    unittest2.main()
