import os
from StringIO import StringIO
from ConfigParser import MissingSectionHeaderError
from os.path import join
from mock import Mock, patch
from unittest2 import TestCase
from tempfile import gettempdir
from h_litp.litp_utils import TCP_CONNECTION, UNIX_CONNECTION
from h_litp.litp_utils import get_connection_type, read_litprc, LitprcConfig, \
                                get_enm_version_deployed, \
                                get_xml_deployment_file, get_cluster_types_from_dd_info


class TestLitpSocketClient(TestCase):
    # test data defer to default path
    litprc_data_no_path = {
        'username': 'litp_username'
    }
    # test data including path
    litprc_data_with_path = {
        'username': 'litp_username',
        'unix_socket_path': '/gsd'
    }

    @patch('h_litp.litp_utils.exists')
    @patch('h_litp.litp_utils.stat.S_ISSOCK')
    @patch('h_litp.litp_utils.os.stat')
    def test_get_connection_type_socket_validation(
            self, os_stat, stat_issock, exists):
        # Is socket is a socket
        stat_issock.return_value = True
        # Does the socket exist
        exists.return_value = False

        (_connection, _path) = get_connection_type(self.litprc_data_no_path)
        self.assertEqual(_connection, TCP_CONNECTION)

        (_connection, _path) = get_connection_type(self.litprc_data_with_path)
        self.assertEqual(_connection, TCP_CONNECTION)

        stat_issock.return_value = False
        exists.return_value = True

        (_connection, _path) = get_connection_type(self.litprc_data_no_path)
        self.assertEqual(_connection, TCP_CONNECTION)

        (_connection, _path) = get_connection_type(self.litprc_data_with_path)
        self.assertEqual(_connection, TCP_CONNECTION)

        stat_issock.return_value = False
        exists.return_value = False

        (_connection, _path) = get_connection_type(self.litprc_data_no_path)
        self.assertEqual(_connection, TCP_CONNECTION)

        (_connection, _path) = get_connection_type(self.litprc_data_with_path)
        self.assertEqual(_connection, TCP_CONNECTION)

    @patch('h_litp.litp_utils.exists')
    @patch('h_litp.litp_utils.stat.S_ISSOCK')
    @patch('h_litp.litp_utils.os.stat')
    def test_get_connection_type_valid_socket_path(
            self, os_stat, stat_issock, exists):
        stat_issock.return_value = True
        exists.return_value = True

        (_connection, _path) = get_connection_type(self.litprc_data_no_path)
        self.assertEqual(_connection, UNIX_CONNECTION)

        (_connection, _path) = get_connection_type(self.litprc_data_with_path)
        self.assertEqual(_connection, UNIX_CONNECTION)

    def test_get_connection_type_no_socket_path(self):
        litprc_data = {
            'username': 'litp_username',
            'password': 'litp_password'
        }
        (_connection, _path) = get_connection_type(litprc_data)
        self.assertEqual(_connection, TCP_CONNECTION)
        litprc_data = {
            'username': 'litp_username',
            'password': ''
        }
        (_connection, _path) = get_connection_type(litprc_data)
        self.assertEqual(_connection, TCP_CONNECTION)
        litprc_data = {
            'username': 'litp_username'
        }
        (_connection, _path) = get_connection_type(litprc_data)
        self.assertEqual(_connection, TCP_CONNECTION)


