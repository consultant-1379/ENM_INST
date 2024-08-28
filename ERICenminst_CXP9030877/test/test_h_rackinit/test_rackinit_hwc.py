import shutil
import json
import os
import sys
from os import makedirs, listdir
from os.path import join, dirname, isdir, exists
from tempfile import gettempdir

from mock import patch, MagicMock, call
from netaddr import IPNetwork, IPAddress
from unittest2 import TestCase

from redfish.rest.v1 import BadRequestError, InvalidCredentialsError, \
    DecompressResponseError, RetriesExhaustedError

from h_util.h_utils import Redfishtool
from h_rackinit.hwc import RedfishClient, Installer, \
    IfcfgGenerator, NodeSetup, NodeTester, get_main_args, main, \
    remove_modeled_nodes, Redfish
from h_rackinit.hwc_utils import PxeTimeoutError, Ssh, \
    NodeSetupError, ModelItem, _LITPNS, SiteDoc, XmlReader, RedfishException


class TestRedfishClient(TestCase):

    def setUp(self):
        self.log_mock = MagicMock()
        self.redfish_client = RedfishClient(self.log_mock)

    def tearDown(self):
        pass

    @patch('h_rackinit.hwc.sleep')
    def test_sleep(self, p_sleep):
        RedfishClient._sleep(0)
        self.assertEqual(0, p_sleep.call_count)
        RedfishClient._sleep(2)
        self.assertEqual(2, p_sleep.call_count)

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
        response.dict = json.loads(response.text)
        return response

    @patch('redfish.rest.v1.HttpClient')
    @patch('redfish.redfish_client')
    def test_valid_login(self, redfish_mock, mock_redfish_client):
        """
        Validating the login functionality in a positive
        workflow when all the arguments are provided correctly
        """
        redfish_mock.return_value = mock_redfish_client
        self.redfish_client._login('ilo', 'user', 'psw')
        mock_redfish_client.login.assert_called_once_with()

    @patch('redfish.rest.v1.HttpClient')
    @patch('redfish.redfish_client')
    def test_login_retries_exhausted_error(self, redfish_mock, mock_redfish_client):
        """
        Validating the login functionality in a negative
        workflow when retries exhausted error arises
        """
        redfish_mock.return_value = mock_redfish_client
        mock_redfish_client.login.side_effect = RetriesExhaustedError()
        self.assertRaises(RetriesExhaustedError, self.redfish_client._login, 'ilo', 'user', 'psw')
        mock_redfish_client.login.assert_called_once_with()

    @patch('redfish.rest.v1.HttpClient')
    @patch('redfish.redfish_client')
    def test_login_invalid_credentials_error(self, redfish_mock, mock_redfish_client):
        """
        Validating the login functionality when the credentials is incorrect
        """
        excep_msg = "Invalid credentials provided for BMC"
        redfish_mock.return_value = mock_redfish_client
        mock_redfish_client.login.side_effect = InvalidCredentialsError(excep_msg)
        self.assertRaises(RedfishException, self.redfish_client._login, 'ilo', 'user', 'psw')
        mock_redfish_client.login.assert_called_once_with()
        self.log_mock.error.assert_called_with('._login: ilo: ' + excep_msg)

    @patch('redfish.rest.v1.HttpClient')
    def test_valid_logout(self, mock_redfish):
        """
        Validating the logout functionality in a positive
        workflow.
        """
        self.redfish_client._logout(mock_redfish)
        mock_redfish.logout.assert_called_once_with()

    @patch('redfish.rest.v1.HttpClient')
    def test_logout_bad_request_error(self, mock_redfish):
        """
        Validating the logout functionality for bad request error case
        """
        mock_redfish.logout.side_effect = BadRequestError('Bad Request')
        self.redfish_client._logout(mock_redfish)
        mock_redfish.logout.assert_called_once_with()
        self.log_mock.error.assert_called_once_with('_logout: Bad Request')

    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_successful_poweron(self, mock_redfish):
        """
        Validating the toggle power on functionality in a positive
        workflow when all the arguments are provided correctly
        """
        mock_redfish.post.return_value = self. \
            get_mock_response(200, 'pxeboot_Success')
        self.redfish_client._toggle_power(mock_redfish, 'On')
        self.log_mock.debug.assert_called_with("._toggle_power: Power On Outcome: Success")

    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_successful_poweroff(self, mock_redfish):
        """
        Validating the toggle power off functionality in a positive
        workflow when all the arguments are provided correctly
        """
        mock_redfish.post.return_value = self. \
            get_mock_response(200, 'pxeboot_Success')
        self.redfish_client._toggle_power(mock_redfish, 'ForceOff')
        self.log_mock.debug.assert_called_with("._toggle_power: Power ForceOff Outcome: Success")

    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_invalid_parameter(self, mock_redfish):
        """
        Validating the toggle power functionality when an invalid
        parameter is passed as an argument
        """
        mock_redfish.post.return_value = self.get_mock_response(400, 'invalid_parameter_response')
        self.assertRaises(RedfishException, self.redfish_client._toggle_power, mock_redfish, 'something')
        self.log_mock.error.assert_called_with("._toggle_power: Power something Outcome: Failure,"
                                          " status:400 :"
                                          " \'Base.1.0."
                                          "ActionNotSupported\'")

    @patch('h_util.h_utils.Redfishtool.get_error_message')
    @patch('redfish.rest.v1.HttpClient')
    def test_toggle_power_invalid_session(self, mock_redfish, mock_get_error):
        """
        Validating the toggle power functionality when an invalid
        parameter is passed as an argument
        """
        mock_get_error.return_value = 'Base.0.10.NoValidSession'
        mock_redfish.post.return_value = self.get_mock_response(401, 'no_valid_session')
        self.assertRaises(RedfishException, self.redfish_client._toggle_power, mock_redfish, 'On')
        self.log_mock.error.assert_called_with("._toggle_power: Power On Outcome: Failure,"
                                                     " status:401 :"
                                                     " \'Base.0.10."
                                                     "NoValidSession\'")

    @patch('redfish.rest.v1.HttpClient')
    def test_set_pxe(self, mock_redfish):
        """
        Validating the _set_pxe functionality in a positive
        workflow.
        """
        mock_redfish.patch.return_value = self. \
            get_mock_response(200, 'pxeboot_Success')
        body = {"Boot": {"BootSourceOverrideTarget": "Pxe",
                         "BootSourceOverrideEnabled": "Once"}}
        self.redfish_client._set_pxe(mock_redfish)
        mock_redfish.patch.assert_called_once_with("/redfish/v1/Systems/1/", body=body)
        self.log_mock.debug.assert_called_with("._set_pxe: Set boot to pxe Outcome: Success")

    @patch('h_util.h_utils.Redfishtool.get_error_message')
    @patch('redfish.rest.v1.HttpClient')
    def test_set_pxe_error(self, mock_redfish, mock_get_error):
        """
        Validating the _set_pxe functionality when a session
        becomes invalid
        """
        mock_get_error.return_value = 'Base.0.10.NoValidSession'
        mock_redfish.patch.return_value = self.get_mock_response(401, 'no_valid_session')
        body = {"Boot": {"BootSourceOverrideTarget": "Pxe",
                 "BootSourceOverrideEnabled": "Once"}}
        self.assertRaises(RedfishException, self.redfish_client._set_pxe, mock_redfish)
        mock_redfish.patch.assert_called_with("/redfish/v1/Systems/1/", body=body)
        self.log_mock.error.assert_called_with("._set_pxe: Set boot to pxe Outcome: Failure,"
                                                     " status:401 :"
                                                     " \'Base.0.10."
                                                     "NoValidSession\'")

    @patch('h_rackinit.hwc.RedfishClient._login')
    @patch('h_rackinit.hwc.RedfishClient._logout')
    @patch('h_rackinit.hwc.RedfishClient._set_pxe')
    @patch('h_rackinit.hwc.RedfishClient._toggle_power')
    @patch('h_rackinit.hwc.RedfishClient._sleep')
    def test_pxe_boot_node(self, _sleep, _toggle_power, _set_pxe, _logout, _login):
        """
        Validating the pxe_boot_node functionality in a positive
        workflow.
        """
        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        config = sed.get_node_config('str_node1')
        redfish_client = MagicMock()
        _login.return_value = redfish_client
        self.redfish_client.pxe_boot_node('sys', config)

        self.assertEqual(_login.call_count, 1)
        _login.assert_called_with('1.1.1.1', 'username', 'password')
        self.assertEqual(_logout.call_count, 1)

        args, kwargs = self.log_mock.debug.call_args_list[0]
        self.assertTrue(args[0] == '.pxe_boot_node: sys : Start')
        args, kwargs = self.log_mock.debug.call_args_list[1]
        self.assertTrue(args[0] == ".pxe_boot_node: sys : "
                                                 "Will create session with Redfish API "
                                                 "at 1.1.1.1 for user username")
        args, kwargs = self.log_mock.debug.call_args_list[2]
        self.assertTrue(args[0] == '.pxe_boot_node: sys : End')

        self.assertEqual(_set_pxe.call_count, 1)
        _set_pxe.assert_called_with(redfish_client)

        self.assertEqual(_toggle_power.call_count, 2)
        args, kwargs = _toggle_power.call_args_list[0]
        self.assertTrue(args[1] == 'ForceOff')
        args, kwargs = _toggle_power.call_args_list[1]
        self.assertTrue(args[1] == 'On')

        self.assertEqual(_sleep.call_count, 3)
        args, kwargs = _sleep.call_args_list[0]
        self.assertTrue(args[0] == 30)
        args, kwargs = _sleep.call_args_list[1]
        self.assertTrue(args[0] == 30)
        args, kwargs = _sleep.call_args_list[2]
        self.assertTrue(args[0] == 90)

    @patch('h_rackinit.hwc.RedfishClient._login')
    @patch('h_rackinit.hwc.RedfishClient._logout')
    @patch('h_rackinit.hwc.RedfishClient._set_pxe')
    @patch('h_rackinit.hwc.RedfishClient._toggle_power')
    @patch('h_rackinit.hwc.RedfishClient._sleep')
    def test_pxe_boot_node_max_retries_exhausted_error(self, _sleep, _toggle_power, _set_pxe, _logout, _login):
        """
        Validating the pxe_boot_node functionality when number of retries exhausted.
        """
        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        config = sed.get_node_config('str_node1')
        _login.side_effect = RetriesExhaustedError
        self.assertRaises(RedfishException,
                          self.redfish_client.pxe_boot_node, 'sys', config)
        self.assertEqual(_login.call_count, 1)
        self.assertEqual(_logout.call_count, 1)
        self.assertEqual(_set_pxe.call_count, 0)
        self.assertEqual(_toggle_power.call_count, 0)
        self.assertEqual(_sleep.call_count, 0)
        self.log_mock.error.assert_called_with(".pxe_boot_node: sys : "
                                                     "Max number of retries exhausted")

    @patch('h_rackinit.hwc.RedfishClient._login')
    @patch('h_rackinit.hwc.RedfishClient._logout')
    @patch('h_rackinit.hwc.RedfishClient._set_pxe')
    @patch('h_rackinit.hwc.RedfishClient._toggle_power')
    @patch('h_rackinit.hwc.RedfishClient._sleep')
    def test_pxe_boot_node_decompress_error(self, _sleep, _toggle_power, _set_pxe, _logout, _login):
        """
        Validating the pxe_boot_node functionality when response cannot be decompressed.
        """
        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        config = sed.get_node_config('str_node1')
        _toggle_power.side_effect = DecompressResponseError
        self.assertRaises(RedfishException,
                          self.redfish_client.pxe_boot_node, 'sys', config)
        self.assertEqual(_login.call_count, 1)
        self.assertEqual(_logout.call_count, 1)
        self.assertEqual(_toggle_power.call_count, 1)
        self.assertEqual(_set_pxe.call_count, 0)
        self.assertEqual(_sleep.call_count, 0)
        self.log_mock.error.assert_called_with(".pxe_boot_node: sys : "
                                                     "Error while decompressing response")

    @patch('os.path')
    @patch('os.access')
    def test_redfish_cloud_tool_exec(self, mock_os_path, mock_access):
        """
        Validating when Redfish tool path file exist and is accessible.
        """
        mock_os_path.isfile.return_value = True
        mock_access.return_value = True
        self.assertTrue(Redfishtool.is_cloud_env())

    @patch('os.path')
    def test_redfish_no_cloud_tool(self, mock_os_path):
        """
        Validating when Redfish tool file doesn't exist.
        """
        mock_os_path.isfile.return_value = False
        self.assertFalse(Redfishtool.is_cloud_env())

    @patch('os.access')
    @patch('os.path')
    def test_redfish_cloud_tool_no_exec(self, mock_os_path, mock_access):
        """
        Validating when Redfish tool path file exist but is not accessible.
        """
        mock_os_path.isfile.return_value = True
        mock_access.return_value = False
        self.assertFalse(Redfishtool.is_cloud_env())

    @patch('os.path')
    def test_redfish_cloud_tool_exception(self, mock_os_path):
        """
        Validating when Redfish tool path resource throw an exception.
        """
        mock_os_path.isfile.side_effect = OSError
        self.assertFalse(Redfishtool.is_cloud_env())

    @patch('os.path')
    @patch('os.access')
    def test_redfish_cloud_adapter(self, mock_os_path, mock_access):
        """
        Validating cloud adapter invocation
        """
        mock_os_path.isfile.return_value = True
        mock_access.return_value = True
        self.assertTrue(Redfishtool.is_cloud_env())

        sys.modules['redfishtool'] = MagicMock()
        with patch('imp.load_source') as module:
            cloud_adapter_mock = MagicMock()
            module.return_value = cloud_adapter_mock
            self.redfish_client._login('ilo', 'user', 'psw')
            self.assertTrue(module.called)


