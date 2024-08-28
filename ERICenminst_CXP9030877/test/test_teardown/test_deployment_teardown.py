import shutil
import sys

import time
from mock import MagicMock
from os import makedirs

from h_litp.litp_rest_client import LitpRestClient
from litpd import LitpIntegration

try:
    import yum
except ImportError:
    sys.modules['yum'] = MagicMock()

import os
import json
import socket
from os.path import join, dirname, exists, isdir
from socket import gethostname
from tempfile import gettempdir

import unittest2
from mock import patch, call, ANY

import deployment_teardown
from h_util.h_utils import ExitCodes

sed = '''#SED Template Version: 1.0.27

Variable_Name=Variable_Value

db_node1_hostname=host1
db_node2_hostname=host2
svc_node1_hostname=svc_node1_hostname
svc_node2_hostname=svc_node2_hostname
svc_node3_hostname=svc_node3_hostname
svc_node4_hostname=svc_node4_hostname
sfs_console_IP=2.3.4.5
sfssetup_username=admin
sfssetup_password=shroot
ENMservices_IPv6gateway=2001:1b70:82a1:16:0:3018:0:1
ENMIPv6_subnet=2001:1b70:82a1:0017/64
storage_subnet=10.42.2.0/23
backup_subnet=10.0.24.0/21
jgroups_subnet=192.168.5.0/24
internal_subnet=192.168.55.0/24
VLAN_ID_backup=256'''

cobbler_output = '''
   rhel_6_4-x86_64

'''


