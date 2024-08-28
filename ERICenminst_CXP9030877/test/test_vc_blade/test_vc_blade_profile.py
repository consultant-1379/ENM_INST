import os
import re
import sys
from os.path import join
from tempfile import mktemp

import unittest2
from mock import patch, MagicMock

import vc_blade_profile

CURRENT_PATH = os.path.dirname(__file__)
SED1017_FILE = os.path.join(CURRENT_PATH, '../Resources/sed1017')
BLADE_PROFILES_FILE = join(CURRENT_PATH,
                           '../Resources/blade_profiles')
VC_BLADE_PROFILE_FILE = join(CURRENT_PATH,
                             '../../src/main/python/vc_blade_profile.py')
VC_PROFILE_CONFIGURATION_FILE = join(CURRENT_PATH,
                                     'vc_profile_configuration.log')


class TestVCBlade(unittest2.TestCase):
    '''
    Test class containing Test Cases designed to test the
    SAN Restore Snapshot functionality.
    Uses Unittest.
    '''
    vc_blade_profile.pexpect.spawn.close

    def setUp(self):
        self.blade_profiles_path = os.path.join(CURRENT_PATH,
                                                '../Resources/blade_profiles')
        # create a HpVcProfile object
        self.vcip = "10.36.49.179"
        self.vcuser = "root"
        self.vcpasswd = "shroot12"

        self.log = MagicMock()
        # The following are needed for blades_info{}
        self.port = '1'
        self.port2 = '2'
        self.port3 = '3'
        self.port4 = '4'
        self.port_type = 'MN'
        self.pxe = 'enabled'
        self.speed = 'preferred'
        self.uplink = 'uplink_A'  # OSS1_Shared_Uplink_A'
        self.nets = '159.107.173.3'  # 121.212.333'

        self.setUpVxBlade()
        self.setupSed()
        self.setupServerRc()
        self.setupNetworkRc()
        self.setupUplinkRc()
        self.stash_functions_to_be_mocked()

    def setUpVxBlade(self):

        ''' setup a HP VC Blade Profile object '''

        # Setup object
        self.Hp_Vc_Profile = vc_blade_profile.HpVcProfile(self.vcip,
                                                          self.vcuser,
                                                          self.vcpasswd,
                                                          self.log)
        self.Hp_Vc_Profile.profile_definitions = ''
        self.Hp_Vc_Profile.network_definitions = ''
        self.Hp_Vc_Profile.blades_info = {}

    def setupSed(self):
        self.sed_p_name = ''
        self.sed_data = vc_blade_profile.SED_DATA
        sed_file = open(SED1017_FILE, 'r')

        with sed_file as f:
            for line in f:
                match = re.search(r'^\s*(\w+)\s*=(.*)', line)
                if match:
                    self.sed_data[match.group(1)] = (match.group(2)).strip()

    def setupServerRc(self):
        self.serverRc = ('Server ID      : enc0:1\r\n\
                          Enclosure Name : OSS1_Shared_Uplink_A\r\n\
                          Enclosure ID   : enc0\r\n\
                          Bay            : 1\r\n\
                          Description    : HP ProLiant BL495c G5\r\n\
                          Status         : OK\r\n\
                          Power          : Off\r\n\
                          UID            : Off\r\n\
                          Server Profile : <Unassigned>\r\n\
                          Height         : Half-Height\r\n\
                          Width          : 1\r\n\
                          Part Number    : 123458-003\r\n\
                          Serial Number  : CZ3204768D\r\n\
                          Server Name    : [Unknown]\r\n\
                          OS Name        : [Unknown]\r\n\
                          Asset Tag      : [Unknown]\r\n\
                          ROM Version    : [Unknown]\r\n\
                          Memory         : 512\r\n\
                         --------------------- \r\n\
                         Server ID      : enc0:2\r\n\
                         Enclosure Name : OSS1_Shared_Uplink_B\r\n\
                         Enclosure ID   : enc0\r\n\
                         Bay            : 2\r\n\
                         Description    : HP ProLiant BL460c G6\r\n\
                         Status         : OK\r\n\
                         Power          : Off\r\n\
                         UID            : Off\r\n\
                         Server Profile : <Unassigned>\r\n\
                         Height         : Half-Height\r\n\
                         Width          : 1\r\n\
                         Part Number    : 404663-B21\r\n\
                         Serial Number  : CZ32057XNV\r\n\
                         Server Name    : [Unknown]\r\n\
                         OS Name        : [Unknown]\r\n\
                         Asset Tag      : [Unknown]\r\n\
                         ROM Version    : [Unknown]\r\n\
                         Memory         : 512')

    def setupNetworkRc(self):
        # Output from 'SHOW NETWORK *' command
        self.networkRc = ('Name              : ENM_backup_A\r\n\
                              Status            : OK\r\n\
                              Smart Link        : Disabled\r\n\
                              State             : Enabled\r\n\
                              Connection Mode   : Auto\r\n\
                              Shared Uplink Set : OSS1_Shared_Uplink_A\r\n\
                              VLAN ID           : 270\r\n\
                              Native VLAN       : Disabled\r\n\
                              Private           : Disabled\r\n\
                              VLAN Tunnel       : Disabled\r\n\
                              Preferred Speed   : Preferred\r\n\
                              Max Speed         : 9.9Gb\r\n\
                              -------------------------\r\n\
                              Name              : ENM_backup_B\r\n\
                              Status            : OK\r\n\
                              Smart Link        : Disabled\r\n\
                              State             : Enabled\r\n\
                              Connection Mode   : Auto\r\n\
                              Shared Uplink Set : OSS1_Shared_Uplink_B\r\n\
                              VLAN ID           : 270\r\n\
                              Native VLAN       : Disabled\r\n\
                              Private           : Disabled\r\n\
                              VLAN Tunnel       : Disabled\r\n\
                              Preferred Speed   : Preferred\r\n\
                              Max Speed         : 9.9Gb')

    def setupUplinkRc(self):
        # Output from 'SHOW UPLINKSET *' command
        self.uplinksetRc = (
            "Name            : ENM_backup_A\r\n\
            Status          : OK\r\n\
            Connection Mode : Auto\r\n\
            ----------------------\r\n\
            Name            : OSS1_Shared_Uplink_A\r\n\
            Status          : OK\r\n\
            Connection Mode : Auto\r\n\
            Associated Networks (VLAN Tagged)\r\n\
            =================================\r\n\
            Name             VLAN ID  Native VLAN  SmartLink  Private  \r\n\
            ========================================================= \r\n\
            OSS1_Shared_Uplink_A  270       Disabled     Disabled   "
            "Disabled \r\n\
            rk                                                         \r\n\
            --- \r\n\
            Name            : ENM_backup_B\r\n\
            Status          : OK\r\n\
            Connection Mode : Auto\r\n\
            ----------------------\r\n\
            Name            : OSS1_Shared_Uplink_B\r\n\
            Status          : OK\r\n\
            Connection Mode : Auto\r\n\
            Associated Networks (VLAN Tagged)\r\n\
            =================================\r\n\
            Name             VLAN ID  Native VLAN  SmartLink  Private  \r\n\
            ========================================================= \r\n\
            OSS1_Shared_Uplink_B  270       Disabled     Disabled   "
            "Disabled \r\n\
            rk                                                         \r\n\
            ---")

    class StashFunctions:

        def __init__(self):
            self.vc_exec = vc_blade_profile.HpVcProfile.vc_exec
            self.load_profile = vc_blade_profile.HpVcProfile.load_profile
            self.vc_blades_to_configure = \
                vc_blade_profile.HpVcProfile.vc_blades_to_configure
            self.is_hide_unused_flexnics_supported = \
                vc_blade_profile.HpVcProfile.is_hide_unused_flexnics_supported
            self.function_logger = vc_blade_profile.function_logger
            self.network_commands = \
                vc_blade_profile.HpVcProfile.network_commands
            self.profile_commands = \
                vc_blade_profile.HpVcProfile.profile_commands

            self.vc_connect_sim = vc_blade_profile.HpVcProfile.vc_connect_sim
            self.vc_disconnect = vc_blade_profile.HpVcProfile.vc_disconnect
            self.is_hide_unused_flexnics_supported = \
                vc_blade_profile.HpVcProfile.is_hide_unused_flexnics_supported
            self.check_if_profile_name_exist = \
                vc_blade_profile.HpVcProfile.check_if_profile_name_exist
            self.poweroff_server = \
                vc_blade_profile.HpVcProfile.poweroff_server
            self.assign_server_profile = \
                vc_blade_profile.HpVcProfile.assign_server_profile
            self.poweron_server = vc_blade_profile.HpVcProfile.poweron_server

    def stash_functions_to_be_mocked(self):
        self.stashedFunctions = self.StashFunctions()

    def reset_mocked_functions(self):
        self.Hp_Vc_Profile.vc_exec = self.stashedFunctions.vc_exec
        self.Hp_Vc_Profile.load_profile = self.stashedFunctions.load_profile

        self.Hp_Vc_Profile.vc_blades_to_configure = \
            self.stashedFunctions.vc_blades_to_configure

        self.Hp_Vc_Profile.is_hide_unused_flexnics_supported = \
            self.stashedFunctions.is_hide_unused_flexnics_supported

        self.function_logger = self.stashedFunctions.function_logger
        self.Hp_Vc_Profile.network_commands = \
            self.stashedFunctions.network_commands

        self.Hp_Vc_Profile.profile_commands = \
            self.stashedFunctions.profile_commands

        vc_blade_profile.HpVcProfile.vc_connect_sim = \
            self.stashedFunctions.vc_connect_sim
        vc_blade_profile.HpVcProfile.vc_disconnect = \
            self.stashedFunctions.vc_disconnect
        vc_blade_profile.HpVcProfile.is_hide_unused_flexnics_supported = \
            self.stashedFunctions.is_hide_unused_flexnics_supported

        vc_blade_profile.HpVcProfile.check_if_profile_name_exist = \
            self.stashedFunctions.check_if_profile_name_exist

        vc_blade_profile.HpVcProfile.poweroff_server = \
            self.stashedFunctions.poweroff_server

        vc_blade_profile.HpVcProfile.assign_server_profile = \
            self.stashedFunctions.assign_server_profile
        vc_blade_profile.HpVcProfile.poweron_server = \
            self.stashedFunctions.poweron_server

    def tearDown(self):
        self.reset_mocked_functions()
        unittest2.TestCase.tearDown(self)

    @patch('vc_blade_profile.pexpect.spawn')
    def test_connect_exec_and_disconnect(self, spawn):
        spawn.return_value.expect.side_effect = [0, 0]
        spawn.return_value.sendline.side_effect = [None, None]
        self.assertEquals(5, self.Hp_Vc_Profile.vc_connect())
        spawn.reset_mock()
        spawn.return_value.expect.side_effect = [0, 7, 0, 0, 0, 0, 0]
        spawn.return_value.before.return_value = ["\r\n TestBefore"] * 2
        spawn.return_value.sendline.side_effect = [None] * 6
        result_from_search = re.search(r'\r\n(.+)', '\r\n Test', re.S)
        with patch('vc_blade_profile.re.search') as re_search:
            re_search.return_value = result_from_search
            self.assertRaises(RuntimeError, self.Hp_Vc_Profile.vc_connect)
            self.assertRaises(RuntimeError, self.Hp_Vc_Profile.vc_connect_sim)
            logger = MagicMock()
            self.Hp_Vc_Profile.function_logger = MagicMock(return_value=logger)
            res = self.Hp_Vc_Profile.vc_exec('SHOW SERVER *', 1)
        self.assertEqual(' Test', res)  # Test function vc_exec
        self.assertIsNone(self.Hp_Vc_Profile.vc_disconnect())

    def test_vc_blades_to_configure(self):
        rc = ('Server ID      : enc0:1\r\n\
                Enclosure Name : Enclosure1\r\n\
                Enclosure ID   : enc0\r\n\
                Bay            : 1\r\n\
                Description    : HP ProLiant BL495c G5\r\n\
                Status         : OK\r\n\
                Power          : Off\r\n\
                UID            : Off\r\n\
                Server Profile : <Unassigned>\r\n\
                Height         : Half-Height\r\n\
                Width          : 1\r\n\
                Part Number    : 123458-003\r\n\
                Serial Number  : CZ3204768D\r\n\
                Server Name    : [Unknown]\r\n\
                OS Name        : [Unknown]\r\n\
                Asset Tag      : [Unknown]\r\n\
                ROM Version    : [Unknown]\r\n\
                Memory         : 512\r\n\
                -------------\r\n\
                Server ID      : enc0:2\r\n\
                Enclosure Name : Enclosure1\r\n\
                Enclosure ID   : enc0\r\n\
                Bay            : 2\r\n\
                Description    : HP ProLiant BL460c G6\r\n\
                Status         : OK\r\n\
                Power          : Off\r\n\
                UID            : Off\r\n\
                Server Profile : <Unassigned>\r\n\
                Height         : Half-Height\r\n\
                Width          : 1\r\n\
                Part Number    : 404663-B21\r\n\
                Serial Number  : CZ32057XNV\r\n\
                Server Name    : [Unknown]\r\n\
                OS Name        : [Unknown]\r\n\
                Asset Tag      : [Unknown]\r\n\
                ROM Version    : [Unknown]\r\n\
                Memory         : 512')

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=rc)
        self.assertIsNone(self.Hp_Vc_Profile.vc_blades_to_configure())

    def test_get_vc_networks(self):
        rc = 'No networks exist'
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=rc)
        self.assertIsNone(self.Hp_Vc_Profile.get_vc_networks())

        rc = ("Name            : test_network_1\r\n\
                Status          : OK\r\n\
                Smart Link      : Disabled\r\n\
                State           : Enabled\r\n\
                Connection Mode : Auto\r\n\
                Native VLAN     : Disabled\r\n\
                Private         : Disabled\r\n\
                VLAN Tunnel     : Disabled\r\n\
                Preferred Speed : Auto\r\n\
                Max Speed       : Unrestricted\r\n\
                -----------------------------\r\n\
                Name              : test_network_2\r\n\
                Status            : OK\r\n\
                Smart Link        : Disabled\r\n\
                State             : Enabled\r\n\
                Connection Mode   : Auto\r\n\
                Shared Uplink Set : ul_set_unit_test\r\n\
                VLAN ID           : 1\r\n\
                Native VLAN       : Disabled\r\n\
                Private           : Disabled\r\n\
                VLAN Tunnel       : Disabled\r\n\
                Preferred Speed   : Auto\r\n\
                Max Speed         : Unrestricted")
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=rc)
        self.assertIsNone(self.Hp_Vc_Profile.get_vc_networks())

    def test_is_hide_unused_flexnics_supported(self):
        rc = ("ID               : enc0:1\r\n\
                Enclosure        : Enclosure1\r\n\
                Bay              : 1\r\n\
                Type             : VC-ENET\r\n\
                Firmware Version : 4.15 2009-10-07T10:16:12Z\r\n\
                Status           : OK\r\n\
                ---------------------------\r\n\
                ID               : enc0:2\r\n\
                Enclosure        : Enclosure1\r\n\
                Bay              : 2\r\n\
                Type             : VC-ENET+FC\r\n\
                Firmware Version : 4.15 2009-10-07T10:16:12Z\r\n\
                Status           : NOTOK")
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=rc)
        self.assertFalse(
                self.Hp_Vc_Profile.is_hide_unused_flexnics_supported())

    def test_is_hide_unused_flexnics_supported_fail(self):
        rc = 'No firmware exist'
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=rc)
        self.assertRaises(
                RuntimeError,
                self.Hp_Vc_Profile.is_hide_unused_flexnics_supported)

    def test_get_vc_uplinks(self):
        rc = ("Name            : test_ul_set\r\n\
              Status          : OK\r\n\
              Connection Mode : Auto\r\n\
              ----------------------\r\n\
              Name            : unit_test_ul_set\r\n\
              Status          : OK\r\n\
              Connection Mode : Auto\r\n\
              Associated Networks (VLAN Tagged)\r\n\
              =================================\r\n\
              Name             VLAN ID  Native VLAN  SmartLink  Private  \r\n\
              ========================================================= \r\n\
              unit_test_netwo  12       Disabled     Disabled   Disabled \r\n\
              rk                                                         \r\n\
              ---")
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=rc)
        self.assertIsNone(self.Hp_Vc_Profile.get_vc_uplinks())

    def test_get_vc_uplinks_fail(self):
        rc = 'No shared uplink'
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=rc)
        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.get_vc_uplinks)

    @patch('vc_blade_profile.logging.FileHandler')
    @patch('vc_blade_profile.os.rename')
    def test_function_logger(self, rename, lfh):
        vc_blade_profile.log_file = join(CURRENT_PATH,
                                         'vc_profile_configuration.log')
        logger = vc_blade_profile.function_logger()
        self.assertEqual(20, logger.level)
        self.assertEqual("app", logger.name)

    def test_network_commands_success(self):

        ''' testing test_network_commands_success '''

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.uplinksetRc)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.networkRc)
        self.Hp_Vc_Profile.get_vc_networks()

        self.sed_p_name = 'ENM_SE'
        self.server_type = 'db_node'

        block_type = '{0}_{1}'.format(self.sed_p_name, self.server_type)

        loaded_profile = self.Hp_Vc_Profile.load_profile(block_type,
                                                         BLADE_PROFILES_FILE)

        self.assertIsNone(self.Hp_Vc_Profile.network_commands(
                loaded_profile, block_type))

    def test_network_commands_failure_invalid_network_definition(self):

        '''testing test_network_commands_failure_invalid_network_definition '''

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.uplinksetRc)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.networkRc)
        self.Hp_Vc_Profile.get_vc_networks()

        self.sed_p_name = 'ENM_SE'
        self.server_type = 'db_node'

        block_type = '{0}_{1}'.format(self.sed_p_name, self.server_type)

        self.nets = ['backup_A:false:true', 'storage_A:false:true:none',
                     'jgroups_A:false:false:none', 'internal_A:true:true:none']
        b_profile = {}

        b_profile[self.port] = \
            self.port_type, self.pxe, self.speed, self.uplink, self.nets

        loaded_profile_errors = b_profile

        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.network_commands,
                          loaded_profile_errors, block_type)

    def test_network_commands_failure_invalid_untagged_value(self):

        ''' testing test_network_commands_failure_invalid_untagged_value '''

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.uplinksetRc)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.networkRc)
        self.Hp_Vc_Profile.get_vc_networks()

        self.sed_p_name = 'ENM_SE'
        self.server_type = 'db_node'

        block_type = '{0}_{1}'.format(self.sed_p_name, self.server_type)

        self.nets = ['backup_A:error:true:2500', 'storage_A:false:true:none',
                     'jgroups_A:false:false:none', 'internal_A:true:true:none']
        b_profile = {
            self.port:
                (self.port_type, self.pxe, self.speed, self.uplink, self.nets)}

        loaded_profile_errors = b_profile

        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.network_commands,
                          loaded_profile_errors, block_type)

    def test_network_commands_failure_invalid_uplinkset(self):

        ''' testing test_network_commands_failure_invalid_uplinkset '''

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.uplinksetRc)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.networkRc)
        self.Hp_Vc_Profile.get_vc_networks()

        self.sed_p_name = 'ENM_SE'
        self.server_type = 'db_node'

        block_type = '{0}_{1}'.format(self.sed_p_name, self.server_type)

        self.nets = ['backup_A:false:error:2500', 'storage_A:false:true:none',
                     'jgroups_A:false:false:none', 'internal_A:true:true:none']
        b_profile = {
            self.port:
                (self.port_type, self.pxe, self.speed, self.uplink, self.nets)}
        loaded_profile_errors = b_profile

        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.network_commands,
                          loaded_profile_errors, block_type)

    def test_network_commands_failure_invalid_networkmaxspeed(self):

        ''' testing test_network_commands_failure_invalid_networkmaxspeed '''

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.uplinksetRc)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.networkRc)
        self.Hp_Vc_Profile.get_vc_networks()

        self.sed_p_name = 'ENM_SE'
        self.server_type = 'db_node'

        block_type = '{0}_{1}'.format(self.sed_p_name, self.server_type)

        self.nets = ['backup_A:false:true:a', 'storage_A:false:true:none',
                     'jgroups_A:false:false:none', 'internal_A:true:true:none']
        b_profile = {
            self.port:
                (self.port_type, self.pxe, self.speed, self.uplink, self.nets)}
        loaded_profile_errors = b_profile

        self.assertRaises(ValueError, self.Hp_Vc_Profile.network_commands,
                          loaded_profile_errors, block_type)

    def test_network_commands_failure_incorrect_networkmaxspeed(self):

        ''' testing test_network_commands_failure_incorrect_networkmaxspeed '''

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.uplinksetRc)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.networkRc)
        self.Hp_Vc_Profile.get_vc_networks()

        self.sed_p_name = 'ENM_SE'
        self.server_type = 'db_node'

        block_type = '{0}_{1}'.format(self.sed_p_name, self.server_type)

        self.nets = ['backup_A:false:true:25', 'storage_A:false:true:none',
                     'jgroups_A:false:false:none', 'internal_A:true:true:none']
        b_profile = {
            self.port:
                (self.port_type, self.pxe, self.speed, self.uplink, self.nets)}
        loaded_profile_errors = b_profile

        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.network_commands,
                          loaded_profile_errors, block_type)

    def test_network_commands_failure_network_already_defined_on_vc(self):

        '''testing test_network_commands_failure_network_already_defined_on_vc\
        '''

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.uplinksetRc)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value=self.networkRc)
        self.Hp_Vc_Profile.get_vc_networks()

        self.sed_p_name = 'ENM_SE'
        self.server_type = 'db_node'

        block_type = '{0}_{1}'.format(self.sed_p_name, self.server_type)

        self.nets = ['backup_A:false:false:2500', 'storage_A:false:true:none',
                     'jgroups_A:false:false:none', 'internal_A:true:true:none']
        b_profile = {
            self.port:
                (self.port_type, self.pxe, self.speed, self.uplink, self.nets)}
        loaded_profile_errors = b_profile

        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.network_commands,
                          loaded_profile_errors, block_type)

    def test_check_vlanid_not_in_uplink(self):

        ''' testing test_check_vlanid_not_in_uplink '''

        # Set current_vc_networks
        self.Hp_Vc_Profile.rc = self.networkRc
        self.Hp_Vc_Profile.vc_exec = MagicMock(
                return_value=self.Hp_Vc_Profile.rc)
        self.Hp_Vc_Profile.get_vc_networks()

        self.nets = ['backup_A:false:true:2500', 'storage_A:false:true:none',
                     'jgroups_A:false:false:none', 'internal_A:true:true:none']
        b_profile = {
            self.port:
                (self.port_type, self.pxe, self.speed, self.uplink, self.nets),
            self.port2:
                (self.port_type, self.pxe, 'custom', self.uplink, self.nets),
            self.port3: ('SN', self.pxe, self.speed, self.uplink, self.nets),
            self.port4: ('SN', self.pxe, 'custom', self.uplink, self.nets)}
        loaded_profile = b_profile

        net = self.nets[0].split(':')
        n_name_key = net[0].strip()
        n_name = self.sed_data[n_name_key]
        vlanid = self.Hp_Vc_Profile.current_vc_networks[n_name][1]

        uplinkset_key = loaded_profile[self.port][3]
        uplinkset = self.sed_data[uplinkset_key]

        self.assertRaises(RuntimeError,
                          self.Hp_Vc_Profile.check_vlanid_not_in_uplink,
                          vlanid, uplinkset)

    def test_load_profile(self):

        ''' testing test_load_profile '''

        self.Hp_Vc_Profile.rc = self.uplinksetRc
        self.Hp_Vc_Profile.vc_exec = MagicMock(
                return_value=self.Hp_Vc_Profile.rc)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.sed_p_name = 'ENM_SE'
        self.server_type = 'db_node'

        block_type = '{0}_{1}'.format(self.sed_p_name, self.server_type)

        self.Hp_Vc_Profile.load_profile(block_type, BLADE_PROFILES_FILE)

        empty_blade_profiles_file = mktemp()
        with open(empty_blade_profiles_file, 'w'):
            pass

        self.assertRaises(ValueError, self.Hp_Vc_Profile.load_profile,
                          block_type, empty_blade_profiles_file)

        os.remove(empty_blade_profiles_file)

    def test_profile_commands(self):

        ''' testing test_profile_commands '''
        self.Hp_Vc_Profile.rc = self.serverRc
        self.Hp_Vc_Profile.vc_exec = MagicMock(
                return_value=self.Hp_Vc_Profile.rc)  # upslinksetCmdRes)
        self.Hp_Vc_Profile.get_vc_uplinks()

        self.Hp_Vc_Profile.is_hide_unused_flexnics_supported = MagicMock(
                returnValue=True)

        self.nets = ['backup_A:false:true:2500', 'storage_A:false:true:none',
                     'jgroups_A:false:false:none', 'internal_A:true:true:none']
        b_profile = {
            self.port:
                (self.port_type, self.pxe, self.speed, self.uplink, self.nets),
            self.port2:
                (self.port_type, self.pxe, 'custom', self.uplink, self.nets),
            self.port3: ('SN', self.pxe, self.speed, self.uplink, self.nets),
            self.port4: ('SN', self.pxe, 'custom', self.uplink, self.nets)}
        loaded_profile = b_profile

        # setup the blades_info data from the sed and rc above.
        self.Hp_Vc_Profile.vc_blades_to_configure()

        for node in self.Hp_Vc_Profile.blades_info:
            b_id = self.Hp_Vc_Profile.blades_info[node][1]
            sed_sname = self.Hp_Vc_Profile.blades_info[node][7]
            vc_p_name = '{0}_Bay_{1}_{2}'.format(
                    self.sed_p_name, b_id.split(':')[1], sed_sname)

        self.assertIsNone(self.Hp_Vc_Profile.profile_commands(
                loaded_profile, vc_p_name))

    def test_add_profile(self):

        ''' testing test_add_profile '''

        self.Hp_Vc_Profile.vc_blades_to_configure = MagicMock()

        self.sed_p_name = 'profile1'
        self.Hp_Vc_Profile.blades_info['node1'] = (self.sed_p_name,
                                                   'blade1:1a:2', 'up', 'on',
                                                   'pro1', '10', '12345',
                                                   'sname1', 'type_cv')

        for node in self.Hp_Vc_Profile.blades_info:
            sed_p_name = self.Hp_Vc_Profile.blades_info[node]  # [0]

        b_profile = {
            self.port:
                (self.port_type, self.pxe, self.speed, self.uplink, self.nets)}
        self.Hp_Vc_Profile.load_profile = MagicMock(return_value=b_profile)

        self.Hp_Vc_Profile.network_commands = MagicMock()
        self.Hp_Vc_Profile.profile_commands = MagicMock()

        self.Hp_Vc_Profile.vc_exec = MagicMock(
                return_value='No profiles exist SUCCESS')
        self.assertIsNone(self.Hp_Vc_Profile.add_profile(
                'profile_path', dry_run=False, force_assign=True,
                vc_assign=True))

        self.Hp_Vc_Profile.last_loaded_profile = '{0}_NON_MGMT'.format(
                self.sed_p_name)
        self.assertIsNone(self.Hp_Vc_Profile.add_profile(
                'profile_path', dry_run=False, force_assign=True,
                vc_assign=False))

        self.Hp_Vc_Profile.blades_info['node1'] = (self.sed_p_name,
                                                   'blade1:1a:2', 'up', 'on',
                                                   'pro1', '10', '12345',
                                                   'sname1', 'type_cv')

        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.add_profile,
                          'profile_path', dry_run=False, force_assign=False,
                          vc_assign=False)

    def test_exec_net_commands(self):

        ''' testing test_exec_net_commands '''

        self.Hp_Vc_Profile.network_definitions = 'add network {0}'.format(
                'network1')

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='SUCCESS')
        self.assertIsNone(self.Hp_Vc_Profile.exec_net_commands(dry_run=False))

        self.assertIsNone(self.Hp_Vc_Profile.exec_net_commands(dry_run=True))

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILURE')
        self.assertRaises(
                RuntimeError, self.Hp_Vc_Profile.exec_net_commands, False)

    def test_exec_profile_commands(self):

        ''' testing test_exec_profile_commands '''

        self.Hp_Vc_Profile.profile_definitions = \
            'ADD profile port1_Bay_blade:1_sed1 -nodefaultenetconn'

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='SUCCESS')
        self.assertIsNone(self.Hp_Vc_Profile.exec_profile_commands(
                vc_p_name='port1_Bay_blade:1_sed1', dry_run=False))

        self.assertIsNone(self.Hp_Vc_Profile.exec_profile_commands(
                vc_p_name='port1_Bay_blade:1_sed1', dry_run=True))

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILURE')
        self.assertRaises(
                RuntimeError, self.Hp_Vc_Profile.exec_profile_commands,
                'port1_Bay_blade:1_sed1', False)

    def test_check_if_profile_name_exist(self):

        ''' testing test_check_if_profile_name_exist '''
        self.Hp_Vc_Profile.vc_exec = MagicMock(
                return_value='No profiles exist SUCCESS')

        self.assertIsNone(self.Hp_Vc_Profile.check_if_profile_name_exist(
                vc_p_name='port1_Bay_blade:1_sed1', dry_run=False))

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILURE')
        self.assertRaises(RuntimeError,
                          self.Hp_Vc_Profile.check_if_profile_name_exist,
                          'port1_Bay_blade:1_sed1', False)

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILURE')

        self.assertIsNone(self.Hp_Vc_Profile.check_if_profile_name_exist(
                vc_p_name='port1_Bay_blade:1_sed1', dry_run=True))

    def test_unassign_server_profile(self):

        ''' testing test_unassign_server_profile '''
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='SUCCESS')

        self.assertIsNone(self.Hp_Vc_Profile.unassign_server_profile(
                'blade1', vc_p_name='port1_Bay_blade:1_sed1', dry_run=False))

        self.assertIsNone(self.Hp_Vc_Profile.unassign_server_profile(
                'blade1', vc_p_name='port1_Bay_blade:1_sed1', dry_run=True))

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILURE')
        self.assertRaises(
                RuntimeError, self.Hp_Vc_Profile.unassign_server_profile,
                'blade1', 'port1_Bay_blade:1_sed1', False)

    def test_assign_server_profile(self):

        ''' testing test_assign_server_profile '''
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='SUCCESS')
        self.assertIsNone(self.Hp_Vc_Profile.assign_server_profile(
                'blade1', vc_p_name='port1_Bay_blade:1_sed1', dry_run=False))

        self.assertIsNone(self.Hp_Vc_Profile.assign_server_profile(
                'blade1', vc_p_name='port1_Bay_blade:1_sed1', dry_run=True))

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILURE')
        self.assertRaises(
                RuntimeError, self.Hp_Vc_Profile.assign_server_profile,
                'blade1', 'port1_Bay_blade:1_sed1', False)

    def test_remove_server_profile(self):

        ''' testing test_remove_server_profile '''
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='SUCCESS')

        self.assertIsNone(self.Hp_Vc_Profile.remove_server_profile(
                'blade1', dry_run=False))

        self.assertIsNone(self.Hp_Vc_Profile.remove_server_profile(
                'blade1', dry_run=True))

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILURE')
        self.assertRaises(
                RuntimeError, self.Hp_Vc_Profile.remove_server_profile,
                'blade1', False)

    def test_poweroff_server(self):

        ''' testing test_poweroff_server '''
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='SUCCESS')
        self.assertIsNone(self.Hp_Vc_Profile.poweroff_server(
                'blade1', dry_run=False))

        self.assertIsNone(self.Hp_Vc_Profile.poweroff_server(
                'blade1', dry_run=True))

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILED')
        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.poweroff_server,
                          'bladeNonExist', False)

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='SUCCESS')

        self.Hp_Vc_Profile.poweroff_server('blade1', dry_run=False)

    def test_poweron_server(self):

        ''' testing test_poweron_server '''
        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='SUCCESS')

        self.assertIsNone(self.Hp_Vc_Profile.poweron_server('blade1',
                                                            dry_run=False))

        self.assertIsNone(self.Hp_Vc_Profile.poweron_server('blade1',
                                                            dry_run=True))

        self.Hp_Vc_Profile.vc_exec = MagicMock(return_value='FAILURE')
        self.assertRaises(RuntimeError, self.Hp_Vc_Profile.poweron_server,
                          'blade1', False)

    def vc_exec_mock(self, command):

        if command == "SHOW SERVER *":
            result = self.serverRc
        elif command == "SHOW NETWORK *":
            result = self.networkRc
        elif command == "SHOW UPLINKSET *":
            result = self.uplinksetRc

        return result

    @patch('vc_blade_profile.function_logger')
    def test_main(self, logger):

        ''' testing test_main '''

        vc_blade_profile.HpVcProfile.vc_exec = MagicMock(
                side_effect=self.vc_exec_mock)

        vc_blade_profile.log_file = VC_PROFILE_CONFIGURATION_FILE

        vc_blade_profile.HpVcProfile.vc_connect_sim = MagicMock()
        vc_blade_profile.HpVcProfile.vc_disconnect = MagicMock()

        vc_blade_profile.HpVcProfile.is_hide_unused_flexnics_supported = \
            MagicMock(returnValue=True)
        vc_blade_profile.HpVcProfile.check_if_profile_name_exist = MagicMock()
        vc_blade_profile.HpVcProfile.poweroff_server = MagicMock()
        vc_blade_profile.HpVcProfile.assign_server_profile = MagicMock()
        vc_blade_profile.HpVcProfile.poweron_server = MagicMock()

        raised = False
        sys.argv = [VC_BLADE_PROFILE_FILE, SED1017_FILE, BLADE_PROFILES_FILE,
                    '-s', '-f', '-d', '-dr']

        try:
            vc_blade_profile.main()
        except SystemExit as e:
            raised = True
            self.assertEquals(e.code, 1)
            self.assertEquals(os.strerror(e.code), 'Operation not permitted')
        self.assertFalse(raised, 'Exception raised')
