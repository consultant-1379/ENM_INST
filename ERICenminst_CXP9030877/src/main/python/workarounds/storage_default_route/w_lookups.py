"""
Functions to look up deployment information
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from netaddr import IPNetwork, IPAddress

from enm_snapshots import Decryptor
from h_litp.litp_rest_client import LitpRestClient
from h_util.h_nas_console import NasConsole
from h_xml.xml_utils import load_xml, xpath, get_xml_element_properties

PROVIDER_TYPE_SFS = 'sfs-service'
PROVIDER_TYPE_SAN = 'san-emc'

INFRA = '/infrastructure'
INFRA_STORAGE_PROVIDERS = '{0}/storage/storage_providers'.format(INFRA)
INFRA_NETWORKING = '{0}/networking'.format(INFRA)
INFRA_NETWORKS = '{0}/networks'.format(INFRA_NETWORKING)
INFRA_ROUTES = '{0}/routes'.format(INFRA_NETWORKING)

_LITP = None


class DefaultRouteException(Exception):
    """  Add route operation failed. """
    pass


def litp():
    """
    Get a LITP client ref.

    :returns: LITP client class
    :rtype LitpRestClient
    """
    global _LITP  # pylint: disable=W0603
    if not _LITP:
        _LITP = LitpRestClient()
    return _LITP


def check_in_network(addr, subnet):
    """
    Check if an IPv4 address is in the network's allowable address
    range

    :param addr: IP address to check is is the modeled network
    :type addr: IPAddress
    :param subnet:
    :type subnet: The subnet to check ``addr`` is in or not
    :returns: ``True`` is the ``addr`` is in network defined by
    ``subnet``
    :rtype: bool
    """
    return addr in subnet


def _get_storage_providers_litp(provider_type):
    """
    Get a list of modeled storage providers from LITP.

    :param provider_type: The provider item-type
    :type provider_type: str
    :returns: List of modeled storage providers or ``None`` if nothing found
    :rtype: list|None
    """
    storage_providers = []
    for modeled_provider in litp().get_children(INFRA_STORAGE_PROVIDERS):
        if modeled_provider['data']['item-type-name'] == provider_type:
            properties = modeled_provider['data']['properties']
            storage_providers.append(properties)
    return storage_providers


def _get_storage_providers_xml(provider_type, xml):
    """
    Get a list of modeled storage providers from a deployment XML file.

    :param provider_type: The provider item-type
    :type provider_type: str
    :param xml: The XML to query.
    :type xml: etree.Element
    :returns: List of modeled storage providers or ``None`` if nothing found
    :rtype: list
    """
    root = load_xml(xml)
    nodes = xpath(root, provider_type)
    storage_providers = []
    for node in nodes:
        storage_providers.append(get_xml_element_properties(node))
    return storage_providers


def _get_network_subnet_litp(network_name):
    """
    Get the subnet CIDR for a modeled network from LITP.
    :param network_name: The network name
    :type network_name: str
    :returns: The subnet for the network name or ``None`` if nothing found.
    :rtype: IPNetwork
    """
    for network in litp().get_children(INFRA_NETWORKS):
        properties = network['data']['properties']
        if network_name == properties['name']:
            return IPNetwork(properties['subnet'], implicit_prefix=False)
    return None


def _get_network_subnet_xml(network_name, xml):
    """
    Get the subnet CIDR for a modeled network from a deployment XML file.
    :param network_name: The network name
    :type network_name: str
    :param xml: The XML to query.
    :type xml: etree.Element
    :returns: The subnet for the network name or ``None`` if nothing found.
    :rtype: IPNetwork
    """
    root = load_xml(xml)
    infra = xpath(root, 'infrastructure',
                  attributes={'id': 'infrastructure'})[0]
    for network in xpath(infra, 'network'):
        netname = xpath(network, 'name', namespace=False)[0].text
        if network_name == netname:
            return IPNetwork(
                xpath(network, 'subnet', namespace=False)[0].text,
                implicit_prefix=False
            )
    return None


def _get_modeled_route_litp(gateway_ip):
    """
    Get the route from LITP with the gateway property equal to ``gateway_ip``
    from LITP

    :param gateway_ip: The gateway address
    :type gateway_ip: IPAddress
    :returns: tuple (id, properties) on the model item or (None, None) if
    nothing found

    :rtype tuple
    """
    for route in litp().get_children(INFRA_ROUTES):
        properties = route['data']['properties']
        if properties['gateway'] == str(gateway_ip):
            return route['data']['id'], properties
    return None, None


def _get_modeled_route_xml(gateway_ip, xml):
    """
    Get the route from LITP with the gateway property equal to ``gateway_ip``
    from a deployment XML file.

    :param gateway_ip: The gateway address
    :type gateway_ip: IPAddress
    :param xml: The XML to query.
    :type xml: etree.Element
    :returns: tuple (id, properties) on the model item or (None, None) if
    nothing found

    :rtype tuple
    """
    root = load_xml(xml)
    infra = xpath(root, 'infrastructure',
                  attributes={'id': 'infrastructure'})[0]
    for route in xpath(infra, 'route'):
        props = get_xml_element_properties(route)
        if props['gateway'] == str(gateway_ip):
            return route.get('id'), props
    return None, None


# def _get_modeled_defaultroute_xml(subnet, xml):
#     """
#     Get the modeled default route if its defined.
#
#     :param xml: The XML to query.
#     :type xml: str
#     :returns: list of tuple(str, IPAddress) on the model item or empty list
#     if nothing found
#
#     :rtype list
#     """
#     root = load_xml(xml)
#     infra = xpath(root, 'infrastructure', element_id='infrastructure')[0]
#     routes = []
#     for route in xpath(infra, 'route'):
#         props = get_xml_element_properties(route)
#         if props['subnet'] == str(subnet):
#             routes.append((route.get('id'), IPAddress(props['gateway'])))
#     return routes


