"""
Main goal of this module is to provide some puppet utility functions like
finding all puppet agent hosts or to get the agent status on peer(s)/LMS
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
from logging.config import fileConfig
from socket import gethostname
from datetime import datetime
from optparse import OptionParser
import re
import sys
from logging import DEBUG, Handler, getLogger
from time import localtime, strftime

from h_util.h_utils import exec_process, keyboard_interruptable, ExitCodes
from litp.core import rpc_commands
from litp.core.litp_logging import LitpLogger
from litp.core.rpc_commands import PuppetExecutionProcessor, \
    PuppetCatalogRunProcessor

_LITP_LOGGER = None
MCO = '/usr/bin/mco'
LITP_LOG_CONF = '/etc/litp_logging.conf'
ENMLOG = getLogger('enminst')


class McoException(Exception):
    """
    MCO rpc operation failed.
    """
    pass


class InterceptHandler(Handler, object):
    """
    Handler to get log messages and print them to stdout
    """
    def __init__(self):
        Handler.__init__(self)
        self.regex = r'.*completed (a|an old) Puppet run:\s+' \
                     r'([0-9]+)\s+<\s+([0-9]+)'
        self.time_format = '%Y-%m-%d %H:%M:%S'

    def emit(self, record):
        """
        If the log message matches a puppet log message, reformat and print
        to stdout

        :param record: The record to check
        :return:
        """
        msg = record.getMessage()
        _match = re.match(self.regex, msg)
        if _match:
            last_time = _match.group(2)
            completed_tstamp = _match.group(3)

            msg = msg.replace(last_time,
                              strftime(self.time_format,
                                       localtime(
                                           float(last_time))))

            msg = msg.replace(completed_tstamp,
                              strftime(self.time_format,
                                       localtime(float(
                                           completed_tstamp))))
        print(msg)  # pylint: disable=superfluous-parens


def _init_logging(logging_config=LITP_LOG_CONF):
    """
    Initialize logging. Used in cli mode (i.e. called from bash)


    :param logging_config: The logging config file
    :type logging_config: str
    :returns: a ``LitpLogger`` instance
    :rtype: LitpLogger
    """
    fileConfig(logging_config)
    _logger = LitpLogger()
    # Add a StreamHandler to see the output on the console too otherwise
    # you're staring at what looks like a hanging command, this way you'll
    # see a bit of feedback from the LITP stuff.
    _logger.trace.addHandler(InterceptHandler())
    return _logger


def _get_litp_logger():
    """
    Get a logger. Used in cli mode (i.e. called from bash)
    :returns: A ``LitpLogger`` instance
    :rtype: LitpLogger
    """
    global _LITP_LOGGER  # pylint: disable=global-statement
    if not _LITP_LOGGER:
        _LITP_LOGGER = _init_logging()
    return _LITP_LOGGER


def discover_all_nodes(include_lms=True, lms_hostname=None):
    """
    Get node's known to Puppet/mco

    :param include_lms: Include the LMS in the list of nodes (if
    mco knows about it)
    :type include_lms: bool
    :param lms_hostname: The LMS hostname.
    :type lms_hostname: str
    :return: list(str)
    """
    hosts = exec_process([MCO, 'find'])
    hosts = hosts.split()
    if not include_lms:
        if lms_hostname:
            hostname = lms_hostname
        else:
            hostname = gethostname()
        if hostname in hosts:
            hosts.remove(hostname)
    return hosts


def discover_peer_nodes(peer_filter='.*'):
    """
    Get a list of puppet agent nodes.

    :param peer_filter: Limit return results that match this regex
    :type peer_filter: str
    :return: list(str)
    """
    nodes = []
    for node in discover_all_nodes(include_lms=False):
        if re.search(peer_filter, node):
            nodes.append(node)
    return nodes


def sync_agents_interrupt():
    """
    Show a specific message if the sync/wait gets interrupted by a CTRL-C

    """
    logger = _get_litp_logger()
    logger.trace.info('Puppet agent sync interrupted, rerun again to ensure'
                      ' all agents have fully synced to all nodes.')


def check_for_puppet_catalog_run():
    """
    Wait for puppet to complete all ongoing catalog runs on all nodes in
    the deployment.
    """
    all_nodes = discover_all_nodes()
    ENMLOG.info('Waiting for ongoing puppet catalog runs '
                'to complete on {0}'.format(', '.join(all_nodes)))
    puppet_trigger_wait(False, ENMLOG.info)
    ENMLOG.info('All catalog runs have now completed.')


@keyboard_interruptable(callback=sync_agents_interrupt)
def puppet_trigger_wait(full_sync,  # pylint: disable=too-many-locals
                        logger_info, host_list=None):
    """
    Wait for a puppet catalog run to complete.

    :param full_sync: Should a full sync be triggered or not.
    If ``False`` then wait for any ongoing puppet runs to complete, if
    ``True`` then trigger a puppet run and wait for them to finish.

    :type full_sync: bool
    :param host_list: If set only sync these puppet agents nodes
    :type host_list: list(str)
    :param logger_info: Logger instance to log with (Optional)
    """
    if not logger_info:
        log_method = _get_litp_logger()
        rpc_commands.log = log_method
    else:
        log_method = logger_info

    if host_list:
        master_list = host_list
    else:
        master_list = discover_all_nodes()

    pepe = PuppetCatalogRunProcessor()
    start_time = datetime.now().replace(microsecond=0)
    if full_sync:
        new_catalog_version = pepe.update_config_version()
        pepe.trigger_and_wait(new_catalog_version, master_list)
    else:
        pepe = PuppetExecutionProcessor()
        pepe.wait(master_list, verify_disabled=False)
    total_time = datetime.now().replace(microsecond=0) - start_time
    hours, remainder = divmod(total_time.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    log_method('Finished synching agents to nodes, '
               'took {0}h:{1}m:{2}s'.format(hours, minutes,
                                            seconds))
    if not full_sync:
        log_method('Summary:')
        hostnames = sorted(pepe.nodes.keys())
        for hostname in hostnames:
            data = pepe.nodes[hostname]
            completed_time = strftime('%Y-%m-%d %H:%M:%S',
                                      localtime(data['lastrun']))
            log_method('  {0} completed at {1}'.format(hostname,
                                                       completed_time))


def puppet_status(host_list=None):
    """
    Show the puppet status from nodes
    :param host_list: List of nodes to get the puppet status from
    :return:
    """
    cmd = ['mco', 'puppet', 'status', '--json']
    if host_list:
        for host in host_list:
            cmd.extend(['-I', host])
    for line in exec_process(cmd).split('\n'):
        line = line.strip()
        if line:
            # pylint: disable=superfluous-parens
            print(line)


def puppet_enable_disable(host_list=None, state='enable'):
    """
    Enable or Disable puppet agent from nodes
    :param host_list: List of nodes to get the puppet status from
    :param state: Expected state to change from nodes 'enable' or 'disable'
    :return:
    """
    cmd = ['mco', 'puppet', state, '--json']
    if host_list:
        for host in host_list:
            cmd.extend(['-I', host])
    for line in exec_process(cmd).split('\n'):
        line = line.strip()
        if line:
            # pylint: disable=superfluous-parens
            print(line)


def puppet_runall():
    """
    Push the puppet agent to run from all nodes
    :return:
    """
    cmd = ['mco', 'puppet', 'runall', '10', '--json']
    for line in exec_process(cmd).split('\n'):
        line = line.strip()
        if line:
            # pylint: disable=superfluous-parens
            print(line)


def main(args):
    """
    Handle input args/usage from shell.

    :param args: sys.argv
    """
    arg_parser = OptionParser(description='MCO stuff.')
    arg_parser.add_option('--status', action='store_true',
                          help='Display MCO status.')
    arg_parser.add_option('--sync', action='store_true',
                          dest='trigger_and_wait',
                          help='Sync mcollective agents.')
    arg_parser.add_option('--wait', action='store_true', dest='wait',
                          help='Wait for puppet run to complete.')
    arg_parser.add_option('-V', action='store_true', dest='verbose')
    arg_parser.add_option('-I', dest='include_host', action='append',
                          type='str', default=None)
    arg_parser.add_option('-L', dest='litp_logging', type=str,
                          default=LITP_LOG_CONF,
                          help='logging conf, default '
                               '/etc/litp_logging.conf')
    if len(args) <= 1:
        arg_parser.print_help()
        raise SystemExit(ExitCodes.INVALID_USAGE)

    prog_options, _ = arg_parser.parse_args(args)

    litp_logger = _init_logging(prog_options.litp_logging)
    if prog_options.verbose:
        litp_logger.trace.setLevel(DEBUG)

    if prog_options.trigger_and_wait:
        puppet_trigger_wait(True, litp_logger.trace.info,
                            host_list=prog_options.include_host)
    elif prog_options.wait:
        puppet_trigger_wait(False, litp_logger.trace.info,
                            host_list=prog_options.include_host)
    elif prog_options.status:
        puppet_status(prog_options.include_host)


if __name__ == '__main__':
    main(sys.argv)
