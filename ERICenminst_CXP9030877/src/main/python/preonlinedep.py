# pylint: disable=C0103,W1401,R0902,R0201
"""
Provision preonline triggers
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2015 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#

from h_util.h_utils import (ExitCodes, get_env_var, exec_process)
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import (init_enminst_logging,
                                       set_logging_level)
import logging
from h_litp.litp_rest_client import LitpRestClient
from litp.core.base_plugin_api import BasePluginApi
from litp.core.model_manager import ModelManager
from h_puppet.mco_agents import EnminstAgent
from string import Template
from base64 import standard_b64encode
import textwrap
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter

PREONLINE_TEMPLATE = \
"eval \'exec $${VCS_HOME:-/opt/VRTSvcs}/bin/perl5 -I \
${VCS_HOME:-/opt/VRTSvcs}/lib -S $$0 $${1+\"$$@\"}\'\n\
    if 0;\n\
use strict;\n\
use warnings;\n\
\n\
my $$sys_name = $$ARGV[0];\n\
my $$group_name = $$ARGV[1];\n\
##########my $path_to_grps = \"/root/p2.txt\";\n\
\n\
my $$vcs_home = $$ENV{\"VCS_HOME\"};\n\
if (!defined ($$vcs_home)) {\n\
    $$vcs_home=\"/opt/VRTSvcs\";\n\
}\n\
\n\
use ag_i18n_inc;\n\
VCSAG_SET_ENVS();\n\
\n\
if (!defined $$ARGV[0]) {\n\
    VCSAG_LOG_MSG (\"W\", \"Failed to continue; \
undefined system name\", 15028);\n\
    exit;\n\
} elsif (!defined $$ARGV[1]) {\n\
    VCSAG_LOG_MSG (\"W\", \"Failed to continue; \
undefined group name\", 15031);\n\
    exit;\n\
}\n\
\n\
# Check Priority 2 list and make an array\n\
# Priority 2 list is composed of SGs that depend on lvsrouter only\n\
my @lines = $p2;\n\
\n\
# Make a hash of the array and look for element matches\n\
# if an element matches wait for lvsrouter to online\n\
# if the element does not match go to the elsif and wait\n\
#for both lvsrouter and SPS to be online\n\
# except where the groups is in fact lvsrouter and sps\n\
\n\
my %groups = map { $$_ => 1 } @lines;\n\
\n\
if(exists($$groups{$$group_name})) {\n\
    VCSAG_LOG_MSG(\"I\",  \"$$group_name present in priority 2 dependent \
groups list.\",15333);\n\
    while (1) {\n\
        my (@lvs) = split(\'\\n\', `$$vcs_home/bin/hagrp \
-state Grp_CS_svc_cluster_lvsrouter | grep ONLINE \
| awk \'{for(i=1;i<NF;i++)printf\"%s\",\$$i OFS;\
if(NF)printf\"%s\",\$$NF;printf ORS}\'`);\n\
        VCSAG_LOG_MSG(\"I\", \"Waiting for lvsrouter to online  \
- $group_name\",15334);\n\
        if ($$#lvs != -1) {\n\
            VCSAG_LOG_MSG(\"I\", \"lvsrouter is online... \
$$group_name\",15333);\n\
            foreach my $$sg (@lvs)\n\
                {\n\
                    VCSAG_LOG_MSG(\"I\", \"$sg\",15335);\n\
                }\n\
                last;\n\
        }\n\
        sleep(10);\n\
    }\n\
}\n\
\n\
#\n\
elsif ($$group_name ne \"Grp_CS_svc_cluster_lvsrouter\" and \
$$group_name ne \"Grp_CS_svc_cluster_sps\") {\n\
VCSAG_LOG_MSG(\"I\", \"$$group_name not in priority 2 dependent groups list \
sleeping for 480sec\" ,15336);\n\
    sleep(480);\n\
    while (1) {\n\
        my (@lvs_router) = split(\'\\n\', `$$vcs_home/bin/hagrp \
-state Grp_CS_svc_cluster_lvsrouter | grep ONLINE | \
awk \'{for(i=1;i<NF;i++)\
printf\"%s\",\$$i OFS;\
if(NF)printf\"%s\",\$$NF;\
printf ORS}\'`);\n\
        my (@sps) = split(\'\\n\', `$$vcs_home/bin/hagrp \
-state Grp_CS_svc_cluster_sps | grep ONLINE | \
awk \'{for(i=1;i<NF;i++) \
printf\"%s\",\$$i OFS;\
if(NF)printf\"%s\",\$$NF;\
printf ORS}\'`);\n\
        VCSAG_LOG_MSG(\"I\", \"Waiting for lvsrouter and sps to online \
- $$group_name\",15334);\n\
        if (($$#lvs_router != -1) && ($$#sps != -1)) {\n\
            VCSAG_LOG_MSG(\"I\", \"lvsrouter and sps are available...onlining \
$$group_name\",15336);\n\
            foreach my $$sgs (@lvs_router, @sps){\n\
                VCSAG_LOG_MSG(\"I\", \"$$sgs\",15335);\n\
            }\n\
            last;\n\
        }\n\
        sleep(10);\n\
    }\n\
 }\n\
\n\
# give control back to HAD.\n\
\n\
if (defined $$ARGV[3]) {\n\
   VCSAG_SYSTEM(\"$$vcs_home/bin/hagrp -online -nopre $$ARGV[1] \
    -sys $$ARGV[0] -checkpartial $$ARGV[3]\");\n\
   exit;\n\
}\n\
\n\
\n\
VCSAG_SYSTEM(\"$$vcs_home/bin/hagrp -online \
-nopre $$ARGV[1] -sys $$ARGV[0]\");\n\
\n\
exit;\n\
"

SVC_CLUSTER = '/deployments/enm/clusters/svc_cluster'
TUNED_APP_NUM_THREADS = 10


class PreOnlineProvisionerException(Exception):
    """
    PreOnlineProvisioner failure
    """
    pass


class PreOnlineProvisioner(object):
    """
    Provide mechanism to set/unset preonline trigger
    """

    def __init__(self, logger_name='enminst'):
        """
        Initialise LitpRestClient, ModelManager and BasePluginApi
        """
        self.log = logging.getLogger(logger_name)
        self.rest = LitpRestClient()
        self.model_manager = ModelManager()
        self.base_api = BasePluginApi(self.model_manager)
        self.agent = EnminstAgent()
        self.all_sgs = None
        self.trigger_script = None
        self.app_agent_num_threads = None
        self.nodes = None
        self.init_dependency_lists()

    def init_dependency_lists(self):
        """
        Initialise dependency lists
        """
        svc_cluster = self.rest.get(SVC_CLUSTER)
        self.app_agent_num_threads =\
        svc_cluster['properties']['app_agent_num_threads']
        self.nodes = self.rest.get_items_by_type(SVC_CLUSTER, 'node', [])

        clustered_services = self.rest.get_items_by_type(SVC_CLUSTER,
                                           'vcs-clustered-service', [])
        _, p2, p3 = self.get_dependency_tree2(clustered_services)

        p2_union = []
        for node in p2.keys():
            p2_union = list(set(p2_union).union(set(p2[node])))

        p3_union = []
        for node in p3.keys():
            p3_union = list(set(p3_union).union(set(p3[node])))

        p2_sgs, p2_sgs_qw = self.convert_to_sgnames(p2_union)
        p3_sgs, _ = self.convert_to_sgnames(p3_union)
        self.all_sgs = list(set(p2_sgs) | set(p3_sgs))
        self.log.debug("All SGs to provision : {0}".format(self.all_sgs))

        self.log.info("Priority 2 SGs to add to template: {0}".
                       format(p2_sgs_qw))
        template_dict = {'p2': p2_sgs_qw}
        output = Template(PREONLINE_TEMPLATE).safe_substitute(
            template_dict)
        self.trigger_script = standard_b64encode(output)

    def set_preonline_trigger(self):
        """
        Provide mechanism to set preonline trigger
        """
        self.log.info("Setting preonline trigger...")
        self.set_consul_flag('enminst/preonline', self.trigger_script)
        self.enable_preonline(self.all_sgs)
        self.set_app_num_threads(TUNED_APP_NUM_THREADS)

    def unset_preonline_trigger(self):
        """
        Provide mechanism to unset preonline trigger
        """
        self.log.info("Unsetting preonline trigger...")
        self.disable_preonline(self.all_sgs)
        self.set_app_num_threads(self.app_agent_num_threads)

    def checkRC(self, out):
        """
        Check for mco Result code

        :param out: stdout from executed command
        :type: String
        """
        for line in out.splitlines():
            if 'Result code:' in line:
                rc = int(line.split(':')[-1].strip())
                if rc:
                    raise PreOnlineProvisionerException(out)

    def enable_preonline(self, services):
        """
        Provide mechanism to enable preonline trigger

        :param services: List of SG names
        :type: list
        """
        url = 'consul_url=http://ms-1:8500/v1/kv/enminst/preonline'
        cmd = ['mco', 'rpc', 'filemanager',
                       'pull_file',
                       url,
                       'file_path=/opt/VRTSvcs/bin/triggers/preonline']

        for node in self.nodes:
            cmd.append('-I')
            cmd.append(node['data']['properties']['hostname'])
        self.log.info("executing : {0}".format(cmd))
        self.checkRC(exec_process(cmd))

        for servicename in services:
            if servicename != "Grp_CS_svc_cluster_lvsrouter":
                cmd = ['mco', 'rpc', 'enminst',
                       'hagrp_add_triggers_enabled',
                       'group_name={0}'.format(servicename),
                       'attribute_val=PREONLINE',
                       '-I', self.nodes[0]['data']['properties']['hostname']]
                self.log.info("executing : {0}".format(cmd))
                self.checkRC(exec_process(cmd))

                cmd = ['mco', 'rpc', 'enminst',
                    'hagrp_modify',
                    'group_name={0}'.format(servicename),
                    'attribute=PreonlineTimeout',
                    'attribute_val=1500',
                    '-I',
                    self.nodes[0]['data']['properties']['hostname']]
                self.log.info("executing : {0}".format(cmd))
                self.checkRC(exec_process(cmd))

                cmd = ['mco', 'rpc', 'enminst',
                    'hagrp_modify',
                    'group_name={0}'.format(servicename),
                    'attribute=PreOnline',
                    'attribute_val=1',
                       '-I', self.nodes[0]['data']['properties']['hostname']]
                self.log.info("executing : {0}".format(cmd))
                self.checkRC(exec_process(cmd))

    def set_app_num_threads(self, app_agent_num_threads):
        """
        Provide mechanism to set app_agent_num_threads

        :param app_agent_num_threads: VCS NumThreads property value
        :type: Integer
        """
        cmd = ['mco', 'rpc', 'enminst', 'cluster_app_agent_num_threads',
                    'app_agent_num_threads={0}'.
                    format(str(app_agent_num_threads)),
                    '-I', self.nodes[0]['data']['properties']['hostname']]
        self.log.info("executing : {0}".format(cmd))
        self.checkRC(exec_process(cmd))

    def disable_preonline(self, services):
        """
        Provide mechanism to disable preonline trigger

        :param services: List of SG names
        :type: list
        """
        for servicename in services:
            cmd = ['mco', 'rpc', 'enminst',
                    'hagrp_delete_triggers_enabled',
                    'group_name={0}'.format(servicename),
                    'attribute_val=PREONLINE',
                    '-I',
                    self.nodes[0]['data']['properties']['hostname']]
            self.log.info("executing : {0}".format(cmd))
            self.checkRC(exec_process(cmd))

            cmd = ['mco', 'rpc', 'enminst',
                    'hagrp_modify',
                    'group_name={0}'.format(servicename),
                    'attribute=PreOnline',
                    'attribute_val=0',
                    '-I', self.nodes[0]['data']['properties']['hostname']]
            self.log.info("executing : {0}".format(cmd))
            self.checkRC(exec_process(cmd))

    def set_consul_flag(self, key, value):
        """
        Set a flag in consul kv store

        :param key: Key for entry
        :type: String
        :param value: Value for entry
        :type: list
        """
        cmd = "curl --request PUT --data {0}\
        http://ms-1:8500/v1/kv/{1}".format(value, key)
        self.log.info("executing : {0}".format(cmd))
        exec_process(cmd, use_shell=True)

    def convert_to_sgnames(self, services):
        """
        Provide mechanism to convert service names to SG names

        :param services: List of vm-service Item Ids
        :type: list
        :return: List of SG names
        """
        sgs = []
        sgs_qw = "qw("
        for service in services:
            if '-' in service:
                digit = service.split('-')[-1]
                if digit.isdigit():
                    service = '-'.join(service.split('-')[:-1]) + '_' + digit
                else:
                    service = '_'.join(service.split('-'))
                service = 'Grp_CS_svc_cluster_' + service
                cmd = ['mco', 'rpc', 'enminst', 'hagrp_display',
                        'groups={0}'.format(service),
                        '-I',
                        self.nodes[0]['data']['properties']['hostname']]
                stdout = exec_process(cmd)
                if 'VCS WARNING V-16-1-10133 Group does not exist'\
                    in stdout:
                    raise PreOnlineProvisionerException(stdout)
            else:
                service = 'Grp_CS_svc_cluster_' + service

            sgs.append(service)
            sgs_qw = sgs_qw + service + " "

        sgs_qw = sgs_qw + ")"
        return sgs, sgs_qw

    def get_dependency_tree2(self, clustered_services):
        """
        Construct the initial_online_dependency tree provisioned in LITP

        :param clustered_services: List of vcs-clustered-service Items
        :type: list
        :return: 3 dictionaries of services.
                 dependency_tree, priority2, priority3
        """
        dependency_tree = {}
        priority2 = {}
        priority3 = {}

        for service in clustered_services:
            service_name = service['data']['properties']['name']
            try:
                initial_online_dependency_list = service[
                'data']['properties']['initial_online_dependency_list']

                if initial_online_dependency_list == 'lvsrouter':
                    nodes = service['data']['properties']['node_list']
                    for node in nodes.split(','):
                        if node in priority2:
                            priority2[node].append(service_name)
                        else:
                            priority2[node] = [service_name]
                elif initial_online_dependency_list != '':
                    nodes = service['data']['properties']['node_list']
                    for node in nodes.split(','):
                        if node in priority3:
                            priority3[node].append(service_name)
                        else:
                            priority3[node] = [service_name]
            except KeyError:
                initial_online_dependency_list = None
            if initial_online_dependency_list:
                dependency_tree[service_name] = (
                    initial_online_dependency_list.split(','))
            else:
                dependency_tree[service_name] = []
        return dependency_tree, priority2, priority3


def create_argument_parser():
    """
    Creates and configures parser to process command line arguments

    :return: argument parser instance
    :rtype ArgumentParser
    """

    preonlinedep_epilog = textwrap.dedent('''
Examples:
Provision preonline trigger
# %(prog)s --action set \n\
Deprovision preonline trigger
# %(prog)s --action unset\
''')

    parser = ArgumentParser(prog="preonlinedep.py",
                        description='provision/deprovision dependency based '
                        'VCS preonline trigger on the svc cluster ',
                        formatter_class=RawDescriptionHelpFormatter,
                        epilog=preonlinedep_epilog)
    requiredNamed = parser.add_argument_group('required named arguments')

    requiredNamed.add_argument('--action', dest='action', required=True,
                    choices=['set', 'unset'],
                    help="%(prog)s action i.e.\n"\
                    "'set' will provision preonline trigger.\n"\
                    "'unset' will deprovision preonline trigger.\n")

    return parser


def preonline(options):
    """
    Execute preonline operation depending on the arguments given.

    :param options: arg options
    :type args: args
    """
    logger = init_enminst_logging()
    try:
        log_level = get_env_var('LOG_LEVEL')
        set_logging_level(logger, log_level)
    except KeyError:
        set_logging_level(logger, 'DEBUG')

    logger.info('Beginning preonline trigger provisioner')

    pop = PreOnlineProvisioner()
    if options.action == "set":
        pop.set_preonline_trigger()
    if options.action == "unset":
        pop.unset_preonline_trigger()


def main(args):
    """
    Main function for preonline operation.

    :param args: Main CLI args
    :type args: list(str)
    """
    arg_parser = create_argument_parser()
    options = arg_parser.parse_args(args)

    try:
        preonline(options)
    except SystemExit as error:
        if error.args[0] == ExitCodes.INVALID_USAGE:
            arg_parser.print_help()
        else:
            raise

if __name__ == '__main__':
    main_exceptions(main, sys.argv[1:])
