from os.path import join, abspath, exists
import logging
import os

from tempfile import mkstemp

from mock import patch, MagicMock

from unittest2 import TestCase

from encrypt_passwords import EncryptPassword, main, create_parser
from h_litp.litp_utils import main_exceptions
from h_util.h_utils import exec_process_via_pipes, ExitCodes
from h_litp.litp_rest_client import LitpException

current_path = os.path.dirname(__file__)
log = logging.getLogger()

log.setLevel('INFO')

EXAMPLE_PROPERTY_NAME = 'openidm_admin_password'
EXAMPLE_CLEAR_TEXT_PASSWORD = 'OpenidmAdm01PasswordToFind32Char'
EXAMPLE_PASSKEY_PASSWORD = '+RAojat/6ddOyCePpE6Ejg=='

prop_dictionary = \
    {'property_openidm_admin_password': 'encrypted_openidm_value',
     'property_com_inf_ldap_amin_access': 'encrypted_com_inf_ldap_value',
     'property_ldap_amin_password': 'encrypted_ldap_amin_value',
     'property_postgresql01_admin_password': 'encrypted_postgresql01_value',
     'property_default_security_admin_password': 'encrypted_security_value',
     'property_neo4j_admin_user_password': 'encrypted_admin_user_value',
     'property_neo4j_dps_user_password': 'encrypted_dps_user_value',
     'property_neo4j_reader_user_password': 'encrypted_reader_value',
     'property_neo4j_ddc_user_password': 'encrypted_ddc_user_value'
     }

litp_get_value = {'properties': {'key': 'property_openidm_admin_password',
                                    'value': 'encrypted_password'}}

passwords_dictionary = \
    {'openidm_admin_password': 'encrypted_openidm_value',
     'com_inf_ldap_admin_access': 'encrypted_com_inf_ldap_value',
     'ldap_admin_password': 'encrypted_ldap_amin_value',
     'postgresql01_admin_password': 'encrypted_postgresql01_value',
     'default_security_admin_password': 'encrypted_security_value',
     'neo4j_admin_user_password': 'encrypted_admin_user_value',
     'neo4j_dps_user_password': 'encrypted_dps_user_value',
     'neo4j_reader_user_password': 'encrypted_reader_value',
     'neo4j_ddc_user_password': 'encrypted_ddc_user_value'
     }

