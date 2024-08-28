"""
The purpose of this script is to set initial credentials on
all the peer nodes after ENM initial install
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2019 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : set_initial_passwords.py
# Purpose : The purpose of this script is to set initial credentials on
# all the peer nodes after ENM initial install
# ********************************************************************

import sys
from getpass import getpass
from subprocess import Popen
from subprocess import PIPE


from h_util.h_utils import ExitCodes
from h_logging.enminst_logger import init_enminst_logging
from h_puppet.mco_agents import EnminstAgent, McoAgentException
from h_puppet.h_puppet import discover_peer_nodes

LOG = init_enminst_logging(logger_name='enmhealthcheck')


def set_credentials(nodes, user, new_pass):
    """
    Calls an mco agent to update initial credentials for a user
    on a list of nodes. Then list out any nodes where
    credentials were not set

    :param nodes: a list of nodes
    :param user: a str containing the username
    :param new_pass: a str containing the new password
    """
    sucess_msg = "updated successfully"
    LOG.info('Setting new credentials for user "{0}" on peer nodes'
                  .format(user))
    all_nodes_set = True
    try:
        set_pass = EnminstAgent()
        output = set_pass.update_initial_credentials(nodes, user, new_pass)
        for node in output.keys():
            if sucess_msg not in output[node]:
                LOG.info('Unable to set new credentials for user "{0}" '
                         'on node "{1}", please update manually.'
                         .format(user, node))
                all_nodes_set = False
        if all_nodes_set:
            LOG.info('Credentials set successfully'
                     ' for user "{0}" on peer nodes'.format(user))
    except SystemExit:
        LOG.error('For user "{0}" setting of new credentials: '
                       'FAILED.'.format(user))
        raise SystemExit(ExitCodes.ERROR)
    except McoAgentException as mco_ret:
        for node in mco_ret[0]:
            if mco_ret[0][node]['errors']:
                LOG.error(
                    'Unable to set new credentials for user "{0}" on node '
                    '"{1}" due to error: "{2}"'.format(
                        user, node, mco_ret[0][node]['errors']))


def get_peer_nodes():
    """
    Returns a list of the peer nodes
    :return: list of the peer nodes
    """
    node_list = discover_peer_nodes()
    if node_list:
        LOG.info('Peer nodes found: "{0}"'.format('", "'.join(node_list)))
        return node_list
    else:
        LOG.info('No Peer nodes found.')


def valid_password(pswd):
    """
    Check the password strength
    :param pswd: a str containing the password
    """
    echo_pswd = Popen(['echo', pswd], stdout=PIPE)
    check_result = Popen(['cracklib-check'], stdin=echo_pswd.stdout,
                         stdout=PIPE).communicate()[0]
    echo_pswd.stdout.close()

    if 'OK\n' not in check_result:
        LOG.info('Bad password! Reason {0}'.format(
            check_result.split(': ')[-1]))
        return False

    return True


def get_user_credentials(user):
    """
    Get the passwords for an user. There are 3 attempts before it exits.
    :param user: a str containing the username
    """
    retry = 1

    while retry <= 3:
        creden_1 = getpass('Enter new password for {0}: '.format(user))
        if not valid_password(creden_1):
            retry += 1
            continue

        creden_2 = getpass('Retype new password for {0}: '.format(user))

        if creden_1 != creden_2:
            LOG.info('New passwords do not match.')
            retry += 1
            continue

        break

    if retry > 3:
        LOG.info('Too many retries!')
        sys.exit(0)

    return creden_1


def main():
    """
    Main function
    :param args: sys args
    :return:
    """

    LOG.info('Update_initial_password script: '
             'This script is to be run once after '
             'initial install to update initial passwords.')

    node_list = get_peer_nodes()

    if not node_list:
        sys.exit(0)

    user_pass = {
        'litp-admin': None,
        'root': None
    }

    for user in user_pass:
        user_pass[user] = get_user_credentials(user)

    if node_list:
        for user, passwd in user_pass.iteritems():
            set_credentials(node_list, user, passwd)


if __name__ == '__main__':
    main()
