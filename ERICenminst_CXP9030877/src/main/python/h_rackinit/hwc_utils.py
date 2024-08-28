"""
Utility functions
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
import re
from ConfigParser import ConfigParser
from os import makedirs, remove, chmod
from os.path import exists, isdir, join, dirname, abspath, basename
from tempfile import gettempdir

from netaddr.ip import IPNetwork

from h_util.h_utils import exec_process, Sed
from h_xml.xml_utils import is_ns_tag, get_xml_element_properties, _LITPNS, \
    xpath, load_xml


class RedfishException(Exception):
    """
    Redfish Errors
    """
    pass


class PxeTimeoutError(Exception):
    """ PXE Boot timeout errors """

    def __init__(self, node, address, timout):  # pylint: disable=W0231
        self._node = node
        self._address = address
        self._timout = timout

    @property
    def node(self):
        """ Node that failed to PXE """
        return self._node

    @property
    def address(self):
        """ The address assigned to the nodes PXE device """
        return self._address

    @property
    def timeout(self):
        """ Timeout """
        return self._timout

    def __str__(self):
        return 'Node {0}/{1} has not come up within {2} seconds'.format(
                self._node, self._address, self._timout)


class NodeSetupError(Exception):
    """ OS Configuration errors """
    pass


class KickstartException(Exception):
    """ Kickstart generation errors """
    pass


class CobblerCliException(Exception):
    """ Cobbler cli errors """
    pass


def ping(address):
    """
    Ping an address

    :param address: IPV4 address to ping
    :type address: str

    :returns: True if the address is pingable, False otherwise
    :rtype bool
    """
    try:
        exec_process(['ping', '-c', '1', address])
        return True
    except IOError:
        return False


class BaseObject(object):
    """
    Common base methods
    """

    def __init__(self, logger):
        super(BaseObject, self).__init__()
        self.tmpdir = BaseObject.get_temp_dir()
        self.confdir = join(dirname(dirname(abspath(__file__))), 'conf')
        self._log = logger

    @staticmethod
    def get_temp_dir():
        """
        Get path to a tempory directory

        :returns: Temp dir path
        :rtype: str
        """
        return join(gettempdir(), '.hwchecker')

    @staticmethod
    def exec_process(command):
        """
        Wrapper around the main exec_process function to enable mocking in
        tests.
        :param command: Command to run
        :type command: str[]

        :returns: stdout of the command
        :rtype: str
        """
        return exec_process(command)

    def _readfile(self, file_path):
        """
        Read a file, checking it exists first.

        :param file_path: PAth of the file to read
        :type file_path: str

        :returns: Contents of the file
        :rtype: str[]
        """
        self._log.debug('Reading {0}'.format(file_path))
        if not exists(file_path):
            raise IOError('File {0} not found'.format(file_path))
        with open(file_path, 'r') as _reader:
            return _reader.readlines()

    def _writefile(self, file_path, contents):
        """
        Write stuff to a file (creating it and any directories needed)

        :param file_path: Path of the file to write
        :type file_path: str
        :param contents: What to write to the file
        :type contents: bytes | bytearray

        """
        self._log.debug('Writing {0}'.format(file_path))
        _parentdir = dirname(file_path)
        if not isdir(_parentdir):
            makedirs(_parentdir)
        with open(file_path, 'w') as _writer:
            _writer.write(contents)


class Ssh(BaseObject):
    """
    Ssh actions
    """

    @staticmethod
    def _pub():
        """
        Path of the public file

        :returns: Path of the public file
        :rtype: str
        """
        return Ssh._priv() + '.pub'

    @staticmethod
    def _priv():
        """
        Path of the private file

        :returns: Path of the private file
        :rtype: str
        """
        return join(BaseObject.get_temp_dir(), '.tmpkey')

    @staticmethod
    def exists():
        """
        Test if the private file exists.

        :returns: True if the private file exists, False otherwise
        :rtype: bool
        """
        return exists(Ssh._priv())

    @staticmethod
    def ssh_pub():
        """
        Get the path of the public file. An error is raised of it doesn't
         exist

        :returns: Path of the public file
        :rtype: str
        """
        if not exists(Ssh._pub()):
            raise IOError('File not found!')
        return Ssh._pub()

    @staticmethod
    def ssh_priv():
        """
        Get the path of the private file. An error is raised of it doesn't
         exist

        :returns: Path of the private file
        :rtype: str
        """
        if not exists(Ssh._priv()):
            raise IOError('File not found!')
        return Ssh._priv()

    @staticmethod
    def keygen():
        """
        Generate a public/private key pair

        """
        if exists(Ssh._priv()):
            remove(Ssh._priv())
            remove(Ssh._pub())
        if not isdir(dirname(Ssh._priv())):
            makedirs(dirname(Ssh._priv()))
        BaseObject.exec_process(
                ['/usr/bin/ssh-keygen', '-N', "", '-f', Ssh._priv()])
        chmod(Ssh._priv(), 0600)
        chmod(Ssh._pub(), 0600)

    @staticmethod
    def exec_remote(command, host):
        """
        Execute a command on a remote host

        :param command: The command to execute
        :type command: str[]
        :param host: The host to execute the command on
        :type host: str

        :returns: Output of the command
        :rtype: str
        """
        ssh_cmd = ['/usr/bin/ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                   '-i', Ssh.ssh_priv(), 'root@{0}'.format(host)]
        ssh_cmd.extend(command)
        return BaseObject.exec_process(ssh_cmd)

    @staticmethod
    def restart(service, host):
        """
        Restart a service on a remote host

        :param service: The service to restart
        :type service: str
        :param host: The host to execute the command on
        :type host: str

        """
        Ssh.exec_remote(['/etc/init.d/{0}'.format(service), 'restart'],
                        host)

    @staticmethod
    def cat(file_path, host):
        """
        cat a remote file

        :param file_path: Remote file path
        :type file_path: str
        :param host: Remote host
        :type host: str

        :returns: Contents of remote file
        :rtype: str
        """
        return Ssh.exec_remote(['cat', file_path], host)


class Scp(BaseObject):
    """
    Scp actions
    """

    def __init__(self, host, user, key, logger):
        """
        Init

        :param host: Address of remote host
        :param user: User to log in as
        :param key: Private key to log in with
        """
        super(Scp, self).__init__(logger)
        self._host = host
        self._user = user
        self._privkey = key

    def put(self, local, remote):
        """
        Copy a file from the local machine to a remote host

        :param local: Path of the local file
        :type local: str
        :param remote: Path to put the file on the remote host
        :type remote: str
        """
        self._log.debug('Uploading {0} to {1}'.format(remote, self._host))
        self.exec_process([
            '/usr/bin/scp', '-i', self._privkey,
            '-o', 'StrictHostKeyChecking=no',
            local,
            '{0}@{1}:{2}'.format(self._user, self._host, remote)
        ])
        self._log.debug('Uploaded {0}'.format(basename(remote)))


class ModelItem(object):
    """
    Wrapper around an XML element to mimic the LITP ModelItem class.
    """

    def __init__(self, xml_node):
        """
        :param xml_node: XML node to wrap
        :type xml_node: Element
        """
        super(ModelItem, self).__init__()
        self._node = xml_node
        self._props = get_xml_element_properties(self._node)
        self._children = self._get_child_elements()

    def _get_child_elements(self):
        """
        Get any child element od the XML node

        :returns: List of child elements
        :rtype: dict
        """
        _children = {}
        for _child in self._node:
            if is_ns_tag(_child.tag):
                _node = ModelItem(_child)
                _children[_node.item_id] = _node
        return _children

    def element(self):
        """
        Get the XML element this instance is wrapping

        :returns: Wrapped XML Element
        :rtype: Element
        """
        return self._node

    def children(self):
        """
        Get items children, if any.

        :returns: Items children
        :rtype: ModelItem[]
        """
        return self._children.values()

    def set_defaults(self, defaults):
        """
        Set default values on the item

        :param defaults: Default properties to set
        :type defaults: dict
        """
        for _key, _value in defaults.items():
            if _key not in self._props:
                self._props[_key] = _value

    @property
    def item_type_id(self):
        """ Items Model type  """
        return self._node.tag.replace(_LITPNS, '')

    @property
    def item_id(self):
        """ Items ID """
        return self._node.get('id')

    def __getattr__(self, name):
        if name in self._props:
            return self._props[name]
        elif name in self._children:
            return self._children[name]
        else:
            return None

    def __str__(self):
        return '{0}:{1}'.format(self.item_type_id, self.item_id)


class XmlReader(object):
    """
    XML DOM reader
    """

    def __init__(self):
        self._doc = None

    def load(self, xml_file):
        """
        Load a file.

        :param xml_file: Path of an XML file to load
        :type xml_file: str
        """
        self._doc = load_xml(xml_file)

    @staticmethod
    def xpath_items(xml_node, element_type, attributes=None,
                    namespace=True):
        """
        Query the loaded XML with for element types and return the results
         as ModelItem instances

        :param xml_node: The XML nodes to start the query from
        :type xml_node: Element
        :param element_type: The XML Element type to search for
        :type element_type: str
        :param attributes: Filter of element attributes
        :type attributes: dict
        :param namespace: Should namespaces be used to filter element types
        :type namespace: bool

        :returns: Results of the query. An empty list means to results found
        :rtype: ModelItem[]
        """
        _items = []
        for _xn in xpath(xml_node, element_type, attributes=attributes,
                         namespace=namespace):
            _items.append(ModelItem(_xn))
        return _items

    def get_nodes_by_id(self, node_ids):
        """
        Search for litp:node elements with matching ids

        :param node_ids: List of node ids to search for
        :type node_ids: str[]

        :returns: List of "litp:node" elements that match the input ids
        :rtype: Element[]
        """
        _nodes = []
        all_nodes = xpath(self._doc, 'node')
        for _regex in node_ids:
            for _node in all_nodes:
                if re.search(_regex, _node.get('id')):
                    _nodes.append(_node)
        return _nodes

    @staticmethod
    def get_bond_eth_slaves(node_networks, bond):
        """
        Get the slave devices that have the bond as their master

        :param node_networks: All network devices modeled on the node
        :type node_networks: ModelItem[]
        :param bond: The master bond
        :type bond: ModelItem

        :returns:
        :rtype: ModelItem[]
        """
        if bond.item_type_id != 'bond':
            raise ValueError("The interface %s must be a bond type "
                             "to get its slaves." % bond)
        ifaces = [_net for _net in node_networks if _net.item_type_id == 'eth']
        name = bond.device_name
        slaves = [e for e in ifaces if hasattr(e, 'master') and
                  e.master == name]
        slaves.sort(lambda a, b: cmp(a.device_name, b.device_name))
        return slaves

    def get_bridge_root_nic(self, node_networks, bridge):
        """
        The the root eth device for a bridge. Used when figuring out the
         device that will be used for PXE boots. e.g.
         for "eth4:eth7 -> bond9 -> br3" eth4 is the root nic

        :param node_networks: All interfaces modeled on the node the bridge
         is on
        :type node_networks: ModelItem[]
        :param bridge: The bridge
        :type bridge: ModelItem

        :returns: The first eth device that is in the device tree making up a
         bridge interface
        :rtype: ModelItem
        """
        br_ifaces = [nic for nic in node_networks if
                     nic.item_type_id in ['eth', 'vlan', 'bond'] and hasattr(
                             nic,
                             'bridge') and nic.bridge == bridge.device_name]
        if not br_ifaces:
            return None
        br_iface = br_ifaces[0]
        if br_iface.item_type_id == 'eth':
            return br_iface
        elif br_iface.item_type_id == 'bond':
            return self.get_bond_eth_slaves(node_networks, br_iface)[0]
        return None

    def get_pxe_device(self, litp_node, network_name):
        """
        Get the network interface that will be used to PXE boot the node.

        :param litp_node: The node the figure out the PXE boot device for
        :type litp_node: Element
        :param network_name: The LITP management network name
        :type network_name: str

        :returns: The device name that will be use to PXE the node
        :rtype: ModelItem
        """
        net_node = None
        for netname in xpath(litp_node, 'network_name', namespace=False):
            if netname.text.strip() == network_name:
                net_node = netname.getparent()
                break
        if net_node is None:
            raise ValueError(
                    'No network called "{0}" defined under node {1}'.format(
                            network_name, litp_node.get('id')))
        node_networks = [ModelItem(_n) for _n in net_node.getparent()]
        for _net in node_networks:
            if _net.pxe_boot_only and _net.pxe_boot_only == 'true':
                return _net

        interface = ModelItem(net_node)
        if interface.item_type_id == 'bridge':
            return self.get_bridge_root_nic(node_networks, interface)
        elif interface.item_type_id == 'bond':
            raise Exception('Not Implemented.')
        else:
            return interface

    @property
    def infrastructure(self):
        """
        Get the /infrastructure element in the loaded XML

        :returns: /infrastructure node
        :rtype: Element
        """
        return xpath(self._doc, 'infrastructure')[0]

    @property
    def lms(self):
        """
        Get the /ms element in the loaded XML

        :returns: /ms node
        :rtype: Element
        """
        return self.xpath_items(self._doc, 'ms')[0]

    def get_managment_network(self):
        """
        Get the LITP management network name (the network that has
         litp_management set to True)

        :returns: The LITP mangament network or None if one isn't found
        :rtype: str|None
        """
        for _net in xpath(self.infrastructure, 'network'):
            props = get_xml_element_properties(_net)
            if props['litp_management'] == 'true':
                return props['name']
        return None

    def get_boot_disk(self, litp_node):
        """
        Get a nodes boot disk name

        :param litp_node: The node
        :type litp_node: Element

        :returns: The nodes boot disk name
        :rtype: str
        """
        nid = litp_node.get('id')
        system_path = xpath(litp_node, '*', attributes={'id': 'system'})[0]
        source_name = basename(system_path.get('source_path'))
        system = xpath(self.infrastructure, '*',
                       attributes={'id': source_name})
        if not system:
            raise KeyError(
                    'Could not find a system definition for {0}'.format(nid))
        system = system[0]
        _disk = None
        for _bootable in xpath(system, 'bootable', namespace=False):
            if _bootable.text.strip() == 'true':
                _disk = _bootable.getparent()
                break
        if _disk is not None:
            return get_xml_element_properties(_disk).get('name')
        else:
            raise ValueError('Could not find a bootable disk for {0}'.format(
                    nid))

    def get_subnets(self, env_sed):
        """
        Get the subnets (as IPNetwork instance) that are defined in
        Site Eng. Doc.

        :param env_sed: SED
        :type env_sed: SiteDoc

        :returns: A collection of network names and their respective subnets
        :rtype: dict
        """
        networks = {}
        for network in self.xpath_items(self.infrastructure, 'network'):
            if network.subnet:
                subnet_sedkey = '{0}_subnet'.format(network.name)
                if network.name == 'services':
                    subnet_sedkey = 'ENM' + subnet_sedkey
                networks[network.name] = IPNetwork(env_sed[subnet_sedkey],
                                                   implicit_prefix=False)
        return networks

    @staticmethod
    def get_bridge_parent(bridge, node_networks):
        """
        Get the device a bridge is connected to

        :param bridge: The bridge to get the parent device for
        :type bridge: ModelItem
        :param node_networks: List of all network interfaces on the node the
         bridge is on
        :type node_networks: ModelItem[]

        :returns: The bridges parent device or None if not configured
        :rtype: ModelItem|None
        """
        for _net in node_networks:
            if hasattr(_net, 'bridge') and _net.bridge == bridge.device_name:
                return _net
        return None

    def get_vcs_llt_nets(self):
        """
        Get the VCS LLT network names

        :returns: Names of the VCS LLT networks
        :rtype: set
        """
        llt_nets = set()
        for _cluster in self.xpath_items(self._doc, 'vcs-cluster'):
            llt_nets |= set(_cluster.llt_nets.split(','))
        return llt_nets

    def get_static_routes(self, node_net):
        """
        Get static routes that should be configured on a node.

        :param node_net: The node
        :type node_net: ModelItem

        :returns: List of static routes to configure
        :rtype: ModelItem[]
        """
        _routes = self.xpath_items(self.infrastructure,
                                   'networking-routes-collection',
                                   attributes={'id': 'routes'})[0]
        infra_routes = {}
        for _route in _routes.children():
            infra_routes[_route.item_id] = _route

        if isinstance(node_net, ModelItem):
            _element = node_net.element()
            _id = node_net.item_id
        else:
            _element = node_net
            _id = node_net.get('id')
        _routes = self.xpath_items(_element, 'route')

        for h_route in xpath(_element, 'route-inherit'):
            inherited = basename(h_route.get('source_path'))
            if inherited not in infra_routes:
                raise ValueError('No source route called "{0}" '
                                 'found for node {1}!'.format(inherited,
                                                              _id))
            _routes.append(infra_routes[inherited])
        return _routes


class Config(ConfigParser):
    """
    Internal config handler
    """
    __THIS = None

    @staticmethod
    def get_config():
        """
        Get rackinit config

        :returns: Internal config settings
        :rtype: Config
        """
        if not Config.__THIS:
            Config.__THIS = ConfigParser()
            Config.__THIS.read(join(dirname(__file__), 'checker.ini'))
        return Config.__THIS


class SiteDoc(Sed):  # pylint: disable=R0904
    """
    Site Engineering Doc interface
    """

    def get_sed_value(self, sed_key):
        """
        Get the value for a SED key, handling both the %%<key_name>%% and
         <key_name> formats
        :param sed_key: The key to get
        :type sed_key: str

        :returns: The keys value
        :rtype: str
        """
        _match = re.search('^%%(.*?)%%$', sed_key)
        if _match:
            sed_key = _match.group(1)
        return self.get_value(sed_key, error_if_not_set=True)

    def subset(self, key_filter):
        """
        Get a subset of key/values from the SED based on a key filter

        :param key_filter: Key filter regex
        :type key_filter: str

        :returns: Subnet of the SiteDoc
        :rtype: SiteDoc
        """
        _sed = SiteDoc(None)
        _sed._sedfile = '{0} (subset=[{1}])'.format(  # pylint: disable=W0212
                self.get_file(), key_filter)
        _sed.sed = super(SiteDoc, self).subset(key_filter)
        return _sed
