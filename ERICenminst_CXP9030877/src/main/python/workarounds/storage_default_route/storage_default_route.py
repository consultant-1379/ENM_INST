"""
Workaround script for TORF-65895 where the SAN SP addresses are
one the Management VLAN. This adds a default route using the Storage VLAN
gateway which has the Management VLAN routed.
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
from os.path import exists, dirname, basename, join
from shutil import copyfile
import socket
import sys

from argparse import ArgumentParser

from netaddr import IPAddress

from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import ExitCodes, Sed
from workarounds.storage_default_route.w_lookups import \
    get_storage_providers
from workarounds.storage_default_route.w_lookups import PROVIDER_TYPE_SAN
from workarounds.storage_default_route.w_lookups import get_network_subnet
from workarounds.storage_default_route.w_lookups import DefaultRouteException
from workarounds.storage_default_route.w_lookups import get_modeled_route
from workarounds.storage_default_route.w_lookups import INFRA_ROUTES
from workarounds.storage_default_route.w_lookups import \
    get_nas_storage_default_route
from workarounds.storage_default_route.w_lookups import check_in_network
from workarounds.storage_default_route.w_lookups import litp
from h_xml.xml_utils import write_xml, xpath, load_xml, add_infra_route, \
    inherit_infra_route

LOGGER = init_enminst_logging()


def ipv4(addr):
    """
    Check if an address string is an IPv4 format address.

    :param addr:
    :param addr: str
    :returns: ``True`` if ``addr`` is an IPv4 format address, ``False``
    otherwise

    :rtype: bool
    """
    try:
        socket.inet_aton(addr)
        return True
    except socket.error:
        return False


def is_pxe_on_services(env_sed):
    """
    Check if the PXE boot network is the Services VLAN
    :param env_sed: The Site Engineering file being used to deploy the system
    :returns: `True` if the network with `litp_management=true` is the
    services network/vlan, `False` otherwise
    """
    sed = Sed(env_sed)
    has_key = sed.has_site_key('litp_management')
    if has_key:
        value = sed.get_value('litp_management')
        return value == 'services'
    else:
        return False


def _check_updates_needed(storage_network_name, env_sed, source=None):
    """

    Check if the SP addresses are on the Storage VLAN or not.

    :param storage_network_name:  The LITP modeled Storage VLAN name
    :type storage_network_name: str
    :param source: Where to get information from, directly from the LITP model
    ``source=None`` or a deployment XML file ``source=somefile.xml``

    :type source: str|None

    :returns: ``True`` if the SAN SP addresses are NOT in the Storage VLAN,
    ``False`` otherwise

    :rtype: bool
    """
    if is_pxe_on_services(env_sed):
        LOGGER.info('Services VLAN is the management network, no further '
                    'checks/updates being made.')
        return False
    LOGGER.info('Getting subnet for network \'{nwk}\''
                ''.format(nwk=storage_network_name))
    storage_subnet = get_network_subnet(storage_network_name, source)
    LOGGER.info(
        'Storage VLAN subnet is {subnet}'.format(subnet=storage_subnet))
    sans = get_storage_providers(PROVIDER_TYPE_SAN, source)
    updates_needed = False
    for san in sans:
        for sp_ipname in ['ip_a', 'ip_b']:
            sp_address = san[sp_ipname]
            LOGGER.info('Checking if StorageProcessor address {ip} is in '
                        'subnet {subnet}'.format(ip=sp_address,
                                                 subnet=storage_subnet))
            if not check_in_network(IPAddress(sp_address), storage_subnet) \
                    and sp_address != '127.0.0.1':
                LOGGER.info(
                    'SAN StorageProcessor IP {ip} is not in subnet {subnet}'
                    ''.format(ip=sp_address, subnet=storage_subnet))
                updates_needed = True
    if not updates_needed:
        LOGGER.info('SAN StorageProcessor addresses are on the Storage VLAN,'
                    ' no updates required.')
    return updates_needed


def _add_default_route(new_route_name, storage_gateway, update_target=None):
    """
    Add a default route

    :param new_route_name: The new item name
    :type new_route_name: str
    :param storage_gateway: The default route IPv4 address
    :type storage_gateway: IPAddress
    :param update_target: Where to make the updates, if ``None`` then update
    the LITP model directly, otherwise it's assumed ``update_target`` is a
    deployment XML file and the updates are made there.

    :type update_target: str|None
    """
    LOGGER.info('Adding a default route called {name} using {ip}'
                ''.format(name=new_route_name, ip=storage_gateway))
    if update_target:
        root = load_xml(update_target)

        node_list = []
        for node in xpath(root, 'node'):
            node_list.append(node.get('id'))
        db_list = [node for node in node_list if "db-" in node]

        infra = xpath(root, 'infrastructure',
                      attributes={'id': 'infrastructure'})[0]
        routes = xpath(infra, 'networking-routes-collection',
                       attributes={'id': 'routes'})[0]

        add_infra_route(routes, new_route_name, str(storage_gateway))
        LOGGER.info('Added infrastructure route \'{route}\' with gateway'
                    ' {gateway}'.format(route=new_route_name,
                                        gateway=storage_gateway))
        source_path = '{0}/{1}'.format(INFRA_ROUTES, new_route_name)
        for node_id in db_list:
            inherit_infra_route(root, source_path, node_id)
            LOGGER.info('Linked node {node} to route {route}'
                        ''.format(node=node_id, route=source_path))
        backup_file = join(dirname(update_target), 'orig_{0}'.
                           format(basename(update_target)))
        copyfile(update_target, backup_file)
        LOGGER.info('Backed up {orig} to {bk}'.format(orig=update_target,
                                                      bk=backup_file))
        write_xml(root, update_target)
        LOGGER.info('Written updates to {xml}'.format(xml=update_target))
    else:
        litp().create(INFRA_ROUTES, new_route_name, 'route',
                      properties={'subnet': '0.0.0.0/0',
                                  'gateway': str(storage_gateway)})
        LOGGER.info('Added infrastructure route \'{route}\' with gateway'
                    ' {gateway}'.format(route=new_route_name,
                                        gateway=storage_gateway))
        source_path = '{0}/{1}'.format(INFRA_ROUTES, new_route_name)
        db_list = []
        path = '/deployments/enm/clusters/db_cluster/nodes'
        nodes = litp().get_items_by_type(path, 'node', [])
        for node in nodes:
            db_list.append(node['data']['id'])
        for node_id in db_list:
            npath = '/deployments/enm/clusters/db_cluster/nodes/' \
                    '{node}/routes/{name}'.format(node=node_id,
                                                  name=new_route_name)
            litp().inherit(npath, source_path)
            LOGGER.info('Linked node {node} to route {route}'
                        ''.format(node=node_id, route=source_path))


def check_and_update(storage_network_name, env_sed,  # pylint: disable=R0913
                     xml_file=None,
                     auto_detect_gateway=False,
                     storage_gateway_ip=None,
                     new_route_name='storage_gateway_route',
                     check_only=False):
    """
    Check if a Storage VLAN default route is needed and update (if
    ``check_only`` == ``False``)

    :param storage_network_name: The new model item name (if added)
    :type storage_network_name: str
    :param env_sed: The SED being used to install/upgrade the env
    :type env_sed: str
    :param xml_file: Deployment XML file to update if set, if ``None`` then
    updates are made directly in LITP.

    :type xml_file: str|None
    :param auto_detect_gateway: If ``True`` then get the gateway address from
    the NAS being used in the deployment. If ``False`` then the value of
    ``storage_gateway_ip`` is used.

    :type auto_detect_gateway: bool
    :param storage_gateway_ip: Use this IPv4 address as the default route (
    Note: ``auto_detect_gateway`` should be ``False``

    :type storage_gateway_ip: IPAddress
    :param new_route_name: The new model item name (if added)
    :type new_route_name: str
    :param check_only: If ``True`` only check if an update is needed. If
    ``False`` updates are made if needed.

    :type check_only: bool
    """
    if xml_file:
        LOGGER.info('Using {0} as source'.format(xml_file))
    else:
        LOGGER.info('Using LITP as source.')
    updates_needed = _check_updates_needed(storage_network_name, env_sed,
                                           xml_file)
    if updates_needed:
        storage_subnet = get_network_subnet(storage_network_name,
                                            xml_file)
        if auto_detect_gateway:
            LOGGER.info('Looking up default route from deployment NAS')
            storage_gateway = get_nas_storage_default_route(storage_subnet,
                                                            xml_file)
            LOGGER.info('Found a NAS provider that has default route {ip}'
                        ''.format(ip=storage_gateway))
        else:
            if not ipv4(str(storage_gateway_ip)):
                raise DefaultRouteException(
                    'The IPv4 address \'{ip}\' is not a valid'.format(
                        ip=storage_gateway_ip))
            storage_gateway = IPAddress(storage_gateway_ip)
            if not check_in_network(storage_gateway, storage_subnet):
                raise DefaultRouteException(
                    'User defined gateway address {ip} is not in subnet '
                    '{subnet}'.format(ip=storage_gateway,
                                      subnet=storage_subnet))
            LOGGER.info('Using user defined gateway {ip} for '
                        'default route'.format(ip=storage_gateway))
        LOGGER.info('Checking if gateway {ip} already defined'
                    ''.format(ip=storage_gateway))
        eroutename, modeled_route = get_modeled_route(storage_gateway,
                                                      xml_file)
        if modeled_route:
            LOGGER.info('The gateway {ip} is already defined as {name}, no '
                        'changes needed.'.format(ip=storage_gateway,
                                                 name=eroutename))
        else:
            if check_only:
                LOGGER.info('SAN StorageProcessor addresses are not on Storage'
                            ' VLAN. A default route is needed in the '
                            'deployment description.')
            else:
                _add_default_route(new_route_name, storage_gateway, xml_file)


def create_arg_parser():
    """
    Create a parser to check the input arguements
    :returns: Instance of ArgumentParser
    """
    desc = 'Check if the SAN StorageProcessor addresses are on the Storage ' \
           'VLAN. If not then add a default route to the DB nodes using the' \
           ' Storage VLAN default route IPv4 gateway address.'
    parser = ArgumentParser(description=desc)

    group = parser.add_mutually_exclusive_group(required=True)
    parser.add_argument('--check', dest='check_only', action='store_true',
                        help='Check it.')

    group.add_argument('--auto', dest='auto_detect',
                       action='store_true', default=False,
                       help='Auto discover the Storage VLAN default gateway '
                            'IPv4 address used on the deployments\' associated'
                            ' SFS and use that IPv4 as the gateway address for'
                            ' Storage VLAN default route on the DB nodes.')
    group.add_argument('--gw', dest='storage_gw',
                       metavar='<Storage VLAN gateway IPv4 address>',
                       help='Gateway address for Storage VLAN default route.')

    parser.add_argument('--update', dest='update_type', required=True,
                        nargs='?',
                        help='How the updates are made.......')

    parser.add_argument('--sed', dest='sed', required=True,
                        help='Used to make some further checks')

    parser.add_argument('--deployment', dest='deployment',
                        default='enm', metavar='<Deployment Name>',
                        help='The deployment name in LITP.')
    parser.add_argument('--db_cluster', dest='db_cluster',
                        metavar='<DB Cluster Name>', default='db_cluster',
                        help='The database cluster name in LITP.')
    parser.add_argument('--nwk_storage', dest='nwk_storage',
                        metavar='<Storage Network Name>', default='storage',
                        help='The Storage VLAN network name in LITP.')
    return parser


def main(args):
    """
    Main function, arguement handling.

    :param args: sys.argv[1:]
    :type args: list
    :return:
    """

    arg_parser = create_arg_parser()
    if not args:
        arg_parser.print_help()
        raise SystemExit(ExitCodes.INVALID_USAGE)
    parsed_args = arg_parser.parse_args(args)
    auto_detect = parsed_args.auto_detect
    storage_gw = parsed_args.storage_gw

    if parsed_args.update_type:
        if not exists(parsed_args.update_type):
            LOGGER.error('The file {file} does not exist'
                         ''.format(file=parsed_args.update_type))
            raise SystemExit(ExitCodes.INVALID_USAGE)
    check_and_update(parsed_args.nwk_storage,
                     parsed_args.sed,
                     parsed_args.update_type,
                     auto_detect_gateway=auto_detect,
                     storage_gateway_ip=storage_gw,
                     check_only=parsed_args.check_only)


if __name__ == '__main__':
    main_exceptions(main, sys.argv[1:])