class TestReadLitprc(TestCase):
    @patch('h_litp.litp_utils.exists')
    def test_litprc_test_home(self, exists):
        exists.return_value = False

        environ = {'TEST_HOME': 'test/home/'}
        original = os.environ
        with patch.dict(os.environ, environ, clear=True):
            result_litprc_data = read_litprc()
        os.environ = original
        expected_litprc_data = LitprcConfig(path="test/home/.litprc")
        expected_litprc_data.file_missing = True
        expected_litprc_data.file_broken = False
        self.assertEqual(expected_litprc_data.path, result_litprc_data.path)
        self.assertEqual(
                expected_litprc_data.file_missing,
                result_litprc_data.file_missing)
        self.assertEqual(
                expected_litprc_data.file_broken,
                result_litprc_data.file_broken)

    @patch('h_litp.litp_utils.expanduser')
    @patch('h_litp.litp_utils.exists')
    def test_litprc_user_home(self, exists, expanduser):
        exists.return_value = False
        expanduser.return_value = "home"

        environ = {'USER_HOME': 'user/home/'}
        original = os.environ
        with patch.dict(os.environ, environ, clear=True):
            result_litprc_data = read_litprc()
        os.environ = original
        expected_litprc_data = LitprcConfig(path="home/.litprc")
        expected_litprc_data.file_missing = True
        expected_litprc_data.file_broken = False
        self.assertEqual(expected_litprc_data.path, result_litprc_data.path)
        self.assertEqual(
                expected_litprc_data.file_missing,
                result_litprc_data.file_missing)
        self.assertEqual(
                expected_litprc_data.file_broken,
                result_litprc_data.file_broken)

    @patch('h_litp.litp_utils.ConfigParser.read')
    @patch('h_litp.litp_utils.expanduser')
    @patch('h_litp.litp_utils.exists')
    def test_litprc_missing_section(self, exists, expanduser, reader):
        environ = {'USER_HOME': 'user/home/'}
        exists.return_value = True
        expanduser.return_value = "home"

        reader.side_effect = Mock(
                side_effect=MissingSectionHeaderError('filename', 1,
                                                      'someline'))

        original = os.environ
        with patch.dict(os.environ, environ, clear=True):
            result_litprc_data = read_litprc()
        os.environ = original

        expected_litprc_data = LitprcConfig(path="home/.litprc")
        expected_litprc_data.file_missing = False
        expected_litprc_data.file_broken = True
        self.assertEqual(expected_litprc_data.path, result_litprc_data.path)
        self.assertEqual(
                expected_litprc_data.file_missing,
                result_litprc_data.file_missing)
        self.assertEqual(
                expected_litprc_data.file_broken,
                result_litprc_data.file_broken)

    @patch('h_litp.litp_utils.ConfigParser.sections')
    @patch('h_litp.litp_utils.ConfigParser.get')
    @patch('h_litp.litp_utils.ConfigParser.read')
    @patch('h_litp.litp_utils.expanduser')
    @patch('h_litp.litp_utils.exists')
    def test_litprc_valid_section(
            self, exists, expanduser, reader, getter, sections):
        environ = {'USER_HOME': 'user/home/'}
        exists.return_value = True
        expanduser.return_value = "home"

        litprc_data = {
            'username': 'litp_username',
            'password': 'litp_password'
        }

        sections.return_value = litprc_data

        def lookup_rc(section, arg):
            return litprc_data.get(arg)

        getter.side_effect = lookup_rc

        original = os.environ
        with patch.dict(os.environ, environ, clear=True):
            result_litprc_data = read_litprc()
        os.environ = original

        expected_litprc_data = LitprcConfig(path="home/.litprc")
        expected_litprc_data.file_missing = False
        expected_litprc_data.file_broken = False
        expected_litprc_data['username'] = litprc_data.get('username')
        expected_litprc_data['password'] = litprc_data.get('password')
        expected_litprc_data['unix_socket_path'] = litprc_data.get(
                'unix_socket_path')
        self.assertEqual(expected_litprc_data.path, result_litprc_data.path)
        self.assertEqual(
                expected_litprc_data.file_missing,
                result_litprc_data.file_missing)
        self.assertEqual(
                expected_litprc_data.file_broken,
                result_litprc_data.file_broken)
        self.assertEqual(
                expected_litprc_data, result_litprc_data)

        litprc_data['unix_socket_path'] = 'path/to/socket'
        original = os.environ
        with patch.dict(os.environ, environ, clear=True):
            result_litprc_data = read_litprc()
        os.environ = original

        expected_litprc_data = LitprcConfig(path="home/.litprc")
        expected_litprc_data.file_missing = False
        expected_litprc_data.file_broken = False
        expected_litprc_data['username'] = litprc_data.get('username')
        expected_litprc_data['password'] = litprc_data.get('password')
        expected_litprc_data['unix_socket_path'] = litprc_data.get(
                'unix_socket_path')
        self.assertEqual(expected_litprc_data.path, result_litprc_data.path)
        self.assertEqual(
                expected_litprc_data.file_missing,
                result_litprc_data.file_missing)
        self.assertEqual(
                expected_litprc_data.file_broken,
                result_litprc_data.file_broken)
        self.assertEqual(expected_litprc_data, result_litprc_data)


class TestGetEnmVersionDeployed(TestCase):

    @patch('__builtin__.open')
    def test_get_enm_version_deployed(self, m_open):
        """test_get_enm_version_deployed"""
        enm_version = "2.12.35"
        etc_enm_version = ("ENM 22.13 (ISO Version: {0}) AOM 901 151 R1FL"
                           .format(enm_version))

        m_open.return_value = StringIO(etc_enm_version)
        self.assertEqual(get_enm_version_deployed(), "2.12.35",
                         "Did not return the correct enm_version")

    @patch('__builtin__.open')
    def test_get_enm_version_deployed_ioerror(self, m_open):
        """test_get_enm_version_deployed"""
        m_open.side_effect = IOError

        self.assertRaises(IOError, get_enm_version_deployed)