class TestRedfish(TestCase):
    def test_pxe_boot_node(self):
        redfish_mock = Redfish(MagicMock())
        impl = MagicMock(name='redfish_implementation')
        redfish_mock._redfish = impl
        mocked_pxe_boot_node = MagicMock()

        impl.pxe_boot_node = mocked_pxe_boot_node

        cfg = MagicMock(name='env_sed', spec=SiteDoc)
        redfish_mock.pxe_boot_node('node', cfg)

        mocked_pxe_boot_node.assert_called_once_with('node', cfg)


class TestInstaller(TestCase):
    def setUp(self):
        super(TestInstaller, self).setUp()
        self.tmpdir = join(gettempdir(), 'TestInstaller')
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        makedirs(self.tmpdir)

    def tearDown(self):
        super(TestInstaller, self).tearDown()
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    @patch('h_rackinit.hwc.BaseObject.get_temp_dir')
    def test_init(self, p_get_temp_dir):
        tmpdir = join(self.tmpdir, 'init')
        p_get_temp_dir.return_value = tmpdir
        inst = Installer(MagicMock())
        inst.init()
        self.assertTrue(isdir(tmpdir))

    @patch('h_rackinit.hwc.sleep')
    @patch('h_rackinit.hwc.Installer.exec_process')
    def test_wait_for_node(self, p_exec_process, p_sleep):
        inst = Installer(MagicMock())

        inst.wait_for_node('sys', '1.1.1.1')
        p_exec_process.assert_called_once_with(
                ['/usr/bin/nc', '-w', '30', '1.1.1.1', '22'])

        p_exec_process.reset_mock()
        p_exec_process.side_effect = [IOError(), 'worked']
        inst.wait_for_node('sys', '1.1.1.1')
        p_sleep.assert_called_once_with(1.0)
        self.assertEqual(2, p_exec_process.call_count)

        p_exec_process.reset_mock()
        p_exec_process.side_effect = [IOError(), IOError()]
        inst._max_waiting_time_for_node = -1
        self.assertRaises(PxeTimeoutError, inst.wait_for_node,
                          'sys', '1.1.1.1')

    @patch('h_rackinit.hwc.Installer.wait_for_node')
    @patch('h_rackinit.hwc.ping')
    @patch('h_rackinit.hwc.Redfish')
    @patch('h_rackinit.hwc.Kickstarts.generate')
    @patch('h_rackinit.hwc.CobblerCli')
    @patch('h_rackinit.hwc.BaseObject.get_temp_dir')
    def test_pxe_nodes(self, p_get_temp_dir, p_cobbler, p_kickstart,
                       p_redfish, p_ping, p_wait_for_node):
        p_get_temp_dir.return_value = self.tmpdir
        with open(Ssh._priv(), 'w') as _w:
            _w.write('a')
        with open(Ssh._pub(), 'w') as _w:
            _w.write('a')
        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))

        xml = XmlReader()
        xml.load(join(dirname(__file__), 'hwc_test_model.xml'))

        m_log = MagicMock()
        inst = Installer(m_log)

        self.assertRaises(ValueError, inst.pxe_nodes, ['abc'], sed, xml, '')

        def assert_call_installs():
            p_ping.assert_called_once_with(sed['str_node1_IP_internal'])
            p_cobbler.assert_has_calls([
                call(m_log),
                call().deconfigure_system('test-system'),
                call().configure_system('test-system',
                                        sed.get_node_config('str_node1'),
                                        'node.ks',
                                        'eth4',
                                        sed['str_node1_IP_internal'], ''),
                call().sync(),
                call().deregister_system('test-system'),
                call().sync()
            ])
            self.assertEqual(1, p_wait_for_node.call_count)
            p_redfish.assert_has_calls([
                call(sed, m_log),
                call().pxe_boot_node('test-system',
                                     sed.get_node_config('str_node1'))
            ])

        p_ping.return_value = False
        p_kickstart.return_value = 'node.ks'
        inst.pxe_nodes(['str-1'], sed, xml, '')
        assert_call_installs()

        p_ping.return_value = True
        p_kickstart.reset_mock()
        p_cobbler.reset_mock()
        with patch('__builtin__.raw_input', return_value='n') as _:
            inst.pxe_nodes(['str-1'], sed, xml, '')
        self.assertEqual(0, p_kickstart.call_count)
        # The one call is the constructor
        self.assertEqual(1, p_cobbler.call_count)

        p_ping.reset_mock()
        p_ping.return_value = True
        p_kickstart.reset_mock()
        p_cobbler.reset_mock()
        p_wait_for_node.reset_mock()
        with patch('__builtin__.raw_input', return_value='y') as _:
            inst.pxe_nodes(['str-1'], sed, xml, '')
        assert_call_installs()

        p_ping.reset_mock()
        p_ping.return_value = True
        p_kickstart.reset_mock()
        p_cobbler.reset_mock()
        p_wait_for_node.reset_mock()
        inst.pxe_nodes(['str-1'], sed, xml, '', force=True)
        assert_call_installs()

        e_error = PxeTimeoutError('n', '1', 5)
        p_ping.return_value = False
        p_wait_for_node.side_effect = [e_error]
        m_log.reset_mock()
        inst.pxe_nodes(['str-1'], sed, xml, '', force=True)
        m_log.assert_has_calls(call.exception(e_error))


