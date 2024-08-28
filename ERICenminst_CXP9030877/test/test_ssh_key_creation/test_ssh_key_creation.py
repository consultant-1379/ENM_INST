import os
import shutil
import sys

import unittest2
from mock import patch, MagicMock, call

from h_litp.litp_rest_client import LitpException
from litpd import LitpIntegration

__patched_m2crypto = MagicMock()

sys.modules['M2Crypto'] = __patched_m2crypto
sys.modules['pwd'] = MagicMock()

from os import makedirs
from tempfile import gettempdir
from os.path import join, exists
import ssh_key_creation

working = '''
jboss_image=ERICrhel79jbossimage_CXP9041916-1.9.1.qcow2
vm_ssh_key=vm_private_key.pub
uuid_appvg_DB2=6006016028503200EE87EF774281E411
'''

Empty_Working = '''
vm_ssh_key=

'''

cfg = '''
vm_ssh_key=ssh-rsa blah
'''


class TestSshCreation(unittest2.TestCase):
    def __init__(self, method_name='runTest'):
        super(TestSshCreation, self).__init__(method_name)
        self.tmpdir = join(gettempdir(), 'TestSshKeyCreation')

    def setUp(self):
        """
        Construct a model, sufficient for test cases
        that you wish to implement in this suite.
        """
        self.tempdir = join(gettempdir(), 'cat/.ssh/')
        if not exists(self.tempdir):
            makedirs(self.tempdir)
        self.public_key = join(self.tempdir, 'vm_private_key.pub')
        ssh_key_creation.SshCreation.PUBLIC_KEY_FILE = self.public_key
        self.cfg_file = join(self.tempdir, 'enminst.cfg')
        self.write_file(self.cfg_file, working)

    def tearDown(self):
        if exists(self.tempdir):
            try:
                shutil.rmtree(self.tempdir)
            except OSError:
                pass

    def write_file(self, location, contents):
        with open(location, 'w') as _file:
            _file.writelines(contents)

    @patch('ssh_key_creation.SshCreation.get_ssh_key_value')
    def test_update_enminst_working(self, get_ssh_key):
        ssh = ssh_key_creation.SshCreation()
        get_ssh_key.return_value = 'vm_private_key.pub'
        ssh.update_enminst_working('empty_file.txt')
        self.assertIn(get_ssh_key.return_value,
                      open('empty_file.txt').read())
        ssh.update_enminst_working('missing_file.txt')
        self.assertTrue(os.path.exists('missing_file.txt'))
        ssh.update_enminst_working('existing_ssh_file.txt')
        self.assertIn(get_ssh_key.return_value,
                      open('existing_ssh_file.txt').read())
        if os.path.isfile('existing_ssh_file.txt'):
            os.remove('existing_ssh_file.txt')
        if os.path.isfile('empty_file.txt'):
            os.remove('empty_file.txt')
        if os.path.isfile('missing_file.txt'):
            os.remove('missing_file.txt')

    @patch('ssh_key_creation.os.chmod')
    @patch('ssh_key_creation.b64encode')
    @patch('ssh_key_creation.RSA.gen_key')
    @patch('ssh_key_creation.os.path.isdir')
    def test_get_ssh_key_value(self, direct, gen_key, b64, chmod):
        ssh = ssh_key_creation.SshCreation()
        direct.return_value = True
        ssh.get_ssh_key_value()
        self.assertTrue(gen_key.called)
        self.assertTrue(b64.called)
        self.assertTrue(chmod.called)

    @patch('ssh_key_creation.os.chmod')
    @patch('ssh_key_creation.b64encode')
    @patch('ssh_key_creation.RSA.gen_key')
    @patch('ssh_key_creation.os.mkdir')
    @patch('ssh_key_creation.os.path.isdir')
    def test_get_ssh_key_value_mkdirs(self, direct, makedir, gen_key, b64,
                                      chmod):
        ssh = ssh_key_creation.SshCreation()
        direct.return_value = False
        ssh.get_ssh_key_value()
        self.assertTrue(makedir.called)
        self.assertTrue(chmod.called)
        ssh.SSH_PATH = self.tempdir
        self.assertTrue(gen_key.called)
        self.assertTrue(b64.called)
        self.assertTrue(chmod.called)

    @patch('ssh_key_creation.RSA.gen_key')
    def test_get_ssh_key_value_OSError(self, gen):
        ssh = ssh_key_creation.SshCreation()
        ssh.SSH_PATH = self.tempdir
        gen.side_effect = OSError(2, "")
        self.assertRaises(SystemExit, ssh.get_ssh_key_value)

    @patch('ssh_key_creation.os.mkdir')
    @patch('ssh_key_creation.os.path.isdir')
    def test_get_ssh_key_value_OSError_no1(self, direct, makedir):
        ssh = ssh_key_creation.SshCreation()
        direct.return_value = False
        makedir.side_effect = OSError(2, "")
        self.assertRaises(SystemExit, ssh.get_ssh_key_value)

    @patch('ssh_key_creation.SshCreation.collect_all_vm_service_paths')
    @patch('ssh_key_creation.read_enminst_config')
    @patch('ssh_key_creation.SshCreation.update_enminst_working')
    @patch('ssh_key_creation.SshCreation.regenerate_keys')
    def test_manage_ssh_action(self, gen, enminst_w, config, path):
        ssh = ssh_key_creation.SshCreation()
        enminst_w.side_effect = 'key'
        path.return_value = ['path']
        ssh.manage_ssh_action('regenerate')
        self.assertTrue(gen.called)
        self.assertTrue(config.called)

    @patch('ssh_key_creation.SshCreation.collect_all_vm_service_paths')
    @patch('ssh_key_creation.read_enminst_config')
    @patch('ssh_key_creation.SshCreation.update_enminst_working')
    @patch('ssh_key_creation.SshCreation.regenerate_keys')
    def test_manage_ssh_action_no_plan(self, gen, enminst_w, config,
                                       path):
        ssh = ssh_key_creation.SshCreation()
        enminst_w.side_effect = 'key'
        #path.side_effect = ['path']
        path.return_value = ['path']
        ssh.manage_ssh_action(True, True)
        self.assertTrue(gen.called)
        self.assertTrue(config.called)

    @patch('ssh_key_creation.SshCreation.collect_all_vm_service_paths')
    @patch('ssh_key_creation.SshCreation.update_enminst_working')
    @patch('ssh_key_creation.SshCreation.regenerate_keys')
    def test_manage_ssh_action_if_else(self, geb, enminst, path):
        ssh = ssh_key_creation.SshCreation()
        path.return_value = ['']
        ssh.manage_ssh_action('regenerate')
        self.assertTrue(path.called)

    @patch('ssh_key_creation.read_enminst_config')
    @patch('ssh_key_creation.SshCreation.update_enminst_working')
    @patch('ssh_key_creation.SshCreation.check_enminst_working')
    def test_manage_ssh_action_else(self, check, enminst_w, config):
        ssh = ssh_key_creation.SshCreation()
        check.return_value = False
        ssh.manage_ssh_action()
        self.assertTrue(enminst_w.called)
        self.assertTrue(config.called)

    def test_check_enminst_working(self):
        ssh = ssh_key_creation.SshCreation()
        param_file = join(self.tempdir, 'vm_private_key')
        with open(param_file, 'w+') as _fp:
            _fp.write('vm_ssh_key0000=123\n')
        self.assertFalse(ssh.check_enminst_working(param_file))

        with open(param_file, 'w+') as _fp:
            _fp.write('vm_ssh_key=123\n')
        has_key = ssh.check_enminst_working(param_file)
        self.assertTrue(has_key)

    def test_sshkey_to_file(self):
        param_file = join(self.tempdir, 'vm_private_key')
        with open(param_file, 'w+') as _fp:
            _fp.write('vm_ssh_key=ssh-rsa 111111\n')
        ssh = ssh_key_creation.SshCreation()
        has_key = ssh.check_enminst_working(param_file)
        self.assertTrue(has_key)
        match_found = False
        with open(param_file, 'r') as _reader:
            for newline in _reader.readlines():
                if newline.startswith('vm_ssh_key=file://'):
                    match_found = True
                    break
        self.assertTrue(match_found, 'No file:// entry found for vm_ssh_key')

    def test_check_enminst_working_mock_working(self):
        ssh = ssh_key_creation.SshCreation()
        param_file = self.cfg_file
        with open(self.cfg_file, 'w+') as _fp:
            _fp.write(working)
        self.assertTrue(ssh.check_enminst_working(param_file))

    def test_check_enminst_working_mock_EmptyWorking(self):
        ssh = ssh_key_creation.SshCreation()
        param_file = self.cfg_file
        with open(self.cfg_file, 'w+') as _fp:
            _fp.write(Empty_Working)
        self.assertTrue(ssh.check_enminst_working(param_file))

    def test_check_enminst_working_mock_cfg(self):
        ssh = ssh_key_creation.SshCreation()
        param_file = self.cfg_file
        with open(self.cfg_file, 'w+') as _fp:
            _fp.write(cfg)
        self.assertTrue(ssh.check_enminst_working(param_file))

    @patch('ssh_key_creation.SshCreation.check_enminst_working')
    @patch('ssh_key_creation.SshCreation.regenerate_keys')
    @patch('ssh_key_creation.SshCreation.update_enminst_working')
    @patch('ssh_key_creation.SshCreation.collect_all_vm_service_paths')
    def test_main_with_two_args(self, path, m_update, m_regen, m_check):
        ssh_key_creation.main(['', '--regenerate'])
        self.assertTrue(path.called)
        self.assertTrue(m_update.called)
        self.assertTrue(m_regen.called)

        m_update.reset_mock()
        m_check.side_effect = [True]
        ssh_key_creation.main([''])
        self.assertFalse(m_update.called)

        m_update.reset_mock()
        m_check.side_effect = [False]
        ssh_key_creation.main([''])
        self.assertTrue(m_update.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.monitor_plan')
    @patch('h_litp.litp_rest_client.LitpRestClient.set_plan_state')
    @patch('h_litp.litp_rest_client.LitpRestClient.create_plan')
    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    def test_regenerate_keys(self, update, create, m_set, monitor):
        ssh = ssh_key_creation.SshCreation()
        ssh.regenerate_keys(pubkey='123', list_of_paths=['path', 'loc'])
        self.assertTrue(update.called)
        self.assertTrue(create.called)
        self.assertTrue(m_set.called)
        self.assertTrue(monitor.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    def test_regenerate_keys_no_plan(self, update):
        ssh = ssh_key_creation.SshCreation()
        ssh.regenerate_keys(pubkey='123', list_of_paths=['path', 'loc'],
                            no_litp_plan=True)
        self.assertTrue(update.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    def test_regenerate_keys_Exception(self, update):
        ssh = ssh_key_creation.SshCreation()
        update.side_effect = LitpException
        self.assertRaises(SystemExit, ssh.regenerate_keys, pubkey='123',
                          list_of_paths=['path'])

    @patch('h_litp.litp_rest_client.LitpRestClient.monitor_plan')
    @patch('h_litp.litp_rest_client.LitpRestClient.set_plan_state')
    @patch('h_litp.litp_rest_client.LitpRestClient.create_plan')
    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    def test_regenerate_keys_SysError(self, update, create, m_set, monitor):
        ssh = ssh_key_creation.SshCreation()
        ssh.regenerate_keys(pubkey='123', list_of_paths=['path', 'loc'])
        self.assertTrue(update.called)
        self.assertTrue(create.called)
        self.assertTrue(m_set.called)
        monitor.side_effect = LitpException
        self.assertRaises(SystemExit, ssh.regenerate_keys, pubkey='123',
                          list_of_paths=['path'])

    @patch('ssh_key_creation.SshCreation.update_enminst_working')
    def test_collect_all_vm_service_paths(self, m_update_enminst_working):
        expected_value = 'regenerated_ssh_key'
        m_update_enminst_working.return_value = expected_value
        litpd = LitpIntegration()
        litpd.setup_svc_cluster()

        def create_vm(vm_path, ssh_key):
            litpd.create_item(vm_path, 'vm-service')
            litpd.create_item(vm_path + '/vm_ssh_keys', 'vm-service')
            litpd.create_item(vm_path + '/vm_ssh_keys/vm-ssh-key',
                              'vm-ssh-key', {'ssh_key': ssh_key})

        esmon = '/ms/services/esmon'
        said = '/software/services/said'

        create_vm(esmon, 'invalid_ssh_key')
        create_vm(said, 'invalid_ssh_key')

        m_update = MagicMock()
        litpd.update = m_update

        with patch('ssh_key_creation.LitpRestClient') as _mock:
            _mock.return_value = litpd
            test_ssh = ssh_key_creation.SshCreation()

            test_ssh.manage_ssh_action(regenerate=True, no_litp_plan=True)

        m_update.assert_has_calls([
            call(said + '/vm_ssh_keys/vm-ssh-key',
                 {'ssh_key': expected_value}, verbose=False),
            call(esmon + '/vm_ssh_keys/vm-ssh-key',
                 {'ssh_key': expected_value}, verbose=False)
        ], any_order=True)


if __name__ == '__main__':
    unittest2.main()