class TestEncryptPassword(TestCase):
    def setUp(self):

        self.sed_filename = os.path.join(current_path, 'data/sed.txt')

        tdir = abspath(join(current_path, '../../target'))
        if not exists(tdir):
            os.makedirs(tdir)

        (_, self.password_store_filename) = mkstemp(dir=tdir)

        log.info(self.password_store_filename)
        self.password_value_dict = {}
        self.encrypt_password = EncryptPassword(self.sed_filename,
                                                self.password_store_filename,
                                                upgrade=False,
                                                verbose=True)

    def tearDown(self):
        try:
            os.remove(self.password_store_filename)
        except OSError:
            pass

    @patch('encrypt_passwords.exec_process_via_pipes')
    @patch('os.path.isfile')
    @patch('encrypt_passwords.EncryptPassword.write_timestamp_file')
    def test_encrypt(self, ep, m_isfile, m_time):
        ep.return_value = 'encrytped_text!'
        m_isfile.return_value = True
        m_time.return_value = '1696420490.21'

        self.encrypt_password.encrypt_passwords()

        self.assertEquals(10,
                          self.check_output_file(self.password_store_filename))

    def check_output_file(self, filename):
        with open(filename, 'r') as output:
            lines = output.readlines()
            for line in lines:
                log.info(line)
            return len(lines)

    def test_encrypt_clear_text_password(self):

        log.info('clear_password         \'%s\'', EXAMPLE_CLEAR_TEXT_PASSWORD)
        encrypted_password = self.encrypt_password.encrypt_clear_text_password(
            EXAMPLE_PROPERTY_NAME,
            EXAMPLE_CLEAR_TEXT_PASSWORD,
            EXAMPLE_PASSKEY_PASSWORD)
        log.info('encrypted_password     \'%s\'', encrypted_password)
        self.assertTrue(encrypted_password)
        self.assertNotIn('\n', encrypted_password)
        log.info('fixed password(salted) \'%s\'',
                 'U2FsdGVkX18z3w3cKK7iRm74W1o9wlXnM2voU7oYytY=')
        decrypted_password = self.decrypt_password(encrypted_password,
                                                   EXAMPLE_PASSKEY_PASSWORD)
        log.info('decrypted_password     \'%s\'', decrypted_password)

        self.assertEquals(EXAMPLE_CLEAR_TEXT_PASSWORD, decrypted_password)

    def decrypt_password(self, encrypted_password, passkey_password):
        echo_command = "echo %s " % encrypted_password
        echo_command_parts = echo_command.split()

        openssl_command = \
            "/usr/bin/openssl enc -d -aes-128-cbc -a -salt -k %s" \
            % passkey_password
        openssl_command_parts = openssl_command.split()

        try:
            output = \
                exec_process_via_pipes(echo_command_parts,
                                       openssl_command_parts)
            decrypted_password = output.strip()
            return decrypted_password
        except Exception as ex:
            raise SystemExit(ex)

    @patch('encrypt_passwords.exec_process_via_pipes')
    def test_encrypt_clear_text_password_fail(self, exec_proc_via_pipes):

        exec_proc_via_pipes.side_effect = IOError('process failed')

        self.assertRaises(SystemExit, self.encrypt_password.encrypt_clear_text_password, EXAMPLE_PROPERTY_NAME,
                          EXAMPLE_CLEAR_TEXT_PASSWORD, EXAMPLE_PASSKEY_PASSWORD)

    @patch('encrypt_passwords.exec_process_via_pipes')
    def test_encrypt_clear_text_password_fail_generated_empty(self, exec_proc_via_pipes):

        exec_proc_via_pipes.return_value = ""

        self.assertRaises(SystemExit, self.encrypt_password.encrypt_clear_text_password, EXAMPLE_PROPERTY_NAME,
                          EXAMPLE_CLEAR_TEXT_PASSWORD, EXAMPLE_PASSKEY_PASSWORD)

    def test_create_parser(self):
        parser = create_parser()
        self.assertTrue(parser)

    def test_main_help(self):
        args = ['encrypt_passwords.py', '-h']
        self.assertRaises(SystemExit, main, args)

    @patch('encrypt_passwords.EncryptPassword.write_timestamp_file')
    def test_main(self, m_time,):
        args = ['encrypt_passwords.py', '--sed', self.sed_filename, '--passwords_store', self.password_store_filename]
        main(args)
        self.assertEquals(10, self.check_output_file(self.password_store_filename))

    @patch('encrypt_passwords.ArgumentParser')
    @patch('encrypt_passwords.encrypt')
    def test_KeyboardInterrupt_handling(self, m_encrypt, ap):
        m_encrypt.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main_exceptions(main, [])
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        m_encrypt.reset_mock()
        m_encrypt.side_effect = IOError()
        self.assertRaises(IOError, main_exceptions, main, [])

    def test_get_md5digest(self):
        self.assertEqual('7872fee3f1608ff1520679bda3333202',
                         self.encrypt_password.get_md5digest('host_mac_ip_datetime'))

    def test_gen_timestamp_filename(self):
        expected_filename = '/root/d4976ffc8db96caf98c4907ff0d3451a'
        self.assertEqual(expected_filename,
                         self.encrypt_password.gen_timestamp_filename('host', 'mac', 'ip'))

    def test_get_passkey_prefix(self):
        self.assertEqual('a_b_c_d_',
                         self.encrypt_password.gen_passkey_prefix('a', 'b', 'c', 'd'))

    @patch('encrypt_passwords.EncryptPassword.get_hostname')
    @patch('encrypt_passwords.EncryptPassword.get_mac_address')
    @patch('encrypt_passwords.EncryptPassword.get_host_ipaddress')
    @patch('encrypt_passwords.EncryptPassword.gen_timestamp_filename')
    @patch('os.path.exists')
    @patch('__builtin__.open')
    @patch('time.time')
    def test_write_timestamp_file(self, m_time, m_open, m_exists, m_tfile, m_ip, m_mac, m_host):
        m_tfile.return_value = '4976ffc8db96caf98c4907ff0d3451a'
        m_host.return_value = 'lms'
        m_mac.return_value = '10:10:10:1E'
        m_ip.return_value = '10.10.10.1'
        m_exists.return_value = False

        m_time.return_value = 12345.67

        def _mocked_open(self, path):
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock()
            mock_context.__exit__ = MagicMock()
            return mock_context

        m_open.side_effect = _mocked_open
        m_open.return_value = '12345.67'

        result = self.encrypt_password.write_timestamp_file()
        self.assertEqual(result, m_open.return_value)

    @patch('os.path.isfile')
    @patch('encrypt_passwords.EncryptPassword.write_timestamp_file')
    @patch('logging.Logger.info')
    def test_encrypt_sed_passwords(self, m_info, m_tfile, m_isfile):
        self.encrypt_password.encrypt_sed_passwords()
        m_info.assert_called_with(
            'Function sed properties completed')
        self.assertEquals(10, self.check_output_file(self.password_store_filename))

    @patch('os.path.isfile')
    @patch('encrypt_passwords.EncryptPassword.write_timestamp_file')
    @patch('encrypt_passwords.EncryptPassword.read_values')
    @patch('encrypt_passwords.EncryptPassword.decrypt_passwords')
    @patch('logging.Logger.info')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_encrypt_configmanager_passwords(self, m_rest, m_info, m_decrypt, m_read, m_tfile, m_isfile):
        self.encrypt_password.password_value_dict = prop_dictionary
        self.encrypt_password.encrypt_configmanager_passwords()
        m_info.assert_called_with(
            'Function configmanager properties completed')
        self.assertEquals(10, self.check_output_file(self.password_store_filename))

    @patch('encrypt_passwords.EncryptPassword.get_hostname')
    @patch('encrypt_passwords.EncryptPassword.get_mac_address')
    @patch('encrypt_passwords.EncryptPassword.get_host_ipaddress')
    @patch('encrypt_passwords.EncryptPassword.gen_passkey_prefix')
    def test_encrypt_algorithm(self, m_prefix, m_host, m_mac, m_ip):
        m_host.return_value = 'lms'
        m_mac.return_value = '10:10:10:1E'
        m_ip.return_value = '10.10.10.1'
        m_prefix.return_value = 'lms_10:10:10:1E_10.10.10.1_12345.67_'

        res = self.encrypt_password.encrypt_algorithm('neo4j_passkey', '12345.67')
        self.assertEquals(res, '874ded33438f0f4f9fae866c5c11e4ce')