class IfcfgGeneratorTest(TestCase):
    def assert_cfg(self, cfg, required, excluded=None):
        for req in required:
            self.assertTrue(req in cfg,
                            msg='Did not find "{0}" in device config'.format(
                                    req))
        if excluded:
            for exc in excluded:
                self.assertFalse(exc in cfg,
                                 msg='Found "{0}" in device config'.format(
                                         exc))

    def test_generate_bridge(self):
        cfg = IfcfgGenerator.generate_bridge('dn', 'addr', 'netm', 'b',
                                             'abc')
        self.assert_cfg(cfg, ['NETMASK=netm',
                              'DEVICE=dn',
                              'IPADDR=addr',
                              'BROADCAST=b',
                              'BRIDGING_OPTS="abc"',
                              'TYPE=Bridge',
                              'ONBOOT=yes'])

    def test_generate_bond(self):
        cfg = IfcfgGenerator.generate_bond('b', 'opts')
        self.assert_cfg(cfg,
                        ['DEVICE=b',
                         'BONDING_OPTS="opts"',
                         'TYPE=Bonding',
                         'ONBOOT=yes'],
                        ['BRIDGE='])

        cfg = IfcfgGenerator.generate_bond('b', 'opts', bridge='br0')
        self.assert_cfg(cfg, ['DEVICE=b',
                              'BONDING_OPTS="opts"',
                              'TYPE=Bonding',
                              'BRIDGE=br0',
                              'ONBOOT=yes'])

    def test_generate_slave_nic(self):
        cfg = IfcfgGenerator.generate_slave_nic('eth', 'm')
        self.assert_cfg(cfg, ['DEVICE=eth',
                              'MASTER=m',
                              'SLAVE=yes',
                              'ONBOOT=yes'])

    def test_generate_eth(self):
        cfg = IfcfgGenerator.generate_eth('eth', '1', '2', '3')
        self.assert_cfg(cfg,
                        ['DEVICE=eth',
                         'ONBOOT=yes',
                         'IPADDR=1',
                         'NETMASK=2',
                         'BROADCAST=3'],
                        ['BRIDGE=', 'SLAVE='])

        cfg = IfcfgGenerator.generate_eth('eth', '1', '2', '3', bridge='br0')
        self.assert_cfg(cfg,
                        ['DEVICE=eth',
                         'ONBOOT=yes',
                         'IPADDR=1',
                         'NETMASK=2',
                         'BROADCAST=3',
                         'BRIDGE=br0'],
                        ['SLAVE='])

        cfg = IfcfgGenerator.generate_eth('eth')
        self.assert_cfg(cfg,
                        ['DEVICE=eth',
                         'ONBOOT=yes'],
                        ['SLAVE=',
                         'IPADDR=',
                         'NETMASK=',
                         'BROADCAST='])

        cfg = IfcfgGenerator.generate_eth('eth', bridge='br0')
        self.assert_cfg(cfg,
                        ['DEVICE=eth',
                         'ONBOOT=yes',
                         'BRIDGE=br0'],
                        ['SLAVE=',
                         'IPADDR=',
                         'NETMASK=',
                         'BROADCAST='])

    def test_generate_vlan(self):
        cfg = IfcfgGenerator.generate_vlan('v', '1', '2', '3')
        self.assert_cfg(cfg,
                        ['DEVICE=v',
                         'ONBOOT=yes',
                         'VLAN=yes',
                         'IPADDR=1',
                         'NETMASK=2',
                         'BROADCAST=3'],
                        ['BRIDGE='])

        cfg = IfcfgGenerator.generate_vlan('v', '1', '2', '3', bridge='br1')
        self.assert_cfg(cfg,
                        ['DEVICE=v',
                         'ONBOOT=yes',
                         'VLAN=yes',
                         'IPADDR=1',
                         'NETMASK=2',
                         'BROADCAST=3',
                         'BRIDGE=br1'])

        cfg = IfcfgGenerator.generate_vlan('v', bridge='br1')
        self.assert_cfg(cfg,
                        ['DEVICE=v',
                         'ONBOOT=yes',
                         'VLAN=yes',
                         'BRIDGE=br1'],
                        ['IPADDR=',
                         'NETMASK=',
                         'BROADCAST='])

        cfg = IfcfgGenerator.generate_vlan('v')
        self.assert_cfg(cfg,
                        ['DEVICE=v',
                         'ONBOOT=yes',
                         'VLAN=yes'],
                        ['IPADDR=',
                         'NETMASK=',
                         'BROADCAST=',
                         'BRIDGE='])


