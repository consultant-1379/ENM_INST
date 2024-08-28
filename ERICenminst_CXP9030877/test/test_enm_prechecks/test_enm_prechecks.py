import mock as mock
import requests
import random
from unittest2 import TestCase
import ConfigParser
from mock import call, patch, Mock, MagicMock
from h_puppet.mco_agents import McoAgentException
import os.path
from enm_upgrade_prechecks import EnmPreChecks, Translator
import enm_upgrade_prechecks
tran = Translator('ERICenminst_CXP9030877')
_ = tran._


class MockTimeout(Mock):
    def has_elapsed(self):
        return True
    def sleep(self, sleep_time):
        pass


class TestEnmPrechecks(TestCase):
    FIRST_ATTEMPT = 1
    SECOND_ATTEMPT = 2

    def __init__(self, *args, **kwargs):
        super(TestEnmPrechecks, self).__init__(*args, **kwargs)
        self.boot_partition_test_count = 0
        self.change_pvscan_on_count = 0
        self.mount_count = 0
        self.second_mount = True
        self.boot_partition_test_error_msg1 = None
        self.get_global_filter_count = 0
        self.get_count_dmsetup_deps_non_dm_count = 0
        self.get_count_dmsetup_deps_non_dm_return_vals = []
        self.include_sd_path = 0
        self._mocked_pvscan_count = 0
        self.boot_partition_test_error_msg2 = None
        self.properties_file = '/ericsson/tor/data/global.properties'
        self.lvm_dot_conf = '/etc/lvm/lvm.conf'
        self.mount_dir = '/mnt'

    def setUp(self):
        self.prechecks = EnmPreChecks()
        self.prechecks.create_arg_parser()
        self.prechecks.current_action = 'test'
        self.prechecks.set_verbosity_level()

    def mocked_translation_text(self, key):
        return 'Nothing'

    def get_msg(self, msg_key, is_heading=False):
        return self.prechecks._u(msg_key) if is_heading \
               else self.prechecks._(msg_key)

    def tearDown(self):
        pass

    # pylint: disable=R0912
    def call_method_and_assert_msgs(self, action_handler, *args, **kwargs):

        response = None

        if 'msg' in kwargs:
            self.prechecks.print_message = MagicMock()

        if 'hdr_msg' in kwargs:
            self.prechecks.print_action_heading = MagicMock()

        if 'success_msg' in kwargs:
            self.prechecks.print_success = MagicMock()

        if 'err_msg' in kwargs:
            self.prechecks.print_error = MagicMock()
            if 'mco_agent_object' in kwargs:
                try:
                    response = action_handler(*args, mco_agent_object=kwargs.get('mco_agent_object'))
                except SystemExit as e:
                    self.assertEqual(1, e.code)
            else:
                try:
                    response = action_handler(*args)
                except SystemExit as e:
                    self.assertEqual(1, e.code)
            if 'add_suffix' in kwargs.keys():
                self.prechecks.print_error.assert_called_once_with(kwargs.get('err_msg'),
                                                                   add_suffix=kwargs.get('add_suffix', True))
            elif 'multi_call' in kwargs.keys():
                self.prechecks.print_error.assert_called_any(kwargs.get('err_msg'))
            else:
                self.prechecks.print_error.assert_called_once_with(kwargs.get('err_msg'))
        else:
            response = action_handler(*args)

        if 'hdr_msg' in kwargs:
            self.prechecks.print_action_heading.assert_called_once_with(kwargs.get('hdr_msg'))

        if 'success_msg' in kwargs:
            self.prechecks.print_success.assert_called_once_with(kwargs.get('success_msg'))

        if 'msg' in kwargs:
            self.prechecks.print_message.assert_called_once_with(kwargs.get('msg'))

        return response

    def _mocked_get_ldap_root(self, file_path):
        return 'dc=apache,dc=com'

    def _mocked_get_ldap_root_02(self, file_path):
        return ''

    def _mocked_get_cleartext_password_01(self, file_path):
        return 'ldapadmin'

    def _mocked_get_cleartext_password_02(self, file_path):
        return ''

    def _mocked_get_global_properties_found(self):
        return ['COM_INF_LDAP_ROOT_SUFFIX=dc=apache,dc=com',
                'LDAP_ADMIN_PASSWORD=secret']

    def _mocked_get_global_properties_not_found(self):
        return  ['USELESS_KEY=useless_value',]

    def _mock_get_global_properties(self, found=True):
        the_file = self._mocked_get_global_properties_found() \
                   if found \
                   else self._mocked_get_global_properties_not_found()
        for line in the_file:
            line = line.strip()
            key, value = line.partition("=")[::2]
            self.prechecks.global_properties[key.strip()] = value.strip()

    def _get_clustered_service_data(self, host, state, service='opendj'):
        return ' db_cluster Grp_CS_db_cluster_%s_clustered_service %s standalone lsb %s OK -\n' % (service, host, state)

    def _mock_run_command_check_opendj_01(self, command):
        # Just 1 DB node
        text = self._get_clustered_service_data('db-1', 'ONLINE')
        return (0, text)

    def _mock_run_command_check_opendj_02(self, command):
        # One of the DB nodes is offline
        text = self._get_clustered_service_data('db-1', 'ONLINE') + \
               self._get_clustered_service_data('db-2', 'OFFLINE')
        return (0, text)

    def _mock_run_command_check_opendj_03(self, command):
        # Both DB nodes ok
        text = self._get_clustered_service_data('db-1', 'ONLINE') + \
               self._get_clustered_service_data('db-2', 'ONLINE')
        return (0, text)

    @staticmethod
    def _get_repl_data(base_dn, host, entries='56', enabled='true', mc_count='0'):
        return "%s : ldap-%s:4444 : %s : %s : 28862 : 27057 : 8989 : %s : : true\n" % \
               (base_dn, host, entries, enabled, mc_count)

    def _mocked_repl_data_01(self, host, base_dn, password):
        # Just 1 repl node
        return TestEnmPrechecks._get_repl_data(base_dn, 'local')

    def _mocked_repl_data_02(self, host, base_dn, password):
        # Entries mismatch
        return TestEnmPrechecks._get_repl_data(base_dn, 'local') + \
               TestEnmPrechecks._get_repl_data(base_dn, 'remote', entries='96')

    def _mocked_repl_data_03(self, host, base_dn, password):
        # Both not enabled
        return TestEnmPrechecks._get_repl_data(base_dn, 'local') + \
               TestEnmPrechecks._get_repl_data(base_dn, 'remote', enabled='false')

    def _mocked_repl_data_04(self, host, base_dn, password):
        # MC count mismatch
        return TestEnmPrechecks._get_repl_data(base_dn, 'local') + \
               TestEnmPrechecks._get_repl_data(base_dn, 'remote', mc_count='99')

    def _mocked_repl_data_05(self, host, base_dn, password):
        # All A-OK
        return TestEnmPrechecks._get_repl_data(base_dn, 'local') + \
               TestEnmPrechecks._get_repl_data(base_dn, 'remote')

    def _mocked_repl_data_06(self, host, base_dn, password):
        # All A-OK
        return "monitor_replication......OK"

    def _mocked_run_command_synchronized_model_01(self, command, timeout_secs=0, do_logging=False):
        return (1, 'DoNothingPlanError    Create plan failed: no tasks were generated')

    def _mocked_run_command_synchronized_model_02(self, command, timeout_secs=0, do_logging=False):
        return (0, '')

    def _mocked_run_command_synchronized_model_03(self, command, timeout_secs=0, do_logging=False):
        return (1, '')

    def _mocked_succesful_check_fallback_vms(self, ip_address, use_dp1_test):
        return 200

    def _mocked_unsuccesful_check_fallback_vms(self, ip_address, use_dp1_test):
        return 0

    def _mocked_failure_check_fallback_vms(self, ip_address, use_dp1_test):
        return 'connectionError'

    def _mocked_run_command_elasticsearch_01(self, command, timeout_secs=0):
        return  (0, "health status index                           pri rep docs.count docs.deleted store.size pri.store.size \n" + \
                    "green  open   enm-help-search                   1   0       1693           20        3mb            3mb \n" + \
                    "green  open   enm_logs-application-2018.02.20   1   0   13629415            0      7.4gb          7.4gb \n" + \
                    "green  open   enm_logs-application-2018.02.21   1   0   15750686            0      9.6gb          9.6gb \n" + \
                    "green  open   enm_logs-application-2018.02.22   1   0   21757971            0     30.1gb         30.1gb \n" + \
                    "green  open   enm_logs-application-2018.02.23   1   0   19443004            0     12.8gb         12.8gb \n" + \
                    "green  open   enm_logs-application-2018.02.19   1   0   13687453            0      6.8gb          6.8gb \n" + \
                    "green  open   enm_logs-application-2018.02.17   1   0   19443004            0     12.8gb         12.8gb \n" + \
                    "green  open   enm_logs-application-2018.02.18   1   0   15920160            0      7.8gb          7.8gb \n")

    def _mocked_run_command_elasticsearch_02(self, command, timeout_secs=0):
        return  (0, "health status index                           pri rep docs.count docs.deleted store.size pri.store.size \n" + \
                    "green  open   enm-help-search                   1   0       1693           20        3mb            3mb \n" + \
                    "yellow open   enm_logs-application-2018.02.20   1   0   13629415            0      7.4gb          7.4gb \n" + \
                    "green  open   enm_logs-application-2018.02.21   1   0   15750686            0      9.6gb          9.6gb \n" + \
                    "green  open   enm_logs-application-2018.02.22   1   0   21757971            0     30.1gb         30.1gb \n" + \
                    "red    open   enm_logs-application-2018.02.23   1   0                                                   \n" + \
                    "green  open   enm_logs-application-2018.02.19   1   0   13687453            0      6.8gb          6.8gb \n" + \
                    "green  open   enm_logs-application-2018.02.17   1   0   19443004            0     12.8gb         12.8gb \n" + \
                    "green  open   enm_logs-application-2018.02.18   1   0   15920160            0      7.8gb          7.8gb \n")

    def _mocked_run_command_elasticsearch_03(self, command, timeout_secs=0):
        return (2, "Error case")

    def _mocked_run_command_elasticsearch_04(self, command, timeout_secs=0):
        return  (0, "health status index pri rep docs.count docs.deleted store.size pri.store.size")

    def test_check_opendj(self):

        # --- Virtual environment, do nothing ---
        self.prechecks.is_virtual_environment = lambda: True
        self.prechecks.check_opendj_replication()

        # --- Non-virtual environment from here on ---
        self.prechecks.is_virtual_environment = lambda: False

        # --- Changed output from vcs.bsh ---
        expected_err = self.get_msg('OPENDJ_NOT_ONLINE_ON_TWO_NODES')
        expected_hdr = self.get_msg('CHECKING_OPENDJ_REPLICATION', True)

        for func in (self._mock_run_command_check_opendj_01,
                     self._mock_run_command_check_opendj_02):
            self.prechecks.run_command = func
            self.call_method_and_assert_msgs(self.prechecks.check_opendj_replication,
                                             err_msg=expected_err, hdr_msg=expected_hdr, add_suffix=False)

        self.prechecks.run_command = self._mock_run_command_check_opendj_03

        # --- Password not found ---
        self.prechecks.get_cleartext_password = self._mocked_get_cleartext_password_02
        expected_err = self.get_msg('OPENDJ_PASSWORD_CANNOT_BE_RETRIEVED').format(self.properties_file)
        self.call_method_and_assert_msgs(self.prechecks.check_opendj_replication, err_msg=expected_err)

        self.prechecks.get_cleartext_password = self._mocked_get_cleartext_password_01

        # --- LDAP root not found ---
        self.prechecks.get_ldap_root = self._mocked_get_ldap_root_02
        expected_err = self.get_msg('OPENDJ_LDAP_ROOT_CANNOT_BE_RETRIEVED').format(self.properties_file)
        self.call_method_and_assert_msgs(self.prechecks.check_opendj_replication, err_msg=expected_err)

        self.prechecks.get_ldap_root = self._mocked_get_ldap_root


        # --- Changed replication data ---
        msg_suffix = self.get_msg('REFER_TO_OPENDJ_SECTION_OF_GUIDE')
        test_data = [(self._mocked_repl_data_01, 'OPENDJ_REPL_NODES_NOT_FOUND', False),
        (self._mocked_repl_data_02, 'MISMATCH_IN_NUMBER_OF_OPENDJ_ENTRIES', True),
        (self._mocked_repl_data_03, 'REPLICATION_NOT_ENABLED_ON_BOTH_NODES', True),
        (self._mocked_repl_data_04, 'MC_IS_NOT_ZERO_ON_BOTH_NODES', True)]

        for (func, msg_key, with_suffix) in test_data:
            self.prechecks.mco_agent.get_replication_status = func
            self.prechecks.print_error = MagicMock()
            msg = self.get_msg(msg_key)
            expected_err = msg if not with_suffix else msg + msg_suffix
            self.call_method_and_assert_msgs(self.prechecks.check_opendj_replication, err_msg=expected_err)


        # --- Positive case new ---
        self.prechecks.mco_agent.get_replication_status = self._mocked_repl_data_06
        msg = self.get_msg('OPENDJ_REPLICATION_INTACT')
        self.call_method_and_assert_msgs(self.prechecks.check_opendj_replication, success_msg=msg)

        # --- Positive case old ---
        self.prechecks.mco_agent.get_replication_status = self._mocked_repl_data_05
        msg = self.get_msg('OPENDJ_REPLICATION_INTACT')
        self.call_method_and_assert_msgs(self.prechecks.check_opendj_replication, success_msg=msg)

    @patch('subprocess.Popen')
    def test_run_command_01(self, mock_popen):
        mock_process1 = Mock()
        mock_process1.poll.return_value = 'terminate'
        mock_process1.communicate.return_value = ('xyz', None)
        mock_popen.return_value = mock_process1
        mock_process1.returncode = 0

        rc, output = self.prechecks.run_command('ls')

    @patch('subprocess.Popen')
    @patch('enm_upgrade_prechecks.EnmPreChecks.Timeout', new=MockTimeout)
    def test_run_command_02(self, mock_popen):
        mock_process1 = Mock()
        mock_process1.poll.return_value = None
        mock_popen.return_value = mock_process1

        expected_err = self.get_msg('TIMEOUT_OUT_COMMAND').format('ls')
        self.call_method_and_assert_msgs(self.prechecks.run_command, 'ls', err_msg=expected_err)

    @patch('subprocess.Popen')
    def test_run_command_03(self, mock_popen):
        mock_popen.side_effect = OSError("OS Error")
        expected_err = self.get_msg('ERROR_PROCESSING_COMMAND').format('ls', None, None)
        self.call_method_and_assert_msgs(self.prechecks.run_command, 'ls', err_msg=expected_err)

    def _mock_prompt_user_boolean_false(self, prompt):
        expected_prompt = self.get_msg('MOUNT_DIRECTORY_IS_USED').format(self.mount_dir)
        self.assertEqual(prompt, expected_prompt)
        return False

    def _mock_prompt_user_boolean_true(self, prompt):
        return True

    def _mock_get_db_systems(self, service):
        return set(['db-1', 'db-2'])

    def _mock_read_config(self):
        pass

    def _mock_get_config_attr(self, attr):
        return '/path/to/bogus/lock_file'

    def _mock_two_db_nodes(self, state):
        db1 = Mock()
        db1.state = state
        db1.system = 'db-1'
        db1.is_online = lambda: True if state == 'ONLINE' else False
        db2 = Mock()
        db2.state = state
        db2.system = 'db-2'
        db2.is_online = lambda: True if state == 'ONLINE' else False
        return [db1, db2]

    def _mock_get_online_db_nodes(self, service):
        return self._mock_two_db_nodes('ONLINE')

    def _mock_get_offline_db_nodes(self, service):
        return self._mock_two_db_nodes('OFFLINE')

    def _get_enm_iso_mount_line(self):
        return '/software/autoDeploy/ERICenm_CXP9027091-1.2.3.iso on /mnt type iso9660 (rw,loop=/dev/loop0)'

    def _get_litp_iso_mount_line(self):
        return '/software/autoDeploy/ERIClitp_CXP9024296-2.76.3.iso on /mnt/litp type iso9660 (rw,loop=/dev/loop0)'

    def _mock_run_command_unmount_01(self, command, timeout_secs=0, do_logging=False):
        return (0, '')

    def _mock_run_command_unmount_02(self, command, timeout_secs=0, do_logging=False):
        return (0, self._get_enm_iso_mount_line())

    def _mock_run_command_unmount_03(self, command, timeout_secs=0, do_logging=False):
        return (0,
                self._get_enm_iso_mount_line() + self._get_litp_iso_mount_line())

    def _mock_run_command_unmount_04(self, command, timeout_secs=0, do_logging=False):
        if 'umount' in command:
            return (0, '')
        else:
            self.mount_count += 1
            if self.mount_count == 1:
                return (0, self._get_enm_iso_mount_line())
            else:
                if self.second_mount:
                    return (0, self._get_enm_iso_mount_line())
                else:
                    return (0, '')

    def test_unmount_iso_image_01(self):
        self.mount_dir = '/mnt'
        self.prechecks.assert_mount_dir_empty = lambda x: True

        # --- Nothing originally mounted ---
        self.prechecks.run_command = self._mock_run_command_unmount_01
        expected_hdr = self.get_msg('CHECKING_FOR_MOUNTED_IMAGE', True).format(self.mount_dir)
        expected_msg = self.get_msg('MOUNT_DIRECTORY_NOT_USED').format(self.mount_dir)
        self.call_method_and_assert_msgs(self.prechecks.unmount_iso_image, success_msg=expected_msg, hdr_msg=expected_hdr)

        # --- A mount but User discontinues unmount action ---
        self.prechecks.run_command = self._mock_run_command_unmount_02
        self.prechecks.prompt_user_boolean = self._mock_prompt_user_boolean_false
        expected_msg = self.get_msg('UNMOUNT_MANUALLY').format(self.prechecks.current_action)
        self.call_method_and_assert_msgs(self.prechecks.unmount_iso_image, msg=expected_msg)

        # --- A mount plus nested mounts ---
        self.prechecks.run_command = self._mock_run_command_unmount_03
        self.prechecks.prompt_user_boolean = self._mock_prompt_user_boolean_true
        expected_err = self.get_msg('NESTED_MOUNTS_FOUND').format(self.mount_dir)
        self.call_method_and_assert_msgs(self.prechecks.unmount_iso_image, err_msg=expected_err)

        # -- A mount but the unmount attempt fails ---
        self.mount_count = 0
        self.second_mount = True
        self.prechecks.run_command = self._mock_run_command_unmount_04
        self.prechecks.prompt_user_boolean = self._mock_prompt_user_boolean_true
        expected_err = self.get_msg('MOUNT_DIRECTORY_IS_BUSY').format(self.mount_dir)
        self.call_method_and_assert_msgs(self.prechecks.unmount_iso_image, err_msg=expected_err)

        # -- A mount and the unmount attempt succeeds ---
        self.mount_count = 0
        self.second_mount = False
        expected_msg = self.get_msg('SUCCESSFULLY_UNMOUNTED').format(self.mount_dir)
        self.call_method_and_assert_msgs(self.prechecks.unmount_iso_image, success_msg=expected_msg)

    @patch('os.listdir')
    def test_unmount_iso_image_02(self, mock_lister):
        mount_dir = '/mnt'
        self.prechecks.run_command = self._mock_run_command_unmount_01

        # --- No content in mount directory ---
        mock_lister.return_value = []
        self.prechecks.unmount_iso_image()

        # --- No content in mount directory ---
        mock_lister.return_value = ['file1', 'file2', 'dir1', 'dir2']
        expected_msg = self.get_msg('DIRECTORY_NOT_EMPTY').format(mount_dir)
        self.call_method_and_assert_msgs(self.prechecks.unmount_iso_image, msg=expected_msg)

    def _mock_run_command_vcs_group_cs_full(self, command, timeout_secs=0, do_logging=False):
        return (0, "db_cluster Grp_CS_db_cluster_jms_clustered_service           db-1  active-standby lsb   OFFLINE OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_jms_clustered_service           db-2  active-standby lsb   ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_mysql_clustered_service         db-1  active-standby lsb   OFFLINE OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_mysql_clustered_service         db-2  active-standby lsb   ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_postgres_clustered_service      db-1  active-standby lsb   OFFLINE OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_postgres_clustered_service      db-2  active-standby lsb   ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_elasticsearch_clustered_service db-1  active-standby lsb   OFFLINE OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_elasticsearch_clustered_service db-2  active-standby lsb   ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_opendj_clustered_service        db-1  parallel       lsb   ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_opendj_clustered_service        db-2  parallel       lsb   ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_versant_clustered_service       db-1  active-standby mixed ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_versant_clustered_service_1     db-2  active-standby mixed OFFLINE OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_sg_neo4j_clustered_service      db-1  parallel       lsb   ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_sg_neo4j_clustered_service      db-2  parallel       lsb   ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_modeldeployment_cluster_service_1    db-1  active-standby lsb ONLINE  OK -\n" + \
                   "db_cluster Grp_CS_db_cluster_modeldeployment_clustered_service_1  db-2  active-standby lsb OFFLINE OK -\n")

    def test_get_db_systems(self):

        self.prechecks.run_command = self._mock_run_command_vcs_group_cs_full

        for service in ('elasticsearch', 'opendj', 'versant', 'jms',
                        'mysql', 'postgres', 'neo4j', 'modeldeployment'):
            nodes = self.prechecks.get_db_systems_by_service(service)
            self.assertEquals(2, len(nodes))

    def test_check_for_corrupted_indexes(self):
        err_suffix = self.get_msg('REFER_TO_ELASTICSEARCH_BUR_SAG')

        # -- No faulted indices ---
        self.prechecks.run_command = self._mocked_run_command_elasticsearch_01
        expected_msg = self.get_msg('CHECKING_ELASTICSEARCH_INDEXES')
        indexes = self.call_method_and_assert_msgs(self.prechecks.check_for_corrupted_indexes, err_suffix, msg=expected_msg)
        self.assertEquals([], indexes)

        # --- Return faulted index ---
        self.prechecks.run_command = self._mocked_run_command_elasticsearch_02
        expected_indexes = ['enm_logs-application-2018.02.20',
                            'enm_logs-application-2018.02.23']
        self.assertEquals(expected_indexes, self.prechecks.check_for_corrupted_indexes(err_suffix))

        # --- Error returned by curl ---
        self.prechecks.run_command = self._mocked_run_command_elasticsearch_03
        expected_err = self.get_msg('FAILED_TO_RUN_COMMAND').format('elasticsearch curl')
        self.call_method_and_assert_msgs(self.prechecks.check_for_corrupted_indexes, '', err_msg=expected_err)

        # --- Elasticsearch has no indexes ---
        self.prechecks.run_command = self._mocked_run_command_elasticsearch_04
        expected_err = self.get_msg('COULD_NOT_RETRIEVE_HEALTH_OF_ELASTICSEARCH_INDEXES') + err_suffix
        self.call_method_and_assert_msgs(self.prechecks.check_for_corrupted_indexes, err_suffix, err_msg=expected_err, add_suffix=False)

    def _gen_boot_partition_test_success_msg(self):
        return ('1+0 records in\n' +
                '1+0 records out\n' +
                '1024 bytes (1.0 kB) copied, 0.00748487 s, 137 kB/s')

    def _mock_boot_partition_test(self, system):
        self.boot_partition_test_count += 1
        if self.boot_partition_test_count == 1:
            return self.boot_partition_test_error_msg1
        else:
            if self.boot_partition_test_error_msg2:
                return self.boot_partition_test_error_msg2
            else:
                return self._gen_boot_partition_test_success_msg()

    def test_handle_boot_partition(self):

        system = 'db-1'
        self.prechecks.mco_agent.boot_partition_test_cleanup = lambda x: True

        # --- /boot already mounted and writable ---
        self.prechecks.mco_agent.boot_partition_test = lambda x: self._gen_boot_partition_test_success_msg()
        self.prechecks.handle_boot_partition(system)

        # --- /boot write errors ---
        self.prechecks.mco_agent.boot_partition_mount = lambda x: True
        self.prechecks.mco_agent.boot_partition_test = self._mock_boot_partition_test

        expected_msg1 = self.get_msg('BOOT_PARTITION_NOT_AVAILABLE').format(system)
        for error_txt in ('error',
                          'Input/output error',
                          'Read-only file system'):
            self.prechecks.print_message = MagicMock()

            self.boot_partition_test_count = 0
            self.boot_partition_test_error_msg1 = error_txt

            # --- /boot mounted successfully on 2nd attempt ---
            self.boot_partition_test_error_msg2 = None
            expected_msg2 = self.get_msg('BOOT_PARTITION_AVAILABLE').format(system)
            self.call_method_and_assert_msgs(self.prechecks.handle_boot_partition, system, success_msg=expected_msg2, msg=expected_msg1)

            # --- /boot did not mount on 2nd attempt ---
            self.boot_partition_test_error_msg2 = 'some error writing to /boot'
            expected_msg3 = self.get_msg('BOOT_PARTITION_REMAINS_UNAVAILABLE').format(system)
            self.call_method_and_assert_msgs(self.prechecks.handle_boot_partition, system, err_msg=expected_msg3, msg=expected_msg1)

    @patch('enm_upgrade_prechecks.SanHealthChecks')
    @patch('enm_upgrade_prechecks.get_nas_type')
    def test_san_alert_check_not_unityxt(self, nas_type, san_hc):
        expected_hdr = self.get_msg('CHECKING_SAN_STORAGE_FOR_ALERTS', True)
        nas_type.return_value = 'vnx'
        san_hc.return_value.san_critical_alert_healthcheck.side_effect = None
        skip_msg = 'SKIPPING NAS SERVER IMBALANCE CHECK. Only applicable to ENM on Rackmount Servers.'
        expected_success = 'Successfully Completed SAN alert Healthcheck'
        self.prechecks.print_message = MagicMock()
        self.prechecks.print_action_heading = MagicMock()
        self.prechecks.print_error = MagicMock()
        self.prechecks.log.debug = MagicMock()
        self.call_method_and_assert_msgs(self.prechecks.san_alert_check, hdr_msg=expected_hdr)
        self.prechecks.log.debug.assert_any_call(skip_msg)
        self.prechecks.print_message.assert_any_call(expected_success)

    @patch('enm_upgrade_prechecks.SanHealthChecks')
    @patch('enm_upgrade_prechecks.get_nas_type')
    def test_san_alert_check_not_unityxt_alerts_found(self, nas_type, san_hc):
        expected_hdr = self.get_msg('CHECKING_SAN_STORAGE_FOR_ALERTS', True)
        self.prechecks.print_message = MagicMock()
        self.prechecks.print_action_heading = MagicMock()
        self.prechecks.print_error = MagicMock()
        nas_type.return_value = 'vnx'
        san_hc.return_value.san_critical_alert_healthcheck.side_effect = SystemExit
        error_msg = self.get_msg('SAN_ALERT_CHECK_FAILED')
        critical_alerts_msg = 'There are critical alerts on the SAN Storage.'
        try:
            self.prechecks.san_alert_check()
        except SystemExit as err:
            self.assertEqual(1, err.code)
        self.prechecks.print_action_heading.assert_any_call(expected_hdr)
        self.prechecks.print_error.assert_any_call(error_msg)
        self.prechecks.print_message.assert_any_call(critical_alerts_msg)

    @patch('enm_upgrade_prechecks.SanFaultCheck')
    @patch('enm_upgrade_prechecks.SanCleanup')
    @patch('enm_upgrade_prechecks.SanHealthChecks')
    @patch('enm_upgrade_prechecks.get_nas_type')
    def test_san_alert_check_unityxt_pass(self, nas_type, san_hc, san_cleanup, san_fault):
        expected_success = 'Successfully Completed SAN alert Healthcheck'
        expected_hdr = self.get_msg('CHECKING_SAN_STORAGE_FOR_ALERTS', True)
        nas_type.return_value = 'unityxt'
        san_hc.return_value.san_critical_alert_healthcheck.side_effect = None
        san_cleanup.get_san_info.return_value = {'san' : ['spa_ip', 'spb_ip', 'san_site_id',
                                                          'login_scope', 'san_type', 'username',
                                                          'password']}
        san_fault.return_value.check_nas_servers.return_value = None
        san_fault.return_value.nas_server_fault = False
        self.call_method_and_assert_msgs(self.prechecks.san_alert_check, hdr_msg=expected_hdr,
                                         msg=expected_success)

    @patch('enm_upgrade_prechecks.SanFaultCheck')
    @patch('enm_upgrade_prechecks.SanCleanup')
    @patch('enm_upgrade_prechecks.SanHealthChecks')
    @patch('enm_upgrade_prechecks.get_nas_type')
    def test_san_alert_check_unityxt_raise_exception(self, nas_type, san_hc, san_cleanup, san_fault):
        expected_hdr = self.get_msg('CHECKING_SAN_STORAGE_FOR_ALERTS', True)
        self.prechecks.print_action_heading = MagicMock()
        self.prechecks.print_error = MagicMock()
        nas_type.return_value = 'unityxt'
        san_hc.return_value.san_critical_alert_healthcheck.side_effect = None
        san_cleanup.get_san_info.return_value = {'san' : ['spa_ip', 'spb_ip', 'san_site_id',
                                                          'login_scope', 'san_type', 'username',
                                                          'password']}
        san_fault.return_value.check_nas_servers.side_effect = Exception
        self.assertRaises(Exception, self.prechecks.san_alert_check, True)
        try:
            self.prechecks.san_alert_check()
        except Exception as err:
            self.prechecks.print_error.assert_any_call(err)
            self.assertEqual(1, err.code)
        self.prechecks.print_action_heading.assert_any_call(expected_hdr)

    @patch('enm_upgrade_prechecks.SanFaultCheck')
    @patch('enm_upgrade_prechecks.SanCleanup')
    @patch('enm_upgrade_prechecks.SanHealthChecks')
    @patch('enm_upgrade_prechecks.get_nas_type')
    def test_san_alert_check_unityxt_fail(self, nas_type, san_hc, san_cleanup, san_fault):
        expected_hdr = self.get_msg('CHECKING_SAN_STORAGE_FOR_ALERTS', True)
        nas_type.return_value = 'unityxt'
        san_hc.return_value.san_critical_alert_healthcheck.return_value = None
        san_cleanup.return_value.get_san_info.return_value = {'san' : ['spa_ip', 'spb_ip', 'san_site_id',
                                                        'login_scope', 'san_type', 'username',
                                                        'password']}
        san_fault_instance = san_fault.return_value
        san_fault_instance.check_nas_servers.return_value = None
        san_fault_instance.nas_server_fault.return_value = True
        imbalance_msg = 'NAS server imbalance detected.'
        error_msg = self.get_msg('SAN_ALERT_CHECK_FAILED')
        self.prechecks.print_action_heading = MagicMock()
        self.prechecks.print_error = MagicMock()
        self.prechecks.print_message = MagicMock()
        try:
            self.prechecks.san_alert_check()
        except SystemExit as err:
            self.assertEqual(1, err.code)
        self.prechecks.print_action_heading.assert_called_once_with(expected_hdr)
        self.prechecks.print_message.assert_any_call(imbalance_msg)
        self.prechecks.print_error.assert_called_once_with(error_msg)

    def _gen_pvscan_success_msg(self):
        return ('PV /dev/vx/dmp/vmdk0_1s2 VG vg_root lvm2 [299.51 GiB / 10.51 GiB free]\n' +
                'Total: 1 [299.51 GiB] / in use: 1 [299.51 GiB] / in no VG: 0 [0 ]\n')

    def _mocked_pvscan(self, system):
        lun_scan = 'PV /dev/vx/dmp/emc_clariion0_78 VG vg_app lvm2 [150.00 GiB / 45.00 GiB free]\n'
        self._mocked_pvscan_count += 1

        pvscan = self._gen_pvscan_success_msg()

        if self._mocked_pvscan_count == self.change_pvscan_on_count:
            return lun_scan + pvscan
        return pvscan

    def _mock_lvm_conf_global_filter(self, system):
        self.get_global_filter_count += 1

        gfilter = ('[ "r|^/dev/(sda)[0-9]*$|", ' +
                     '"r|/dev/VxDMP.*|", ' +
                     '"r|/dev/vx/dmpconfig|", ' +
                     '"r|/dev/vx/rdmp/.*|", ' +
                     '"r|/dev/dm-[0-9]*|", ' +
                     '"r|/dev/mpath/mpath[0-9]*|", ' +
                     '"r|/dev/mapper/mpath[0-9]*|", ')

        if ((self.get_global_filter_count == 1 and self.include_sd_path == TestEnmPrechecks.FIRST_ATTEMPT)
             or \
            (self.get_global_filter_count == 2 and self.include_sd_path == TestEnmPrechecks.SECOND_ATTEMPT)):
            gfilter += 'r|^/dev/sd.*|, '

        gfilter += ']'
        return gfilter

    def _mock_lvm_conf_global_filter_multiline(self, system):
        return ('[ "r|^/dev/(sda)[0-9]*$|",\n' +
                  '"r|/dev/VxDMP.*|",\n' +
                  '"r|/dev/vx/dmpconfig|",\n' +
                  '"r|/dev/vx/rdmp/.*|",\n' +
                  '"r|/dev/dm-[0-9]*|",\n' +
                  '"r|/dev/mpath/mpath[0-9]*|",\n' +
                  '"r|/dev/mapper/mpath[0-9]*|",\n]')


    def do_setup_for_handle_lvm_conf_global_filter(self, sys_id, service_id):
        system = 'db-' + sys_id
        service = 'maybe-versant' + service_id
        self.change_pvscan_on_count = -1
        self._mocked_pvscan_count = 0
        self.get_global_filter_count = 0
        self.prechecks.mco_agent.lvm_conf_backups_cleanup = lambda x: True
        self.prechecks.mco_agent.physical_volume_scan = self._mocked_pvscan
        return (system, service)

    def test_handle_lvm_conf_global_filter_01(self):
        (system, service) = self.do_setup_for_handle_lvm_conf_global_filter('1', '1')

        # --- Corrupt (multiline) lvm.conf global-filter ---
        self.prechecks.mco_agent.get_lvm_conf_global_filter = self._mock_lvm_conf_global_filter_multiline
        expected_err = self.get_msg('CORRUPTED_PROPERTIES_FILE').format(self.lvm_dot_conf, system)
        self.call_method_and_assert_msgs(self.prechecks.handle_lvm_conf_global_filter, system, err_msg=expected_err)

        # --- global-filter does not have sd disk path and update fails ---
        (system, service) = self.do_setup_for_handle_lvm_conf_global_filter('1', '1')
        self.include_sd_path = 0
        self.prechecks.mco_agent.backup_lvm_conf = lambda x: True
        self.prechecks.mco_agent.update_lvm_conf_global_filter = lambda x: True
        self.prechecks.mco_agent.get_lvm_conf_global_filter = self._mock_lvm_conf_global_filter
        expected_err = self.get_msg('CONFIG_FILE_NOT_IN_CORRECT_FORMAT').format(self.lvm_dot_conf, system, system)
        self.call_method_and_assert_msgs(self.prechecks.handle_lvm_conf_global_filter, system, err_msg=expected_err)

    def test_handle_lvm_conf_global_filter_02(self):
        (system, service) = self.do_setup_for_handle_lvm_conf_global_filter('2', '2')
        self.include_sd_path = TestEnmPrechecks.FIRST_ATTEMPT

        # --- global-filter already has sd disk path ---
        self.prechecks.mco_agent.get_lvm_conf_global_filter = self._mock_lvm_conf_global_filter
        expected_msg = self.get_msg('CONFIG_FILE_IS_COMPLETE').format(self.lvm_dot_conf, system)
        self.call_method_and_assert_msgs(self.prechecks.handle_lvm_conf_global_filter, system, success_msg=expected_msg)

        # --- global-filter does not have sd disk path, the update succeeds, 2nd pvscan matches 1st ---
        (system, service) = self.do_setup_for_handle_lvm_conf_global_filter('2', '2')
        self.include_sd_path = TestEnmPrechecks.SECOND_ATTEMPT
        self.prechecks.mco_agent.get_lvm_conf_global_filter = self._mock_lvm_conf_global_filter
        self.prechecks.print_success = MagicMock()
        self.prechecks.handle_lvm_conf_global_filter(system)

        msg1 = self.get_msg('CONFIG_FILE_SUCCESSFULLY_UPDATED').format(self.lvm_dot_conf, system)
        msg2 = self.get_msg('PVSCAN_COMPARISON_CORRECT').format(self.lvm_dot_conf, system)
        self.prechecks.print_success.assert_has_calls([call(msg1), call(msg2)])

        # --- global-filter does not have sd disk path, update succeeds, 2nd pvscan differs from 1st ---
        (system, service) = self.do_setup_for_handle_lvm_conf_global_filter('2', '2')
        self.change_pvscan_on_count = TestEnmPrechecks.SECOND_ATTEMPT
        self.include_sd_path = TestEnmPrechecks.SECOND_ATTEMPT
        self.prechecks.mco_agent.get_lvm_conf_global_filter = self._mock_lvm_conf_global_filter
        self.prechecks.print_success = MagicMock()
        self.prechecks.print_error = MagicMock()
        try:
            self.prechecks.handle_lvm_conf_global_filter(system)
        except SystemExit as e:
            self.assertEqual(1, e.code)
        expected_msg1 = self.get_msg('CONFIG_FILE_SUCCESSFULLY_UPDATED').format(self.lvm_dot_conf, system)
        expected_msg2 = self.get_msg('PVSCAN_COMPARISON_FAILED').format(self.lvm_dot_conf, system, self.lvm_dot_conf, system)
        self.prechecks.print_success.assert_called_with(expected_msg1)
        self.prechecks.print_error.assert_called_with(expected_msg2)

    @patch('enm_upgrade_prechecks.GrubConfCheck')
    @patch('enm_upgrade_prechecks.report_tab_data')
    @patch('enm_upgrade_prechecks.GrubConfCheck.report_lvs')
    @patch('enm_upgrade_prechecks.is_env_on_rack')
    def test_check_grub_cfg_lvs(self, is_on_rack, report_lvs, tab_data, grub):
        expected_hdr = self.get_msg('CHECKING_ALL_LVs_ARE_IN_GRUB.CFG', True)

        # NOT on Blade
        is_on_rack.return_value = True
        skip_msg = 'SKIPPING THE CHECK NOT applicable to ENM on Rackmount Servers.'
        self.call_method_and_assert_msgs(self.prechecks.check_grub_cfg_lvs, hdr_msg=expected_hdr,
                                         msg=skip_msg)

        # On Blade + Check Successful
        is_on_rack.return_value = False
        report_lvs.return_value = 'report for testing'
        grub.return_value.grub_lvs_check_failed = False
        tab_data.return_value = 'data in a table for testing'
        start_msg = 'STARTING GRUB.CFG LV CHECK'
        complete_msg = 'Successfully Completed grub.cfg Healthcheck'
        success_msg = self.get_msg('GRUB.CFG_LV_CHECK_PASSED')
        self.call_method_and_assert_msgs(self.prechecks.check_grub_cfg_lvs, hdr_msg=expected_hdr,
                                         success_msg=success_msg)
        self.prechecks.print_message.assert_any_call(start_msg)
        self.prechecks.print_message.assert_any_call(complete_msg)

        # On Blade + Check Failed
        grub.return_value.grub_lvs_check_failed = True
        mismatch_msg = 'There is one or more mismatch between LVs in the model and LVs in grub.cfg '
        error_msg = self.get_msg('GRUB.CFG_LV_CHECK_FAILED')
        self.call_method_and_assert_msgs(self.prechecks.check_grub_cfg_lvs, hdr_msg=expected_hdr,
                                         err_msg=error_msg)
        self.prechecks.print_message.assert_any_call(mismatch_msg)

    def _mocked_handle_success(self, system):
        pass

    def _mocked_dmidecode_output_negative(self, cmd):
        manufacturers = ['Red Hat', 'VMware Inc.', 'Virtualbox',
                         'QEMU', 'KVM']
        vm_manufacturer = manufacturers[random.randint(0, 4)]
        return (0, vm_manufacturer)

    def _mocked_dmidecode_output_positive(self, cmd):
        return (0, 'Dell Inc.')

    def test_is_virtual_environment(self):
        self.prechecks.run_command = self._mocked_dmidecode_output_positive
        self.assertFalse(self.prechecks.is_virtual_environment())

        self.prechecks.run_command = self._mocked_dmidecode_output_negative
        self.assertTrue(self.prechecks.is_virtual_environment())

    def _mocked_get_system_names(self, cluster_type):
        return ['db-1', 'db-2', 'db-3', 'db-4']

    def _mocked_get_zero_system_names(self, cluster):
        return []

    def test_storage_setup(self):
        # --- Do nothing for Virtual Environment ---
        self.prechecks.is_virtual_environment = lambda: True
        self.prechecks.check_db_disk_storage_setup()

        self.prechecks.is_virtual_environment = lambda: False

        # ---- Two Versant DB nodes & four total DB nodes----

        self.prechecks.get_db_systems_by_service = self._mock_get_db_systems
        self.prechecks.handle_boot_partition = self._mocked_handle_success
        self.prechecks.handle_lvm_conf_global_filter = self._mocked_handle_success
        self.prechecks.check_disks_device_mapper = self._mocked_handle_success
        self.prechecks.get_running_systems_by_cluster = self._mocked_get_system_names

        # ---- No DB nodes found ----
        self.prechecks.get_running_systems_by_cluster = self._mocked_get_zero_system_names
        expected_msg = self.get_msg('NO_DB_SVC_SYSTEMS_FOUND').format(self.prechecks.current_action)
        self.call_method_and_assert_msgs(self.prechecks.check_db_disk_storage_setup, msg=expected_msg)

        expected_hdr = self.get_msg('CHECKING_DISK_STORAGE', True)
        self.call_method_and_assert_msgs(self.prechecks.check_db_disk_storage_setup, hdr_msg=expected_hdr)

    def _mock_get_count_dmsetup_deps_non_dm(self, system):
        self.get_count_dmsetup_deps_non_dm_count += 1
        return self.get_count_dmsetup_deps_non_dm_return_vals[self.get_count_dmsetup_deps_non_dm_count-1]

    def _mock_prompt_user_re_multipath(self, prompt):
        expected_prompt = self.get_msg('NON_MULTIPATHED_VOLUMES_PRESENT').format('db-1')
        self.assertEqual(prompt, expected_prompt)
        return True

    def _mock_node_checker(self, system):
        return False

    @patch('enm_upgrade_prechecks.is_env_on_rack')
    @patch('time.sleep')
    def test_handle_dmsetup_and_reboot(self, mock_sleep, is_rack):

        system = 'db-1'
        action_key = 'stop_vcs_and_reboot'
        is_rack.return_value = False

        self.prechecks.mco_agent.get_count_dmsetup_deps_non_dm = self._mock_get_count_dmsetup_deps_non_dm
        self.prechecks.mco_agent.stop_vcs_and_reboot = lambda x: True
        self.prechecks.is_reachable_node = lambda x: True

        self.prechecks.prompt_user_boolean = self._mock_prompt_user_re_multipath

        # --- Zero disk paths not using VxDMP ---
        self.get_count_dmsetup_deps_non_dm_count = 0
        self.get_count_dmsetup_deps_non_dm_return_vals = ['0']
        expected_msg = self.get_msg('NO_ACTION_REQUIRED_FOR_LVM_MULTIPATHING').format(system)
        self.call_method_and_assert_msgs(self.prechecks.check_disks_device_mapper, [system], success_msg=expected_msg)

        # --- One path not using VxDMP, reboot success, still one path not using VxVMP ---
        self.get_count_dmsetup_deps_non_dm_count = 0
        self.get_count_dmsetup_deps_non_dm_return_vals = ['1', '1']
        expected_err = self.get_msg('ERRORS_IN_VOLUME_MULTIPATHING').format(system)
        expected_msg = self.get_msg('REBOOTING_AND_WAITING_TWO_MINUTES').format(system)
        self.call_method_and_assert_msgs(self.prechecks.check_disks_device_mapper, [system], err_msg=expected_err, msg=expected_msg)

        # --- One path not using VxDMP, reboot success, then all paths using VxVMP ---
        self.get_count_dmsetup_deps_non_dm_count = 0
        self.get_count_dmsetup_deps_non_dm_return_vals = ['1', '0']
        expected_msg = self.get_msg('LVM_MULTIPATH_CORRECTLY_SETUP').format(system)
        self.call_method_and_assert_msgs(self.prechecks.check_disks_device_mapper, [system], success_msg=expected_msg)

        self.prechecks.run_mco_agent_action = MagicMock()
        self.prechecks.run_mco_agent_action.returnValue = None

        expected_err = self.get_msg('REBOOT_FAILURE').format(system)
        self.call_method_and_assert_msgs(self.prechecks.handle_dmsetup_and_reboot, system, self._mock_node_checker, err_msg=expected_err)

        self.prechecks.get_non_dev_mapper_count = lambda x: '1'
        self.prechecks.handle_dmsetup_and_reboot = lambda x, y: None
        self.prechecks.check_disks_device_mapper(system)
        self.prechecks.run_mco_agent_action.assert_called_once_with(action_key, system)

    def _mocked_requests_get(*args, **kwargs):
        class MockResponse(object):
            def __init__(self, status_code):
                self.status_code = status_code

            def get_status_code(self):
                return self.status_code

        if args[0] == 'http://success:8080/mediationservice/res/health'\
                or args[0] == 'http://success:8558/enm-dp-akka-cluster/bootstrap/seed-nodes':
            return MockResponse(200)
        elif args[0] == 'http://failure:8080/mediationservice/res/health'\
                or args[0] == 'http://failure:8558/enm-dp-akka-cluster/bootstrap/seed-nodes':
            return MockResponse(400)

        raise requests.exceptions.RequestException

    @mock.patch('requests.get', side_effect=_mocked_requests_get)
    def test_curl_command(self, mock_get):

        status_code = self.prechecks.check_fallback_vms('success', False)
        self.assertEqual(status_code, 200)

        status_code = self.prechecks.check_fallback_vms('failure', True)
        self.assertEqual(status_code, 400)

        connection_error = self.prechecks.check_fallback_vms('connectionError', False)
        self.assertEqual(connection_error, 'connectionError')

        with self.assertRaises(ValueError):
            self.prechecks.check_fallback_vms('', True)

    def test_check_fallback_status(self):
        self.prechecks.print_success = MagicMock()
        expected_hdr = self.get_msg('CHECKING_FALLBACK')
        test_file_path = os.path.dirname(__file__)

        # --- Pass check because no file exists ---
        self.prechecks.check_fallback_status()
        expected_msg = self.get_msg('SKIPPING_FALLBACK_CHECK_AS_FILE_DOES_NOT_EXIST')
        self.prechecks.print_success.assert_any_call(expected_msg)

        # --- Failed check because unable to retrieve ip ---
        fallback_check_file = os.path.join(test_file_path, '../Resources/fallback_check_empty.ini')
        enm_upgrade_prechecks.EnmPreChecks.FALLBACK_SED = fallback_check_file

        expected_err = self.get_msg('FALLBACK_CHECK_FAILED_CANNOT_FIND_IP_ADDRESS')
        self.call_method_and_assert_msgs(self.prechecks.check_fallback_status, err_msg=expected_err, add_suffix=False)

        # --- Failed check due to invalid ip ---
        fallback_check_file = os.path.join(test_file_path, '../Resources/fallback_check_data.ini')
        enm_upgrade_prechecks.EnmPreChecks.FALLBACK_SED = fallback_check_file

        self.prechecks.check_fallback_vms = self._mocked_failure_check_fallback_vms
        expected_err = self.get_msg('FALLBACK_CHECK_FAILED_CONNECTION_ERROR')
        self.call_method_and_assert_msgs(self.prechecks.check_fallback_status,
                                         hdr_msg=expected_hdr, err_msg=expected_err, add_suffix=False)

        # --- Pass check ---
        expected_msg = self.get_msg('FALLBACK_IS_ONLINE_CHECK_WAS_SUCCESSFUL')
        self.prechecks.check_fallback_vms = self._mocked_succesful_check_fallback_vms
        self.prechecks.check_fallback_status()
        self.prechecks.print_success.assert_any_call(expected_msg)

        # --- Failed check due to invalid response ---
        expected_err = self.get_msg('FALLBACK_CHECK_FAILED')
        self.prechecks.check_fallback_vms = self._mocked_unsuccesful_check_fallback_vms
        self.call_method_and_assert_msgs(self.prechecks.check_fallback_status, err_msg=expected_err, add_suffix=False)

    @patch('logging.Logger.info')
    @patch('enm_upgrade_prechecks.LitpRestClient')
    @patch('enm_upgrade_prechecks.ExitCodes')
    @patch('enm_upgrade_prechecks.EnmPreChecks.run_command')
    @patch('enm_upgrade_prechecks.EnmPreChecks.print_action_heading')
    @patch('enm_upgrade_prechecks.EnmPreChecks.print_error')
    @patch('enm_upgrade_prechecks.EnmPreChecks.print_success')
    @patch('enm_upgrade_prechecks.puppet_trigger_wait')
    def test_restart_puppet_services(self, mock_trigger_wait, mock_print_success,
                                     mock_print_error, mock_print_action_heading,
                                     mock_run_command, mock_exit_codes,
                                     mock_litp_rest_client, mock_info):
        instance = EnmPreChecks()

        # Mock LitpRestClient
        mock_litp_instance = Mock()
        mock_litp_instance.is_plan_running.return_value = False
        mock_litp_rest_client.return_value = mock_litp_instance

        # Mock run_command
        def run_command_side_effect(command):
            if 'puppet' in command:
                return 0, 'None'

        mock_run_command.side_effect = run_command_side_effect
        mock_exit_codes.OK = 0
        instance.restart_puppet_services()
        mock_trigger_wait.return_value = None

        # Assertions
        mock_info.assert_any_call('Checking if litp plan is running')
        mock_info.assert_any_call('No running litp plan found')
        mock_info.assert_any_call('Waiting for ongoing catalog runs to complete')
        mock_info.assert_any_call('Catalog runs have completed')
        mock_info.assert_any_call('Stopping Service puppetdb_monitor')
        mock_info.assert_any_call('Service puppetdb_monitor stop : successful')
        mock_info.assert_any_call('Starting Service puppetserver_monitor')
        mock_info.assert_any_call('Service puppetserver_monitor stop : successful')
        mock_info.assert_any_call('Restarting Service puppetdb')
        mock_print_action_heading.assert_called_once()
        mock_trigger_wait.assert_called_once()
        mock_litp_instance.is_plan_running.assert_called_once_with('plan')
        mock_run_command.assert_any_call('/usr/bin/systemctl restart puppetdb')
        mock_run_command.assert_any_call('/usr/bin/systemctl restart puppetserver')
        mock_run_command.assert_any_call('/usr/bin/systemctl start puppetserver_monitor')
        mock_run_command.assert_any_call('/usr/bin/systemctl stop puppetdb_monitor')
        self.assertFalse(mock_print_error.called)
        expected_msg = self.get_msg('RESTARTING OF PUPPET SERVICES WAS SUCCESSFUL')
        self.prechecks.print_success.assert_any_call(expected_msg)
        mock_print_success.assert_called_once()

    @patch('enm_upgrade_prechecks.LitpRestClient')
    @patch('enm_upgrade_prechecks.EnmPreChecks.run_command')
    @patch('enm_upgrade_prechecks.puppet_trigger_wait')
    def test_restart_puppet_services_failure(self, mock_trigger_wait, mock_run_command,
                                             mock_litp_rest_client):
        instance = EnmPreChecks()

        # Mock LitpRestClient
        mock_litp_instance = Mock()
        mock_litp_instance.is_plan_running.return_value = False
        mock_litp_rest_client.return_value = mock_litp_instance

        # Mock run_command
        def run_command_side_effect(command):
            if 'puppetdb' in command:
                return 1, 'PuppetDB failed to restart.'

        mock_run_command.side_effect = run_command_side_effect
        with self.assertRaises(SystemExit) as sys_exit:
            instance.restart_puppet_services()
        mock_trigger_wait.return_value = None

        # Assertions
        self.assertRaises(SystemExit)
        expected_err = self.get_msg('Stopping service puppetdb_monitor : PuppetDB failed to restart.')
        self.call_method_and_assert_msgs(self.prechecks.restart_puppet_services, err_msg=expected_err, add_suffix=False)

    @patch('enm_upgrade_prechecks.LitpRestClient')
    @patch('enm_upgrade_prechecks.puppet_trigger_wait')
    def test_restart_puppet_services_plan_running(self, mock_litp_rest_client,
                                                  mock_trigger_wait):
        instance = EnmPreChecks()

        # Mock LitpRestClient
        mock_litp_instance = Mock()
        mock_litp_instance.is_plan_running.return_value = True
        mock_litp_rest_client.return_value = mock_litp_instance
        with self.assertRaises(SystemExit) as sys_exit:
            instance.restart_puppet_services()

        # Assertions
        expected_err = self.get_msg('A plan is currently running, wait for it to '
                                    'complete before restarting puppet services.')
        self.call_method_and_assert_msgs(self.prechecks.restart_puppet_services, err_msg=expected_err, add_suffix=False)
        mock_trigger_wait.assert_not_called()

    @patch('enm_upgrade_prechecks.LitpRestClient')
    def test_perform_service_action_invalid_action(self, mock_litp_rest_client):

        instance = EnmPreChecks()

        # Mock LitpRestClient
        mock_litp_instance = Mock()
        mock_litp_instance.is_plan_running.return_value = False
        mock_litp_rest_client.return_value = mock_litp_instance

        services = ["service1", "service2"]
        action = "invalid_action"
        with self.assertRaises(ValueError) as error:
            instance.perform_service_action(services, action)
        self.assertEqual(str(error.exception), "Invalid action: invalid_action")

    def test_elasticsearch_healthcheck(self):
        err_suffix = self.get_msg('REFER_TO_ELASTICSEARCH_BUR_SAG')

        # --- Pass both subchecks ---
        self.prechecks.print_success = MagicMock()
        self.prechecks.get_db_nodes_by_service = self._mock_get_online_db_nodes
        self.prechecks.run_command = self._mocked_run_command_elasticsearch_01
        self.prechecks.check_elasticsearch_status()
        expected_msg_running = self.get_msg('ELASTICSEARCH_IS_RUNNING').format('db-1')
        expected_msg2 = self.get_msg('ELASTICSEARCH_INDEXES_ARE_HEALTHY')
        for expected_msg in (expected_msg_running, expected_msg2):
            self.prechecks.print_success.assert_any_call(expected_msg)

        # --- Fail due to no online instances ---
        self.prechecks.get_db_nodes_by_service = self._mock_get_offline_db_nodes
        expected_err = self.get_msg('ELASTICSEARCH_STATUS_CHECK_FAILED') + err_suffix
        self.call_method_and_assert_msgs(self.prechecks.check_elasticsearch_status, err_msg=expected_err, add_suffix=False)

        # --- Pass first check but fail due to corrupted indexes ---
        self.prechecks.get_db_nodes_by_service = self._mock_get_online_db_nodes
        self.prechecks.run_command = self._mocked_run_command_elasticsearch_02
        corrupted_indexes = ['enm_logs-application-2018.02.20',
                             'enm_logs-application-2018.02.23']
        expected_err = self.get_msg('ELASTICSEARCH_INDEXES_ARE_CORRUPTED').format(
                                        ', '.join(corrupted_indexes),
                                        ('are' if len(corrupted_indexes) > 1 else 'is')) + err_suffix
        self.call_method_and_assert_msgs(self.prechecks.check_elasticsearch_status, err_msg=expected_err, success_msg=expected_msg_running, add_suffix=False)

    def test_check_litp_model_synchronized(self):
        # --- Model synced with Deployment ---
        self.prechecks.is_virtual_environment = lambda: False
        self.prechecks.run_command = self._mocked_run_command_synchronized_model_01
        expected_msg = self.get_msg('MODEL_SYNCHRONIZED')
        expected_hdr = self.get_msg('CHECKING_MODEL_SYCHRONIZED_WITH_DEPLOYMENT', True)
        self.call_method_and_assert_msgs(self.prechecks.check_litp_model_synchronized, success_msg=expected_msg, hdr_msg=expected_hdr)

        # --- Model not synced with Deployment ---
        self.prechecks.run_command = self._mocked_run_command_synchronized_model_02
        expected_err = self.get_msg('MODEL_NOT_SYNCHRONIZED')
        self.call_method_and_assert_msgs(self.prechecks.check_litp_model_synchronized, err_msg=expected_err)

        # --- Failed to run litp create_plan command ---
        self.prechecks.run_command = self._mocked_run_command_synchronized_model_03
        expected_err = self.get_msg('FAILED_TO_RUN_COMMAND').format('LITP model synchronization check')
        self.call_method_and_assert_msgs(self.prechecks.check_litp_model_synchronized, err_msg=expected_err)

        # --- Do nothing for a Virtual environment ---
        self.prechecks.is_virtual_environment = lambda: True
        self.prechecks.check_litp_model_synchronized()

    def test_is_reachable_node(self):
        for response in (0, 1):
            self.prechecks.run_command = lambda x: (response, None)
            self.prechecks.is_reachable_node('db-1')

    def mock_run_mco_agent_action_sys_state(self, action, system, **kwargs):
        return None, ({'Name' : 'db-1', 'State' : ['RUNNING']},
                      {'Name' : 'db-2', 'State' : ['RUNNING']})

    def test_is_vcs_running_on_node(self):
        self.prechecks.run_mco_agent_action = self.mock_run_mco_agent_action_sys_state
        self.prechecks.is_vcs_running_on_node('db-1')

    @patch('__builtin__.raw_input')
    def test_prompt_user(self, mock_raw_input):
        mock_raw_input.return_value = 'YeS'
        self.assertTrue(self.prechecks.prompt_user_boolean('question'))

        mock_raw_input.return_value = 'n'
        self.assertFalse(self.prechecks.prompt_user_boolean('question'))

        # --- Using assumeyes ---
        self.prechecks.processed_args = Mock()
        self.prechecks.processed_args.assumeyes = True
        self.assertTrue(self.prechecks.prompt_user_boolean('question'))

    def _mocked_ombs_conf_missing_value(self):
        return {'precondition': None}

    def _mocked_ombs_conf(self):
        return {'precondition': 'some/path'}

    def _mock_get_ombs_missing_param(self, section, param_name):
        raise ConfigParser.NoOptionError(param_name, section)

    def _mock_get_ombs_missing_section(self, section, param_name):
        raise ConfigParser.NoSectionError(section)

    def _mocked_ombs_conf_missing_param(self):
        conf = MagicMock()
        conf.get = self._mock_get_ombs_missing_param
        return conf

    def _mocked_ombs_conf_missing_section(self):
        conf = MagicMock()
        conf.get = self._mock_get_ombs_missing_section
        return conf

    def test_deactivate_ombs_backup(self):
        # --- system_backup_lock_file value missing ---
        self.prechecks.create_and_read_ombs_conf = self._mocked_ombs_conf_missing_value
        bos_conf_file = '/opt/ericsson/itpf/bur/etc/bos.conf'
        err_text = "Value missing for parameter 'system_backup_lock_file' in section 'precondition'"
        expected_err = self.get_msg('OMBS_CONF_ERROR').format(bos_conf_file, err_text)
        self.call_method_and_assert_msgs(self.prechecks.deactivate_ombs_backup, err_msg=expected_err)

        # --- Section found in bos.conf ---
        self.prechecks.create_and_read_ombs_conf = self._mocked_ombs_conf

        # --- Backup is inactive ---
        self.prechecks.ombs_lock_file_exists = lambda x: True
        expected_msg = self.get_msg('OMBS_BACKUP_IS_INACTIVE')
        expected_hdr = self.get_msg('DEACTIVATING_OMBS_BACKUP')
        self.call_method_and_assert_msgs(self.prechecks.deactivate_ombs_backup, success_msg=expected_msg, msg_hdr=expected_hdr)

        # -- Does not exist, mock the create-lock-file
        self.prechecks.ombs_lock_file_exists = lambda x: False
        self.prechecks.create_backup_lock_file = lambda z: True
        self.prechecks.deactivate_ombs_backup()

    def test_deactivate_ombs_backup_missing_config_param(self):
        bos_conf_file = '/opt/ericsson/itpf/bur/etc/bos.conf'
        self.prechecks.create_and_read_ombs_conf = self._mocked_ombs_conf_missing_param
        expected_err = self.get_msg('OMBS_CONF_ERROR').format(bos_conf_file,
                              "No option 'system_backup_lock_file' in section: 'precondition'")
        self.call_method_and_assert_msgs(self.prechecks.deactivate_ombs_backup, err_msg=expected_err)

    def test_deactivate_ombs_backup_missing_config_section(self):
        bos_conf_file = '/opt/ericsson/itpf/bur/etc/bos.conf'
        self.prechecks.create_and_read_ombs_conf = self._mocked_ombs_conf_missing_section
        expected_err = self.get_msg('OMBS_CONF_ERROR').format(bos_conf_file,
                                                              "No section: 'precondition'")
        self.call_method_and_assert_msgs(self.prechecks.deactivate_ombs_backup, err_msg=expected_err)

    @patch('__builtin__.open')
    def test_create_backup_lock_file(self, _mock_open):
        def _mocked_open(self, path):
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock()
            mock_context.__exit__ = MagicMock()
            return mock_context

        # --- Succussfully create the lock file ---
        _mock_open.side_effect = _mocked_open
        expected_msg = self.get_msg('OMBS_BACKUP_DEACTIVATED')
        self.call_method_and_assert_msgs(self.prechecks.create_backup_lock_file, 'some/path', success_msg=expected_msg)

        # --- Error occurs while trying to create lock file ---
        _mock_open.side_effect = IOError()
        expected_err = self.get_msg('ERROR_WHILE_DEACTIVATING_OMBS_BACKUP')
        self.call_method_and_assert_msgs(self.prechecks.create_backup_lock_file, 'bogus/path', err_msg=expected_err)

        # --- Error setting ownership on lock file ---
        _mock_open.side_effect = KeyError()
        expected_msg = self.get_msg('OMBS_BACKUP_SET_OWNER_FAILED').format('some/file')
        self.call_method_and_assert_msgs(self.prechecks.create_backup_lock_file, 'some/file', msg=expected_msg)

    @patch('enm_upgrade_prechecks.ConfigParser.SafeConfigParser')
    @patch('os.path.exists', MagicMock(return_value=True))
    def test_create_and_read_ombs_conf(self, conf):
        self.prechecks.create_and_read_ombs_conf()

    @patch('os.path.exists', MagicMock(return_value=False))
    def test_create_and_read_missing_ombs_conf(self):
        bos_conf_file = '/opt/ericsson/itpf/bur/etc/bos.conf'
        expected_err = self.get_msg('OMBS_CONF_ERROR').format(bos_conf_file, 'File not found')
        self.call_method_and_assert_msgs(self.prechecks.create_and_read_ombs_conf, err_msg=expected_err)

    def test_ombs_lock_file_exists(self):
        self.prechecks.ombs_lock_file_exists('file')

    def _mock_load_global_properties(self, filename):
        self.prechecks.global_properties = {'LDAP_ADMIN_PASSWORD': 'encrypted-secret',
                                            'COM_INF_LDAP_ROOT_SUFFIX': 'dc=enmms1,dc=com',
                                            'hqs_persistence_provider_es': 'true',
                                            'enm_deployment_type': 'Extra_Large_ENM_On_Rack_Servers'}

    def _mock_load_garbage_global_properties(self, filename):
        self.prechecks.global_properties = {'garbage': 'bogus'}

    def _mocked_run_command_for_cleartext_password(self, command, timeout_secs=0, do_logging=False):
        return (0, 'decrypted-secret')

    def test_get_cleartext_password(self):
        clear_password = 'decrypted-secret'
        self.prechecks.run_command = self._mocked_run_command_for_cleartext_password
        filename = '/some/file/path'

        self.prechecks.global_properties = {'LDAP_ADMIN_PASSWORD': 'encrypted-secret'}
        self.assertEquals(self.prechecks.get_cleartext_password(filename), clear_password)

        # --- Begin with global-properties not loaded ---

        self.prechecks.global_properties = None
        self.prechecks.load_global_properties = self._mock_load_global_properties
        self.assertEquals(self.prechecks.get_cleartext_password(filename), clear_password)

    def test_process_actions(self):
        self.prechecks.check_litp_model_synchronized = lambda: True
        self.prechecks.san_alert_check = lambda: True
        self.prechecks.check_lvm_conf_non_db_nodes = lambda: True
        self.prechecks.check_grub_cfg_lvs = lambda: True
        self.prechecks.check_db_disk_storage_setup = lambda: True
        self.prechecks.check_elasticsearch_status = lambda: True
        self.prechecks.check_opendj_replication = lambda: True
        self.prechecks.unmount_iso_image = lambda: True
        self.prechecks.remove_packages = lambda: True
        self.prechecks.apply_puppet_timeouts = lambda: True
        self.prechecks.check_fallback_status = lambda: True
        self.prechecks.global_properties = {"hqs_persistence_provider_es": "true"}
        self.prechecks.deactivate_ombs_backup = lambda: True
        self.prechecks.check_https_port_ilo_available = lambda: True
        self.prechecks.remove_seed_file_after_check = lambda: True
        self.prechecks.restart_puppet_services = lambda: True

        arguments_sprint1 = ['litp_model_synchronized_check',
                             'elastic_search_status_check',
                             'unmount_iso_image_check',
                             'remove_packages',
                             'check_fallback_status',
                             'upgrade_prerequisites_check',
                             'restart_puppet_services']
        arguments_sprint2 = ['storage_setup_check',
                             'opendj_replication_check',
                             'deactivate_ombs_backup']
        arguments_sprint3 = ['san_alert_check',
                             'check_lvm_conf_non_db_nodes',
                             'check_grub_cfg_lvs',
                             'check_https_port_ilo_available',
                             'remove_seed_file_after_check']
        arguments = arguments_sprint1 + arguments_sprint2 + arguments_sprint3

        for argument in arguments:
            self.prechecks.process_actions([argument])

    def test_load_global_properties_01(self):
        with patch('__builtin__.open') as mocked_open:
            mm = MagicMock(spec=file)
            mm.__enter__.return_value.readlines.return_value = self._mocked_get_global_properties_not_found()
            mocked_open.return_value = mm
            self.prechecks.load_global_properties('bogus.file')
            self.assertNotEquals(self.prechecks.global_properties.get('LDAP_ADMIN_PASSWORD', None), 'secret')
            self.assertNotEquals(self.prechecks.global_properties.get('COM_INF_LDAP_ROOT_SUFFIX', None), 'dc=apache,dc=com')

    def test_load_global_properties_02(self):
        with patch('__builtin__.open') as mocked_open:
            mm = MagicMock(spec=file)
            mm.__enter__.return_value.readlines.return_value = self._mocked_get_global_properties_found()
            mocked_open.return_value = mm
            self.prechecks.load_global_properties('bogus.file')
            self.assertEquals(self.prechecks.global_properties.get('LDAP_ADMIN_PASSWORD', None), 'secret')
            self.assertEquals(self.prechecks.global_properties.get('COM_INF_LDAP_ROOT_SUFFIX', None), 'dc=apache,dc=com')

    def test_get_ldap_root(self):
        # --- Entry not found in conf file ---
        self.prechecks.global_properties = None
        self.prechecks.load_global_properties = self._mock_load_garbage_global_properties
        self.assertEquals(self.prechecks.get_ldap_root('some_file'), None)

        # --- Entry found ---
        self.prechecks.global_properties = None
        self.prechecks.load_global_properties = self._mock_load_global_properties
        self.assertEquals(self.prechecks.get_ldap_root('some_file'), 'dc=enmms1,dc=com')

    def test_for_coverage(self):

        # --- Cover the print methods ---
        text = 'Test message'
        self.prechecks.print_action_heading(text)
        self.prechecks.print_success(text)
        self.prechecks.print_error(text)
        self.prechecks.print_error(text, add_suffix=False)
        self.prechecks.print_message(text)

        # --- Cover the setting of verbose debug ---
        self.prechecks.processed_args = Mock()
        self.prechecks.processed_args.verbose = True
        self.prechecks.set_verbosity_level()
        self.prechecks.log_mco_action('sample_action1', 'host1')
        self.prechecks.log_mco_action('sample_action2', 'host2', arg1="value1", arg2="value2")
        self.prechecks.log_mco_action('get_replication_status', 'host1')

    def _mocked_mco_action_handler(self, system):
        raise McoAgentException("something went wrong with MCO")

    def _mocked_mco_action_handler_2(self, system):
        raise McoAgentException({'retcode' : 1, 'err' : 'dummy_error'})

    def _mocked_mco_action_handler_3(self, system):
        raise McoAgentException({'retcode': 1, 'out': 'dummy_error'})

    def test_run_mco_agent_action(self):

        action_key = 'test_mco_action_handler'
        self.prechecks.mco_agent.test_mco_action_handler = self._mocked_mco_action_handler

        expected_err = self.get_msg('FAILED_TO_RUN_MCO_ACTION').format(action_key,
                                                                       "something went wrong with MCO")
        self.call_method_and_assert_msgs(self.prechecks.run_mco_agent_action,
                                         action_key, 'db-1', err_msg=expected_err)

        self.prechecks.enminst_agent.test_mco_action_handler = self._mocked_mco_action_handler

        self.call_method_and_assert_msgs(self.prechecks.run_mco_agent_action,
                                         action_key, 'db-1', err_msg=expected_err,
                                         mco_agent_object=self.prechecks.enminst_agent)

        self.prechecks.mco_agent.test_mco_action_handler = self._mocked_mco_action_handler_2

        with self.assertRaises(McoAgentException):
            self.prechecks.run_mco_agent_action(action_key, 'db-1', non_exit_errors=['dummy_error'])

        self.prechecks.mco_agent.test_mco_action_handler = self._mocked_mco_action_handler_3

        with self.assertRaises(McoAgentException):
            self.prechecks.run_mco_agent_action(action_key, 'db-1', non_exit_errors=['dummy_error'])

    def test_services_valid_on_node(self):
        self.prechecks.run_command = self._mock_run_command_vcs_group_cs_full
        self.assertTrue(self.prechecks.services_valid_on_node('db-1'))

    def test_torf_265975(self):
        cluster_type = 'db_cluster'

        for service in ('jms', 'mysql', 'postgres', 'elasticsearch', 'opendj'):
            expected_gname = 'Grp_CS_%s_%s_clustered_service' % (cluster_type, service)
            self.assertEqual(expected_gname, self.prechecks.gen_cs_group_pattern(cluster_type, service))

        expected_gname = r'Grp_CS_%s_(sg_)?neo4j_clustered_service' % (cluster_type)
        self.assertEqual(expected_gname, self.prechecks.gen_cs_group_pattern(cluster_type, 'neo4j'))

        expected_gname = r'Grp_CS_%s_versant_clustered_service(_1)?' % (cluster_type)
        self.assertEqual(expected_gname, self.prechecks.gen_cs_group_pattern(cluster_type, 'versant'))

        expected_gname = r'Grp_CS_%s_modeldeployment_cluster(ed)?_service(_1)?' % (cluster_type)
        self.assertEqual(expected_gname, self.prechecks.gen_cs_group_pattern(cluster_type, 'modeldeployment'))

        expected_gname = r'Grp_CS_%s_(sg_)?[^\s]+_cluster(ed)?_service(_1)?' % (cluster_type)
        self.assertEqual(expected_gname, self.prechecks.gen_cs_group_pattern(cluster_type, 'ALL'))

    def _mock_vcs_get_systems_db(self, cluster):
        return (0, "----------  -------  ----------  ------ \n" + \
                    "    System    State     Cluster  Frozen \n" + \
                    "----------  -------  ----------  ------ \n" + \
                    "cloud-db-1  RUNNING  db_cluster       - \n" + \
                    "cloud-db-2  RUNNING  db_cluster       - \n" + \
                    "----------  -------  ----------  ------")

    def _mock_vcs_get_systems_broken(self, cluster):
        return (0, "garbage")

    def _mock_vcs_get_systems_error(self, cluster):
        return (1, "error")

    def test_get_system_names_by_cluster(self):
        cluster_type = 'db_cluster'
        self.prechecks.run_command = self._mock_vcs_get_systems_db
        expected_list = ['cloud-db-1', 'cloud-db-2']
        self.assertEqual(expected_list, self.prechecks.get_running_systems_by_cluster(cluster_type))

        # vcs command returns incompatable text
        self.prechecks.run_command = self._mock_vcs_get_systems_broken
        self.assertEqual([], self.prechecks.get_running_systems_by_cluster(cluster_type))

        # vcs command returns an error
        self.prechecks.run_command = self._mock_vcs_get_systems_error
        expected_err = self.get_msg('FAILED_TO_RUN_COMMAND').format('Get db_cluster nodes check')
        self.call_method_and_assert_msgs(self.prechecks.get_running_systems_by_cluster, cluster_type, err_msg=expected_err)

    @patch('enm_upgrade_prechecks.EnmPreChecks.get_nodes')
    @patch('enm_upgrade_prechecks.EnmPreChecks.run_command')
    def test_remove_packages_success(self, m_run_command, m_get_nodes):
        m_get_nodes.return_value = ['cloud-svc-1']
        expected_msg = self.get_msg('PERL-COMPRESS-RAW-ZLIB REMOVED')
        expected_hdr = self.get_msg('REMOVING PERL-COMPRESS-RAW-ZLIB')
        self.call_method_and_assert_msgs(self.prechecks.remove_packages, success_msg=expected_msg, hdr_msg=expected_hdr)
        m_run_command.assert_called_with("yum remove -y perl-Compress-Raw-Zlib")

    @patch('enm_upgrade_prechecks.EnmPreChecks.get_running_systems_by_cluster')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_deployment_cluster_list')
    def test_get_nodes(self, m_get_deployment_cluster_list,
                       m_get_running_systems_by_cluster):
        m_get_deployment_cluster_list.return_value = [u'svc_cluster', u'db_cluster']
        m_get_running_systems_by_cluster.side_effect = [['cloud-svc-1', 'cloud-svc-2', 'cloud-svc-3'],
                                                        ['cloud-db-1']]
        expected_list = ['cloud-svc-1', 'cloud-svc-2', 'cloud-svc-3', 'cloud-db-1']
        self.assertEquals(expected_list, self.prechecks.get_nodes())

    @patch('enm_upgrade_prechecks.exec_process')
    @patch('enm_upgrade_prechecks.EnmPreChecks._replace_puppet_timeout_values')
    def test_apply_puppet_timeouts(self, replace_puppet_timeout_values,
                                   exec_process):
        replace_puppet_timeout_values.return_value = True
        success_msg = self.get_msg('Puppet timeout checks have completed')
        expected_hdr = self.get_msg('CHECKING IF PUPPET TIMEOUT VALUES ARE'
                                    ' LONG ENOUGH')
        msg = self.get_msg('A timeout value has been changed. '
                         'The puppet sync command will be run. '
                         'This can take several minutes per node to complete.')
        self.call_method_and_assert_msgs(self.prechecks.apply_puppet_timeouts,
                                         msg=msg, success_msg=success_msg,
                                         hdr_msg=expected_hdr)
        exec_process.assert_called_with(
            '/opt/ericsson/enminst/bin/puppet.bsh --sync', use_shell=True
        )

        exec_process = MagicMock()
        replace_puppet_timeout_values.return_value = False
        success_msg = self.get_msg('Puppet timeout checks have completed')
        expected_hdr = self.get_msg('CHECKING IF PUPPET TIMEOUT VALUES ARE'
                                    ' LONG ENOUGH')
        self.call_method_and_assert_msgs(self.prechecks.apply_puppet_timeouts,
                                         success_msg=success_msg,
                                         hdr_msg=expected_hdr)
        self.assertFalse(exec_process.called)

    def _mock_puppet_config_values_equal(self):
        return """report=true
                localconfig = $vardir/localconfig
                runinterval = 1800
                configtimeout = 1720
                filetimeout = 5
                certname = ms1
                """

    def _mock_puppet_config_values_greater(self):
        return """report=true
                localconfig = $vardir/localconfig
                runinterval = 3000
                configtimeout = 3000
                filetimeout = 5
                certname = ms1
                """

    def _mock_puppet_config_values_less(self):
        return """report=true
                localconfig = $vardir/localconfig
                runinterval = 800
                configtimeout = 700
                filetimeout = 5
                certname = ms1
                """

    def test_replace_puppet_timeout_values(self):
        with patch('__builtin__.open') as mocked_open:
            mm = MagicMock(spec=file)
            mm.__enter__.return_value.read.return_value = \
                self._mock_puppet_config_values_equal()
            mocked_open.return_value = mm
            values_changed = self.prechecks._replace_puppet_timeout_values(
                '/etc/puppet/puppet.conf',
                self.prechecks.SEARCH_PATTERN.format('runinterval'),
                self.prechecks.REPLACE_PATTERN.format('runinterval'),
                self.prechecks.RUN_INTERVAL_VALUE
            )
            self.assertFalse(values_changed)

        with patch('__builtin__.open') as mocked_open:
            mm = MagicMock(spec=file)
            mm.__enter__.return_value.read.return_value = \
                self._mock_puppet_config_values_greater()
            mocked_open.return_value = mm
            values_changed = self.prechecks._replace_puppet_timeout_values(
                '/etc/puppet/puppet.conf',
                self.prechecks.SEARCH_PATTERN.format('runinterval'),
                self.prechecks.REPLACE_PATTERN.format('runinterval'),
                self.prechecks.RUN_INTERVAL_VALUE
            )
            self.assertFalse(values_changed)

        with patch('__builtin__.open') as mocked_open:
            mm = MagicMock(spec=file)
            mm.__enter__.return_value.read.return_value = \
                self._mock_puppet_config_values_less()
            mocked_open.return_value = mm
            values_changed = self.prechecks._replace_puppet_timeout_values(
                '/etc/puppet/puppet.conf',
                self.prechecks.SEARCH_PATTERN.format('runinterval'),
                self.prechecks.REPLACE_PATTERN.format('runinterval'),
                self.prechecks.RUN_INTERVAL_VALUE
            )
            self.assertTrue(values_changed)

    @patch('enm_upgrade_prechecks.get_edp_generated_sed')
    def test_check_https_port_ilo_available_no_sed_no_ilo(self,
                                                          mock_sed):
        mock_sed.return_value = {}
        expected_message = 'No iLO IP addresses found, skipping HTTPS check...'
        self.call_method_and_assert_msgs(
            self.prechecks.check_https_port_ilo_available,
            msg=expected_message
        )
        mock_sed.assert_called_once_with('.*_ilo_IP')

    @patch('enm_upgrade_prechecks.get_edp_generated_sed')
    @patch('enm_upgrade_prechecks._exec_curl_command')
    def test_check_https_port_ilo_available_success(self,
                                                    mock_exec_curl,
                                                    mock_sed):

        mock_sed.return_value = {'LMS_ilo_IP': '1.2.3.4'}
        expected_message = 'iLO HTTPS Success for Node "LMS"'
        mock_exec_curl.return_value = 0
        self.call_method_and_assert_msgs(
            self.prechecks.check_https_port_ilo_available,
            success_msg=expected_message
        )
        mock_sed.assert_called_once_with('.*_ilo_IP')
        mock_exec_curl.assert_called_once_with(
            '/usr/bin/curl -k https://1.2.3.4', hide_output=True)

    @patch('enm_upgrade_prechecks.get_edp_generated_sed')
    @patch('enm_upgrade_prechecks._exec_curl_command')
    def test_check_https_port_ilo_available_fail(self,
                                                 mock_exec_curl,
                                                 mock_sed):

        mock_sed.return_value = {'LMS_ilo_IP': '1.2.3.4'}
        expected_message = 'HTTPS PORT UNAVAILABLE ON iLO'
        mock_exec_curl.return_value = 1
        self.call_method_and_assert_msgs(
            self.prechecks.check_https_port_ilo_available,
            err_msg=expected_message, multi_call=True
        )
        mock_sed.assert_called_once_with('.*_ilo_IP')
        mock_exec_curl.assert_called_once_with(
            '/usr/bin/curl -k https://1.2.3.4', hide_output=True)

    def test_convert_to_tuple(self):
        data = {"1.2.3": (1, 2, 3),
                "1.100.108": (1, 100, 108),
                "2.73": (2, 73),
                "2.19.117": (2, 19, 117),
                "2.24.36": (2, 24, 36),
                "0.0.0.0.0": (0, 0, 0, 0, 0)}
        for key, val in data.iteritems():
            self.assertEqual(val, self.prechecks.convert_to_tuple(key))

    @patch('__builtin__.open')
    def test_seed_file_check_where_from_iso_is_equal_to_cutoff_version(self, _mock_open):
        with patch('__builtin__.open') as mocked_open:
            mm = MagicMock(spec=file)
            mm.__enter__.return_value.readlines.return_value = \
                self._mock_seed_file_check_where_from_iso_is_equal_to_cutoff_version()
            mocked_open.return_value = mm
            return mm

        msg = self.get_msg('DP_RETAIN_CONF_SEED_FILE')
        success_msg = self.get_msg('DP_CHECKING_ENM_VERSION_COMPLETED')
        self.prechecks.run_command = lambda: True
        self.prechecks.seed_conf_file_exists = lambda x: True
        self.call_method_and_assert_msgs(self.prechecks.remove_seed_file_after_check,
                                         msg=msg, success_msg=success_msg)

    def _mock_seed_file_check_where_from_iso_is_equal_to_cutoff_version(self):
        return "ENM 23.03 (ISO Version: 2.19.117) AOM 901 151 R1FX/2"

    @patch('__builtin__.open')
    def test_seed_file_check_where_from_iso_is_less_than_cutoff_version(self, _mock_open):
        with patch('__builtin__.open') as mocked_open:
            mm = MagicMock(spec=file)
            mm.__enter__.return_value.readlines.return_value = \
                self._mock_seed_file_check_where_from_iso_is_less_than_cutoff_version()
            mocked_open.return_value = mm
            return mm

        msg = self.get_msg('DP_REMOVE_CONF_SEED_FILE')
        success_msg = self.get_msg('DP_CHECKING_ENM_VERSION_COMPLETED')
        self.prechecks.run_command = lambda: True
        self.prechecks.seed_conf_file_exists = lambda x: True
        self.call_method_and_assert_msgs(self.prechecks.remove_seed_file_after_check,
                                         msg=msg, success_msg=success_msg)

    def _mock_seed_file_check_where_from_iso_is_less_than_cutoff_version(self):
        return "ENM 23.03 (ISO Version: 2.19.114) AOM 901 151 R1FX"

    @patch('__builtin__.open')
    def test_seed_file_check_where_from_iso_is_greater_than_cutoff_version(self, _mock_open):
        with patch('__builtin__.open') as mocked_open:
            mm = MagicMock(spec=file)
            mm.__enter__.return_value.readlines.return_value = \
                self._mock_seed_file_check_where_from_iso_is_greater_than_cutoff_version()
            mocked_open.return_value = mm
            return mm

        msg = self.get_msg('DP_RETAIN_CONF_SEED_FILE')
        success_msg = self.get_msg('DP_CHECKING_ENM_VERSION_COMPLETED')
        self.prechecks.run_command = lambda: True
        self.prechecks.seed_conf_file_exists = lambda x: True
        self.call_method_and_assert_msgs(self.prechecks.remove_seed_file_after_check,
                                         msg=msg, success_msg=success_msg)

    def _mock_seed_file_check_where_from_iso_is_greater_than_cutoff_version(self):
        return "ENM 23.08 (ISO Version: 2.24.100) AOM 901 151 R1GC"

    @patch('__builtin__.open')
    def test_seed_file_check_where_env_version_file_does_not_exist(self, _mock_open):
        msg = self.get_msg('The file /ericsson/tor/data/domainProxy/seed.conf does not exist. '
                           'There is nothing to do here.')
        success_msg = self.get_msg('DP_CHECKING_ENM_VERSION_COMPLETED')
        self.prechecks.seed_conf_file_exists = lambda x: False
        self.call_method_and_assert_msgs(self.prechecks.remove_seed_file_after_check,
                                         msg=msg, success_msg=success_msg)