class TestGetXmlDeploymentFile(TestCase):

    ug_model_xml = "/ericsson/deploymentDescriptions/medium/medium__production_IPv4_dd.xml"
    expansion_model_xml = "/ericsson/deploymentDescriptions/large/large__production_IPv4__2evt_dd.xml"
    rhel7_ug_model_xml = "/ericsson/deploymentDescriptions/large/large__production_IPv4__2evt_dd.xml"

    cmd_args_log_ii = ("./deploy_enm.sh -t ENM_Deployment "
        "-s /var/tmp/btc_enm_sed_rev3.txt "
        "-m /ericsson/deploymentDescriptions/4svc_2scp_2evt_enm_15k_physical_production_dd.xml "
        "-e /software/ENM/ERICenm_CXP9027091_19_04.iso -v\n")
    cmd_args_log_ug = cmd_args_log_ii + (
        "./upgrade_enm.sh --litp_iso /software/LITP/LITP_2_Base_Software_2.109.10.iso "
        "--sed /software/ENM/sed_batelco-enm-prod.txt "
        "--model {0} "
        "--enm_iso /software/ENM/ERICenm_CXP9027091-1.87.150.iso "
        "--noreboot --assumeyes\n"
        "./upgrade_enm.sh --litp_iso /software/LITP/LITP_2_Base_Software_2.109.10.iso "
        "--sed /software/ENM/sed_batelco-enm-prod.txt "
        "--model {0} "
        "--enm_iso /software/ENM/ERICenm_CXP9027091-1.87.150.iso "
        "--noreboot --assumeyes\n".format(ug_model_xml))
    cmd_args_log_exp = cmd_args_log_ug + (
        "./upgrade_enm.sh --sed /software/ENM/ENM_SED_21.07IP7_Expansion_15K_to_40K.txt.updated "
        "--model {0}\n".format(expansion_model_xml))
    cmd_args_log_rh7_ug = cmd_args_log_ug + (
        "./upgrade [rh7_upgrade_enm.sh] --action rh7_uplift "
        "-v --sed /tmp/ansible_tmp_sed.txt "
        "--model {0} "
        "--to_state_enm /software/ENM/ERICenm_CXP9027091-2.7.92.iso "
        "--to_state_litp /software/LITP/LITP_2_Base_Software_3.9.16.iso\n"
        .format(rhel7_ug_model_xml))
    cmd_args_log_rh7_ug_after_exp = cmd_args_log_exp + (
        "./upgrade [rh7_upgrade_enm.sh] --action rh7_uplift "
        "-v --sed /tmp/ansible_tmp_sed.txt "
        "--model {0} "
        "--to_state_enm /software/ENM/ERICenm_CXP9027091-2.7.92.iso "
        "--to_state_litp /software/LITP/LITP_2_Base_Software_3.9.16.iso\n"
        .format(rhel7_ug_model_xml))

    @patch('__builtin__.open')
    @patch('os.path.exists')
    @patch('os.path.isfile')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    def test_get_xml_deployment_file_last_entry_ug(
            self, m_get_enm_version_deployed, m_is_file, m_exists, m_open):
        """test_get_xml_deployment_file_last_entry_ug"""
        m_get_enm_version_deployed.return_value = "1.87.150"
        m_is_file.return_value = True
        m_exists.side_effect = [False, True]
        m_open.return_value = StringIO(self.cmd_args_log_ug)

        self.assertTrue(get_xml_deployment_file() == self.ug_model_xml,
                        "Did not select the correct model DD xml file")

    @patch('__builtin__.open')
    @patch('os.path.exists')
    @patch('os.path.isfile')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    def test_get_xml_deployment_file_last_entry_rh7_ug(
            self, m_get_enm_version_deployed, m_is_file, m_exists, m_open):
        """test_get_xml_deployment_file_last_entry_rh7_ug"""
        m_get_enm_version_deployed.return_value = "2.7.92"
        m_is_file.return_value = True
        m_exists.side_effect = [False, True]
        m_open.return_value = StringIO(self.cmd_args_log_rh7_ug)

        self.assertTrue(get_xml_deployment_file() == self.rhel7_ug_model_xml,
                        "Did not select the correct model DD xml file")

    @patch('__builtin__.open')
    @patch('os.path.exists')
    @patch('os.path.isfile')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    def test_get_xml_deployment_file_last_entry_expansion(
            self, m_get_enm_version_deployed, m_is_file, m_exists, m_open):
        """test_get_xml_deployment_file_last_entry_expansion"""
        m_get_enm_version_deployed.return_value = "1.108.121"
        m_is_file.return_value = True
        m_exists.side_effect = [False, True]
        m_open.return_value = StringIO(self.cmd_args_log_exp)

        self.assertTrue(get_xml_deployment_file() == self.expansion_model_xml,
                        "Did not select the correct model DD xml file")

    @patch('__builtin__.open')
    @patch('os.path.exists')
    @patch('os.path.isfile')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    def test_get_xml_deployment_file_expansion_before_rh7_ug(
            self, m_get_enm_version_deployed, m_is_file, m_exists, m_open):
        """test_get_xml_deployment_file_expansion_before_rh7_ug"""
        m_get_enm_version_deployed.return_value = "1.108.121"
        m_is_file.return_value = True
        m_exists.side_effect = [False, True]
        m_open.return_value = StringIO(self.cmd_args_log_rh7_ug_after_exp)

        self.assertTrue(get_xml_deployment_file() == self.expansion_model_xml,
                        "Did not select the correct model DD xml file")

    @patch('os.path.isfile')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    def test_get_xml_deployment_file_cmd_arg_log_missing(
            self, m_get_enm_version_deployed, m_is_file):
        '''test_get_xml_deployment_file_cmd_arg_log_missing'''
        m_is_file.return_value = False

        with self.assertRaises(IOError) as context:
            get_xml_deployment_file()
        self.assertTrue("cmd_arg.log file does not exist" in context.exception)

    @patch('__builtin__.open')
    @patch('os.path.isfile')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    def test_get_xml_deployment_file_not_found(
            self, m_get_enm_version_deployed, m_is_file, m_open):
        """test_get_xml_deployment_file_not_found"""
        m_get_enm_version_deployed.return_value = "x.yy.zzz"
        m_is_file.return_value = True
        m_open.return_value = StringIO(self.cmd_args_log_ug)

        with self.assertRaises(IOError) as context:
            get_xml_deployment_file()
        self.assertTrue("Error getting path of the xml file from cmd_arg.log"
                        in context.exception)

    @patch('__builtin__.open')
    @patch('os.path.exists')
    @patch('os.path.isfile')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    def test_get_xml_deployment_file_path_not_found(
            self, m_get_enm_version_deployed, m_is_file, m_exists, m_open):
        """test_get_xml_deployment_file_path_not_found"""
        m_get_enm_version_deployed.return_value = "1.87.150"
        m_is_file.return_value = True
        m_exists.side_effect = [False, False]
        m_open.return_value = StringIO(self.cmd_args_log_ug)

        with self.assertRaises(IOError) as context:
            get_xml_deployment_file()
        self.assertTrue("DeploymentDescription XML file:{0} does not exist"
                        .format(self.ug_model_xml) in context.exception)


