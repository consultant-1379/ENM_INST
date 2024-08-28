# pylint: disable=C0302
"""
Main goal of this module is to provide the ability to check the network
cabling and VLAN connectivity for rack based machines as part of a pre-install
(or pre-expansion) activity.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2018
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import datetime
import re
import shutil
import sys
import time
import imp
from os import makedirs
from os.path import isdir, isfile, join, basename
from time import sleep
import redfish  # pylint: disable=import-error
# pylint: disable=import-error
from redfish.rest.v1 import BadRequestError, \
    InvalidCredentialsError, RetriesExhaustedError, DecompressResponseError

from argparse import ArgumentParser, RawTextHelpFormatter, Action
from netaddr.ip import IPAddress

from h_util.h_utils import Redfishtool
from h_litp.litp_rest_client import LitpRestClient
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from hwc_cobbler import Kickstarts, CobblerCli
from hwc_utils import BaseObject, Ssh, XmlReader, ping, \
    Scp, ModelItem, RedfishException, PxeTimeoutError, NodeSetupError, SiteDoc


class RedfishClient(BaseObject):
    """
    Redfish client
    """

    CLOUD_REDFISH_PATH = '/opt/ericsson/nms/litp/bin/redfishtool.cloud'

    def _login(self, ipaddr, user, pwd):
        """
        Create a Redfish Client at the ip address given
        and login with the give user, password.
        """

        preamble = '._login: ' + ipaddr + ': '
        if Redfishtool.is_cloud_env():
            redfish_tool = imp.load_source('redfishtool',
                                           self.CLOUD_REDFISH_PATH)
            redfish_client = redfish_tool.RedfishClient(
                base_url=ipaddr, username=user, password=pwd,
                default_prefix='/redfish/v1')
        else:
            redfish_client = redfish.redfish_client(
                base_url='https://' + ipaddr, username=user, password=pwd,
                default_prefix='/redfish/v1')
        try:
            redfish_client.login()
            return redfish_client
        except InvalidCredentialsError as excep:
            msg = "Invalid credentials provided for BMC"
            self._log.error(preamble + msg)
            raise RedfishException(excep)

    def _logout(self, redfish_client):
        """
        Logout redfish client object
        :param redfish_client: redfish client object
        """
        try:
            redfish_client.logout()
        except BadRequestError as excep:
            self._log.error('_logout: ' + str(excep))

    def pxe_boot_node(self, system_name, config):
        """
        PXE boot a node.

        :param system_name: The system name (for logging)
        :type system_name: str
        :param config: Site specific values of the node
        :type config: SiteDoc
        """
        preamble = '.pxe_boot_node: ' + system_name + ' : '

        ipaddr = config.get_sed_value(SiteDoc.SK_ILO_IP)
        user = config.get_sed_value(SiteDoc.SK_ILO_USERNANE)
        password = config.get_sed_value(SiteDoc.SK_ILO_PASSWORD)

        self._log.debug(preamble + 'Start')

        self._log.debug((preamble +
                          "Will create session with Redfish API at %s " +
                          "for user %s") % (ipaddr, user))
        redfish_client = None
        try:
            redfish_client = self._login(ipaddr, user, password)

            self._toggle_power(redfish_client, "ForceOff")
            RedfishClient._sleep(30)
            self._set_pxe(redfish_client)
            RedfishClient._sleep(30)
            self._toggle_power(redfish_client, "On")
            RedfishClient._sleep(90)
        except RetriesExhaustedError:
            error_msg = preamble + "Max number of retries exhausted"
            self._log.error(error_msg)
            raise RedfishException(error_msg)
        except DecompressResponseError:
            error_msg = preamble + "Error while decompressing response"
            self._log.error(error_msg)
            raise RedfishException(error_msg)
        finally:
            self._logout(redfish_client)

        self._log.debug(preamble + 'End')

    def _toggle_power(self, redfish_client, reset_type):
        """
        Toggle power on the node.
        :param redfish_client: redfish client object
        :param reset_type: value to be set for ResetType parameter in the body
        """
        preamble = '._toggle_power: '
        body = {"ResetType": reset_type}
        response = redfish_client.post(
            "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/", body=body)

        if response.status == 200:
            self._log.debug(preamble + "Power {0} Outcome: Success"
                             .format(reset_type))
        else:
            error = Redfishtool.get_error_message(response)
            if response.status == 400 and \
                    'InvalidOperationForSystemState' in error:
                msg = "Power {0} Outcome: system is already in power {0} " \
                      "state".format(reset_type)
                self._log.debug(preamble + msg)
            else:
                msg = "Power {0} Outcome: Failure, status:{1} : '{2}'".format(
                    reset_type, response.status, error)
                self._log.error(preamble + msg)
                raise RedfishException(msg)

    def _set_pxe(self, redfish_client):
        """
        Set boot device to PXE.
        :param redfish_client: redfish client object
        """
        preamble = '._set_pxe: '

        body = {"Boot": {"BootSourceOverrideTarget": "Pxe",
                         "BootSourceOverrideEnabled": "Once"}}
        response = redfish_client.patch("/redfish/v1/Systems/1/", body=body)

        if response.status == 200:
            self._log.debug(preamble +
                                  "Set boot to pxe Outcome: Success")
        else:
            error = Redfishtool.get_error_message(response)
            msg = "Set boot to pxe Outcome: Failure, status:{0} : '{1}'" \
                .format(response.status, error)
            self._log.error(preamble + msg)
            raise RedfishException(msg)

    @staticmethod
    def _sleep(sleep_time):
        """
        Sleep for a time.

        :param sleep_time: Time (in seconds) to sleep
        :type sleep_time: int
        """
        if not sleep_time:
            return None
        counter = 0.0
        interval = 1.0 if sleep_time >= 1 else sleep_time
        while counter < sleep_time:
            counter += interval
            sleep(interval)
        return None


class Redfish(BaseObject):
    """
    Redfish interface.
    """

    def __init__(self, logger):
        super(Redfish, self).__init__(logger)
        #TO DO: Use cloud adapter if it is installed.
        self._redfish = RedfishClient(logger)

    def pxe_boot_node(self, system_name, config):
        """
        PXE boot a node.

        :param system_name: The system name (for logging)
        :type system_name: str
        :param config: Site specific values of the node
        :type config: SiteDoc
        """
        self._redfish.pxe_boot_node(system_name, config)


class Installer(BaseObject):
    """
    Class to handle the cobbler actions needed to PXE boot a node.
    """

    def __init__(self, logger):
        super(Installer, self).__init__(logger)
        self._max_waiting_time_for_node = 1800  # 30 minutes

    def init(self):
        """
        init

        :return:
        """
        if not isdir(self.tmpdir):
            makedirs(self.tmpdir)

    def wait_for_node(self, system_name, ip_address):
        """
        Wait for port 22 to be pingable.

        :param system_name: System name (logging)
        :param ip_address: The IPv4 address to check the port on.

        """
        epoch = int(time.time())
        _wmesg = 'Waiting for node to come up: {0} ({1})'.format(system_name,
                                                                 ip_address)
        self._log.info(_wmesg)
        while True:
            try:
                self.exec_process(
                        ['/usr/bin/nc', '-w', '30', ip_address, '22'])
                break
            except IOError:
                counter = int(time.time()) - epoch
                if counter % 60 == 0:
                    self._log.info(_wmesg)
                if counter >= self._max_waiting_time_for_node:
                    raise PxeTimeoutError(system_name, ip_address,
                                          self._max_waiting_time_for_node)
                sleep(1.0)
        self._log.info('Node {0} ({1}) has come up.'.format(
                system_name, ip_address))

    def pxe_nodes(self,  # pylint: disable=R0913,R0914,R0915
                  node_ids, env_sed, xml, system_profile, force=False):
        """
        PXE boot a set of nodes based on their LITP model ID

        :param node_ids: List of node ids e.g. str-1 or asr-6
        :type node_ids: str[]
        :param env_sed: SED with site specific values.
        :type env_sed: SiteDoc
        :param xml: The ENM deployment description that contains the
         nodes network model.
        :type xml: XmlReader
        :param system_profile: Cobbler profile to use.
        :type system_profile: str
        :param force: Force reinstall of a node if it's pingable.
        :type force: bool
        """
        xml_nodes = xml.get_nodes_by_id(node_ids)
        if not xml_nodes:
            raise ValueError(
                    'No XML definitions found for any of the nodes '
                    '{0}'.format(', '.join(node_ids)))

        pxe_network = xml.get_managment_network()
        pxe_ip_sed_key = SiteDoc.get_network_key(pxe_network)
        self._log.info('PXE booting on the "{0}" network.'.format(
                pxe_network))
        wait_systems = {}
        cobbler = CobblerCli(self._log)
        kickstart = Kickstarts(self._log)
        redfishtool = Redfish(env_sed, self._log)

        failed_systems = {}
        systemid_to_modelid = {}
        for xnode in xml_nodes:
            pxe_device = xml.get_pxe_device(xnode, pxe_network)
            model_id = xnode.get('id')
            sed_id = SiteDoc.modelid_to_sedid(model_id)

            config = env_sed.get_node_config(sed_id)
            pxe_ipaddress = config.get_sed_value(pxe_ip_sed_key)
            if ping(pxe_ipaddress):
                if force:
                    self._log.warning('Node {0}/{1} is pingable and '
                                      '"force" is set.'.format(model_id,
                                                               pxe_ipaddress))
                else:
                    self._log.warning(
                            'Node {0}/{1} is pingable, '
                            'continue with PXE [y/n]?: '.format(
                                    model_id, pxe_ipaddress))
                    action = raw_input()
                    if action.lower() == 'n':
                        self._log.info('Skipping {0}'.format(model_id))
                        continue
                    else:
                        self._log.info('Node {0} will be reinstalled based '
                                       'on user input.'.format(model_id))

            self._log.info('Node {0} ({1}) will PXE on {2}'.format(
                    model_id, sed_id, pxe_device.device_name))

            system_name = config.get_sed_value(SiteDoc.SK_HOSTNAME)
            systemid_to_modelid[system_name] = model_id
            cobbler.deconfigure_system(system_name)
            boot_disk = xml.get_boot_disk(xnode)
            ks_file = kickstart.generate(config, Ssh.ssh_pub(),
                                         pxe_device.device_name,
                                         boot_disk)
            cobbler.configure_system(
                    system_name, config, ks_file,
                    pxe_device.device_name,
                    pxe_ipaddress,
                    system_profile)
            cobbler.sync()

            self._log.info('PXE booting {0}'.format(system_name))
            try:
                redfishtool.pxe_boot_node(system_name, config)
                wait_systems[system_name] = pxe_ipaddress
            except Exception as error:  # pylint: disable=W0703
                self._log.exception(error)
                failed_systems[model_id] = error

        success_systems = {}
        if wait_systems:
            self._log.info('Waiting for systems to install ...')
            for system_name, pxe_address in wait_systems.items():
                try:
                    self.wait_for_node(system_name, pxe_address)
                    cobbler.deregister_system(system_name)
                    cobbler.sync()
                    success_systems[system_name] = pxe_address
                except PxeTimeoutError as error:
                    self._log.exception(error)
                    failed_systems[systemid_to_modelid[system_name]] = error

        return failed_systems


class IfcfgGenerator(BaseObject):
    """
    ifcfg file generator.
    """

    @staticmethod
    def generate_bridge(device_name, address, netmask, broadcast, options):
        """
        Generate the contents of an ifcfg file for a bridge

        :param device_name: The device name
        :type device_name: str
        :param address: The IP address of the device
        :type address: str
        :param netmask: Device netmask
        :type address: str
        :param broadcast: Device broadcast address
        :type broadcast: str
        :param options: Device options
        :type options: str

        :returns: Data to write to the ifcfg file.
        :rtype: str[]
        """
        return '\n'.join([
            'NETMASK=' + netmask,
            'DEVICE=' + device_name,
            'IPADDR=' + address,
            'BROADCAST=' + broadcast,
            'BRIDGING_OPTS="{0}"'.format(options),
            'NOZEROCONF=yes',
            'TYPE=Bridge',
            'USERCTL=no',
            'ONBOOT=yes',
            'STP=off',
            'DELAY=0',
            'BOOTPROTO=static',
            'HOTPLUG=no',
        ])

    @staticmethod
    def generate_bond(device_name, options, bridge=None):
        """
        Generate the contents of an ifcfg file for a bond

        :param device_name: The device name
        :type device_name: str
        :param options: Device options
        :type options: str
        :param bridge: Device name of a bridge connected to the bond.
        :type bridge: str

        :returns: Data to write to the ifcfg file.
        :rtype: str[]
        """
        _conf = [
            'DEVICE=' + device_name,
            'BONDING_OPTS="{0}"'.format(options),
            'NOZEROCONF=yes',
            'TYPE=Bonding',
            'USERCTL=no',
            'ONBOOT=yes',
            'BOOTPROTO=static',
            'HOTPLUG=no'
        ]
        if bridge:
            _conf.append('BRIDGE=' + bridge)
        return '\n'.join(_conf)

    @staticmethod
    def generate_slave_nic(device_name, master):
        """
        Generate the contents of an ifcfg file for slave nic

        :param device_name: The device name
        :type device_name: str
        :param master: The devices master
        :type master: str

        :returns: Data to write to the ifcfg file.
        :rtype: str[]
        """
        return '\n'.join([
            'DEVICE=' + device_name,
            'MASTER=' + master,
            'NOZEROCONF=yes',
            'USERCTL=no',
            'ONBOOT=yes',
            'SLAVE=yes',
            'BOOTPROTO=static',
        ])

    @staticmethod
    def generate_eth(device_name, address=None, netmask=None,
                     broadcast=None, bridge=None):
        """
        Generate the contents of an ifcfg file for an eth device

        :param device_name: The device name
        :type device_name: str
        :param address: The IP address of the device. If None, netmask &
         broadcast are ignored.
        :type address: str|None
        :param netmask: Device netmask
        :type address: str
        :param broadcast: Device broadcast address
        :type broadcast: str
        :param bridge: Device name of a bridge connected to the eth.
        :type bridge: str

        :returns: Data to write to the ifcfg file.
        :rtype: str[]
        """
        _conf = [
            'DEVICE=' + device_name,
            'USERCTL=no',
            'ONBOOT=yes',
            'BOOTPROTO=static',
            'NOZEROCONF=yes'
        ]
        if bridge:
            _conf.append('BRIDGE=' + bridge)
        if address:
            _conf.append('IPADDR=' + address)
            _conf.append('NETMASK=' + netmask)
            _conf.append('BROADCAST=' + broadcast)
        return '\n'.join(_conf)

    @staticmethod
    def generate_vlan(device_name, address=None, netmask=None,
                      broadcast=None, bridge=None):
        """
        Generate the contents of an ifcfg file for a VLAN tagged device.

        :param device_name: The device name
        :type device_name: str
        :param address: The IP address of the device. If None, netmask &
         broadcast are ignored.
        :type address: str
        :param netmask: Device netmask
        :type address: str
        :param broadcast: Device broadcast address
        :type broadcast: str
        :param bridge: Device name of a bridge connected to the tagged device.
        :type bridge: str

        :returns: Data to write to the ifcfg file.
        :rtype: str[]
        """
        _conf = [
            'DEVICE=' + device_name,
            'NOZEROCONF=yes',
            'BOOTPROTO=static',
            'ONBOOT=yes',
            'VLAN=yes',
            'HOTPLUG=no',
            'USERCTL=no'
        ]
        if address:
            _conf.append('IPADDR=' + address)
            _conf.append('NETMASK=' + netmask)
            _conf.append('BROADCAST=' + broadcast)
        if bridge:
            _conf.append('BRIDGE=' + bridge)
        return '\n'.join(_conf)


class NodeSetup(BaseObject):
    """
    OS configuration class.
    """
    _SNAP_PREFIX = 'hwcsnap_'
    _SNAP_TAG = 'hwc'

    def __init__(self, logger):
        super(NodeSetup, self).__init__(logger)

    @staticmethod
    def _get_address_subnet(node_id, address, device_name,
                            network_name, infra_subnets):
        """
        Get the modeled network (subnet) for an IP address

        :param node_id: Node ID (logging)
        :type node_id: str
        :param address: IPv4 address
        :type address: str
        :param device_name: Device the address will be allocated to (logging)
        :type device_name: str
        :param network_name: The network name
        :type network_name: str
        :param infra_subnets: List of all modeled networks
        :type infra_subnets: dict

        :returns: The IPAddress and subet it belongs to.
        :rtype: IPAddress, IPNetwork
        """
        if network_name not in infra_subnets:
            raise NodeSetupError(
                    'No network called "{0}" for node {1} '
                    'is defined in the model!'.format(
                            network_name, node_id))

        _ipaddr = IPAddress(address)
        if _ipaddr not in infra_subnets[network_name]:
            raise NodeSetupError(
                    'Node {0} has device {1} configured for network '
                    '"{2}" but the SED address "{3}" is not in the subnet '
                    'range defined by "{4}"'.format(
                            node_id,
                            device_name,
                            network_name,
                            _ipaddr,
                            infra_subnets[network_name]))
        return _ipaddr, infra_subnets[network_name]

    @staticmethod
    def _get_bonding_options(bond):
        """
        Get a bond BONDING_OPTS string

        :param bond: Bond
        :type bond: ModelItem

        :returns: The bonds BONDING_OPTS string for its ifcfg file
        :rtype: str
        """
        if bond.arp_interval and bond.arp_ip_target:
            monitoring_str = "arp_interval={0} arp_ip_target={1} "
            monitoring_str = monitoring_str.format(bond.arp_interval,
                                                   bond.arp_ip_target)
            if bond.arp_validate and bond.arp_all_targets:
                monitoring_str += "arp_validate={0} arp_all_targets={1} "
                monitoring_str = monitoring_str.format(bond.arp_validate,
                                                       bond.arp_all_targets)
        elif hasattr(bond, 'miimon') and bond.miimon:
            monitoring_str = "miimon={0} ".format(bond.miimon)
        else:
            monitoring_str = ''

        if bond.primary and bond.primary_reselect:
            primary_str = ' primary={0} primary_reselect={1}'.format(
                    bond.primary, bond.primary_reselect)
        else:
            primary_str = ''
        if not bond.mode:
            raise NodeSetupError('The "mode" property is not set!')
        mode_str = "mode={0}".format(bond.mode)

        xmit_hash_policy_str = ''
        if hasattr(bond, 'xmit_hash_policy') and bond.xmit_hash_policy:
            xmit_hash_policy_str = ' {0}={1}'.format('xmit_hash_policy',
                                                     bond.xmit_hash_policy)

        options_str = monitoring_str + mode_str + primary_str
        options_str += xmit_hash_policy_str
        return options_str

    @staticmethod
    def _get_bridging_options(bridge):
        """
        Get a bridges BRIDGING_OPTS string

        :param bridge: Bridge
        :type bridge: ModelItem

        :returns: The bonds BRIDGING_OPTS string for its ifcfg file
        :rtype: str
        """
        bridge.set_defaults({
            'multicast_querier': '0',
            'multicast_router': '1',
            'hash_max': '512',
            'hash_elasticity': '4'
        })

        options_str = ''
        if bridge.multicast_snooping:
            options_str = 'multicast_snooping=%s' % bridge.multicast_snooping

        if bridge.multicast_querier:
            options_str += ' multicast_querier=%s' % bridge.multicast_querier

        if bridge.multicast_router:
            options_str += ' multicast_router=%s' % bridge.multicast_router

        if bridge.hash_max:
            options_str += ' hash_max=%s' % bridge.hash_max

        if bridge.hash_elasticity:
            options_str += ' hash_elasticity=%s' % bridge.hash_elasticity

        return options_str

    def _get_bridge_config(self, node_id, bridge, env_sed, infra_subnets):
        """
        Get the contents of a bridges's ifcfg file

        :param node_id: The node the VLAN is on
        :type node_id: str
        :param bridge: The bridge to configure
        :type bridge: ModelItem
        :param env_sed: Site Env. Description
        :type env_sed: SiteDoc
        :param infra_subnets: List of networks in the deployment
        :type infra_subnets: dict

        :returns: The pyhsical device name (with SED values substituted) and
         the contents of the tagged bridges ifcfg file
        :rtype: str, str
        """
        addr_key = '{0}_{1}'.format(
                SiteDoc.modelid_to_sedid(node_id),
                SiteDoc.get_network_key(bridge.network_name))

        addr, subnet = self._get_address_subnet(
                node_id, env_sed.get_sed_value(addr_key),
                bridge.device_name, bridge.network_name, infra_subnets
        )

        return bridge.device_name, IfcfgGenerator.generate_bridge(
                bridge.device_name,
                str(addr), str(subnet.netmask), str(subnet.broadcast),
                self._get_bridging_options(bridge))

    @staticmethod
    def get_real_device_name(device_name, env_sed):
        """
        Get the physical device name. Substitutes SED values into a template
         name e.g. bond0.%%VLAN_ID_services%% to bond0.123. If there's no
         Site key in the device_name then the device_name is returned
         e.g. br0 to br0

        :param device_name: The XML device name
        :type device_name: str
        :param env_sed: Site Env. Description
        :type env_sed: SiteDoc

        :returns: The device name with SED values substitued.
        :rtype: str
        """
        _match = re.search('.*(%%(.*?)%%).*', device_name)
        if _match:
            return device_name.replace(
                    _match.group(1),
                    env_sed.get_sed_value(_match.group(2)))
        else:
            return device_name

    def _get_vlan_config(self, node_id, vlan, env_sed, infra_subnets):
        """
        Get the contents of a tagged vlan's ifcfg file

        :param node_id: The node the VLAN is on
        :type node_id: str
        :param vlan: The vlan to configure
        :type vlan: ModelItem
        :param env_sed: Site Env. Description
        :type env_sed: SiteDoc
        :param infra_subnets: List of networks in the deployment
        :type infra_subnets: dict

        :returns: The pyhsical device name (with SED values substituted) and
         the contents of the tagged vlans ifcfg file
        :rtype: str, str
        """
        real_device_name = self.get_real_device_name(vlan.device_name,
                                                     env_sed)

        if vlan.ipaddress:
            addr_key = '{0}_{1}'.format(
                    SiteDoc.modelid_to_sedid(node_id),
                    SiteDoc.get_network_key(vlan.network_name))
            addr, subnet = self._get_address_subnet(
                    node_id, env_sed.get_sed_value(addr_key),
                    vlan.device_name, vlan.network_name, infra_subnets
            )
            _cfg = IfcfgGenerator.generate_vlan(
                    real_device_name,
                    str(addr), str(subnet.netmask), str(subnet.broadcast))
        else:
            _cfg = IfcfgGenerator.generate_vlan(real_device_name,
                                                bridge=vlan.bridge)
        return real_device_name, _cfg

    @staticmethod
    def _get_static_route_config(gateway_address):
        """
        Get the contents of a static route file

        :param gateway_address: Default gateway IPv4 address
        :type gateway_address: str

        :returns: Contents of a static route file
        :rtype: str
        """
        return 'ADDRESS0=0.0.0.0 NETMASK0=0.0.0.0 GATEWAY0={0}'.format(
                gateway_address)

    @staticmethod
    def _get_bond_slave_config(slave):
        """
        Get the ifcfg file contents for a bonds slave device

        :param slave: The slave nic
        :type slave: ModelItem

        :returns:
        :rtype: str, str
        """
        return slave.device_name, IfcfgGenerator.generate_slave_nic(
                slave.device_name, slave.master)

    def _get_bond_config(self, bond):
        """
        Get the contents of a bonds ifcfg file

        :param bond: Bond
        :type bond: ModelItem

        :returns: The pyhsical device name (with SED values substituted) and
         the contents of the bonds ifcfg file
        :rtype: str, str
        """
        return bond.device_name, IfcfgGenerator.generate_bond(
                bond.device_name,
                self._get_bonding_options(bond),
                bridge=bond.bridge
        )

    def _get_plumbed_eth_config(self, node_id, eth, env_sed, infra_subnets):
        """
        Get the contents of as plumbed eth ifcfg file

        :param node_id: The node the VLAN is on
        :type node_id: str
        :param eth: The eth to configure
        :type eth: ModelItem
        :param env_sed: Site Env. Description
        :type env_sed: SiteDoc
        :param infra_subnets: List of networks in the deployment
        :type infra_subnets: dict

        :returns: The pyhsical device name (with SED values substituted) and
         the contents of the tagged vlans ifcfg file
        :rtype: str, str
        """
        addr_key = '{0}_{1}'.format(
                SiteDoc.modelid_to_sedid(node_id),
                SiteDoc.get_network_key(eth.network_name))
        addr, subnet = self._get_address_subnet(
                node_id, env_sed.get_sed_value(addr_key),
                eth.device_name, eth.network_name, infra_subnets
        )
        return eth.device_name, IfcfgGenerator.generate_eth(
                eth.device_name, str(addr), str(subnet.netmask),
                str(subnet.broadcast))

    @staticmethod
    def _get_blank_eth_config(eth):
        """
        Get the contents of as plumbed eth ifcfg file

        :param eth: The eth to configure
        :type eth: ModelItem

        :returns: The pyhsical device name (with SED values substituted) and
         the base contents of an eth ifcfg file
        :rtype: str, str
        """
        return eth.device_name, IfcfgGenerator.generate_eth(eth.device_name)

    @staticmethod
    def _get_bridged_eth_config(eth):
        """
        Get the contents of a eth ifcfg file that has a bridge device attached.

        :param eth: eth
        :type eth: ModelItem

        :returns: The pyhsical device name (with SED values substituted) and
         the contents of the eth ifcfg file
        :rtype: str, str
        """
        return eth.device_name, IfcfgGenerator.generate_eth(
                eth.device_name, bridge=eth.bridge)

    def create_snapshot(self, node_id, address):
        """
        Create LVS snapshots on a node

        :param node_id: The modeled node ID
        :type node_id: str
        :param address: IPv4 address to access the node
        :type address: str

        """
        lvs_ls = [
            'lvs', '--unbuffered', '--separator', ',', '--noheadings',
            '-o', 'lv_name,lv_path,origin']
        volumes = {}
        snapshots = {}
        for _line in Ssh.exec_remote(lvs_ls, address).split('\n'):
            _line = _line.strip()
            if not _line:
                continue
            attrs = _line.split(',')
            if not attrs[0].startswith(NodeSetup._SNAP_PREFIX):
                volumes[attrs[0]] = attrs
            if attrs[2]:
                snapshots[attrs[2]] = attrs
        for volume in volumes.keys():
            self._log.info('Ensuring {0} is snapped.'.format(volume))
            if volume in snapshots:
                self._log.info('{0}: Volume {1} already snapped.'.format(
                        node_id, volume))
            else:
                vol_path = volumes[volume][1]
                Ssh.exec_remote(
                        ['lvcreate', '--snapshot',
                         '--addtag', NodeSetup._SNAP_TAG,
                         '--extents', '10%ORIGIN',
                         '--name', '{0}{1}'.format(NodeSetup._SNAP_PREFIX,
                                                   volume), vol_path],
                        address)
                self._log.info('{0}: Snapped volume {1}'.format(node_id,
                                                                volume))
                self._log.info(
                        '{0}: Node can be restored using '
                        '"lvconvert --merge @{1}"'.format(node_id,
                                                          NodeSetup._SNAP_TAG))

    def delete_snapshots(self, node_id, address):
        """
        Delete LVS snapshots of a node

        :param node_id: The modeled node ID
        :type node_id: str
        :param address: IPv4 address to access the node
        :type address: str
        """
        Ssh.exec_remote(['lvremove', '-f', '@{0}'.format(NodeSetup._SNAP_TAG)],
                        address)
        self._log.info('{0}: Deleted any existing snapshots'.format(node_id))

    @staticmethod
    def diff(data_set_one, data_set_2):
        """
        Diff to strings

        :param data_set_one: String 1
        :param data_set_2:  String 2
        :returns: symmetric_difference
        :rtype: set
        """
        return set(data_set_one).symmetric_difference(data_set_2)

    def _get_network_configs(self,  # pylint: disable=R0913,R0914
                             node_id, node_net, generated,
                             env_sed, model, infra_nets, node_networks,
                             device_to_network, vcs_llt_networks,
                             slave_devices):
        """
        Get the ifcfg file name and contents to provide a network.

        :param node_id: Node model ID
        :type node_id: str
        :param node_net: The network to configure
        :type node_net: ModelItem
        :param generated: Dictionary to store generate configs
        :type generated: dict
        :param env_sed: Site Eng. Doc
        :type env_sed: SiteDoc
        :param model: XML containing networking definitions
        :type model: XmlReader
        :param infra_nets: List of all available networks in a deployment
        :type infra_nets: dict
        :param node_networks: List of all networks on the node
        :type node_networks: ModelItem[]
        :param device_to_network: Mapping of what device is plumbed for
         what network
        :type device_to_network: dict
        :param vcs_llt_networks: VCS LLT network names
        :type vcs_llt_networks: set
        :param slave_devices: Lsit of devices that are slaves to other devices
        :type slave_devices: str[]

        """
        if node_net.item_type_id == 'bridge':
            self._log.info('Generating bridge device "{0}"'.format(
                    node_net.device_name))
            devname, cfg = self._get_bridge_config(node_id, node_net,
                                                   env_sed, infra_nets)
            device_to_network[node_net.network_name] = devname
            generated['ifcfg-{0}'.format(devname)] = cfg

            parent = model.get_bridge_parent(node_net, node_networks)
            if parent.item_type_id == 'eth':
                devname, cfg = self._get_bridged_eth_config(parent)
                self._log.info('Generating bridging device "{0}" '
                               'for "{1}"'.format(devname,
                                                  node_net.device_name))
                generated['ifcfg-{0}'.format(devname)] = cfg
                slave_devices.append(devname)
        elif node_net.item_type_id == 'bond':
            self._log.info('Generating "{0}"'.format(node_net.device_name))
            devname, cfg = self._get_bond_config(node_net)
            device_to_network[node_net.network_name] = devname
            generated['ifcfg-{0}'.format(devname)] = cfg

            slaves = model.get_bond_eth_slaves(node_networks, node_net)
            for slave in slaves:
                devname, cfg = self._get_bond_slave_config(slave)
                self._log.info('Generating slave device "{0}" for '
                               '"{1}"'.format(devname,
                                              node_net.device_name))
                generated['ifcfg-{0}'.format(devname)] = cfg
                slave_devices.append(devname)
        elif node_net.item_type_id == 'eth':
            pbo = node_net.pxe_boot_only
            if node_net.bridge:
                # Skip this, the bridge config above will do it
                return
            if pbo and pbo == 'true':
                devname, cfg = self._get_blank_eth_config(node_net)
                generated['ifcfg-{0}'.format(devname)] = cfg
            elif node_net.device_name not in slave_devices:
                if node_net.network_name not in vcs_llt_networks:
                    self._log.info('Generating eth device "{0}"'.format(
                            node_net.device_name))
                    devname, cfg = self._get_plumbed_eth_config(
                            node_id, node_net, env_sed, infra_nets)
                    device_to_network[node_net.network_name] = devname
                    generated['ifcfg-{0}'.format(devname)] = cfg
        elif node_net.item_type_id == 'vlan':
            self._log.info('Generating tagged interface for "{0}"'.format(
                    node_net.device_name))
            devname, cfg = self._get_vlan_config(node_id,
                                                 node_net,
                                                 env_sed,
                                                 infra_nets)
            device_to_network[node_net.network_name] = devname
            generated['ifcfg-{0}'.format(devname)] = cfg

    def networks(self,  # pylint: disable=R0912,R0914,R0915
                 node_ids, env_sed, xml):
        """
        Configure modeled networks on a node.

        :param node_ids: List of node ids to configure
        :type node_ids: str[]
        :param env_sed: Site Env. Description
        :type env_sed: SiteDoc
        :param xml: The ENM deployment description that contains the
         nodes network model.
        :type xml: XmlReader
        """
        if not node_ids:
            return

        infra_nets = xml.get_subnets(env_sed)
        vcs_llt_networks = xml.get_vcs_llt_nets()

        model_nodes = [ModelItem(_n) for _n in xml.get_nodes_by_id(node_ids)]
        if not model_nodes:
            raise ValueError('No nodes found matching "{0}"'.format(
                    node_ids))

        files = {}
        pxe_network = xml.get_managment_network()
        pxe_ip_sed_key = SiteDoc.get_network_key(pxe_network)

        for model_node in model_nodes:
            node_id = model_node.item_id

            # Upload over the PXE address as that's the only one available.
            sed_id = SiteDoc.modelid_to_sedid(node_id)
            config = env_sed.get_node_config(sed_id)
            pxe_ipaddress = config.get_sed_value(pxe_ip_sed_key)
            node_networks = model_node.network_interfaces.children()

            slave_devices = []
            device_to_network = {}
            for node_net in node_networks:
                self._get_network_configs(node_id, node_net,
                                          files, env_sed,
                                          xml, infra_nets, node_networks,
                                          device_to_network,
                                          vcs_llt_networks, slave_devices)

            for static_route in xml.get_static_routes(model_node):
                gateway_address = self.get_real_device_name(
                        static_route.gateway, env_sed)
                for net_name, subnet in infra_nets.items():
                    if IPAddress(gateway_address) in subnet:
                        if net_name in device_to_network:
                            devname = device_to_network[net_name]
                            self._log.info(
                                    'Generating static route '
                                    '"{0}/{1}/{2}"'.format(net_name,
                                                           gateway_address,
                                                           devname))
                            cfg = self._get_static_route_config(
                                    gateway_address)
                            files['route-{0}'.format(devname)] = cfg

            for ifcfg in sorted(files.keys()):
                self._log.debug('=' * 10)
                self._log.debug(ifcfg)
                self._log.debug('v' * 10)
                self._log.debug(files[ifcfg])

            local_dir = join(self.tmpdir, node_id)
            if isdir(local_dir):
                shutil.rmtree(local_dir)
            makedirs(local_dir)

            for net_conf, data in files.items():
                self._log.debug(
                        'Generated {0} for {1}'.format(net_conf, node_id))
                local = join(local_dir, net_conf)
                with open(local, 'w') as _writer:
                    _writer.write('#Generated on {0}\n'.format(
                            datetime.datetime.now()))
                    _writer.write(data)

            self.create_snapshot(node_id, pxe_ipaddress)

            scp = Scp(pxe_ipaddress, 'root', Ssh.ssh_priv(), self._log)
            changes = False
            for net_conf, data in files.items():
                local = join(local_dir, net_conf)
                remote = join('/etc/sysconfig/network-scripts/', net_conf)
                try:
                    remote_data = Ssh.cat(remote, pxe_ipaddress).split('\n')
                    remote_data = remote_data[1:]
                except IOError:
                    remote_data = []
                _diff = self.diff(remote_data, data.split('\n'))
                if _diff:
                    changes = True
                    scp.put(local, remote)
                    self._log.info('Uploaded {0}:{1}'.format(node_id, remote))
                else:
                    self._log.info(
                            'No changes detected for {0} on {1}'.format(
                                    net_conf, node_id))

            if changes:
                self._log.info('Restarting networking on {0}'.format(node_id))
                Ssh.restart('network', pxe_ipaddress)
                self._log.info('Done.')
            else:
                self._log.info('No network config changes detected.')


class NodeTester(BaseObject):
    """
    Test network connectivity between nodes.

    """

    def __init__(self, logger):
        super(NodeTester, self).__init__(logger)

    @staticmethod
    def get_node_networks(node):
        """
        Get the networks attached to a node

        :param node: A node.
        :type node: ModelItem

        :returns: Set of networks attached to a node.
        :rtype: dict
        """
        _nets = {}
        for _net in node.network_interfaces.children():
            if _net.ipaddress:
                _nets[_net.network_name] = {
                    'device_name': _net.device_name,
                    'ipaddress': _net.ipaddress
                }
        return _nets

    def test_lms_node_connectivity(self, test_nodes, lms_networks, env_sed):
        """
        Test the network connectivity from the LMS to a set of nodes.

        :param test_nodes: List of node to check
        :type test_nodes: str[]
        :param lms_networks: Networks attached to the LMS
        :type lms_networks: dict
        :param env_sed: Site Env. Description
        :type env_sed: SiteDoc

        :returns: True if a node can't be pinged over a network,
         False otherwise
        :rtype bool
        """
        errors = False
        for test_node in test_nodes:
            self._log.info('Checking network connectivity from the LMS '
                           'to {0}'.format(test_node.item_id))
            for network in test_node.network_interfaces.children():
                if network.ipaddress:
                    if network.network_name not in lms_networks:
                        self._log.info(
                                'LMS not connected to the "{0}" network'
                                '.'.format(network.network_name))
                        continue
                    dev = lms_networks[network.network_name]['device_name']

                    address = env_sed.get_sed_value(network.ipaddress)
                    _cmd = ['ping', '-c', '1', '-I', dev, address]
                    devname = NodeSetup.get_real_device_name(
                            network.device_name, env_sed)
                    self._log.debug('Pinging {0} {1} address {2}'.format(
                            test_node.item_id, network.network_name,
                            address))
                    addrstr = '{0}/{1}/{2}'.format(
                            network.network_name, devname, address)
                    try:
                        self.exec_process(_cmd)
                        self._log.info('Connectivity between the LMS and {0} '
                                       'on the "{1}" networks looks to '
                                       'be OK.'.format(test_node.item_id,
                                                       addrstr))
                    except IOError:
                        errors = True
                        self._log.error('Can\'t ping {0} {1} from '
                                        'the LMS!'.format(test_node.item_id,
                                                          addrstr))
        return errors

    def ping_network(self,  # pylint: disable=R0913
                     source_node, source_node_internal,
                     source_device, target_node, target_address, network_name):
        """
        Ping a node via a certain device i.e. log into source_node and ping
         target_address via source_device i.e. execute "ping -I br0 1.1.1.1"
         on a remote node.

        :param source_node: ID of the node to ping from
        :type source_node: str
        :param source_node_internal: IPv4 address of hte node to ping from
        :type source_node_internal: str
        :param source_device: The device name attached to the network
        :type source_device: str
        :param target_node: ID of the node to ping (target)
        :type target_node: str
        :param target_address: IPv4 address to ping
        :type target_address: str
        :param network_name: Modeled name of the network being checked.
        :type network_name: str

        :returns: True of the ping succeeeded, False otherwise
        :type: bool
        """
        _cmd = ['ping', '-c', '1', '-I', source_device, target_address]
        try:
            Ssh.exec_remote(_cmd, source_node_internal)
            self._log.info(
                    'Connectivity from {0} ({1}) to {2} ({3}) '
                    'on network "{4}" looks OK.'.format(
                            source_node, source_device, target_node,
                            target_address, network_name))
            return True
        except IOError as error:
            self._log.error('Can\'t ping {0} ({1}/{2}) from {3} ({4})'.format(
                    target_node, target_address, network_name, source_node,
                    source_device))
            for _line in error.args[1].split('\n'):
                _line = _line.strip()
                if _line:
                    self._log.error(_line)
            return False

    def test_inter_node_connectivity(self, test_nodes, env_sed, pxe_network):
        """
        Test the network connectivity from one node to other node(s).
         This logs in to each node and tried to ping all the others over the
         networks configured on the node

        :param test_nodes: List of node to check the connectivity between
        :type test_nodes: str[]
        :param env_sed: Site Env. Description
        :type env_sed: SiteDoc
        :param pxe_network: LITP management network (usually internal)
        :type pxe_network: str

        :returns: True if a node can't be pinged over a network,
         False otherwise
        :rtype bool
        """
        self._log.info('Checking connectivity between nodes.')
        ping_errors = False
        for node in test_nodes:
            networks = self.get_node_networks(node)
            # pxe network is the only one guaranteed to be configured.
            source_node_internal = env_sed.get_sed_value(
                    networks[pxe_network]['ipaddress'])
            for other in test_nodes:
                if other.item_id == node.item_id:
                    continue
                for other_net, info in self.get_node_networks(other).items():
                    if other_net in networks:
                        source_dev = NodeSetup.get_real_device_name(
                                networks[other_net]['device_name'], env_sed)
                        target_address = env_sed.get_sed_value(
                                info['ipaddress'])
                        if not self.ping_network(node.item_id,
                                                 source_node_internal,
                                                 source_dev,
                                                 other.item_id,
                                                 target_address,
                                                 other_net):
                            ping_errors = True
                    else:
                        self._log.warning('Node {0} not connected to {1}'
                                          ''.format(other.item_id, other_net))
        return ping_errors

    def test(self, test_systems, env_sed, xml):
        """
        Run network connectivity tests
         Ping the nodes from the LMS
         Ping each node from all the others.

        :param test_systems: List of node to check the connectivity between
        :type test_systems: str[]
        :param env_sed: Site Env. Description
        :type env_sed: SiteDoc
        :param xml: The ENM deployment description that contains the
         nodes network model.
        :type xml: XmlReader

        :raise SystemExit: If any network check fails.
        """

        if not test_systems:
            return

        pxe_network = xml.get_managment_network()
        model_nodes = [ModelItem(_n) for _n in
                       xml.get_nodes_by_id(test_systems)]
        if not model_nodes:
            raise ValueError('No nodes found matching "{0}"'.format(
                    test_systems))

        lms_networks = self.get_node_networks(xml.lms)
        errors = self.test_lms_node_connectivity(model_nodes,
                                                 lms_networks, env_sed)
        if len(model_nodes) > 1:
            errors |= self.test_inter_node_connectivity(model_nodes,
                                                        env_sed,
                                                        pxe_network)
        if errors:
            raise SystemExit(4)


def get_main_args(sys_argv):
    """
    Parse sys.argv

    :param sys_argv: Input args
    :type sys_argv: str[]
    :returns: Namespace
    :rtype: Namespace
    """
    argparser = ArgumentParser(
            formatter_class=RawTextHelpFormatter
    )

    def is_valid_file(parser, filepath):
        """
        Test if a file path exists

        :param parser: Arguement parser
        :type parser: ArgumentParser
        :param filepath: File path
        :type filepath: str

        :returns:
        :rtype: str
        """
        if not isfile(filepath):
            parser.error('File {0} not found!'.format(filepath))
        else:
            return filepath

    valid_stages = ['pxe', 'net', 'test']

    class ValidateStage(Action):  # pylint: disable=R0903
        """
        Stage validator
        """

        def __call__(self, parser, namespace, values, option_string=None):
            for in_val in values:
                if in_val not in valid_stages:
                    raise ValueError('Invalid stage "{0}"'.format(in_val))
            setattr(namespace, self.dest, values)

    argparser.add_argument('-n', '--nodes', dest='deploy_systems',
                           help='The system(s) to check, seperated by comma'
                                ' e.g. str_node1', required=True)
    argparser.add_argument('-s', '--sed', dest='sed',
                           help='ENM SED', required=True,
                           type=lambda x: is_valid_file(argparser, x))
    argparser.add_argument('-m', '--model', dest='model',
                           help='ENM Deployment Description', required=True,
                           type=lambda x: is_valid_file(argparser, x))
    argparser.add_argument('-cp', '--cobbler_profile',
                           dest='cobbler_profile',
                           help='Value TEMP will generate a new temporary '
                                'profile; value of LITP will reuse the LITP '
                                'generated profile (should exist first).')
    argparser.add_argument('-v', action='store_true', dest='verbose',
                           help='Debug log', default=False)

    argparser.add_argument('--stages',
                           help='Stages to execute, list of '
                                'the following: {0}'.format(
                                   '|'.join(valid_stages)),
                           nargs='+', dest='stages', action=ValidateStage)

    argparser.add_argument('--force', dest='force', action='store_true',
                           help='Force PXE of existing (pingable) nodes.')
    argparser.add_argument('-r', dest='regen', action='store_true')
    return argparser.parse_args(sys_argv[1:])


def remove_modeled_nodes(cli_system_list, logger):
    """
    Remove any node IDs from the input cli list that match and litp:node IDs
    in the current LITP model.

    :param cli_system_list: List of node IDs to check
    :type cli_system_list: str[]
    :param logger: Logger instance
    :type logger: Logger

    :returns: A list of node IDs that are not in the current LITP model.
    :rtype: str[]
    """
    litp = LitpRestClient()
    for cluster, nodes in litp.get_cluster_nodes().items():
        for litp_id in nodes.keys():
            if litp_id in cli_system_list:
                logger.warning('Skipping "{0}" as a node with that ID exists '
                               'in the cluster "{1}" in the current LITP '
                               'model.'.format(litp_id, cluster))
                cli_system_list.remove(litp_id)
    return cli_system_list


def remove_blades(xml, system_list, logger):
    """
    Remove any blades from the system list. A blade is defined as a node that
     has a LUN attached to it in the /infrastructure/systems/<system>/disks
     definition.

    :param xml: XML to check
    :type xml: XmlReader
    :param system_list: List of node IDs to check
    :type system_list: str[]
    :param logger: Logger instance
    :type logger: Logger

    :returns: System list that doesn't include blade entries.
    :rtype: str[]
    """
    for node in xml.get_nodes_by_id(system_list):
        item = ModelItem(node)
        source_path = item.system.element().get('source_path')
        infra_sys = xml.xpath_items(xml.infrastructure, '*',
                                    {'id': basename(source_path)})[0]
        if xml.xpath_items(infra_sys.element(), 'lun-disk'):
            logger.warning(
                    'Skipping "{0}" as there are LUNs attached to it.'.format(
                            item.item_id))
            system_list.remove(item.item_id)
    return system_list


def get_nodes_to_test(xml, cli_list, logger):
    """
    Filter out nodes exist in the model or are of type blade.

    :param xml: The ENM deployment description that contains the
     nodes network model.
    :type xml: XmlReader
    :param cli_list: Input system list form the cli
    :type cli_list: str[]
    :param logger: Logger instance
    :type logger: Logger

    :returns: List of node IDs that doesn't include blades or modeled (Live)
     nodes.
    :rtype: str[]
    """
    xml_nodes = xml.get_nodes_by_id(cli_list)
    if not xml_nodes:
        raise ValueError(
                'No XML definitions found for any of the nodes '
                '{0}'.format(', '.join(cli_list)))
    systems = [n.get('id') for n in xml_nodes]
    systems = remove_modeled_nodes(systems, logger)
    systems = remove_blades(xml, systems, logger)
    return systems


def main(sys_args):  # pylint: disable=R0912,R0914
    """
    Main function

    :param sys_args: Input args
    :type sys_args: str[]
    """
    cli_args = get_main_args(sys_args)
    logger = init_enminst_logging(logger_name='rackinit')
    set_logging_level(logger, 'DEBUG' if cli_args.verbose else 'INFO')
    cli_sed = SiteDoc(cli_args.sed)

    def do_stage(stage_name):
        """
        Check if a stage should be executed based on the value of the
         --stage option.

        :param stage_name: The stage to check
        :type stage_name: str

        :returns: True if the stage should be executed, False otherwise
        :rtype: bool
        """
        return not cli_args.stages or stage_name in cli_args.stages

    xml = XmlReader()
    xml.load(cli_args.model)
    systems = get_nodes_to_test(xml, cli_args.deploy_systems.split(','),
                                logger)
    if not systems:
        return
    logger.info('System list narrowed to "{0}"'.format(', '.join(systems)))

    rk_errors = False
    required_keys = ['hostname', 'IP_internal', 'ilo_IP', 'iloUsername',
                     'iloPassword']
    for nid in systems:
        sid = SiteDoc.modelid_to_sedid(nid)
        for required in required_keys:
            rkey = '{0}_{1}'.format(sid, required)
            try:
                cli_sed.get_value(rkey, error_if_not_set=True)
            except KeyError:
                rk_errors = True
                logger.error('The SED entry for "{0}" is either not '
                             'set or not present!'.format(rkey))
    if rk_errors:
        raise SystemExit(4)

    pxe_failures = False
    if do_stage('pxe'):
        if cli_args.regen or not Ssh.exists():
            Ssh.keygen()
        pxe = Installer(logger)
        pxe.init()
        failed = pxe.pxe_nodes(systems, cli_sed, xml,
                               cli_args.cobbler_profile,
                               cli_args.force)
        if failed:
            pxe_failures = True
            for fsys, ferror in failed.items():
                logger.warning('Removing {0} from subsiquent steps as PXE '
                               'failed!'.format(fsys))
                logger.error('Reason: {0}'.format(str(ferror)))
                systems.remove(fsys)
    if do_stage('net'):
        setup = NodeSetup(logger)
        setup.networks(systems, cli_sed, xml)

    if do_stage('test'):
        tester = NodeTester(logger)
        tester.test(systems, cli_sed, xml)

    if pxe_failures:
        raise SystemExit(4)


if __name__ == '__main__':
    main(sys.argv)