class TestNodeSetup(TestCase):
    def setUp(self):
        super(TestNodeSetup, self).setUp()
        self.tmpdir = join(gettempdir(), 'TestNodeSetup')
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        makedirs(self.tmpdir)

    def tearDown(self):
        super(TestNodeSetup, self).tearDown()
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    def mock_xml_element(self, item_type, item_id):
        m_xml = MagicMock(tag=_LITPNS + item_type)
        m_xml.get.return_value = item_id

        return m_xml

    def mock_model_item(self, item_type, item_id, **properties):
        item = ModelItem(self.mock_xml_element(item_type, item_id))

        item.set_defaults(properties)
        return item

    def test_get_address_info(self):
        setup = NodeSetup(MagicMock())

        net_internal = IPNetwork('192.168.0.0/24')
        subnets = {
            'internal': net_internal,
            'services': IPNetwork('131.75.2.0/28')
        }
        addr, sub = setup._get_address_subnet(
                'str-1', '192.168.0.202', 'eth0', 'internal', subnets)
        self.assertEqual(IPAddress('192.168.0.202'), addr)

        addr, sub = setup._get_address_subnet(
                'str-1', '131.75.2.14', 'eth0', 'services', subnets)
        self.assertEqual(IPAddress('131.75.2.14'), addr)

        self.assertRaises(NodeSetupError, setup._get_address_subnet,
                          'str-1', '192.168.0.202', 'eth0', 'hhhh', subnets)

        self.assertRaises(NodeSetupError, setup._get_address_subnet,
                          'str-1', '131.75.2.20', 'eth0', 'services', subnets)

    def test_get_bonding_options(self):
        setup = NodeSetup(MagicMock())

        self.assertRaises(NodeSetupError, setup._get_bonding_options,
                          self.mock_model_item('bond', 'bond0'))

        bond0 = self.mock_model_item('bond', 'bond0', mode=4)
        self.assertEqual('mode=4', setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     arp_interval=1)
        self.assertEqual('mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     arp_ip_target=1)
        self.assertEqual('mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     arp_interval=1,
                                     arp_ip_target=2)
        self.assertEqual('arp_interval=1 arp_ip_target=2 mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     arp_interval=1,
                                     arp_ip_target=2,
                                     arp_validate=3)
        self.assertEqual('arp_interval=1 arp_ip_target=2 mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     arp_interval=1,
                                     arp_ip_target=2,
                                     arp_all_targets=3)
        self.assertEqual('arp_interval=1 arp_ip_target=2 mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     arp_interval=1,
                                     arp_ip_target=2,
                                     arp_validate=3,
                                     arp_all_targets=4)
        self.assertEqual('arp_interval=1 arp_ip_target=2 '
                         'arp_validate=3 arp_all_targets=4 mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1, miimon=100)
        self.assertEqual('miimon=100 mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1, primary='e')
        self.assertEqual('mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     primary_reselect='e')
        self.assertEqual('mode=1',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     primary='a',
                                     primary_reselect='e')
        self.assertEqual('mode=1 primary=a primary_reselect=e',
                         setup._get_bonding_options(bond0))

        bond0 = self.mock_model_item('bond', 'bond0', mode=1,
                                     xmit_hash_policy='x')
        self.assertEqual('mode=1 xmit_hash_policy=x',
                         setup._get_bonding_options(bond0))

    def test_get_bridging_options(self):
        setup = NodeSetup(MagicMock())

        br = self.mock_model_item('bridge', 'br0', multicast_snooping='1')
        cfg = setup._get_bridging_options(br)
        self.assertTrue('multicast_snooping=1' in cfg)
        self.assertTrue('multicast_querier=0' in cfg)
        self.assertTrue('multicast_router=1' in cfg)
        self.assertTrue('hash_max=512' in cfg)
        self.assertTrue('hash_elasticity=4' in cfg)

        br = self.mock_model_item('bridge', 'br0', multicast_snooping='1',
                                  multicast_querier='2')
        self.assertTrue(
                'multicast_querier=2' in setup._get_bridging_options(br))

        br = self.mock_model_item('bridge', 'br0', multicast_snooping='1',
                                  multicast_router='3')
        self.assertTrue(
                'multicast_router=3' in setup._get_bridging_options(br))

        br = self.mock_model_item('bridge', 'br0', multicast_snooping='1',
                                  hash_max='4')
        self.assertTrue(
                'hash_max=4' in setup._get_bridging_options(br))

        br = self.mock_model_item('bridge', 'br0', multicast_snooping='1',
                                  hash_elasticity='5')
        self.assertTrue(
                'hash_elasticity=5' in setup._get_bridging_options(br))

    def test_get_bridge_config(self):
        setup = NodeSetup(MagicMock())

        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        subnets = {
            'internal': IPNetwork('192.168.1.0/24'),
            'services': IPNetwork('131.75.2.0/28')
        }

        br = self.mock_model_item('bridge', 'br0', multicast_snooping='1',
                                  network_name='internal',
                                  device_name='br0')
        devname, cfg = setup._get_bridge_config('str-1', br, sed, subnets)
        self.assertEqual('br0', devname)
        self.assertTrue('NETMASK=255.255.255.0' in cfg)
        self.assertTrue('DEVICE=br0' in cfg)
        self.assertTrue('IPADDR=192.168.1.22' in cfg)
        self.assertTrue('BROADCAST=192.168.1.255' in cfg)
        self.assertTrue('TYPE=Bridge' in cfg)
        self.assertTrue('BRIDGING_OPTS="multicast_snooping=1 '
                        'multicast_querier=0 multicast_router=1 '
                        'hash_max=512 hash_elasticity=4"' in cfg)

    def test_get_real_device_name(self):
        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        self.assertEqual('vlan.909', NodeSetup.get_real_device_name(
                'vlan.%%VLAN_ID_services%%', sed))

        self.assertEqual('eth3', NodeSetup.get_real_device_name('eth3', sed))

    def test_get_vlan_config(self):
        setup = NodeSetup(MagicMock())
        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        subnets = {
            'internal': IPNetwork('192.168.1.0/24'),
            'services': IPNetwork('131.75.2.0/28')
        }
        vlan = self.mock_model_item('vlan', 'vlan_%%VLAN_ID_services%%',
                                    network_name='services',
                                    device_name='bond0.%%VLAN_ID_services%%')

        devname, cfg = setup._get_vlan_config('str-2', vlan, sed, subnets)
        self.assertEqual('bond0.909', devname)
        self.assertTrue('DEVICE=bond0.909' in cfg)
        self.assertTrue('VLAN=yes' in cfg)
        self.assertFalse('IPADDR=' in cfg)

        vlan = self.mock_model_item('vlan', 'vlan_%%VLAN_ID_services%%',
                                    network_name='services',
                                    device_name='bond0.%%VLAN_ID_services%%',
                                    ipaddress='131.75.2.10')
        devname, cfg = setup._get_vlan_config('str-1', vlan, sed, subnets)
        self.assertEqual('bond0.909', devname)
        self.assertTrue('DEVICE=bond0.909' in cfg)
        self.assertTrue('VLAN=yes' in cfg)
        self.assertTrue('IPADDR=131.75.2.10' in cfg)
        self.assertTrue('NETMASK=255.255.255.240' in cfg)
        self.assertTrue('BROADCAST=131.75.2.15' in cfg)

    def test_get_static_route_config(self):
        self.assertEqual('ADDRESS0=0.0.0.0 NETMASK0=0.0.0.0 GATEWAY0=aaaa',
                         NodeSetup._get_static_route_config('aaaa'))

    def test_get_bond_slave_config(self):
        setup = NodeSetup(MagicMock())

        slave = self.mock_model_item('eth', 'eth0', device_name='eth0',
                                     master='bond0')
        devname, cfg = setup._get_bond_slave_config(slave)
        self.assertEqual('eth0', devname)
        self.assertTrue('DEVICE=eth0' in cfg)
        self.assertTrue('MASTER=bond0' in cfg)
        self.assertTrue('SLAVE=yes' in cfg)

    def test_get_bond_config(self):
        setup = NodeSetup(MagicMock())

        bond0 = self.mock_model_item('bond', 'bond0', mode=1, miimon=100,
                                     device_name='bond0')

        devname, cfg = setup._get_bond_config(bond0)
        self.assertEqual('bond0', devname)
        self.assertTrue('DEVICE=bond0' in cfg)
        self.assertTrue('TYPE=Bonding' in cfg)

    def test_get_plumbed_eth_config(self):
        setup = NodeSetup(MagicMock())
        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        subnets = {
            'internal': IPNetwork('192.168.1.0/24'),
            'services': IPNetwork('131.75.2.0/28')
        }
        eth0 = self.mock_model_item('eth', 'eth0', device_name='eth0',
                                    network_name='internal')
        devname, cfg = setup._get_plumbed_eth_config('str-1', eth0,
                                                     sed, subnets)
        self.assertEqual('eth0', devname)
        self.assertTrue('DEVICE=eth0' in cfg)
        self.assertTrue('IPADDR=192.168.1.22' in cfg)
        self.assertTrue('NETMASK=255.255.255.0' in cfg)
        self.assertTrue('BROADCAST=192.168.1.255' in cfg)

    def test_get_blank_eth_config(self):
        devname, cfg = NodeSetup._get_blank_eth_config(self.mock_model_item(
                'eth', 'eth0', device_name='eth0'))
        self.assertEqual('eth0', devname)
        self.assertTrue('DEVICE=eth0' in cfg)
        self.assertTrue('USERCTL=no' in cfg)
        self.assertTrue('ONBOOT=yes' in cfg)
        self.assertTrue('BOOTPROTO=static' in cfg)
        self.assertTrue('NOZEROCONF=yes' in cfg)

    def test_get_bridged_eth_config(self):
        devname, cfg = NodeSetup._get_bridged_eth_config(self.mock_model_item(
                'eth', 'eth0', device_name='eth0', bridge='br0'))
        self.assertEqual('eth0', devname)
        self.assertTrue('DEVICE=eth0' in cfg)
        self.assertTrue('BRIDGE=br0' in cfg)

    @patch('h_rackinit.hwc.Ssh.ssh_priv')
    @patch('h_rackinit.hwc.BaseObject.exec_process')
    def test_create_snapshot(self, p_exec_process, p_ssh_priv):
        p_ssh_priv.return_value = 'key'
        setup = NodeSetup(MagicMock())

        origin = 'lv_home,/dev/vg_root/lv_home,'
        snapshot = ''

        p_exec_process.return_value = '\n'.join([origin, snapshot])
        setup.create_snapshot('str-1', '1.1.1.1')
        p_exec_process.assert_any_call(
                ['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                 '-i', 'key', 'root@1.1.1.1', 'lvcreate',
                 '--snapshot', '--addtag', NodeSetup._SNAP_TAG, '--extents',
                 '10%ORIGIN', '--name', NodeSetup._SNAP_PREFIX + 'lv_home',
                 '/dev/vg_root/lv_home'])

        origin = 'lv_home,/dev/vg_root/lv_home,'
        snapshot = '{0}lv_home,/dev/vg_root/{0}lv_home,lv_home'.format(
                NodeSetup._SNAP_PREFIX)
        p_exec_process.reset_mock()
        p_exec_process.return_value = '\n'.join([origin, snapshot])
        setup.create_snapshot('str-1', '1.1.1.1')
        try:
            e_args = ['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                      '-i', 'key', 'root@1.1.1.1', 'lvcreate',
                      '--snapshot', '--addtag', NodeSetup._SNAP_TAG,
                      '--extents',
                      '10%ORIGIN', '--name',
                      NodeSetup._SNAP_PREFIX + 'lv_home',
                      '/dev/vg_root/lv_home']
            p_exec_process.assert_any_call(e_args)
            self.fail('Unexpected call with {0}'.format(e_args))
        except AssertionError:
            pass

    @patch('h_rackinit.hwc.Ssh.ssh_priv')
    @patch('h_rackinit.hwc.BaseObject.exec_process')
    def test_delete_snapshot(self, p_exec_process, p_ssh_priv):
        p_ssh_priv.return_value = 'key'
        setup = NodeSetup(MagicMock())
        setup.delete_snapshots('str-1', '1.1.1.1')
        p_exec_process.assert_any_call(
                ['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                 '-i', 'key', 'root@1.1.1.1', 'lvremove', '-f',
                 '@' + NodeSetup._SNAP_TAG])

    def test_diff(self):
        self.assertEqual(set([]), NodeSetup.diff('aa', 'aa'))
        self.assertNotEqual(set([]), NodeSetup.diff('aa', 'ab'))

    @patch('h_rackinit.hwc.NodeSetup.diff')
    @patch('h_rackinit.hwc.Ssh.ssh_priv')
    @patch('h_rackinit.hwc.BaseObject.exec_process')
    def test_networks(self, p_exec_process, p_ssh_priv, p_diff):
        p_ssh_priv.return_value = 'key'

        setup = NodeSetup(MagicMock())
        setup.tmpdir = join(self.tmpdir, 'networks')
        if not isdir(setup.tmpdir):
            makedirs(join(setup.tmpdir, 'str-1'))

        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        xml = XmlReader()
        xml.load(join(dirname(__file__), 'hwc_test_model.xml'))

        self.assertRaises(ValueError, setup.networks, ['str-x'], sed, xml)

        origin = 'lv_home,/dev/vg_root/lv_home,'
        snapshot = '{0}lv_home,/dev/vg_root/{0}lv_home,lv_home'.format(
                NodeSetup._SNAP_PREFIX)
        p_exec_process.return_value = '\n'.join([origin, snapshot])
        p_diff.return_value = 'diffs'
        expected = ['ifcfg-bond0', 'ifcfg-bond0.101', 'ifcfg-bond0.102',
                    'ifcfg-bond0.103', 'ifcfg-bond0.909', 'ifcfg-br0',
                    'ifcfg-br1', 'ifcfg-br2', 'ifcfg-br3', 'ifcfg-eth0',
                    'ifcfg-eth1', 'ifcfg-eth2', 'ifcfg-eth3', 'ifcfg-eth4',
                    'route-br0']
        scp_calls = []
        node_id = 'str-1'
        for cfg_file in expected:
            _tfile = join(setup.tmpdir, node_id, cfg_file)
            scp_calls.append(call([
                '/usr/bin/scp', '-i', 'key', '-o',
                'StrictHostKeyChecking=no', _tfile,
                'root@192.168.1.22:/etc/sysconfig/network-scripts/' + cfg_file
            ]))

        setup.networks([node_id], sed, xml)
        f_list = listdir(join(setup.tmpdir, node_id))
        self.assertEqual(len(expected), len(f_list),
                         msg='Only {0} generated file expected;'
                             ' got {1} {2}'.format(len(expected), len(f_list),
                                                   f_list))
        for cfg_file in expected:
            _tfile = join(setup.tmpdir, node_id, cfg_file)
            self.assertTrue(exists(_tfile))
        p_exec_process.assert_has_calls(scp_calls, any_order=True)
        p_exec_process.assert_any_call(
                ['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                 '-i', 'key', 'root@192.168.1.22', '/etc/init.d/network',
                 'restart'])

        p_exec_process.reset_mock()
        shutil.rmtree(join(setup.tmpdir, node_id))
        p_diff.return_value = None
        setup.networks([node_id], sed, xml)
        f_list = listdir(join(setup.tmpdir, node_id))
        self.assertEqual(len(expected), len(f_list),
                         msg='Only {0} generated file expected;'
                             ' got {1} {2}'.format(len(expected), len(f_list),
                                                   f_list))
        for cfg_file in expected:
            _tfile = join(setup.tmpdir, node_id, cfg_file)
            self.assertTrue(exists(_tfile))
        for nocall in scp_calls:
            try:
                p_exec_process.assert_has_calls([nocall])
                self.fail('Unexpected call with {0}'.format(nocall))
            except AssertionError:
                pass

        p_exec_process.reset_mock()
        shutil.rmtree(join(setup.tmpdir, node_id))
        p_diff.return_value = None

        def r(a, b):
            raise IOError()

        with patch('h_rackinit.hwc.Ssh.cat') as p_cat:
            p_cat.side_effect = r
            setup.networks([node_id], sed, xml)
        f_list = listdir(join(setup.tmpdir, node_id))
        self.assertEqual(len(expected), len(f_list),
                         msg='Only {0} generated file expected;'
                             ' got {1} {2}'.format(len(expected), len(f_list),
                                                   f_list))

        node_id = 'str-4'
        p_exec_process.reset_mock()
        p_diff.return_value = 'diffs'
        setup.networks([node_id], sed, xml)
        expected = ['ifcfg-eth0', 'ifcfg-br0', 'ifcfg-eth1']
        scp_calls = []
        for cfg_file in expected:
            _tfile = join(setup.tmpdir, node_id, cfg_file)
            scp_calls.append(call([
                '/usr/bin/scp', '-i', 'key', '-o',
                'StrictHostKeyChecking=no', _tfile,
                'root@192.168.1.24:/etc/sysconfig/network-scripts/' + cfg_file
            ]))

        f_list = listdir(join(setup.tmpdir, node_id))
        self.assertEqual(len(expected), len(f_list),
                         msg='Only {0} generated file expected;'
                             ' got {1} {2}'.format(len(expected), len(f_list),
                                                   f_list))
        for cfg_file in expected:
            _tfile = join(setup.tmpdir, node_id, cfg_file)
            self.assertTrue(exists(_tfile),
                            msg='Expected file "{0}" not found!'.format(
                                    _tfile))
        p_exec_process.assert_has_calls(scp_calls, any_order=True)
        p_exec_process.assert_any_call(
                ['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                 '-i', 'key', 'root@192.168.1.24', '/etc/init.d/network',
                 'restart'])


class TestNodeTester(TestCase):
    def mock_node_networks(self, name, networks):
        node = MagicMock(name=name)
        _children = []
        for net in networks:
            name = net['name']
            if 'addr' in net:
                m_net = MagicMock(name=name, ipaddress=net['addr'],
                                  network_name=name,
                                  device_name=name)
            else:
                m_net = MagicMock(name=name, ipaddress=None)
            _children.append(m_net)

        node.network_interfaces = MagicMock(name='network_interfaces')
        node.network_interfaces.children.return_value = _children
        return node

    def test_get_node_networks(self):
        node = self.mock_node_networks('n1', [
            {'name': 'net1', 'addr': '1'},
            {'name': 'net2'},
        ])

        networks = NodeTester.get_node_networks(node)
        self.assertEqual(1, len(networks))
        self.assertIn('net1', networks)
        self.assertEqual({'ipaddress': '1', 'device_name': 'net1'},
                         networks['net1'])

    @patch('h_rackinit.hwc.NodeTester.exec_process')
    def test_test_lms_node_connectivity(self, p_exec_process):
        tester = NodeTester(MagicMock())

        node = self.mock_node_networks('n1', [
            {'name': 'net1', 'addr': 'key_ip1'},
            {'name': 'net2', 'addr': 'key_ip2'},
        ])
        lms_nets = {
            'net1': {'device_name': 'eth0'}
        }

        sed = SiteDoc(None)
        sed.sed = {
            'key_ip1': '1',
            'key_ip2': '2'
        }

        self.assertFalse(tester.test_lms_node_connectivity(
                [node], lms_nets, sed))
        p_exec_process.assert_called_once_with(
                ['ping', '-c', '1', '-I', 'eth0', '1'])

        p_exec_process.reset_mock()
        p_exec_process.side_effect = IOError()
        self.assertTrue(tester.test_lms_node_connectivity(
                [node], lms_nets, sed))
        p_exec_process.assert_called_once_with(
                ['ping', '-c', '1', '-I', 'eth0', '1'])

    @patch('h_rackinit.hwc.Ssh.ssh_priv')
    @patch('h_rackinit.hwc.BaseObject.exec_process')
    def test_ping_network(self, p_exec_process, p_ssh_priv):
        p_ssh_priv.return_value = 'key'
        tester = NodeTester(MagicMock())

        self.assertTrue(tester.ping_network('source', 's_internal',
                                            's_device', 'target', 't_addr',
                                            't_net_name'))
        p_exec_process.assert_called_once_with(
                ['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                 '-i', 'key', 'root@s_internal', 'ping', '-c', '1', '-I',
                 's_device', 't_addr']
        )

        p_exec_process.reset_mock()
        p_exec_process.side_effect = IOError(1, 'uh?')
        self.assertFalse(tester.ping_network('source', 's_internal',
                                             's_device', 'target', 't_addr',
                                             't_net_name'))
        p_exec_process.assert_called_once_with(
                ['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                 '-i', 'key', 'root@s_internal', 'ping', '-c', '1', '-I',
                 's_device', 't_addr']
        )

    @patch('h_rackinit.hwc.Ssh.ssh_priv')
    @patch('h_rackinit.hwc.BaseObject.exec_process')
    def test_test_inter_node_connectivity(self, p_exec_process, p_ssh_priv):
        p_ssh_priv.return_value = 'key'
        tester = NodeTester(MagicMock())

        n1 = self.mock_node_networks('n1', [
            {'name': 'net1', 'addr': 'n1_ip1'},
            {'name': 'net2', 'addr': 'n1_ip2'},
            {'name': 'net3', 'addr': 'n1_ip3'}
        ])
        n2 = self.mock_node_networks('n2', [
            {'name': 'net1', 'addr': 'n2_ip1'},
            {'name': 'net2', 'addr': 'n2_ip2'},
        ])
        sed = SiteDoc(None)
        node1_source = '1'
        node2_source = '4'
        sed.sed = {
            'n1_ip1': node1_source,
            'n1_ip2': '2',
            'n1_ip3': '3',
            'n2_ip1': node2_source,
            'n2_ip2': '5'
        }
        self.assertFalse(tester.test_inter_node_connectivity(
                [n1, n2], sed, 'net1'))
        p_exec_process.assert_has_calls([
            call(['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no', '-i',
                  'key', 'root@' + node1_source, 'ping', '-c', '1', '-I',
                  'net2', '5']),
            call(['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no', '-i',
                  'key', 'root@' + node1_source, 'ping', '-c', '1', '-I',
                  'net1', '4']),
            call(['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no', '-i',
                  'key', 'root@' + node2_source, 'ping', '-c', '1', '-I',
                  'net2', '2']),
            call(['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no', '-i',
                  'key', 'root@' + node2_source, 'ping', '-c', '1', '-I',
                  'net1', '1'])
        ], any_order=True)

    @patch('h_rackinit.hwc.NodeTester.test_inter_node_connectivity')
    @patch('h_rackinit.hwc.NodeTester.test_lms_node_connectivity')
    def test_test(self, p_test_lms_node_connectivity,
                  p_test_inter_node_connectivity):
        sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        xml = XmlReader()
        xml.load(join(dirname(__file__), 'hwc_test_model.xml'))

        tester = NodeTester(MagicMock())

        self.assertRaises(ValueError, tester.test, ['str-88'], sed, xml)

        p_test_lms_node_connectivity.return_value = False
        p_test_inter_node_connectivity.return_value = False

        tester.test(['str-1'], sed, xml)
        self.assertEqual(1, p_test_lms_node_connectivity.call_count)
        self.assertEqual(0, p_test_inter_node_connectivity.call_count)

        p_test_lms_node_connectivity.reset_mock()
        p_test_inter_node_connectivity.reset_mock()
        p_test_lms_node_connectivity.return_value = True
        p_test_inter_node_connectivity.return_value = False
        self.assertRaises(SystemExit, tester.test, ['str-1'], sed, xml)
        self.assertEqual(1, p_test_lms_node_connectivity.call_count)
        self.assertEqual(0, p_test_inter_node_connectivity.call_count)

        p_test_lms_node_connectivity.reset_mock()
        p_test_inter_node_connectivity.reset_mock()
        p_test_lms_node_connectivity.return_value = False
        p_test_inter_node_connectivity.return_value = False
        tester.test(['str-1', 'str-4'], sed, xml)
        self.assertEqual(1, p_test_lms_node_connectivity.call_count)
        self.assertEqual(1, p_test_inter_node_connectivity.call_count)

        p_test_lms_node_connectivity.reset_mock()
        p_test_inter_node_connectivity.reset_mock()
        p_test_lms_node_connectivity.return_value = True
        p_test_inter_node_connectivity.return_value = False
        self.assertRaises(SystemExit, tester.test,
                          ['str-1', 'str-4'], sed, xml)
        self.assertEqual(1, p_test_lms_node_connectivity.call_count)
        self.assertEqual(1, p_test_inter_node_connectivity.call_count)

        p_test_lms_node_connectivity.reset_mock()
        p_test_inter_node_connectivity.reset_mock()
        p_test_lms_node_connectivity.return_value = False
        p_test_inter_node_connectivity.return_value = True
        self.assertRaises(SystemExit, tester.test,
                          ['str-1', 'str-4'], sed, xml)
        self.assertEqual(1, p_test_lms_node_connectivity.call_count)
        self.assertEqual(1, p_test_inter_node_connectivity.call_count)

        p_test_lms_node_connectivity.reset_mock()
        p_test_inter_node_connectivity.reset_mock()
        p_test_lms_node_connectivity.return_value = True
        p_test_inter_node_connectivity.return_value = True
        self.assertRaises(SystemExit, tester.test,
                          ['str-1', 'str-4'], sed, xml)
        self.assertEqual(1, p_test_lms_node_connectivity.call_count)
        self.assertEqual(1, p_test_inter_node_connectivity.call_count)


class TestFunctions(TestCase):
    @patch('sys.stdout')
    @patch('sys.stderr')
    @patch('h_rackinit.hwc.set_logging_level')
    @patch('h_rackinit.hwc.init_enminst_logging')
    def test_get_main_args(self, p_init_enminst_logging,
                           p_set_logging_level, mock_stderr, mock_stdout):
        self.assertRaises(SystemExit, get_main_args, [])
        self.assertRaises(SystemExit, get_main_args, ['f.py'])

        self.assertRaises(ValueError, get_main_args,
                          ['', '-n', 'n1', '-m',
                           join(dirname(__file__), 'hwc_test_model.xml'),
                           '--stages', 'asdfdsdf'])

        self.assertRaises(SystemExit, get_main_args,
                          ['', '-n', 'n1', '--stages', 'pxe',
                           '-m', 'asda'])

    @patch('h_rackinit.hwc.LitpRestClient')
    @patch('h_rackinit.hwc.set_logging_level')
    @patch('h_rackinit.hwc.init_enminst_logging')
    @patch('h_rackinit.hwc.NodeTester')
    @patch('h_rackinit.hwc.NodeSetup')
    @patch('h_rackinit.hwc.Installer')
    @patch('h_rackinit.hwc.Ssh.keygen')
    def test_main(self, _, installer, setup, tester,
                  p_init_enminst_logging, p_set_logging_level, p_litp):
        sed = join(dirname(__file__), 'hwc_test_sed.txt')
        model = join(dirname(__file__), 'hwc_test_model.xml')
        p_litp.return_value.get_cluster_nodes.return_value = {}
        m_pxe_nodes = MagicMock(name='pxe_nodes')
        m_networks = MagicMock(name='networks')
        m_test = MagicMock(name='test')
        installer.return_value.pxe_nodes = m_pxe_nodes
        setup.return_value.networks = m_networks
        tester.return_value.test = m_test

        def assert_states(pxe, net, test):
            _args = ['', '-n', 'str-1', '-s', sed, '-m', model,
                     '--stages']
            c_pxe = 0
            c_net = 0
            c_test = 0
            if pxe:
                _args.append('pxe')
                c_pxe += 1
            if net:
                _args.append('net')
                c_net += 1
            if test:
                _args.append('test')
                c_test += 1

            m_pxe_nodes.reset_mock()
            m_pxe_nodes.return_value = {}
            m_networks.reset_mock()
            m_test.reset_mock()

            main(_args)

            self.assertEqual(c_pxe, m_pxe_nodes.call_count)
            self.assertEqual(c_net, m_networks.call_count)
            self.assertEqual(c_test, m_test.call_count)

        assert_states(True, False, False)
        assert_states(False, True, False)
        assert_states(False, False, True)
        assert_states(True, True, False)
        assert_states(False, True, True)
        assert_states(True, True, True)

    @patch('h_rackinit.hwc.LitpRestClient')
    def test_remove_modeled_nodes(self, p_litp):
        litp_model = {
            'c1': {'c1n1': 'path/path', 'c1n2': 'path'},
            'c2': {'c2n1': 'path/path', 'c2n2': 'path'}
        }
        p_litp.return_value.get_cluster_nodes.return_value = litp_model
        m_logger = MagicMock()

        self.assertEqual(['c3n1'], remove_modeled_nodes(['c3n1'], m_logger))
        self.assertEqual([], remove_modeled_nodes(['c1n1'], m_logger))
        self.assertEqual(['c3n1'], remove_modeled_nodes(['c2n2', 'c3n1'],
                                                        m_logger))

        p_litp.return_value.get_cluster_nodes.return_value = {}
        self.assertEqual(['c2n2', 'c3n1'],
                         remove_modeled_nodes(['c2n2', 'c3n1'], m_logger))
