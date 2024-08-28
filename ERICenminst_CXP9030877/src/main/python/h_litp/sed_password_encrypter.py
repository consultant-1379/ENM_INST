"""
Functions around SED password encryption.
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
from re import match
import sys

from argparse import ArgumentParser

from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import Sed, exec_process, get_sed_nodetypes, format_sed_key

LOGGER = init_enminst_logging()


def litpcrypt_set(key_name, username, password):
    """
    Store a password for a user.

    :param key_name: The key name to store the password under
    :type key_name: str
    :param username: The user of the password
    :type username: str
    :param password: The password to store
    :type password: str
    """
    command = ['/usr/bin/litpcrypt', 'set', key_name, username, password]
    exec_process(command)


def set_key_san(sed):
    """
    Use litpcrypt to store the SAN user password.

    :param sed: Site engineering file containing the SAN user info
    :type sed: Sed
    """
    san_system_name = sed.get_value('san_systemName', error_if_not_set=True)
    san_user = sed.get_value('san_user', error_if_not_set=True)
    san_password = sed.get_value('san_password', error_if_not_set=True)
    key_name = 'key-for-san-{0}'.format(san_system_name)

    LOGGER.info('Encrypting password for '
                '"{0}:{1}" as {2}'.format(san_system_name, san_user,
                                          key_name))
    litpcrypt_set(key_name, san_user, san_password)


def set_key_sfs(sed):
    """
    Use litpcrypt to store the SFS support user password.

    :param sed: Site engineering file containing the support user info
    :type sed: Sed
    """
    sfssetup_username = sed.get_value('sfssetup_username',
                                      error_if_not_set=True)
    sfssetup_password = sed.get_value('sfssetup_password',
                                      error_if_not_set=True)
    key_name = 'key-for-sfs'
    LOGGER.info('Encrypting password for '
                '"NAS:{0}" as {1}'.format(sfssetup_username, key_name))
    litpcrypt_set(key_name, sfssetup_username, sfssetup_password)


def set_key_ndmp(sed):
    """
    Use litpcrypt to store the NDMP password.
    There is no user-name associated with NDMP. It is just NDMP password.
    Using ndmp as the default user-name.

    :param sed: Site engineering file containing the ndmp info
    :type sed: Sed
    """
    nas_type = sed.get_value('nas_type', default='veritas')
    if nas_type == 'unityxt':
        nas_ndmp_password = sed.get_value('nas_ndmp_password',
                                      error_if_not_set=True)
        key_name = 'key-for-ndmp'
        ndmp_username = 'ndmp'
        LOGGER.info('Encrypting password for '
                    '"NAS_NDMP:{0}" as {1}'.format(ndmp_username, key_name))
        litpcrypt_set(key_name, ndmp_username, nas_ndmp_password)


def set_key_nodes(sed):
    """
    Use litpcrypt to store the iLO user password for each node.

    :param sed: Site engineering file containing the iLO user info
    :type sed: Sed
    """
    group_regex = '^(.*?)_node([0-9]+)_hostname'
    unset_values = []
    for nodetype, count in get_sed_nodetypes(sed).items():
        for index in range(1, count + 1):
            hostname_key = format_sed_key(nodetype, index, 'hostname')
            hostname_value = sed.get_value(hostname_key)
            if not hostname_value:
                continue

            _match = match(group_regex, hostname_key)
            node_id = '{0}_node{1}'.format(_match.group(1),
                                           _match.group(2))

            try:
                ilo_username = sed.get_value(
                    '{0}_iloUsername'.format(node_id),
                    error_if_not_set=True)
                ilo_password = sed.get_value(
                    '{0}_iloPassword'.format(node_id),
                    error_if_not_set=True)
            except ValueError as error:
                unset_values.append(str(error))
                continue

            keyname = 'key-for-{0}_ilo'.format(node_id)
            LOGGER.info('Encrypting iLO password for '
                        '"{0}:{1}" as {2}'.format(node_id, ilo_username,
                                                  keyname))
            litpcrypt_set(keyname, ilo_username, ilo_password)
    if unset_values:
        raise ValueError('\n'.join(unset_values))


def set_key_nodes_vapp():
    """
    Set the litpcrypt info for the Redfish cloud calls
    This just dummies the entries as the values arn't used by the SPP api
    :return:
    """
    key_name = 'key-for-user'
    ilo_username = 'no_user'
    LOGGER.info('Encrypting vApp iLO password for '
                '"{0}:{1}"'.format(key_name, ilo_username))
    litpcrypt_set(key_name, ilo_username, 'no_password')


def main(args):
    """
    Main function. Takes in the SiteEngineering sed file and sets the
    litpcrypt entries as needed
    :param args: sys.argv
    :return:
    """
    arg_parser = ArgumentParser()
    arg_parser.add_argument('--sed', dest='sed', required=True,
                            help='SED containing passwords to be encrypted')
    arg_parser.add_argument('--type', dest='type', required=True,
                            choices=['blade', 'cloud'],
                            help='The deployment type.')

    prog_args = arg_parser.parse_args(args)
    sed = Sed(prog_args.sed)
    set_key_sfs(sed)
    if prog_args.type == 'blade':
        set_key_san(sed)
        set_key_nodes(sed)
        set_key_ndmp(sed)
    elif prog_args.type == 'cloud':
        set_key_nodes_vapp()


if __name__ == '__main__':
    main(sys.argv[1:])