# def _get_modeled_defaultroute_litp(subnet):
#     """
#     Get the modeled default route if its defined.
#
#     :returns: list of tuple(str, IPAddress) on the model item or empty list
#     if nothing found
#
#     :rtype tuple
#     """
#     routes = []
#     for route in litp().get_children(INFRA_ROUTES):
#         properties = route['data']['properties']
#         if properties['subnet'] == str(subnet):
#             routes.append((route['data']['id'],
#                            IPAddress(properties['gateway'])))
#     return routes


def get_storage_providers(provider_type, source=None):
    """
    Get defined storage provider

    :param provider_type: The model item-type
    :type provider_type: str
    :param source: If ``None`` get the providers from LITP, otherwise it's
    assumed ``source`` is a deployment XML file and the providers are read
    from there.
    :type source: str|None
    :returns: List of modeled storage providers or raises a
    DefaultRouteException if nothing found.

    :rtype: list
    """
    if source:
        _providers = _get_storage_providers_xml(provider_type, source)
    else:
        _providers = _get_storage_providers_litp(provider_type)
    if not _providers:
        raise DefaultRouteException(
            'Could not find any modeled storage providers of '
            'type \'{type}\''.format(type=provider_type))
    return _providers


def get_network_subnet(network_name, source=None):
    """
    Get the subnet CIDR for a modeled network.
    :param network_name: The network name
    :type network_name: str
    :param source: If ``None`` then get the subnet address directly from LITP,
    otherwise it's assumed ``source`` is a deployment XML file and the subnet
    is read from there.

    :type source: etree.Element
    :returns: The subnet for the network name or ``None`` if nothing found.
    :rtype: IPNetwork
    """
    if source:
        _subnet = _get_network_subnet_xml(network_name, source)
    else:
        _subnet = _get_network_subnet_litp(network_name)
    if not _subnet:
        raise DefaultRouteException(
            'No network called \'{network}\' '
            'modeled.'.format(network=network_name))
    return _subnet


def get_modeled_route(gateway_ip, source=None):
    """
    Get the modeled ``route`` item for gateway IPv4 address.

    :param gateway_ip: The gateway address
    :type gateway_ip: IPAddress
    :param source: If ``None`` then get the route info directly from LITP,
    otherwise it's assumed ``source`` is a deployment XML file and the route
    info is read from there.
    :type source: etree.Element
    :returns: tuple (id, properties) on the model item or (None, None) if
    nothing found

    :rtype tuple
    """
    if source:
        return _get_modeled_route_xml(gateway_ip, source)
    else:
        return _get_modeled_route_litp(gateway_ip)


def get_nas_storage_default_route(storage_subnet, source=None):
    """
    Looks for all modeled NAS providers and checks for one that has
    a default route that lies in the Storage VLAN subnet.

    If more than one NAS provider is defined, the first one found in
    the Storage VLAN subnet is used.

    :param storage_subnet: The storage subnet
    :type storage_subnet: IPNetwork
    :param source: If ``None`` then get the deployment NAS profiver info
    directly from LITP, otherwise it's assumed ``source`` is a deployment XML
    file and the NAS provider info is read from there.

    :type source: etree.Element
    :returns: Default route gateway address as used be a NAS provider
    or raise ``StorageVlanDbDefaultRouteException`` if none found.

    :rtype: IPAddress
    """
    sfs_providers = get_storage_providers(PROVIDER_TYPE_SFS, source)
    password_decryptor = Decryptor()
    for properties in sfs_providers:
        username = properties['user_name']
        passkey = properties['password_key']
        passwd = password_decryptor.get_password(passkey, username)
        masconsole = NasConsole(properties['management_ipv4'],
                                properties['user_name'], passwd)
        routes = masconsole.ip_route_show()
        for line in routes:
            line = line.strip()
            if line:
                parts = line.split(' ')
                if 'default' == parts[0]:
                    ipaddress = IPAddress(parts[2])
                    if check_in_network(ipaddress, storage_subnet):
                        return ipaddress
    raise DefaultRouteException('Could not find any SFS providers in subnet'
                                ' {subnet}'.format(subnet=storage_subnet))


# def get_modeled_defaultroute(subnet, source=None):
#     """
#     Get the modeled default route if its defined.
#
#     :param subnet: The default route subnet (0.0.0.0/0)
#     :type subnet: str|IPNetwork
#     :param source: If ``None`` then get the route info directly from LITP,
#     otherwise it's assumed ``source`` is a deployment XML file and the route
#     info is read from there.
#     :type source: str
#     :returns: tuple (str, IPAddress) on the model item or (None, None) if
#     nothing found
#
#     :rtype tuple (str, IPAddress)
#     """
#     if source:
#         return _get_modeled_defaultroute_xml(subnet, source)
#     else:
#         return _get_modeled_defaultroute_litp(subnet)