class TestLvmCleanup(unittest2.TestCase):
    def setUp(self):
        basepath = dirname(dirname(dirname(__file__.replace(os.sep, '/'))))
        os.environ['ENMINST_CONF'] = join(basepath, 'src/main/resources/conf')
        os.environ['ENMINST_BIN'] = join(basepath, 'src/main/bin')
        os.environ['ENMINST_ETC'] = join(basepath, 'src/main/etc')
        os.environ['ENMINST_LIB'] = join(basepath, 'src/main/lib')
        os.environ['ENMINST_RUNTIME'] = gettempdir()
        self.t = deployment_teardown
        self.sed = sed
        self.sed_file = join(gettempdir(), 'sed_file')
        self.ini_file = join(gettempdir(), 'ini_file')
        self.write_file(self.sed_file, sed)
        self.write_file(self.ini_file, sed)
        self.c = deployment_teardown.CleanupDeployment(self.sed_file)

    def write_file(self, location, contents):
        with open(location, 'w') as _f:
            _f.writelines(contents)

    @patch('deployment_teardown.teardown_sfs')
    def test_check_clean_sfs(self, sfs):
        self.c.clean_sfs()
        self.assertTrue(sfs.called)

    @patch('deployment_teardown.exec_process')
    @patch('os.path.isdir', return_value=True)
    @patch('shutil.rmtree')
    def test_check_clean_esm_vm_with_existing_libvirt_dir(self, rmtree, m_isdir,
                                                          exec_proc):
        self.c.clean_esm_vm()
        exec_proc.assert_any_call(['virsh', 'destroy', ANY], True)
        exec_proc.assert_any_call(['virsh', 'undefine', ANY], True)
        self.assertTrue(rmtree.called)

    @patch('deployment_teardown.exec_process')
    @patch('os.path.isdir', return_value=False)
    @patch('shutil.rmtree')
    def test_check_clean_esm_vm_with_no_existing_libvirt_dir(self, rmtree,
                                                             m_isdir, exec_proc):
        self.c.clean_esm_vm()
        exec_proc.assert_any_call(['virsh', 'destroy', ANY], True)
        exec_proc.assert_any_call(['virsh', 'undefine', ANY], True)
        self.assertFalse(rmtree.called)

    @patch('deployment_teardown.exec_process')
    def test_check_esm_vm_remove_esm_dir(self, exec_proc):
        _tmpdir = os.path.join(gettempdir(), 'esm_tests/')
        _tmpdir_mysql_mount = os.path.join(gettempdir(),
                                           'esm_tests_mysql_mount/')
        self.c.esm_mount_dirs = [_tmpdir, _tmpdir_mysql_mount]
        self.c.esm_vm_dir = _tmpdir

        try:
            if os.path.exists(_tmpdir):
                shutil.rmtree(_tmpdir)
            if os.path.exists(_tmpdir_mysql_mount):
                shutil.rmtree(_tmpdir_mysql_mount)
            os.makedirs(_tmpdir)
            os.makedirs(_tmpdir_mysql_mount)
            esmon_vm = os.path.join(_tmpdir, 'esmon')
            os.makedirs(esmon_vm)

            esm_dirs_to_create = [path + '/' + dir_name for path in
                                  self.c.esm_mount_dirs for dir_name in
                                  self.c.esm_dirs]
            for _dir_to_create in esm_dirs_to_create:
                os.makedirs(_dir_to_create)

            self.c.clean_esm_vm()
            self.assertFalse(os.path.exists(esmon_vm))
            for _dir_deleted in esm_dirs_to_create:
                self.assertFalse(os.path.exists(_dir_deleted))

        finally:
            if os.path.exists(_tmpdir):
                shutil.rmtree(_tmpdir)
            if os.path.exists(_tmpdir_mysql_mount):
                shutil.rmtree(_tmpdir_mysql_mount)

    @patch('deployment_teardown.teardown_san')
    def test_check_clean_san(self, san):
        self.c.clean_san()
        self.assertTrue(san.called)

    @patch('deployment_teardown.exec_process')
    def test_cobbler_distro(self, exec_p):
        self.c.remove_cobbler_distro()
        self.assertTrue(exec_p.called)
        exec_p.side_effect = Exception
        self.assertRaises(SystemExit, self.c.remove_cobbler_distro)

    def test_cobbler_distro_else(self):
        mock_value = cobbler_output
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = 0
            process.communicate.return_value = mock_value
            self.c.remove_cobbler_distro()
            self.assertTrue(mock.called)

    @patch('deployment_teardown.Services.source_nodes')
    @patch('deployment_teardown.LitpRestClient')
    @patch('deployment_teardown.CleanupDeployment._delete_matching_files')
    def test_remove_cobbler_kickstart(self, delete, litp, services):
        services.return_value = ['hostname']
        litp.return_value = False
        self.c.remove_cobbler_kickstart()
        self.assertTrue(delete.called)

    @patch('deployment_teardown.Services.source_nodes')
    @patch('deployment_teardown.CleanupDeployment._delete_matching_files')
    def test_remove_cobbler_snippets(self, delete, services):
        services.return_value = ['hostname']
        self.c.remove_cobbler_snippets()
        self.assertTrue(delete.called)

    @patch('deployment_teardown.delete_file')
    def test_delete_matching_files(self, delete):
        gp_file = join(gettempdir(), 'hostname.ks')
        open(gp_file, 'w').close()
        self.c._delete_matching_files(gettempdir(), 'hostname.ks')
        expected = join(gettempdir(), 'hostname.ks')
        delete.assert_called_with(expected)
        if exists(expected):
            os.remove(expected)

    @patch('deployment_teardown.CleanupDeployment.remove_cobbler_distro')
    @patch('deployment_teardown.CleanupDeployment.remove_cobbler_profile')
    @patch('deployment_teardown.CleanupDeployment.remove_cobbler_system')
    @patch('deployment_teardown.CleanupDeployment.remove_cobbler_kickstart')
    @patch('deployment_teardown.CleanupDeployment.remove_cobbler_snippets')
    def test_clean_cobbler(self, m_sys, pro, dis, kick, snip):
        self.c.clean_cobbler()
        self.assertTrue(m_sys.called)
        self.assertTrue(pro.called)
        self.assertTrue(dis.called)
        self.assertTrue(kick.called)
        self.assertTrue(snip.called)

    @patch('deployment_teardown.exec_process')
    def test_cobbler_system(self, exec_p):
        self.c.remove_cobbler_system()
        self.assertTrue(exec_p.called)
        exec_p.side_effect = Exception
        self.assertRaises(SystemExit, self.c.remove_cobbler_system)

    def test_cobbler_system_else(self):
        mock_value = cobbler_output
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = 0
            process.communicate.return_value = mock_value
            self.c.remove_cobbler_system()
            self.assertTrue(mock.called)

    @patch('deployment_teardown.CleanupDeployment.delete_content')
    @patch('deployment_teardown.CleanupDeployment.write_default_hosts_file')
    def test_clean_lms_hosts_file(self, wdhf, dc):
        test_file = join(gettempdir(), 'test_file')
        content = '''
                    bla bla
                    '''
        self.write_file(test_file, content)
        self.c.clean_lms_hosts_file(test_file)
        self.assertTrue(wdhf.called)
        self.assertTrue(dc.called)

    @patch('deployment_teardown.isfile')
    def test_clean_lms_host_file_exception(self, m_isfile):
        m_isfile.side_effect = [False]
        self.assertRaises(SystemExit, self.c.clean_lms_hosts_file, 'bla')

    def test_delete_content(self):
        test_file = join(gettempdir(), 'test_file')
        content = '''
                    bla bla
                    '''
        self.write_file(test_file, content)
        self.c.delete_content(test_file)
        self.assertTrue(os.stat(test_file).st_size == 0)

    def test_write_default_hosts_file(self):
        test_file = join(gettempdir(), 'test_file')
        self.c.write_default_hosts_file(test_file)
        result = open(test_file).read()
        hostname = socket.gethostname()
        self.assertIn('127.0.0.1 {0} localhost\n'.format(hostname), result)
        self.assertIn('::1 {0} localhost\n'.format(hostname), result)

    @patch('deployment_teardown.exec_process')
    def test_cobbler_profile(self, exec_p):
        self.c.remove_cobbler_profile()
        self.assertTrue(exec_p.called)
        exec_p.side_effect = Exception
        self.assertRaises(SystemExit, self.c.remove_cobbler_profile)

    def test_cobbler_profile_else(self):
        mock_value = cobbler_output
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = 0
            process.communicate.return_value = mock_value
            self.c.remove_cobbler_profile()
            self.assertTrue(mock.called)

    @patch('deployment_teardown.os.remove')
    @patch('deployment_teardown.os.path.isfile')
    def test_clean_known_hosts(self, m_isfile, m_remove):
        m_isfile.side_effect = [True, False]

        self.c.clean_known_hosts()
        self.assertTrue(m_remove.called)

        m_remove.reset_mock()
        self.c.clean_known_hosts()
        self.assertFalse(m_remove.called)

    @patch('deployment_teardown.os.path')
    def test_clean_known_hosts_else(self, mock_path):
        mock_path.isfile.return_value = False
        self.c.clean_known_hosts()

    @patch('deployment_teardown.os.path')
    @patch('deployment_teardown.exec_process')
    def test_clean_lvm_snapshots(self, exec_p, mock_path):
        mock_path.isfile.return_value = True
        exec_p.side_effect = IOError
        self.assertRaises(SystemExit, self.c.clean_lvm_snapshots)

    def test_clean_lvm_snapshots_else(self):
        self.c.clean_lvm_snapshots()

    @patch('deployment_teardown.delete_file')
    def test_clean_enm_version_and_history_info(self, delete_file):
        self.c.clean_enm_version_and_history_info()
        self.assertTrue(delete_file.called)
        self.assertEqual(2, delete_file.call_count)

    @patch('deployment_teardown.shutil')
    @patch('deployment_teardown.os.path.isdir')
    def test_clean_runtime(self, m_isdir, m_shutil):
        m_isdir.side_effect = [True, False]
        m_shutil.rmtree = MagicMock()

        self.c.clean_runtime()
        self.assertTrue(m_shutil.rmtree.called)

        m_shutil.rmtree.reset_mock()
        self.c.clean_runtime()
        self.assertFalse(m_shutil.rmtree.called)

    @patch('deployment_teardown.os.path')
    def test_clean_runtime_else(self, mock_path):
        mock_path.isdir.return_value = False
        self.c.clean_runtime()

    @patch('deployment_teardown.shutil')
    @patch('deployment_teardown.os.path.isdir')
    def test_clean_vm_images(self, m_isdir, m_shutil):
        m_isdir.side_effect = [True, False]
        m_shutil.rmtree = MagicMock()

        self.c.clean_vm_images()
        self.assertTrue(m_shutil.rmtree.called)

        m_shutil.rmtree.reset_mock()
        self.c.clean_vm_images()
        self.assertFalse(m_shutil.rmtree.called)

    @patch('deployment_teardown.os.path')
    def test_clean_vm_images_else(self, mock_path):
        mock_path.isdir.return_value = False
        self.c.clean_vm_images()

    def test_clean_lms_crons(self):
        test_cleanup_corn_file = join(gettempdir(), 'clean_corn_file')
        test_backup_corn_file = join(gettempdir(), 'backup_corn_file')
        self.c.cleanup_cron_file = test_cleanup_corn_file
        self.c.backup_cron_file = test_backup_corn_file
        self.c.clean_lms_crons()
        self.assertFalse(os.path.isfile(test_cleanup_corn_file))
        self.assertFalse(os.path.isfile(test_backup_corn_file))

    @patch('deployment_teardown.CleanupDeployment.clean_esm_vm')
    @patch('deployment_teardown.CleanupDeployment.clean_kvm_ssh_keys')
    @patch('deployment_teardown.CleanupDeployment.clean_model_packages')
    @patch('deployment_teardown.CleanupDeployment.clean_yum_repositories')
    @patch('deployment_teardown.CleanupDeployment.clean_ms_packages')
    @patch('deployment_teardown.CleanupDeployment.clean_ms_rsyslog')
    @patch('deployment_teardown.CleanupDeployment.clean_san')
    @patch('deployment_teardown.CleanupDeployment.clean_nas_servers')
    @patch('deployment_teardown.CleanupDeployment.clean_vm_images')
    @patch('deployment_teardown.CleanupDeployment.'
           'clean_enm_version_and_history_info')
    @patch('deployment_teardown.CleanupDeployment.clean_lvm_snapshots')
    @patch('deployment_teardown.CleanupDeployment.clean_litp')
    @patch('deployment_teardown.CleanupDeployment.is_in_maintenance_mode')
    @patch('deployment_teardown.CleanupDeployment.disable_maintenance_mode')
    @patch('deployment_teardown.CleanupDeployment.clean_cobbler')
    @patch('deployment_teardown.CleanupDeployment.clean_puppet_certs')
    @patch('deployment_teardown.CleanupDeployment.clean_puppet')
    @patch('deployment_teardown.CleanupDeployment.clean_runtime')
    @patch('deployment_teardown.CleanupDeployment.clean_sfs')
    @patch('deployment_teardown.CleanupDeployment.clean_lms_hosts_file')
    @patch('deployment_teardown.CleanupDeployment.clean_lms_crons')
    @patch('deployment_teardown.CleanupDeployment.powerdown_racks')
    @patch('deployment_teardown.CleanupDeployment.clean_consul')
    def test_clean_all(self, cl_consul, pwr_dwn_racks, cron, clhf,
                       sfs, run, pup, cer, cob, dis_m, is_m, lit, lvm, enm_v_h_i,
                       vm, nas, san, addmspkg, mspkg, yumrepo, model_pkg, ssh, esm_vm):
        self.c.clean_all()
        for mk in [cl_consul, pwr_dwn_racks, cron, clhf,
                   sfs, run, pup, cer, cob, dis_m, is_m, lit, lvm, enm_v_h_i,
                   vm, nas, san, addmspkg, mspkg, yumrepo, model_pkg, ssh, esm_vm]:
            self.assertTrue(mk.called)

    @patch('deployment_teardown.CleanupDeployment.clean_esm_vm')
    @patch('deployment_teardown.CleanupDeployment.clean_kvm_ssh_keys')
    @patch('deployment_teardown.CleanupDeployment.clean_model_packages')
    @patch('deployment_teardown.CleanupDeployment.clean_yum_repositories')
    @patch('deployment_teardown.CleanupDeployment.clean_ms_packages')
    @patch('deployment_teardown.CleanupDeployment.clean_ms_rsyslog')
    @patch('deployment_teardown.CleanupDeployment.clean_san')
    @patch('deployment_teardown.CleanupDeployment.clean_nas_servers')
    @patch('deployment_teardown.CleanupDeployment.clean_vm_images')
    @patch('deployment_teardown.CleanupDeployment.'
           'clean_enm_version_and_history_info')
    @patch('deployment_teardown.CleanupDeployment.clean_lvm_snapshots')
    @patch('deployment_teardown.CleanupDeployment.clean_litp')
    @patch('deployment_teardown.CleanupDeployment.is_in_maintenance_mode')
    @patch('deployment_teardown.CleanupDeployment.disable_maintenance_mode')
    @patch('deployment_teardown.CleanupDeployment.clean_cobbler')
    @patch('deployment_teardown.CleanupDeployment.clean_puppet_certs')
    @patch('deployment_teardown.CleanupDeployment.clean_puppet')
    @patch('deployment_teardown.CleanupDeployment.clean_runtime')
    @patch('deployment_teardown.CleanupDeployment.clean_sfs')
    @patch('deployment_teardown.CleanupDeployment.clean_lms_hosts_file')
    @patch('deployment_teardown.CleanupDeployment.clean_lms_crons')
    @patch('deployment_teardown.CleanupDeployment.powerdown_racks')
    @patch('deployment_teardown.CleanupDeployment.clean_consul')
    def test_clean_all_maintenance_mode_true(self, cl_consul, pwr_dwn_racks, cron, clhf,
                       sfs, run, pup, cer, cob, dis_m, is_m, lit, lvm, enm_v_h_i,
                       vm, nas, san, addmspkg, mspkg, yumrepo, model_pkg, ssh, esm_vm):
        is_m.return_value = True
        self.c.clean_all()
        for mk in [cl_consul, pwr_dwn_racks, cron, clhf,
                   sfs, run, pup, cer, cob, dis_m, is_m, lit, lvm, enm_v_h_i,
                   vm, nas, san, addmspkg, mspkg, yumrepo, model_pkg, ssh, esm_vm]:
            self.assertTrue(mk.called)

    @patch('deployment_teardown.CleanupDeployment.clean_esm_vm')
    @patch('deployment_teardown.CleanupDeployment.clean_kvm_ssh_keys')
    @patch('deployment_teardown.CleanupDeployment.clean_model_packages')
    @patch('deployment_teardown.CleanupDeployment.clean_yum_repositories')
    @patch('deployment_teardown.CleanupDeployment.clean_ms_packages')
    @patch('deployment_teardown.CleanupDeployment.clean_ms_rsyslog')
    @patch('deployment_teardown.CleanupDeployment.clean_san')
    @patch('deployment_teardown.CleanupDeployment.clean_nas_servers')
    @patch('deployment_teardown.CleanupDeployment.clean_vm_images')
    @patch('deployment_teardown.CleanupDeployment.'
           'clean_enm_version_and_history_info')
    @patch('deployment_teardown.CleanupDeployment.clean_lvm_snapshots')
    @patch('deployment_teardown.CleanupDeployment.clean_litp')
    @patch('deployment_teardown.CleanupDeployment.is_in_maintenance_mode')
    @patch('deployment_teardown.CleanupDeployment.disable_maintenance_mode')
    @patch('deployment_teardown.CleanupDeployment.clean_cobbler')
    @patch('deployment_teardown.CleanupDeployment.clean_puppet_certs')
    @patch('deployment_teardown.CleanupDeployment.clean_puppet')
    @patch('deployment_teardown.CleanupDeployment.clean_runtime')
    @patch('deployment_teardown.CleanupDeployment.clean_sfs')
    @patch('deployment_teardown.CleanupDeployment.clean_lms_hosts_file')
    @patch('deployment_teardown.CleanupDeployment.clean_lms_crons')
    @patch('deployment_teardown.CleanupDeployment.powerdown_racks')
    @patch('deployment_teardown.CleanupDeployment.clean_consul')
    def test_clean_all_maintenance_mode_false(self, cl_consul, pwr_dwn_racks, cron, clhf,
                       sfs, run, pup, cer, cob, dis_m, is_m, lit, lvm, enm_v_h_i,
                       vm, nas, san, addmspkg, mspkg, yumrepo, model_pkg, ssh, esm_vm):
        is_m.return_value = False
        self.c.clean_all()
        for mk in [cl_consul, pwr_dwn_racks, cron, clhf,
                   sfs, run, pup, cer, cob, is_m, lit, lvm, enm_v_h_i,
                   vm, nas, san, addmspkg, mspkg, yumrepo, model_pkg, ssh, esm_vm]:
            self.assertTrue(mk.called)
        self.assertFalse(dis_m.called)

    def test_function_list(self):
        self.t.function_list()

    @patch('deployment_teardown.init_enminst_logging')
    def test_main_no_args(self, _):
        self.assertRaises(SystemExit, self.t.main, [])

    @patch('deployment_teardown.init_enminst_logging')
    def test_main_one_args(self, _):
        self.assertRaises(SystemExit, self.t.main, ['--sed', self.sed_file])

    @patch('deployment_teardown.init_enminst_logging')
    @patch('deployment_teardown.strong_confirmation_or_exit')
    @patch('deployment_teardown.Sed')
    def test_KeyboardInterrupt_handling(self, m_sed,
                                        m_strong_confirmation_or_exit,
                                        m_init_enminst_logging):
        args = ['--sed', 'sed', '--command', 'clean_testfunction']

        def clean_testfunction(self):
            raise raise_error

        deployment_teardown.CleanupDeployment.clean_testfunction = classmethod(
                clean_testfunction)

        raise_error = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            self.t.main(args)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        raise_error = SystemExit(22)
        with self.assertRaises(SystemExit) as error:
            self.t.main(args)
        self.assertEqual(22, error.exception.code)

        self.assertTrue(m_strong_confirmation_or_exit.called)

    @patch('deployment_teardown.os.path.isdir')
    @patch('deployment_teardown.exec_process')
    def test_clean_puppet_first_except(self, m_exec_process, m_isdir):
        m_exec_process.side_effect = [IOError()]
        self.assertRaises(Exception, self.c.clean_puppet)
        self.assertFalse(m_isdir.called)

    @patch('deployment_teardown.CleanupDeployment.clean_known_hosts')
    @patch('deployment_teardown.shutil')
    @patch('deployment_teardown.os.remove')
    @patch('deployment_teardown.os.path.isdir')
    @patch('deployment_teardown.exec_process')
    def test_clean_puppet_no_except(self, m_exec_process, m_isdir,
                                    m_remove, m_shutil, m_clean_known_hosts):
        m_isdir.return_value = True
        m_shutil.rmtree = MagicMock()
        with patch('deployment_teardown.os.walk') as m_walk:
            m_walk.return_value = [
                ('/foo', ('dir',), ('f1',)),
            ]
            self.c.clean_puppet()
        self.assertEqual(2, m_exec_process.call_count)
        m_remove.assert_called_with(join('/foo', 'f1'))
        m_shutil.rmtree.assert_called_with(join('/foo', 'dir'))
        self.assertTrue(m_clean_known_hosts.called)

    @patch('deployment_teardown.CleanupDeployment.clean_known_hosts')
    @patch('deployment_teardown.shutil')
    @patch('deployment_teardown.os.remove')
    @patch('deployment_teardown.os.path.isdir')
    @patch('deployment_teardown.exec_process')
    def test_clean_puppet_last_except(self, m_exec_process, m_isdir,
                                      m_remove, m_shutil,
                                      m_clean_known_hosts):
        m_isdir.return_value = True
        m_shutil.rmtree = MagicMock()
        m_exec_process.side_effect = [None, IOError()]
        with patch('deployment_teardown.os.walk') as m_walk:
            m_walk.return_value = [
                ('/foo', ('dir',), ('f1',)),
            ]
            self.assertRaises(Exception, self.c.clean_puppet)
        self.assertEqual(2, m_exec_process.call_count)
        m_remove.assert_called_with(join('/foo', 'f1'))
        m_shutil.rmtree.assert_called_with(join('/foo', 'dir'))
        self.assertTrue(m_clean_known_hosts.called)


    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.os.path.isfile')
    def test_clean_consul(self, m_isfile, m_ep):
        m_isfile.side_effect = [True]
        _tmpdir = join(gettempdir(), 'consul_clean')
        if isdir(_tmpdir):
            shutil.rmtree(_tmpdir)
        makedirs(_tmpdir)
        self.c.consul_data_dir = os.path.join(_tmpdir, 'data')
        self.c.consul_config_dir = os.path.join(_tmpdir, 'config')
        makedirs(self.c.consul_config_dir)
        makedirs(self.c.consul_data_dir)
        consul_packages = ['ERICconsulconfig_CXP9033977.noarch']
        command = '/usr/bin/yum remove -y -q'.split()
        command.extend(consul_packages)
        self.c.log = MagicMock()
        self.c.clean_consul()
        m_ep.assert_called_with(command)
        self.assertFalse(exists(self.c.consul_config_dir))
        self.assertFalse(exists(self.c.consul_data_dir))
        self.assertEquals(m_ep.call_count, 2)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.os.path.isfile')
    def test_clean_consul_stop_exception(self, m_isfile, m_ep):
        m_isfile.return_value.exists.return_value = True
        m_ep.side_effect = IOError
        self.assertRaises(Exception, self.c.clean_consul)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.os.path')
    def test_clean_litp(self, mock_path, exec_p):
        mock_path.isdir.return_value = True
        exec_p.side_effect = IOError
        self.assertRaises(Exception, self.c.clean_litp)

    @patch('deployment_teardown.shutil')
    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.os.path')
    def test_clean_litp_stop_exception(self, mock_path, exec_p, shut):
        mock_path.isdir.return_value = True
        exec_p.side_effect = IOError
        self.assertRaises(Exception, self.c.clean_litp)

    @patch('deployment_teardown.shutil')
    @patch('deployment_teardown.os.path.isdir')
    @patch('deployment_teardown.exec_process')
    def test_clean_litp_ok(self, m_exec_process, m_isdir, m_shutil):
        m_isdir.return_value = True
        m_rmtree = MagicMock()
        m_shutil.rmtree = m_rmtree
        self.c.clean_litp()
        self.assertTrue(m_rmtree.called)
        self.assertEqual(3, m_exec_process.call_count)

    @patch('deployment_teardown.exec_process')
    def test_clean_puppet_certs_exception(self, ep):
        c_hostname = gethostname()
        cert_list = ['+ "{0}"  (SHA256) 3B:CA (alt names: '
                     '"DNS:{0}", '
                     '"DNS:{0}.athtem.eei.ericsson.se", '
                     '"DNS:puppet", '
                     '"DNS:puppet.athtem.eei.ericsson.se")'.format(c_hostname),
                     '+ "hostname-1" (SHA256) 00:85',
                     '+ "hostname-2" (SHA256) 5C:9D',
                     '']
        ep.side_effect = ['\n'.join(cert_list), None, None]
        self.c.clean_puppet_certs()
        self.assertEqual(3, len(ep.mock_calls))
        self.assertIn(call(['/usr/bin/puppet', 'cert', 'list', '-all']),
                      ep.mock_calls)
        self.assertIn(call(['/usr/bin/puppet', 'cert', 'clean', 'hostname-1']),
                      ep.mock_calls)
        self.assertIn(call(['/usr/bin/puppet', 'cert', 'clean', 'hostname-2']),
                      ep.mock_calls)

        ep.reset()
        ep.side_effect = [IOError('oops...'), None, None]
        self.assertRaises(SystemExit, self.c.clean_puppet_certs)

        ep.reset()
        ep.side_effect = ['\n'.join(cert_list), IOError('oops...'), None]
        self.assertRaises(SystemExit, self.c.clean_puppet_certs)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient.get_children')
    @patch('paramiko.SSHClient')
    @patch('deployment_teardown.NasConsole.nas_server_destroy')
    def test_clean_nas_servers(self, destroy, ssh, litp, ep):
        self.c.nas_type_sed = 'unityxt'
        litp.side_effect = [self.get_model_sfs_service(),
                            self.get_model_virtual_servers()]
        self.c.log = MagicMock()
        self.c.clean_nas_servers()
        self.assertTrue(destroy.called)
        self.c.log.info.assert_called_with('Removed NAS server vs_enm_2')

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient')
    def test_clean_nas_server_veritas(self, litp, ep):
        self.c.nas_type_sed = 'veritas'
        self.c.clean_nas_servers()
        self.assertFalse(litp.called)

    @patch('deployment_teardown.LitpRestClient')
    def test_clean_nas_server_exclude(self, litp):
        self.c.nas_type_sed = 'unityxt'
        self.c.exclude_nas = 'test_fs'
        self.c.clean_nas_servers()
        self.assertFalse(litp.called)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient')
    def test_clean_nas_servers_warn(self, litp, ep):
        self.c.nas_type_sed = 'unityxt'
        self.c.log = MagicMock()
        litp.return_value.get_children.return_value = list()
        self.c.log = MagicMock()
        self.c.clean_nas_servers()
        self.c.log.warning.assert_called_with('No NAS server found in model!')

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient')
    def test_clean_ms_packages(self, litp, ep):
        litp.return_value.get_children.return_value = self.get_ms_items()
        packages = ['ERICtorutilities_CXP9030570',
                    'ERICddc_CXP9030294',
                    'ERICeniqIntegrationService_CXP9031103']
        command = '/usr/bin/yum remove -y -q'.split()
        command.extend(packages)
        self.c.log = MagicMock()
        self.c.clean_ms_packages()
        ep.assert_called_with(command)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient')
    def test_clean_ms_packages_no_pkg(self, litp, ep):
        litp.return_value.get_children.return_value = list()
        self.c.log = MagicMock()
        self.c.clean_ms_packages()
        self.c.log.info.assert_called_with('No MS RPM packages found in model.'
                                           ' Continue.')

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient')
    def test_clean_ms_packages_exception(self, litp, ep):
        litp.return_value.get_children.return_value = self.get_ms_items()
        packages = ['ERICtorutilities_CXP9030570',
                    'ERICddc_CXP9030294',
                    'ERICeniqIntegrationService_CXP9031103']
        command = '/usr/bin/yum remove -y -q'.split()
        command.extend(packages)
        ep.side_effect = IOError
        self.c.log = MagicMock()
        self.assertRaises(IOError, self.c.clean_ms_packages)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient')
    def test_clean_ms_packages_with_exclude(self, litp, ep):
        litp.return_value.get_children.return_value = self.get_ms_items()
        packages = ['ERICtorutilities_CXP9030570',
                    'ERICeniqIntegrationService_CXP9031103']
        command = '/usr/bin/yum remove -y -q'.split()
        command.extend(packages)
        self.c.log = MagicMock()
        self.c.clean_ms_packages(exclude_packages=['ERICddc_CXP9030294'])
        ep.assert_called_with(command)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient')
    def test_clean_ms_packages_with_exclude_non_existant(self, litp, ep):
        litp.return_value.get_children.return_value = self.get_ms_items()
        packages = ['ERICtorutilities_CXP9030570',
                    'ERICddc_CXP9030294',
                    'ERICeniqIntegrationService_CXP9031103']
        command = '/usr/bin/yum remove -y -q'.split()
        command.extend(packages)
        self.c.log = MagicMock()
        self.c.clean_ms_packages(exclude_packages=['NoSuchPacakge_CXP123456'])
        ep.assert_called_with(command)
        self.c.log.debug.assert_called_with(
                'Package NoSuchPacakge_CXP123456 not found in model.')

    @patch('deployment_teardown.exec_process')
    def test_clean_ms_rsyslog(self, ep):
        packages = ['rsyslog']
        command1 = '/usr/bin/yum install -y -q'.split()
        command1.extend(packages)
        command2 = '/usr/bin/systemctl daemon-reload'.split()
        command3 = '/usr/bin/systemctl restart rsyslog'.split()
        command4 = '/usr/bin/systemctl restart systemd-journald.socket'.split()
        commands = [call(command1), call(command2), call(command3), call(command4)]
        self.c.log = MagicMock()
        self.c.clean_ms_rsyslog()
        ep.assert_has_calls(commands, any_order=False)
        ep.reset_mock()
        ep.side_effect = [IOError]
        self.assertRaises(IOError, self.c.clean_ms_rsyslog)
        self.assertEqual(ep.call_count, 1)
        ep.assert_called_with(command1)
        ep.reset_mock()
        ep.side_effect = [None, Exception]
        self.assertRaises(Exception, self.c.clean_ms_rsyslog)
        self.assertEqual(ep.call_count, 2)
        ep.assert_called_with(command2)
        self.c.log.exception.assert_called_with('An error occurred reloading systemd manager configuration')
        ep.reset_mock()
        ep.side_effect = [None, None, Exception]
        self.assertRaises(Exception, self.c.clean_ms_rsyslog)
        self.assertEqual(ep.call_count, 3)
        ep.assert_called_with(command3)
        self.c.log.exception.assert_called_with('An error occurred restarting service')
        ep.reset_mock()
        ep.side_effect = [None, None, None, Exception]
        self.assertRaises(Exception, self.c.clean_ms_rsyslog)
        self.assertEqual(ep.call_count, 4)
        ep.assert_called_with(command4)
        self.c.log.exception.assert_called_with('An error occurred restarting service')

    @patch('deployment_teardown.exec_process')
    def test_clean_yum_repositories(self, m_exec_process):

        _test_repo, _tmpdir, _updated_repo, _multi_repo = self.setup_repo_files()

        self.c.clean_yum_repositories()

        self.assertFalse(exists(_test_repo))
        self.assertTrue(exists(_updated_repo))
        self.assertTrue(exists(_multi_repo))

        self.assertFalse(exists(join(_tmpdir, 'ENM')))
        self.assertFalse(exists(join(_tmpdir, 'ENM_streaming_rhel7')))
        self.assertTrue(exists(join(_tmpdir, 'UPDATES')))
        self.assertEquals(m_exec_process.call_count, 1)

    def setup_repo_files(self):
        _tmpdir = join(gettempdir(), 'repo_clean')
        if isdir(_tmpdir):
            shutil.rmtree(_tmpdir)
        makedirs(_tmpdir)
        self.c.repo_files = _tmpdir
        self.c.repo_base = _tmpdir
        self.c.enm_repos = '{0}/ENM*'.format(_tmpdir)
        _test_repo = join(_tmpdir, 'test.repo')
        _updated_repo = join(_tmpdir, 'updates.repo')
        _multiple_repo = join(_tmpdir, 'multi_repo.repo')
        _tplate = '\n'.join([
            '[test]',
            'name=test',
            'baseurl=http://ieatlms5225/{0}/'])
        _multi_tplate = '\n'.join([
            '[{0}]',
            'name={0}',
            'baseurl=http://ieatlms5225/{0}/',
            '',
            '[{1}]',
            'name={1}',
            'baseurl=http://ieatlms5225/{1}/'])
        with open(_test_repo, 'w') as _writer:
            _writer.write(_tplate.format('ENM_streaming_rhel7'))
        with open(_updated_repo, 'w') as _writer:
            _writer.write(_tplate.format('6/updates/x86_64/Packages'))
        with open(_multiple_repo, 'w') as _writer:
            _writer.write(_multi_tplate.format('ENM_repo',
                                               'some_other_repo'))
        makedirs(join(_tmpdir, 'ENM'))
        makedirs(join(_tmpdir, 'ENM_streaming_rhel7'))
        makedirs(join(_tmpdir, 'UPDATES'))
        return _test_repo, _tmpdir, _updated_repo, _multiple_repo

    @patch('deployment_teardown.exec_process')
    def test_clean_yum_repositories_no_repos(self, m_exec_process):
        _tmpdir = join(gettempdir(), 'repo_clean')
        if isdir(_tmpdir):
            shutil.rmtree(_tmpdir)
        makedirs(_tmpdir)

        self.c.repo_files = _tmpdir
        self.c.repo_base = _tmpdir
        self.c.enm_repos = '{0}/ENM*'.format(_tmpdir)
        self.c.log = MagicMock()
        self.c.clean_yum_repositories()
        self.c.log.info.assert_called_with('No repositories found to remove.')
        self.assertEquals(m_exec_process.call_count, 0)

    @patch('deployment_teardown.exec_process')
    def test_clean_yum_repositories_exception_in_shutil(self, m_exec_process):
        self.setup_repo_files()
        with patch('shutil.rmtree') as _mock:
            _mock.side_effect = [OSError(2, ''), OSError]
            self.assertRaises(OSError, self.c.clean_yum_repositories)

    @patch('deployment_teardown.exec_process')
    def test_clean_yum_repositories_exception_in_remove(self, m_exec_process):
        self.setup_repo_files()
        with patch('os.remove') as _mock:
            _mock.side_effect = [OSError(2, ''), OSError]
            self.assertRaises(OSError, self.c.clean_yum_repositories)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient.get_children')
    def test_clean_model_packages(self, litp, ep):
        litp.side_effect = [self.get_ms_items(), self.get_model_package(),
                            self.get_model_package_packages()]
        packages = ['ERICsmrsservicemodel_CXP9030970',
                    'ERICsshhandlermodel_CXP9031029']
        command = '/usr/bin/yum remove -y -q'.split()
        command.extend(packages)
        self.c.log = MagicMock()
        self.c.clean_model_packages()
        ep.assert_called_with(command)

    @patch('deployment_teardown.exec_process')
    @patch('deployment_teardown.LitpRestClient.get_children')
    def test_clean_model_packages_no_packages(self, litp, ep):
        litp.side_effect = [list(), list(), list()]

        self.c.log = MagicMock()
        self.c.clean_model_packages()
        self.c.log.info.assert_called_with('No model packages found '
                                           'in LITP model. Continue.')

    @patch('deployment_teardown.os.remove')
    @patch('deployment_teardown.os.path.isfile')
    def test_clean_kvm_ssh_keys(self, m_isfile, m_remove):
        m_isfile.side_effect = [True, False, True]
        self.c.clean_kvm_ssh_keys()
        self.assertEqual(2, m_remove.call_count)

        m_isfile.reset_mock()
        m_remove.reset_mock()
        m_isfile.side_effect = [True, True, True]
        m_remove.side_effect = [IOError, None, None]
        try:
            self.c.clean_kvm_ssh_keys()
            self.assertEqual(3, m_remove.call_count)
        except Exception as error:
            self.fail('No exception should have been raised: {0}'.format(
                    str(error)
            ))

    def get_sw_items(self):
        return [{'path': '/software/items/db_repo',
                 'data': {
                     "id": "db_repo",
                     "item-type-name": "yum-repository",
                     "applied_properties_determinable": True,
                     "state": "Applied",
                     "properties": {
                         "cache_metadata": "false",
                         "ms_url_path": "/ENM_db_rhel7/",
                         "name": "db_repo"
                     }
                 }},
                {'path': '',
                 'data': {
                     "id": "common_repo",
                     "item-type-name": "yum-repository",
                     "applied_properties_determinable": True,
                     "state": "Applied",
                     "properties": {
                         "cache_metadata": "false",
                         "ms_url_path": "/ENM_common_rhel7/",
                         "name": "common_repo"
                     }
                 }}
                ]

    def get_ms_items(self):
        return [
            {'path': '/ms/items/enm_repo',
             'data': {
                 'id': 'enm_repo',
                 'item-type-name': 'reference-to-yum-repository',
                 'applied_properties_determinable': True,
                 'state': 'Applied',
                 'properties': {
                     'cache_metadata': 'false',
                     'ms_url_path': '/CXP9027091_R1F15/',
                     'name': 'enm_repo'
                 }
             }
             },
            {'path': '/ms/items/enm_utilities',
             'data': {
                 'id': 'enm_utilities',
                 'item-type-name': 'reference-to-package',
                 'applied_properties_determinable': True,
                 'state': 'Applied',
                 'properties': {
                     'epoch': '0',
                     'name': 'ERICtorutilities_CXP9030570',
                     'repository': 'enm_repo'
                 }
             }
             },
            {'path': '/ms/items/config_manager',
             'data': {
                 'id': 'config_manager',
                 'item-type-name': 'reference-to-config-manager',
                 'applied_properties_determinable': True,
                 'state': 'Applied',
                 'properties': {
                     'owner': 'root',
                     'global_properties_path': '/ericsson/tor/data',
                     'group': 'root',
                     'mode': '0644'
                 }
             }
             },
            {'path': '/ms/items/ntp_service',
             'data': {
                 'item-type-name': 'reference-to-ntp-service',
                 'applied_properties_determinable': True,
                 'state': 'Applied',
                 'id': 'ntp_service'
             }
             },
            {'path': '/ms/items/ddc_package',
             'data': {
                 'id': 'ddc_package',
                 'item-type-name': 'reference-to-package',
                 'applied_properties_determinable': True,
                 'state': 'Applied',
                 'properties': {
                     'epoch': '0',
                     'name': 'ERICddc_CXP9030294',
                     'repository': 'enm_repo'
                 }
             }
             },
            {'path': '/ms/items/3pp',
             'data': {
                 'id': '3pp',
                 'item-type-name': 'reference-to-yum-repository',
                 'applied_properties_determinable': True,
                 'state': 'Applied',
                 'properties': {
                     'cache_metadata': 'false',
                     'ms_url_path': '/3pp_rhel7/',
                     'name': '3pp'
                 }
             }
             },
            {'path': '/ms/items/enm_eniq_integration',
             'data': {
                 'id': 'enm_eniq_integration',
                 'item-type-name': 'reference-to-package',
                 'applied_properties_determinable': True,
                 'state': 'Applied',
                 'properties': {
                     'epoch': '0',
                     'name': 'ERICeniqIntegrationService_CXP9031103',
                     'repository': 'enm_repo'
                 }
             },
             },
            {'path': '/ms/items/model_package',
             'data': {
                 'id': 'model_package',
                 'item-type-name': 'reference-to-package-list',
                 'applied_properties_determinable': True,
                 'state': 'Applied',
                 'properties': {'name': 'models'}
             }
             }
        ]

    def get_model_package(self):
        return [{'path': '/ms/items/model_package/packages',
                 'data': {
                     'item-type-name': 'reference-to-collection-of-package',
                     'applied_properties_determinable': True,
                     'state': 'Applied',
                     'id': 'packages'}
                 }]

    def get_model_package_packages(self):
        return [{'path': '/ms/items/model_package/packages/model_68',
                 'data': {
                     'id': 'model_68',
                     'item-type-name': 'reference-to-model-package',
                     'applied_properties_determinable': True,
                     'state': 'Applied',
                     'properties': {
                         'epoch': '0',
                         'name': 'ERICsmrsservicemodel_CXP9030970'}
                 }
                 },
                {'path': '/ms/items/model_package/packages/model_69',
                 'data': {
                     'id': 'model_69',
                     'item-type-name': 'reference-to-model-package',
                     'applied_properties_determinable': True,
                     'state': 'Applied',
                     'properties': {
                         'epoch': '0',
                         'name': 'ERICsshhandlermodel_CXP9031029'}
                 }}]

    def get_model_sfs_service(self):
        return[
            {'path': '/infrastructure/storage/storage_providers/unityxt',
             'data': {'id': 'unityxt', 'item-type-name': 'sfs-service',
                      'properties': {'management_ipv4': '10.140.1.29',
                                     'nas_type': 'unityxt', 'user_name': 'support',
                                     'password_key': 'key-for-sfs'}}}]

    def get_model_virtual_servers(self):
        return [{'path': '/infrastructure/storage/storage_providers/unityxt/'
                 'virtual_servers/virtual_server_enm_1',
                 'data': {
                     'item-type-name': 'sfs-virtual-server',
                     'state': 'Applied',
                     'properties': {
                         'ipv4address': '10.150.82.18',
                          'name': 'vs_enm_1'}
                 }
                 },
                {'path': '/infrastructure/storage/storage_providers/unityxt/'
                         'virtual_servers/virtual_server_enm_2',
                 'data': {
                     'item-type-name': 'sfs-virtual-server',
                     'state': 'Applied',
                     'properties': {
                         'ipv4address': '10.150.82.19',
                          'name': 'vs_enm_2'}

                 }}]

    def test_get_node_ilo_info_p(self):
        mock_sed_data = {"svc_node1_iloUsername": "root",
                         "svc_node1_iloPassword": "shroot12",
                         "svc_node1_ilo_IP": "10.151.33.217"}
        dt_object = deployment_teardown.CleanupDeployment(self.sed_file)
        dt_object.sed.clear()
        dt_object.sed.update(mock_sed_data)
        node_ilo_info = dt_object.get_node_ilo_info()
        self.assertEqual(node_ilo_info, {"svc_node1": ["10.151.33.217",
                                                       "root",
                                                       "shroot12"]})

    def test_get_node_ilo_info_n(self):
        mock_sed_data = {"svc_node1_iloUsername": "",
                         "svc_node1_iloPassword": "shroot12",
                         "svc_node1_ilo_IP": "10.151.33.217"}
        dt_object = deployment_teardown.CleanupDeployment(self.sed_file)
        dt_object.sed.clear()
        dt_object.sed.update(mock_sed_data)
        node_ilo_info = dt_object.get_node_ilo_info()
        self.assertEqual(node_ilo_info, {})

    @patch('h_util.h_utils.LOG')
    @patch('h_util.h_utils.Redfishtool.login')
    @patch('redfish.rest.v1.HttpClient')
    def test_check_if_nodes_finished_post_y(self, mock_redfish, login_mock, mock_log):
        mock_sed_data = {"svc_node1": ["10.151.33.217", "root", "shroot12"]}
        dt_object = deployment_teardown.CleanupDeployment(self.sed_file)
        mocked_response = self. \
            get_mock_response(200, 'success_response')
        mock_redfish.post.return_value = mocked_response
        login_mock.return_value = mock_redfish
        json_data = {"Oem": {"Hpe": {"PostState": "FinishedPost"}}, "PowerState": "On"}
        mock_http = MagicMock()
        mock_http.status = 200
        mock_http.text = json.dumps(json_data)
        mock_redfish.get.return_value = mock_http
        finished = dt_object.check_if_nodes_finished_post(mock_sed_data)
        self.assertEqual(finished, True)
        json_data = {"Oem": {"Hp": {"PostState": "FinishedPost"}}, "PowerState": "On"}
        mock_http.text = json.dumps(json_data)
        finished = dt_object.check_if_nodes_finished_post(mock_sed_data)
        self.assertEqual(finished, True)

    @patch('h_util.h_utils.LOG')
    @patch('h_util.h_utils.Redfishtool.login')
    @patch('redfish.rest.v1.HttpClient')
    def test_check_if_nodes_finished_post_n(self, mock_redfish, login_mock, mock_log):
        mock_sed_data = {"svc_node1": ["10.151.33.217", "root", "shroot12"]}
        dt_object = deployment_teardown.CleanupDeployment(self.sed_file)
        mocked_response = self. \
            get_mock_response(200, 'success_response')
        mock_redfish.post.return_value = mocked_response
        login_mock.return_value = mock_redfish
        json_data = {"Oem": {"Hpe": {"PostState": "InPost"}}, "PowerState": "On"}
        mock_http = MagicMock()
        mock_http.status = 200
        mock_http.text = json.dumps(json_data)
        mock_redfish.get.return_value = mock_http
        finished = dt_object.check_if_nodes_finished_post(mock_sed_data)
        self.assertEqual(finished, False)
        json_data = {"Oem": {"Hp": {"PostState": "InPost"}}, "PowerState": "On"}
        mock_http.text = json.dumps(json_data)
        finished = dt_object.check_if_nodes_finished_post(mock_sed_data)
        self.assertEqual(finished, False)

    @patch('deployment_teardown.CleanupDeployment.poweron_nodes')
    @patch('deployment_teardown.CleanupDeployment.get_node_ilo_info')
    def test_poweron_nodes(self, get_node_ilo_info, poweron_nodes):
        get_node_ilo_info.return_value = {"svc_node1": ["10.151.33.217",
                                                        "root", "shroot12"]}
        poweron_nodes.return_value = True
        dt_object = deployment_teardown.CleanupDeployment(self.sed_file)
        dt_object.poweron_nodes()

    @patch('deployment_teardown.CleanupDeployment.'
           'check_if_nodes_finished_post')
    @patch('deployment_teardown.CleanupDeployment.poweron_nodes')
    @patch('deployment_teardown.CleanupDeployment.get_node_ilo_info')
    def test_poweron_nodes_with_a_node_off(self, get_node_ilo_info,
                                           poweron_nodes, finished_post):
        get_node_ilo_info.return_value = {"svc_node1": ["10.151.33.217",
                                                        "root", "shroot12"]}
        poweron_nodes.return_value = False
        finished_post.return_value = True
        dt_object = deployment_teardown.CleanupDeployment(self.sed_file)
        dt_object.poweron_nodes()

    @patch('deployment_teardown.poweron_node')
    @patch('deployment_teardown.CleanupDeployment.get_node_ilo_info')
    def test_poweron_nodes_a_node_fails_to_poweron(self, get_node_ilo_info,
                                                   poweron_node):
        with self.assertRaises(SystemExit) as excep:
            get_node_ilo_info.return_value =\
                {"svc_node1": ["10.151.33.217", "root", "shroot12"]}
            poweron_node.side_effect = SystemExit()
            dt_object = deployment_teardown.CleanupDeployment(self.sed_file)
            dt_object.poweron_nodes()
            self.assertEqual(excep.exception.code, 1)

    @staticmethod
    def read_data(filename):
        """
        open the file and reads data from
        the path specified in the arguments
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))
        path = os.path.join(os.path.join(parent_dir, 'Resources'), filename)
        with open(path, 'r') as f:
            return f.read()

    def get_mock_response(self, response_status, resource_text):
        """
        set the response with the provided arguments
        and return mocked response
        """
        response = MagicMock()
        response.status = response_status
        response.text = self.read_data(resource_text)
        if resource_text in ['invalid_parameter_response',
                             'response_with_error_message']:
            response.dict = json.loads(response.text)
        return response

    @patch('clean_san_luns.get_nas_type')
    @patch('h_util.h_utils.LOG')
    @patch('h_util.h_utils.Redfishtool.login')
    @patch('clean_san_luns.LitpRestClient')
    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('redfish.rest.v1.HttpClient')
    @patch('clean_san_luns.BasePluginApi')
    def test_powerdown_racks_model_applied(self, p_base_api, mock_redfish,
                                           m_lvm_litp, m_san_litp, login_mock, log_mock,
                                           m_get_nas_type):
        # Given a deployment that have some clusters using lun storage and
        # some clusters using local lvm storage (racks servers). State of the
        # model all items applied
        time.sleep = MagicMock()
        p_base_api.return_value.get_password.return_value = 'some_password'
        litpd = LitpIntegration()
        litpd.setup_svc_cluster()
        litpd.setup_str_cluster_multiple_nodes(['str-1'], state=LitpRestClient.
                                               ITEM_STATE_APPLIED)

        m_lvm_litp.return_value = litpd
        m_san_litp.return_value = litpd
        m_get_nas_type.return_value = ''

        mocked_response = self. \
            get_mock_response(200, 'success_response')
        mock_redfish.post.return_value = mocked_response
        login_mock.return_value = mock_redfish
        mock_redfish.get.return_value = self. \
            get_mock_response(200, 'power_status_success_response')

        # When the powerdown racks  is called
        self.c.powerdown_racks()

        # Then only rack server in the deployment should be powered off,
        # regardless of their state in the litp model. (Applied/Initial/Updated)
        log_mock.debug.assert_called_with("._toggle_power: Power ForceOff Outcome: Success")

    @patch('clean_san_luns.get_nas_type')
    @patch('h_util.h_utils.LOG')
    @patch('h_util.h_utils.Redfishtool.login')
    @patch('clean_san_luns.LitpRestClient')
    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('redfish.rest.v1.HttpClient')
    @patch('clean_san_luns.BasePluginApi')
    def test_powerdown_racks_model_initial(self, p_base_api, mock_redfish,
                                           m_lvm_litp, m_san_litp, login_mock, log_mock,
                                           m_get_nas_type):
        # Given a deployment that have some clusters using lun storage and
        # some clusters using local lvm storage (racks servers). State of the
        # model all items initial
        time.sleep = MagicMock()
        p_base_api.return_value.get_password.return_value = 'some_password'
        litpd = LitpIntegration()
        litpd.setup_svc_cluster()
        litpd.setup_str_cluster_multiple_nodes(['str-1'], state=LitpRestClient.
                                               ITEM_STATE_INITIAL)
        m_lvm_litp.return_value = litpd
        m_san_litp.return_value = litpd
        m_get_nas_type.return_value = ''

        mocked_response = self. \
            get_mock_response(200, 'success_response')
        mock_redfish.post.return_value = mocked_response
        login_mock.return_value = mock_redfish
        mock_redfish.get.return_value = self. \
            get_mock_response(200, 'power_status_success_response')

        # When the powerdown racks  is called
        self.c.powerdown_racks()

        # Then only rack server in the deployment should be powered off,
        # regardless of their state in the litp model. (Applied/Initial/Updated)

        log_mock.debug.assert_called_with("._toggle_power: Power ForceOff Outcome: Success")


if __name__ == '__main__':
    unittest2.main()

