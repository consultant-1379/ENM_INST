from unittest2 import TestCase
from mock import patch
from tempfile import gettempdir
import os
from generate_runtime_xml import generate_xml_sub_params, main, \
                                 create_parser, GenerateXml, \
                                 remove_temp_sed_file, \
                                 PROPERTY_FILE_PATH, TEMP_SED_PATH

EXAMPLE_TEMP_SED_PATH = os.path.join(gettempdir(), "sed_backup.cfg")

test_sed = '''#SED Template Version: 1.0.27
COM_INF_LDAP_ROOT_SUFFIX=dc=ieatlms4352,dc=com
Variable_Name=Variable_Value

ENMservices_subnet=10.59.142.0/23
ENMservices_gateway=10.59.142.1
ENMservices_IPv6gateway=2001:1b70:82a1:16:0:3018:0:1
ENMIPv6_subnet=2001:1b70:82a1:0017/64
storage_subnet=10.42.2.0/23
backup_subnet=10.0.24.0/21
jgroups_subnet=192.168.5.0/24
internal_subnet=192.168.55.0/24
VLAN_ID_storage=3019
VLAN_ID_backup=256
VLAN_ID_jgroups=2192
VLAN_ID_internal=2199
VLAN_ID_services=3018
svc_node2_IP=10.59.143.92
key_without_value=
line_with_no_equal_sign
=
'''

EXAMPLE_PROPERTY_NAME = 'property_openidm_admin_password'
EXAMPLE_TEMPFILE_NAME = 'openidm_admin_password_encrypted'
EXAMPLE_ENCRYPTED_PASSWORD = '+RAojat/6ddOyCePpE6Ejg=='
litp_get_value = {'properties': {'key': EXAMPLE_PROPERTY_NAME,
                                    'value': EXAMPLE_ENCRYPTED_PASSWORD}}
EXAMPLE_PROPERTY_TO_TEMPFILE_NAME_DICTIONARY = {EXAMPLE_PROPERTY_NAME: EXAMPLE_TEMPFILE_NAME}
EXAMPLE_PROPERTY_TO_PASSKEY_NAME_DICTIONARY = {EXAMPLE_PROPERTY_NAME: 'openidm_passkey'}