class TestGetClusterNames(TestCase):

    def write_dd_info_to_file(self):
        tmp_filename = join(gettempdir(), 'sample_dd.txt')
        with open(tmp_filename, 'a') as tmp_file:
            tmp_file.write('INCLUDE_SERVICES={svc_cluster=[amos, cnom, elementmanager, ops, scripting, traceadmin, winfiol]}\n')
            tmp_file.write('db_cluster=3\n')
            tmp_file.write('db_cluster=5\n')
            tmp_file.write('svc_cluster=asdasd\n')
            tmp_file.write('svc_cluster=3\n')
            tmp_file.write('scp_cluster=3\n')
            tmp_file.write('evt_cluster=3\n')
            tmp_file.write('str_cluster=3\n')
            tmp_file.write('ebs_cluster=0\n')
            tmp_file.write('asr_cluster=3\n')
            tmp_file.write('esn_cluster=3\n')
            tmp_file.write('aut_cluster=3\n')
            tmp_file.write('eba_cluster=33\n')
        return tmp_filename

    @patch('glob.glob')
    def test_get_cluster_types_from_dd_info(self, m_glob):
        tmp_filename = self.write_dd_info_to_file()
        dst_file = [tmp_filename]
        m_glob.return_value = dst_file
        cluster_list = get_cluster_types_from_dd_info()
        self.assertEqual(cluster_list, ['db_cluster', 'svc_cluster', 'scp_cluster', 'evt_cluster', 'str_cluster', 'ebs_cluster', 'asr_cluster', 'esn_cluster', 'aut_cluster', 'eba_cluster'])