class TestPasskeySubParams(TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        try:
            os.remove(EXAMPLE_TEMP_SED_PATH)
        except OSError as why:
            print why

    def write_file(self, location, contents):
        with open(location, 'w') as _f:
            _f.writelines(contents)

    def test_create_parser(self):
        parser = create_parser()
        self.assertTrue(parser)

    @patch('generate_runtime_xml.generate_xml_sub_params')
    def test_main_help(self, m_sub):
        args = ['generate_runtime_xml.py', '-h']
        self.assertRaises(SystemExit, main, args)
        self.assertFalse(m_sub.called)

    @patch('generate_runtime_xml.generate_xml_sub_params')
    def test_main_no_args(self, m_sub):
        self.assertRaises(SystemExit, main, ['generate_runtime_xml.py'])
        self.assertFalse(m_sub.called)

    @patch('generate_runtime_xml.generate_xml_sub_params')
    def test_main_one_args_xml(self, m_sub):
        self.assertRaises(SystemExit, main, ['generate_runtime_xml.py', '--xml_template', 'some_file'])
        self.assertFalse(m_sub.called)

    @patch('generate_runtime_xml.generate_xml_sub_params')
    def test_main_one_args_sed(self, m_sub):
        self.assertRaises(SystemExit, main, ['generate_runtime_xml.py', '--sed', 'some_file'])
        self.assertFalse(m_sub.called)

    def test_file_not_found(self):
        self.assertRaises(SystemExit, main, ['generate_runtime_xml.py',
                                            '--sed', 'some_file', '--xml_template', 'another_file'])

    @patch('encrypt_passwords.Sed')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('os.path.isfile')
    @patch('generate_runtime_xml.copy')
    @patch('generate_runtime_xml.TEMP_SED_PATH', EXAMPLE_TEMP_SED_PATH)
    @patch.dict('encrypt_passwords.PROPERTY_TO_TEMPFILE_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_TEMPFILE_NAME_DICTIONARY,
                clear=True)
    @patch.dict('encrypt_passwords.PROPERTY_TO_PASSKEY_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_PASSKEY_NAME_DICTIONARY,
                clear=True)
    @patch.dict('generate_runtime_xml.PROPERTY_TO_TEMPFILE_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_TEMPFILE_NAME_DICTIONARY,
                clear=True)
    def test_create_temp_sed_file(self, m_copy, m_isfile, m_litp_get, m_litp_exists,
                                    m_encrypt_password_sed):
        m_isfile.return_value = True
        m_litp_exists.return_value = True
        m_litp_get.return_value = litp_get_value
        self.sub_params = GenerateXml(xml_template = 'xml_template',
                                            sed = 'sed',
                                            verbose = False)
        self.write_file(EXAMPLE_TEMP_SED_PATH, test_sed)
        self.sub_params.create_temp_sed_file()
        with open(EXAMPLE_TEMP_SED_PATH, 'r') as file:
            data = file.read()
        expected_contents = test_sed + EXAMPLE_TEMPFILE_NAME + "=" + EXAMPLE_ENCRYPTED_PASSWORD + "\n"
        self.assertEqual(expected_contents, data)

    @patch('encrypt_passwords.Sed')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('os.path.isfile')
    @patch('generate_runtime_xml.copy')
    @patch('generate_runtime_xml.TEMP_SED_PATH', EXAMPLE_TEMP_SED_PATH)
    @patch.dict('encrypt_passwords.PROPERTY_TO_TEMPFILE_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_TEMPFILE_NAME_DICTIONARY,
                clear=True)
    @patch.dict('encrypt_passwords.PROPERTY_TO_PASSKEY_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_PASSKEY_NAME_DICTIONARY,
                clear=True)
    @patch.dict('generate_runtime_xml.PROPERTY_TO_TEMPFILE_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_TEMPFILE_NAME_DICTIONARY,
                clear=True)
    def test_remove_temp_sed_file(self, m_copy, m_isfile, m_litp_get, m_litp_exists,
                                    m_encrypt_password_sed):
        m_isfile.return_value = True
        m_litp_exists.return_value = True
        m_litp_get.return_value = litp_get_value
        self.sub_params = GenerateXml(xml_template = 'xml_template',
                                            sed = 'sed',
                                            verbose = False)
        self.write_file(EXAMPLE_TEMP_SED_PATH, test_sed)
        self.sub_params.create_temp_sed_file()
        remove_temp_sed_file()
        self.assertFalse(os.path.exists(EXAMPLE_TEMP_SED_PATH))

    @patch('generate_runtime_xml.exec_process_via_pipes')
    @patch('generate_runtime_xml.EncryptPassword')
    @patch('os.path.isfile')
    def test_execute_substitute_params(self, m_isfile, m_encrypt_password, m_exec_command):
        m_isfile.return_value = True
        self.sub_params = GenerateXml(xml_template = 'xml_template',
                                            sed = TEMP_SED_PATH,
                                            verbose = False)
        cmd = "/opt/ericsson/enminst/bin/substituteParams.sh " \
                "--xml_template xml_template " \
                "--sed {0} " \
                "--propertyfile {1}".format(TEMP_SED_PATH, PROPERTY_FILE_PATH)
        self.sub_params.execute_substitute_params()
        m_exec_command.assert_called_with(cmd.split())

    @patch('generate_runtime_xml.exec_process_via_pipes')
    @patch('generate_runtime_xml.EncryptPassword')
    @patch('os.path.isfile')
    def test_execute_substitute_params_verbose(self, m_isfile, m_encrypt_password, m_exec_command):
        m_isfile.return_value = True
        self.sub_params = GenerateXml(xml_template = 'xml_template',
                                            sed = TEMP_SED_PATH,
                                            verbose = True)
        cmd = "/opt/ericsson/enminst/bin/substituteParams.sh " \
                "--xml_template xml_template " \
                "--sed {0} " \
                "--propertyfile {1} " \
                "-v".format(TEMP_SED_PATH, PROPERTY_FILE_PATH)
        self.sub_params.execute_substitute_params()
        m_exec_command.assert_called_with(cmd.split())

    @patch('os.path.isfile')
    @patch('generate_runtime_xml.EncryptPassword')
    @patch('generate_runtime_xml.GenerateXml.create_temp_sed_file')
    @patch('generate_runtime_xml.GenerateXml.execute_substitute_params')
    @patch('generate_runtime_xml.remove_temp_sed_file')
    def test_main(self, m_isfile, m_encrypt_password, m_create_tmp_sed, m_sub, m_remove_temp_sed):
        m_isfile.return_value = True
        args = ['generate_runtime_xml.py', '--sed', 'some_file', '--xml_template', 'another_file']
        main(args)
        self.assertTrue(m_create_tmp_sed.called)
        self.assertTrue(m_sub.called)
        self.assertTrue(m_remove_temp_sed.called)

    @patch('os.path.isfile')
    @patch('os.remove')
    @patch('encrypt_passwords.Sed')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('generate_runtime_xml.copy')
    @patch('generate_runtime_xml.exec_process_via_pipes')
    @patch('generate_runtime_xml.TEMP_SED_PATH', EXAMPLE_TEMP_SED_PATH)
    @patch.dict('encrypt_passwords.PROPERTY_TO_TEMPFILE_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_TEMPFILE_NAME_DICTIONARY,
                clear=True)
    @patch.dict('encrypt_passwords.PROPERTY_TO_PASSKEY_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_PASSKEY_NAME_DICTIONARY,
                clear=True)
    @patch.dict('generate_runtime_xml.PROPERTY_TO_TEMPFILE_NAME_DICTIONARY', EXAMPLE_PROPERTY_TO_TEMPFILE_NAME_DICTIONARY,
                clear=True)
    def test_main_full_flow(self, m_exec_command, m_copy, m_litp_get, m_litp_exists,
                            m_encrypt_password_sed, m_remove, m_isfile):
        m_isfile.return_value = True
        m_litp_exists.return_value = True
        m_litp_get.return_value = litp_get_value
        self.write_file(EXAMPLE_TEMP_SED_PATH, test_sed)
        args = ['generate_runtime_xml.py', '--sed', EXAMPLE_TEMP_SED_PATH, '--xml_template', 'test_xml']
        main(args)

        self.assertTrue(m_encrypt_password_sed.called)
        with open(EXAMPLE_TEMP_SED_PATH, 'r') as file:
            data = file.read()
        expected_contents = test_sed + EXAMPLE_TEMPFILE_NAME + "=" + EXAMPLE_ENCRYPTED_PASSWORD + "\n"
        self.assertEqual(expected_contents, data)

        cmd = "/opt/ericsson/enminst/bin/substituteParams.sh " \
                "--xml_template test_xml " \
                "--sed {0} " \
                "--propertyfile {1}".format(EXAMPLE_TEMP_SED_PATH, PROPERTY_FILE_PATH)
        m_exec_command.assert_called_with(cmd.split())

        m_remove.assert_called_with(EXAMPLE_TEMP_SED_PATH)
