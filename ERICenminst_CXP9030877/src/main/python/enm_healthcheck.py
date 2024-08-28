# pylint: disable=C0302,R0904
"""
The purpose of this wrapper script execute all or various
health checks on the enm system.
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2015 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : enm_healthcheck.py
# Purpose : The purpose of this wrapper script execute all or various
# health checks on the enm system.
# ********************************************************************
import argparse
import inspect
import logging
import os
import sys
import textwrap
import re
import traceback
from collections import OrderedDict

from h_hc.hc_mdt import MdtHealthCheck
from h_hc.hc_neo4j_cluster import Neo4jClusterOverview, \
    Neo4jHCNotSupportedException, Neo4jClusterOverviewException, \
    Neo4jClusterCriticalRaftIndexLagException, \
    DbNodesSshCredentials, DbNodesSshCredsException, \
    FORCE_SSH_KEY_ACCESS_FLAG_PATH
from h_hc.hc_ombs import OmbsHealthCheck
# pylint: disable=import-error
from enmfcapshealthcheck.h_hc.hc_fcaps \
    import FCAPSHealthCheck  # pylint: disable=import-error
from h_hc.hc_san import SanHealthChecks
from h_hc.hc_services import Services
from h_hc.hc_consul import ConsulHC
from h_hc.hc_mp_paths import MPpathsHealthCheck
from h_logging.enminst_logger import init_enminst_logging, set_logging_level, \
    log_header
from h_util.h_utils import keyboard_interruptable, ExitCodes, \
    get_env_var, read_enminst_config, Decryptor, sanitize, get_nas_type, \
    is_env_on_rack
from h_vcs.vcs_cli import Vcs
from h_llt.llt_healthcheck import LltHealthCheck
from h_vcs.vcs_utils import report_tab_data, is_dps_using_neo4j
from hw_resources import HwResources
from san_fault_check import SanFaultCheck
from clean_san_luns import SanCleanup
from h_xml.xml_utils import load_xml
from h_puppet.mco_agents import EnminstAgent, McoAgentException, PuppetAgent
from h_util.h_nas_console import NasConsole, NasConsoleException
from h_util.h_postgres import PostgresService, PostgresCredentialsException, \
    PostgresServiceException
from h_litp.litp_rest_client import LitpRestClient
from h_snapshots.litp_snapshots import LitpSanSnapshots
from h_litp.litp_utils import LitpException
from verify_postgres_password_expiry import VerifyPostgresPasswordExpiry, \
    PostgresQueryFailed, DateParserFailed, PostgresDBDoesNotExist, \
    PostgresObjectDoesNotExist, PostgresExpiryNotRetrieved, \
    PostgresPasswordHasExpired
from enm_grub_cfg_check import GrubConfCheck

_LOGGER = None

ACTION_FUNCTION_LIST = ["enminst_healthcheck", "ombs_backup_healthcheck",
                        "fcaps_healthcheck",
                        "nas_healthcheck", "multipath_active_healthcheck",
                        "san_alert_healthcheck", "hw_resources_healthcheck",
                        "stale_mount_healthcheck", "node_fs_healthcheck",
                        "system_service_healthcheck",
                        "vcs_cluster_healthcheck",
                        "vcs_service_group_healthcheck",
                        "storagepool_healthcheck",
                        "consul_healthcheck", "mdt_healthcheck",
                        "lvm_conf_filter_healthcheck",
                        "vcs_llt_heartbeat_healthcheck",
                        "postgres_expiry_check",
                        "postgres_pre_uplift_check",
                        "neo4j_availability_check",
                        "neo4j_raft_index_lag_check",
                        "puppet_enabled_healthcheck", "grub_cfg_healthcheck",
                        "network_bond_healthcheck"]


EPILOG_HC = textwrap.dedent('''
# ./%(prog)s --action enminst_healthcheck           -> Runs all the \
healthchecks listed except for ombs_backup_healthcheck and fcaps_healthcheck.
# ./%(prog)s --action hw_resources_healthcheck      -> Checks status of \
RAM/CPU required to run all assigned VM's on a Blade.
# ./%(prog)s --action nas_healthcheck               -> Checks state of \
UnityXT or VA NAS.
# ./%(prog)s --action storagepool_healthcheck       -> Checks the SAN \
StoragePool usage.
# ./%(prog)s --action stale_mount_healthcheck       -> Checks for stale \
mounts on MS and Peer Nodes.
# ./%(prog)s --action node_fs_healthcheck           -> Checks Filesystem \
Usage on MS, NAS and Peer Nodes.
# ./%(prog)s --action ombs_backup_healthcheck       -> Checks OMBS backups \
and displays a list of recent backups.
# ./%(prog)s --action system_service_healthcheck    -> Checks status of \
key lsb services on each Blade.
# ./%(prog)s --action vcs_cluster_healthcheck       -> Checks the state \
of the VCS clusters on the deployment.
# ./%(prog)s --action vcs_llt_heartbeat_healthcheck -> Checks state of VCS \
llt heartbeat network interfaces on the deployment.
# ./%(prog)s --action vcs_service_group_healthcheck -> Checks state of VCS \
service groups on the deployment.
# ./%(prog)s --action fcaps_healthcheck             -> Runs FCAPS summary \
of the system.
# ./%(prog)s --action consul_healthcheck            -> Checks status of \
consul cluster.
# ./%(prog)s --action multipath_active_healthcheck  -> Checks paths to disks \
on DB nodes are all accessible.
# ./%(prog)s --action puppet_enabled_healthcheck    -> Checks Puppet is \
enabled on all nodes.
# ./%(prog)s --action san_alert_healthcheck         -> Checks if there are \
critical alerts on the SAN.
# ./%(prog)s --action lvm_conf_filter_healthcheck   -> Checks lvm.conf \
filter settings are correct. Only applicable to ENM on Rackmount Servers.
# ./%(prog)s --action mdt_healthcheck               -> Checks if the disk \
space required for model deployment is available.
# ./%(prog)s --action postgres_expiry_check         -> Checks the expiry \
of the postgres user password.
# ./%(prog)s --action postgres_pre_uplift_check     -> Check if Postgres \
# needs a version uplift and /ericsson/postgres has enough space for uplift.
# ./%(prog)s --action neo4j_availability_check      -> Check that Neo4j \
database instances are online and available to accept connections.
# ./%(prog)s --action neo4j_raft_index_lag_check    -> Check if raft \
index lag between leader and follower too big; informal check at this stage, \
should not fail HC in either case.
# ./%(prog)s --action grub_cfg_healthcheck          -> Checks LVs in \
the model are present in grub.cfg. NOT applicable to ENM on Rackmount Servers.
# ./%(prog)s --action network_bond_healthcheck      -> Checks if the network \
bond is in a healthy state. Only applicable to ENM on Rackmount Servers.
If no [action] is specified then enminst_healthcheck will be run by default \
which runs all healthchecks except the ombs_backup_healthcheck and \
fcaps_healthcheck.
# ./%(prog)s --exclude hw_resources_healthcheck     -> Runs all the \
healthchecks listed except for hw_resources_healthcheck.
# ./%(prog)s --exclude nas_healthcheck              -> Runs all the \
healthchecks listed except for nas_healthcheck.
# ./%(prog)s --exclude storagepool_healthcheck      -> Runs all the \
healthchecks listed except for storagepool_healthcheck.
# ./%(prog)s --exclude stale_mount_healthcheck      -> Runs all the \
healthchecks listed except for stale_mount_healthcheck.
# ./%(prog)s --exclude node_fs_healthcheck          -> Runs all the \
healthchecks listed except for node_fs_healthcheck.
# ./%(prog)s --exclude system_service_healthcheck   -> Runs all the \
healthchecks listed except for system_service_healthcheck.
# ./%(prog)s --exclude vcs_cluster_healthcheck      -> Runs all the \
healthchecks listed except for vcs_cluster_healthcheck.
# ./%(prog)s --exclude vcs_llt_heartbeat_healthcheck -> Runs all the \
healthchecks listed except for vcs_llt_heartbeat_healthcheck.
# ./%(prog)s --exclude vcs_service_group_healthcheck -> Runs all the \
healthchecks listed except for vcs_service_group_healthcheck.
# ./%(prog)s --exclude consul_healthcheck           -> Runs all the \
healthchecks listed except for consul_healthcheck.
# ./%(prog)s --exclude multipath_active_healthcheck -> Runs all the \
healthchecks listed except for multipath_active_healthcheck.
# ./%(prog)s --exclude puppet_enabled_healthcheck   -> Runs all the \
healthchecks listed except for puppet_enabled_healthcheck.
# ./%(prog)s --exclude san_alert_healthcheck        -> Runs all the \
healthchecks listed except for san_alert_healthcheck.
# ./%(prog)s --exclude lvm_conf_filter_healthcheck  -> Runs all the \
healthchecks listed except for lvm_conf_filter_healthcheck.
# ./%(prog)s --exclude mdt_healthcheck              -> Runs all the \
healthchecks listed except for mdt_healthcheck.
# ./%(prog)s --exclude postgres_expiry_check        -> Runs all the \
healthchecks listed except for postgres_expiry_check.
# ./%(prog)s --exclude postgres_pre_uplift_check    -> Runs all the \
healthchecks listed except for postgres_pre_uplift_check.
# ./%(prog)s --exclude neo4j_availability_check     -> Runs all the \
healthchecks listed except for neo4j_availability_check.
# ./%(prog)s --exclude neo4j_raft_index_lag_check   -> Runs all the \
healthchecks listed except for neo4j_raft_index_lag_check.
# ./%(prog)s --exclude grub_cfg_healthcheck         -> Runs all the \
healthchecks listed except for grub_cfg_healthcheck.
# ./%(prog)s --exclude network_bond_healthcheck     -> Runs all the \
healthchecks listed except for network_bond_healthcheck.
If no [exclude] is specified then enminst_healthcheck will be run by default \
which runs all healthchecks except the ombs_backup_healthcheck and \
fcaps_healthcheck.
''')


class HealthCheck(object):  # pylint: disable=R0902, R0904
    """
    Class containing health checks
    """

    NAS_RUN_FS_USAGE_CHECK = True
    NAS_CMD_USAGE = 'df -hPTl -x tmpfs -x devtmpfs'
    NAS_AUDIT = '/opt/ericsson/NASconfig/bin/nasAudit.sh'
    NAS_AUDIT_CHECK = '/opt/ericsson/NASconfig/bin/nasauditcheck.sh'
    NAS_VA_CHECK = 'ls /opt/SYMCsnas'
    NAS_VA74_CHECK = 'ls /opt/VRTSnas'
    STORAGE_PATH = '/infrastructure/storage/storage_providers'
    STORAGE_POOL_PATH = '/infrastructure/storage/storage_providers/sfs/pools'
    NAS_AUDIT_REPORT_LINE = 'Report generated to'
    NAS_AUDIT_FAILURE = 'Review log file'

    NAS_AUDIT_SUCCESS = 0
    NAS_AUDIT_WARNING = 1
    NAS_AUDIT_ERROR = 2
    NAS_AUDIT_UNKNOWN = 3

    NAS_AUDIT_INFO_LOC_MSG = ('For more information refer to the audit report '
                              'on the NAS {0} in the location {1}')

    LVM_CONF_FILTER_EXPECTED_VALUE = '[ "a|/dev/mapper/mpath.*|", "r|.*|" ]'

    LVM_CONF_GLOBAL_FILTER_ALT_VAL = '[ "r|/dev/vx/dmp/|", '\
                                       '"r|/dev/Vx.*|", '\
                                       '"a|/dev/mapper/mpath.*|", "r|.*|" ]'

    LVM_CNF_GFLTR_OPNSTCK_VAL = \
                      '[ "a|/dev/sd.*|",  "a|/dev/mapper/mpath.*|", "r|.*|" ]'

    LVM_CNF_GFLTR_OPNSTCK_ALT_VAL = '[ "a|/dev/sd.*|",  '\
                                      '"r|/dev/vx/dmp/|", '\
                                      '"r|/dev/Vx.*|", '\
                                      '"a|/dev/mapper/mpath.*|", "r|.*|" ]'

    NETWORK_BOND_SUCCESS_MSG = "OK"
    NETWORK_BOND_WARNING_MSG = "WARNING"
    NETWORK_BOND_ERROR_MSG = "ERROR"

    def __init__(self, logger_name='enmhealthcheck'):
        self.logger_name = logger_name
        self.logger = logging.getLogger(logger_name)
        self.config = read_enminst_config()
        self.usage_percentages = [self.config.get('base_fs_use'),
                                  self.config.get('nas_fs_use'),
                                  self.config.get(
                                      'dbgeneric_elastic_fs_use')]
        self.fs_exclude = self.config.get('fs_exclude') \
            .replace(' ', '').split(',')
        self.rest = LitpRestClient()
        self.nas_pool_name = ''
        self.excluded = []
        self.neo4j_cluster = Neo4jClusterOverview()
        self.nas_type = get_nas_type(self.rest)

        if self.nas_type == 'unityxt':
            HealthCheck.STORAGE_POOL_PATH = '/infrastructure/storage/' \
            'storage_providers/unityxt/pools'

    def is_openstack_deployment(self):
        """
        Determine if the deployment is on Openstack
        return: True if Openstack else False
        :rtype: bool
        """
        dtype = self.get_global_property('enm_deployment_type')

        if dtype and re.match(r'.*vLITP_ENM_On_Rack_Servers$', dtype):
            return True

        return False

    def pre_checks(self, verbose=False):
        """
        Function Description:
        Prior to healthcheck, ensure the necessary files & folders exist
        :param verbose: Turn on verbose logging
        """
        self.logger.info("Beginning ENM pre-Healthchecks")
        self.check_active_nodes(verbose)
        self.logger.info("Completed ENM pre-Healthchecks")

    def set_exclude(self, exclude):
        """
        Function Description:
        Sets list of functions to exclude
        :param exclude: Array of functions to exclude
        """
        self.excluded = exclude if exclude is not None else []

    def is_healthcheck_excluded(self, healthcheck_name, log_message):
        """
        Function Description:
        Returns True if the given healthcheck is to be excluded
        :param healthcheck_name: Name of healthcheck being checked
        :type healthcheck_name: String
        :param log_message: Description of healthcheck to appear in logs
        if healthcheck is excluded
        :type log_message: String
        :return: bool
        """
        if healthcheck_name in self.excluded:
            self.logger.info('Skipping {0} as excluded.'.format(log_message))
            return True
        return False

    def vcs_llt_heartbeat_healthcheck(self, verbose=False):
        """
        vcs_llt_heartbeat_healthcheck checks the state of the
        heartbeat network interfaces.
        :param verbose: Turn on verbose logging.
        """
        if self.is_healthcheck_excluded('vcs_llt_heartbeat_healthcheck',
                                        'VCS LLT Heartbeat Healthcheck'):
            return

        self.logger.info("Beginning VCS LLT Heartbeat Healthcheck")
        try:
            LltHealthCheck().verify_health(verbose=verbose)
            self.logger.debug('ENM VCS LLT heartbeat healthcheck '
                              'Status: PASSED')
        except SystemExit:
            self.logger.error('VCS LLT heartbeat healthcheck status: FAILED. ')
            self.logger.error('There appears to be a fault with '
                              'the VCS LLT heartbeat network interfaces. ')
            raise

        self.logger.info("Successfully Completed "
                         "VCS LLT Heartbeat Healthcheck")

    def vcs_cluster_healthcheck(self, verbose=False):
        """
        Function Description:
        vcs_cluster_healthcheck checks the state of the clusters on the
        system
        :param verbose: Turn on verbose logging
        """
        if self.is_healthcheck_excluded('vcs_cluster_healthcheck',
                                        'VCS Cluster System Healthcheck'):
            return

        self.logger.info("Beginning VCS Cluster System Healthcheck")
        try:
            Vcs.verify_cluster_system_status(cluster_filter=None,
                                             systemstate_filter=None,
                                             verbose=verbose)
            self.logger.debug('ENM VCS Cluster System Status: PASSED')
        except SystemExit:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error('There appears to be a fault with '
                              'the VCS Cluster Systems. ')
            raise
        self.logger.info("Successfully Completed VCS Cluster "
                         "System Healthcheck")

    def hw_resources_healthcheck(self, verbose=False):
        """
        Function Description:
        hw_resources_healthcheck checks VM RAM and CPU usage per blade.
        :param verbose: Turn on verbose logging
        """
        if self.is_healthcheck_excluded('hw_resources_healthcheck',
                                        'Hardware Resources Healthcheck'):
            return

        hw_resources = HwResources(logger_name=self.logger_name)
        try:
            base_model_xml = hw_resources.base_model_xml
            self.logger.info('Exporting model ...')
            hw_resources.export_model(base_model_xml)

            base_doc = load_xml(base_model_xml)
            self.logger.info('Gathering VM RAM and CPU resources from '
                             'each node')
            base_usage = hw_resources.get_modeled_vm_resources(base_doc)
            vm_resource_usage = hw_resources.get_blade_vm_resources(
                base_usage)
            hostidmappings = hw_resources.get_modeled_hosts(base_doc)
            states = hw_resources.get_node_states()
            hw_resources.show_blade_vm_usage(
                vm_resource_usage, hostidmappings,
                states, verbose=verbose)
        except SystemExit:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error('There appears to be a fault with '
                              'VM RAM being over-provisioned on one '
                              'or more nodes.')
            raise
        self.logger.info("Successfully Completed Hardware "
                         "Resources Healthcheck")

    def check_active_nodes(self, verbose=False):
        """
        Function Description:
        active_node_healthcheck checks the state of the node on the system
        :param verbose: Turn on verbose logging
        """
        try:
            services = Services(logger_name=self.logger_name)
            if services.verify_node_status(systemstate_filter=None,
                                           verbose=verbose):
                _state = 'PASSED'
            else:
                _state = 'FAILED'
            self.logger.info('Node Status: {0}'.format(_state))
        except IOError as error:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error('There appears to be a fault with '
                              'the VCS Cluster. ')
            raise SystemExit(error)

    def system_service_healthcheck(self, verbose=False):
        """
        Function Description:
        system_service_healthcheck checks the state of the services on each
        system in the deployment
        :param verbose: Turn on verbose logging
        """
        if self.is_healthcheck_excluded('system_service_healthcheck',
                                        'System Service Healthcheck'):
            return

        self.logger.info("Checking Services...")
        try:
            services = Services(logger_name=self.logger_name)
            services.verify_service_status(systemstate_filter=None,
                                           verbose=verbose)
            self.logger.info('Service Status: PASSED')
        except IOError as error:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error('There appears to be a fault with '
                              'one or more services. ')
            raise SystemExit(error)
        self.logger.info("Successfully Completed Service Healthcheck")

    def vcs_service_group_healthcheck(self, verbose=False):
        """
        Function Description:
        vcs_cluster_healthcheck checks the state of the service groups
        on the system
        :param verbose: Turn on verbose logging
        """
        if self.is_healthcheck_excluded('vcs_service_group_healthcheck',
                                        'VCS Service Group Healthcheck'):
            return

        self.logger.info("Beginning VCS Service Group Healthcheck")
        try:
            Vcs.verify_cluster_group_status(cluster_filter=None,
                                            group_filter=None,
                                            group_type=None,
                                            system_filter=None,
                                            groupstate_filter=None,
                                            systemstate_filter=None,
                                            verbose=verbose)
            self.logger.debug('ENM VCS Service Group Status: PASSED')
        except SystemExit:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error('There appears to be a fault with '
                              'the one or more VCS Service Groups. ')
            raise

        self.logger. \
            info("Successfully Completed VCS Service Group Healthcheck")

    def san_alert_healthcheck(self, verbose=False):
        """
        Function Description:
        Health check to check if there are any critical alerts
        on the SAN and to detect NAS server imbalance on unityxt SAN.

        :param verbose: Turn on verbose logging
        :type verbose: bool
        """
        if self.is_healthcheck_excluded('san_alert_healthcheck',
                                        'SAN alert Healthcheck'):
            return

        self.logger.info("Checking SAN Storage for alerts:")
        critical_alerts_found = False
        nas_imbalance_detected = False
        try:
            SanHealthChecks(verbose).san_critical_alert_healthcheck()
        except SystemExit:
            critical_alerts_found = True

        if not self.nas_type == 'unityxt':
            self.logger.debug('Skipping NAS server imbalance check. '
                              'Only applicable to ENM on Rackmount '
                              'Servers.')
        else:
            san_fault_check = SanFaultCheck()
            san_cleanup = SanCleanup()
            san_info = san_cleanup.get_san_info()
            for san in san_info:
                try:
                    san_fault_check.check_nas_servers(san_info, san)
                except Exception as error:
                    self.logger.error(error)
                    raise
                nas_fault = san_fault_check.nas_server_fault
                if nas_fault:
                    nas_imbalance_detected = True

        if critical_alerts_found or nas_imbalance_detected:
            self.logger.error('Healthcheck status: FAILED.')
            if critical_alerts_found:
                self.logger.error('There are critical alerts on the'
                                  ' SAN Storage.')
            if nas_imbalance_detected:
                self.logger.error('NAS server imbalance detected.')
            raise SystemExit(ExitCodes.ERROR)

        self.logger.info('Successfully Completed SAN alert '
                         'Healthcheck')

    def nas_healthcheck(self, verbose=False):
        """
        Function Description:
        nas_healthcheck checks whether NAS type is UnityXT or VA.
        If NAS type is VA nas_healthcheck checks the state of the
        NAS by running nasAudit.
        :param verbose: Turn on verbose logging
        """
        if self.is_healthcheck_excluded('nas_healthcheck',
                                        'NAS Healthcheck'):
            return

        self.logger.info('Beginning NAS Healthcheck')

        if self.nas_type == 'unityxt':
            # NAS is UnityXT
            self.logger.info('NAS Healthcheck unavailable on UnityXT')
            return

        # NAS is VA
        nas_info = self._get_nas_info()

        for nas in nas_info:
            nas_pwd = self._get_psw(nas_info[nas][2],
                                    nas_info[nas][1],
                                    sanitise=False)

            nas_console = NasConsole(nas_info[nas][0], nas_info[nas][1],
                                     nas_pwd)

            self.run_nas_audit(nas_console, nas, verbose)

    def mdt_healthcheck(self, verbose=False):
        """
        Function Description:
        Health check to verify if the disk space required
        for model deployment is available.
        :param verbose: turn on verbose logging
        """
        if self.is_healthcheck_excluded('mdt_healthcheck',
                                        'MDT Healthcheck'):
            return

        self.logger.info("Beginning of MDT Health Check")
        try:
            mdt_hc = MdtHealthCheck(verbose)
            if self.nas_type == 'veritas':
                mdt_hc.mdt_nfs_volume_healthcheck(True)
            else:
                mdt_hc.mdt_nfs_volume_healthcheck(False)
            self.logger.info('MDT Health Check status: PASSED.')
        except SystemExit:
            self.logger.error('MDT Health Check status: FAILED.\n'
                              'MDT Health Check error: Not enough '
                              'space in MDT NFS')
            raise
        except OSError as error:
            self.logger.error('MDT Health Check status: FAILED.\n'
                              'There is a fault with obtaining '
                              'filesystem usage information.\n'
                              'Filesystem error: {0}'.format(error))
            raise

        self.logger. \
            info("Successfully Completed MDT Health Check")

    def consul_healthcheck(self, verbose=False):
        """
        Function Description:
        Health check to verify consul is ok, only ran if consul is modelled.
        :param verbose: turn on verbose logging
        """
        if self.is_healthcheck_excluded('consul_healthcheck',
                                        'Consul Healthcheck'):
            return

        if self.rest.exists('/ms/services/consulserver'):
            self.logger.info("Beginning Consul Health Check")
            try:
                consul_hc = ConsulHC(verbose)
                consul_hc.healthcheck_consul()
                self.logger.info('Consul Health Check status: PASSED.')
            except SystemExit:
                self.logger.error('Consul Health Check status: FAILED.')
                raise SystemExit(ExitCodes.ERROR)
        else:
            self.logger.info('Consul not installed, Skipping Health Check.')

    def postgres_expiry_check(self):
        """
        Function Description:
        postgres_expiry_check checks the expiry of the postgres user
        password
        """
        if self.is_healthcheck_excluded('postgres_expiry_check',
                                'Postgres password expiry Healthcheck'):
            return

        self.logger.info("Beginning of postgres password expiry check")
        try:
            postgres_expiry = VerifyPostgresPasswordExpiry()
            postgres_expiry.check_expiry()
            self.logger.debug('Postgres password expiry check: PASSED')
        except (PostgresDBDoesNotExist, PostgresObjectDoesNotExist,
                PostgresQueryFailed, PostgresExpiryNotRetrieved,
                DateParserFailed) as error:
            self.logger.debug("Acceptable Postgres error. Health Check will "
                              "Continue. %s" % str(error))
        except PostgresPasswordHasExpired:
            if postgres_expiry.password_expiry:
                self.logger.error('PostgreSQL Admin User Password will '
                                  'expire on %s. Please \nreset '
                                  'PostgreSQL password expiry. Refer to '
                                  'ENM System Admin \nGuide for '
                                  'more details.' % str(
                    postgres_expiry.password_expiry))
            raise SystemExit(ExitCodes.ERROR)
        except SystemExit:
            self.logger.error('Healthcheck status: FAILED. ')
            raise

        self.logger. \
            info("Successfully Completed Postgres user password expiry check")

    def postgres_pre_uplift_check(self):
        """
        Check if Postgres needs a version uplift and /ericsson/postgres
        has enough space for uplift.
        """
        if self.is_healthcheck_excluded('postgres_pre_uplift_check',
                    'Postgres pre version uplift requirements Healthcheck'):
            return

        self.logger.info("Beginning of Postgres pre version "
                         "uplift requirements check")
        pg_service = PostgresService()
        pg_service.pg_pre_uplift_checks()
        self.logger.info("Check Status: OK")

    def neo4j_availability_check(self):
        """
        Check that Neo4j database instances are online and available to
        accept connections.
        """
        if self.is_healthcheck_excluded('neo4j_availability_check',
                                        'Neo4j availability Healthcheck'):
            return

        self.logger.info("Beginning of Neo4j availability check")
        if is_dps_using_neo4j():
            try:
                self.neo4j_cluster.health_check()
            except Neo4jHCNotSupportedException as err:
                self.logger.warning("Neo4j Health check status: UNDEFINED. "
                                    "Details: %s" % str(err))
            except Neo4jClusterOverviewException as err:
                self.logger.error("Neo4j Health check status: FAILED. "
                                  "Details: %s" % str(err))
                raise SystemExit()
            self.logger.info("Successfully Completed Neo4j availability check")
        else:
            self.logger.info("DPS provider is not using Neo4j. "
                             "Skipping Neo4j health check.")

    def neo4j_raft_index_lag_check(self):
        """
        Check if raft index lag between leader and follower too big;
        informal check at this stage, should not fail HC in either case
        """
        if self.is_healthcheck_excluded('neo4j_raft_index_lag_check',
                                        'Neo4j raft index lag Healthcheck'):
            return

        if self.neo4j_cluster.is_single_mode():
            self.logger.info("Skipping Neo4j raft index lag check "
                             "because the check is not applicable for "
                             "deployments with single instance Neo4j and "
                             "is only applicable to Extra-Large ENM "
                             "deployments  where Neo4j is deployed as a "
                             "Causal Cluster.")
            return

        self.logger.info("Beginning of raft index lag check")
        try:
            self.neo4j_cluster.raft_index_lag_check()
        except Neo4jHCNotSupportedException as err:
            self.logger.info(err)
            return
        except Neo4jClusterCriticalRaftIndexLagException as err:
            self.logger.warning("High raft index lag detected. "
                                "Critical ENM operations "
                                "may be delayed with a low risk of "
                                "data loss. Details: %s" % err)
            return
        self.logger.info("Completed raft index lag check. "
                         "No major lag detected.")

    def neo4j_uplift_creds_check(self, cfg):
        """ Validate database nodes credentials file required for
        major Neo4j version uplift
        """
        force = os.environ.get('FORCE_NEO4J_UPLIFT_CREDS_CHECK',
                               False) == 'true'
        try:
            need_uplift = self.neo4j_cluster.need_uplift()
            need_uplift_4x = force
            if cfg and not force:
                need_uplift_4x = self.neo4j_cluster.need_uplift_4x(cfg)
        except Neo4jClusterOverviewException as error:
            self.logger.error("Failed to determine if uplift required."
                              "Error: %s" % error)
            raise SystemExit()

        db_nodes_creds = DbNodesSshCredentials()
        if not need_uplift and not need_uplift_4x:
            self.logger.info("Skipping check. Neo4j server is up-to-date. "
                             "Version: %s" % self.neo4j_cluster.version)
            # Remove deployed passwords file if exists. This will clean up
            # after initial install.
            db_nodes_creds.remove_cred_file()
            return

        try:
            is_single_mode = self.neo4j_cluster.is_single_mode()
        except Neo4jClusterOverviewException as error:
            self.logger.error("Failed to get cluster mode."
                              "Error: %s" % error)
            raise SystemExit()

        if is_single_mode:
            self.logger.info("Neo4j server is running in single mode. "
                             "Pre uplift check is not required.")
            return

        try:
            if os.path.exists(FORCE_SSH_KEY_ACCESS_FLAG_PATH):
                self.logger.info('Validating credentials for SSH keys for '
                                 'Neo4j Uplift')
                db_nodes_creds.validate_credentials_for_key_access()
            else:
                db_nodes_creds.validate_credentials()
        except DbNodesSshCredsException as error:
            self.logger.error("Failed to validate database blades credentials."
                              " Error: %s" % error)
            raise SystemExit()
        except Exception as error:
            self.logger.error("Unexpected error encountered: %s" % error)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            # pylint: disable=C0103
            tb = '\n'.join(traceback.format_tb(exc_traceback))
            name = getattr(exc_type, "__name__", None)
            self.logger.error("%s: %s\nTraceback (most recent call last):"
                              "\n\n%s\n%s: %s" % (name, exc_value, tb, name,
                                                  exc_value))
            raise SystemExit()
        self.logger.info("Check PASSED. "
                         "Successfully validated db nodes SSH credentials.")

    def neo4j_uplift_space_check(self):
        """ Check if target Neo4j mount has enough space
        to run store migration """
        try:
            need_uplift = self.neo4j_cluster.need_uplift()
        except Neo4jClusterOverviewException as error:
            self.logger.error("Failed to determine if uplift required."
                              "Error: %s" % error)
            raise SystemExit()
        if not need_uplift:
            self.logger.info("Skipping check. Neo4j server is up-to-date. "
                             "Version: %s" % self.neo4j_cluster.version)
            return

        space_report = self.neo4j_cluster.get_pre_uplift_space_report()

        extension = space_report["extension"]
        if space_report['expansion_error']:
            extension = "%s (%s)" % (extension,
                                     space_report['expansion_error'])

        report_template = """
        Require store migration space: %s
        Available space on the mount: %s
        Potential free space total: %s
            Logs: %s
            Prunable transactions: %s
            Labels scan store file: %s
            Schema: %s
            Cluster state: %s
        Potential LUN extension size: %s
        Free space reserved (5%% from total mount size): %s
        """ % (space_report["required"], space_report["avail_space"],
               space_report["can_free"]["total"],
               space_report["can_free"]["logs"],
               space_report["can_free"]["transactions"],
               space_report["can_free"]["labels_scan"],
               space_report["can_free"]["schema"],
               space_report["can_free"]["cluster_state"],
               extension, space_report["reserved"])

        self.logger.info(report_template)

        if not space_report["enough_space"]:
            self.logger.error("Space check FAILED. Not enough space to run "
                              "Neo4j store migration")
            raise SystemExit()
        self.logger.info("Check PASSED. "
                         "Enough space to run Neo4j store migration.")

    def get_global_property(self, prop_name):
        """
        Get a global property value by name
        :param prop_name: Global property name
        :type prop_name: string
        :rtype: string
        """
        gp_vpath = os.path.join(os.sep,
                                'software',
                                'items',
                                'config_manager',
                                'global_properties') + \
                   os.sep + prop_name
        gprop_value = ''

        if self.rest.exists(gp_vpath):
            gprop = self.rest.get(gp_vpath, log=False)
            gprop_value = gprop.get('properties').get('value')

        return gprop_value

    def multipath_active_healthcheck(self, verbose=False):
        # pylint: disable=R0914
        """
        Function Description:
        check if all the paths to a disk in the DB nodes are active and
        mco facts are matching multipath configuration
        :param verbose: Turn on verbose logging
        """
        if self.is_healthcheck_excluded('multipath_active_healthcheck',
                            'multipath number of paths Healthcheck'):
            return

        if self.is_openstack_deployment():
            self.logger.info('Skipping multipath number of paths Healthcheck '
                             'on this environment type')
            return

        self.logger.info("Beginning of DMP paths check")
        deployment_type = LitpSanSnapshots().get_deployment_type()
        if not deployment_type:
            self.logger.info('No SAN provider found in the deployment.'
                             ' Skipping Healthcheck.')
            return

        enm_on_rack = False
        enm_deployment_type = self.get_global_property('enm_deployment_type')
        if enm_deployment_type and \
                re.match(r'.*ENM_On_Rack_Servers$', enm_deployment_type):
            enm_on_rack = True

        fc_switches_value = 'true'
        if enm_on_rack:
            fc_switches_value = self._get_fc_switches()
        mp_enabled_paths = MPpathsHealthCheck(verbose, deployment_type,
                                              fc_switches_value)
        enminst_agent = EnminstAgent()
        nodes = LitpSanSnapshots().get_nodes_with_luns()
        errors = False

        if nodes:
            self.logger.info("Found LUN disks on nodes {0}".format(
                ", ".join(nodes)
            ))
            result = enminst_agent.get_redundancy_level(hosts=list(nodes))
            for node, stdout in result.iteritems():
                mco_facts = enminst_agent.get_mco_fact_disk_list(
                    hosts=node)
                mp_config = enminst_agent.get_mp_bind_names_config(
                    hosts=node)
                node_has_errors = mp_enabled_paths.\
                    process_dmp_paths_node_output(
                        node, stdout, mp_config, mco_facts)
                if node_has_errors:
                    errors = True

        if errors:
            raise SystemExit(ExitCodes.ERROR)
        self.logger.info("Successfully completed DMP paths check")

    def puppet_enabled_healthcheck(self,
                               verbose=False):  # pylint: disable=W0613
        """
        Function Description:
        check Puppet is enabled on all nodes in the deployment.
        :param verbose: Turn on verbose logging
        """
        if self.is_healthcheck_excluded('puppet_enabled_healthcheck',
                                        'LITP Puppet enabled Healthcheck'):
            return

        self.logger.info("Beginning of LITP Puppet enabled check")
        puppet_agent = PuppetAgent()
        nodes_disabled = [k for (k, v) in puppet_agent.status().items()
                          if not v]
        if nodes_disabled:
            self.logger.error("Puppet is disabled on nodes {0}. Please run "
                "mco puppet enable and try again".format(
                ', '.join(nodes_disabled)))
            self.logger.error('Healthcheck status: FAILED.')
            raise SystemExit(ExitCodes.ERROR)
        self.logger.info("Successfully completed LITP Puppet enabled check")

    def run_nas_audit(self, nas_console, nas, verbose):
        """
        Function Description:
        Runs nas_audit on specified nas
        :param nas_console: NASConsole object
        :param nas: Info on NAS
        :param verbose: Turn on verbose logging
        """
        retcode, stdout, stderr, _ = nas_console.exec_basic_nas_command(
            self.NAS_AUDIT, as_master=False)

        report_location, failure_location = self._decode_nas_audit_output(
            stdout)

        if retcode and not report_location:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error('NAS Audit report failed to be generated')
            if failure_location:
                self.logger.info('{0} {1} on NAS node {2}'.format(
                    self.NAS_AUDIT_FAILURE, failure_location, nas))
            else:
                self._log_output_error(stdout, stderr)
            raise SystemExit(ExitCodes.ERROR)
        self._parse_nas_audit_response(retcode, stdout, stderr, nas_console,
                                       nas, report_location, verbose)

    def _parse_nas_audit_response(self,  # pylint: disable=R0913
                                  retcode, stdout, stderr, nas_console,
                                  nas, report_location, verbose):
        """
        Function Description:
        Parses result of running nas audit and reports healthcheck
        success/failure
        :param retcode: Return code from run of nasAudit
        :type retcode: int
        :param stdout: Stdout from run of nasAudit
        :type stdout: str[]
        :param stderr: Stderr from run of nasAudit
        :type stderr: str[]
        :param nas_console: NasConsole object
        :type nas_console: NasConsole
        :param nas: Info on NAS
        :type nas: dict
        :param report_location: Location of audit report from NAS audit output
        :type report_location: string
        :param verbose: Turn on verbose logging
        :type verbose: bool
        """
        if self._get_audit_result(retcode) == self.NAS_AUDIT_SUCCESS:
            if verbose:
                self._audit_check(nas, retcode, nas_console, report_location)
            self.logger.info('Successfully Completed NAS Healthcheck')
        elif self._get_audit_result(retcode) == self.NAS_AUDIT_WARNING:
            self._audit_check(nas, retcode, nas_console, report_location)
            self.logger.info('Successfully Completed NAS Healthcheck'
                             ' with warnings')
        elif self._get_audit_result(retcode) == self.NAS_AUDIT_ERROR:
            self.logger.error('Healthcheck status: FAILED. ')
            self._audit_check(nas, retcode, nas_console, report_location)
            raise SystemExit(ExitCodes.ERROR)
        else:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error('Unexpected return code running NAS Audit.')
            self._log_output_error(stdout, stderr)
            raise SystemExit(ExitCodes.ERROR)
        self.logger.debug('NAS HEALTHCHECK: PASSED')

    def _audit_check(self, nas, audit_retcode, nas_console, report_location):
        """
        Runs the nas_audit_check so can determine number of warnings
        and errors and output them
        :param nas: Info on NAS
        :param audit_retcode: Return code from NAS Audit check
        :param nas_console: NASConsole object
        :param report_location: Audit report determined from nasAudit stdout
        """
        retcode, stdout, _, _ = nas_console.exec_basic_nas_command(
            self.NAS_AUDIT_CHECK, as_master=False)

        log_msg = self._get_audit_check_msg(retcode, stdout, nas,
                                            report_location, audit_retcode)
        if self._get_audit_result(audit_retcode) == self.NAS_AUDIT_SUCCESS:
            self.logger.info(log_msg)
        elif self._get_audit_result(audit_retcode) == self.NAS_AUDIT_WARNING:
            self.logger.warning(log_msg)
        else:
            self.logger.error(log_msg)

    def _log_output_error(self, stdout, stderr):
        """
        Function Description:
        :param stdout: Array of stdout lines
        :param stderr: Array of stderr lines
        """
        for line in stdout:
            self.logger.error('STDOUT: {0}'.format(line))
        for line in stderr:
            self.logger.error('STDERR: {0}'.format(line))

    def enminst_healthcheck(self, verbose=False):
        # pylint: disable=R0915,R0912
        """
        Function Description:
        The enminst_healthcheck function allows the user to execute all
        functions from the enm_healthcheck script
        :param verbose: Turn on verbose logging
        """
        self.logger.info("Beginning ENM System Healthcheck")
        checks_failed = 0

        try:
            log_header(self.logger, "CHECKING VM RAM AND CPU USAGE PER NODE")
            self.hw_resources_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, 'CHECKING ALL NODES FOR STALE MOUNTS')
            self.stale_mount_healthcheck(verbose)
        except SystemExit:
            self.logger.error('Healthcheck status: FAILED.')
            checks_failed += 1
        except (OSError, McoAgentException):
            self.logger.error('Healthcheck status: FAILED.')
            self.logger.error('There appears to be a fault with '
                              'stale mounts healthcheck')
            checks_failed += 1

        try:
            log_header(self.logger, 'CHECKING MS, NAS AND PEER '
                                    'NODE FILESYSTEM USAGE')
            self.node_fs_healthcheck(verbose)
        except SystemExit:
            self.logger.error('Healthcheck status: FAILED.')
            checks_failed += 1
        except (OSError, NasConsoleException, McoAgentException):
            self.logger.error('Healthcheck status: FAILED.')
            self.logger.error('There appears to be a fault with '
                              'obtaining filesystem usage information')
            checks_failed += 1

        try:
            log_header(self.logger,
                       "CHECKING KEY LSB SERVICES IN THE DEPLOYMENT")
            self.system_service_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1
        except IOError:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING VCS CLUSTER SYSTEMS STATUS")
            self.vcs_cluster_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING VCS SERVICE GROUP STATUS")
            self.vcs_service_group_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING SAN STORAGEPOOL STATUS")
            self.storagepool_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING SAN FOR CRITICAL ALERTS")
            self.san_alert_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING NAS STATUS")
            self.nas_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING MDT STATUS")
            self.mdt_healthcheck(verbose)
        except (OSError, SystemExit):
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING CONSUL STATUS")
            self.consul_healthcheck(verbose)
        except SystemExit:
            self.logger.error("Healthcheck status: FAILED.")
            checks_failed += 1
        except (OSError, McoAgentException):
            self.logger.error("Healthcheck status: FAILED.")
            self.logger.error("There appears to be a fault with "
                              "obtaining consul status information")
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING HEARTBEAT STATUS")
            self.vcs_llt_heartbeat_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING POSTGRES EXPIRY STATUS")
            self.postgres_expiry_check()
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING POSTGRES PRE VERSION "
                                    "UPLIFT REQUIREMENTS")
            self.postgres_pre_uplift_check()
        except SystemExit:
            checks_failed += 1
        except (IOError, OSError, PostgresCredentialsException,
                PostgresServiceException) as error:
            self.logger.error(textwrap.fill(
                              "Postgres pre uplift check has failed with "
                              "internal errors. Details: %s" % error,
                              width=65))
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING PATHS TO DISKS ARE ACTIVE")
            self.multipath_active_healthcheck()
        except SystemExit:
            self.logger.error("Healthcheck status: FAILED.")
            checks_failed += 1
        except (OSError, McoAgentException):
            self.logger.error("Healthcheck status: FAILED.")
            self.logger.error("There appears to be a fault with "
                              "obtaining multipath configuration information")
            checks_failed += 1

        try:
            log_header(self.logger, "NEO4J CLUSTER AVAILABILITY CHECK")
            self.neo4j_availability_check()
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "NEO4J RAFT INDEX LAG CHECK")
            self.neo4j_raft_index_lag_check()
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING PUPPET ENABLED ON ALL NODES")
            self.puppet_enabled_healthcheck()
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING LVM.CONF FILTERS ARE CORRECT")
            self.lvm_conf_filter_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING LVs IN GRUB.CFG")
            self.grub_cfg_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        try:
            log_header(self.logger, "CHECKING NETWORK BOND IS IN A "
                                    "HEALTHY STATE")
            self.network_bond_healthcheck(verbose)
        except SystemExit:
            checks_failed += 1

        if checks_failed:
            log_header(self.logger, "ENM System Healthcheck errors! There "
                       "were {0} errors found.".format(checks_failed))
            raise SystemExit(ExitCodes.ERROR)
        else:
            log_header(self.logger, "Successfully Completed ENM System "
                                    "Healthcheck")

    def neo4j_uplift_healthcheck(self, cfg):
        """
        Function Description:
        The neo4j_uplift_healthcheck run healthchecks
        functions at Neo4j 4.0 Upgrade Uplift only and verify deployment
        is prepared for uplift
        """
        self.logger.info("Beginning Neo4j Uplift Healthcheck")
        checks_failed = False

        try:
            log_header(self.logger, "NEO4J PRE UPLIFT CREDENTIALS VALIDATION")
            self.neo4j_uplift_creds_check(cfg)
        except SystemExit:
            checks_failed = True

        try:
            log_header(self.logger, "NEO4J PRE UPLIFT MOUNT SPACE VALIDATION")
            self.neo4j_uplift_space_check()
        except Neo4jClusterOverviewException as err:
            self.logger.error("Failed to verify Neo4j space. Error: %s" % err)
            checks_failed = True
        except SystemExit:
            checks_failed = True

        if checks_failed:
            log_header(self.logger, "Neo4j Uplift Healthcheck errors!")
            raise SystemExit(ExitCodes.ERROR)
        else:
            log_header(self.logger, "Successfully Completed Neo4j Uplift "
                                    "Healthcheck")

    def node_fs_healthcheck(self, verbose=False):  # pylint: disable=R0914
        """
        Function Description:
        Check if peer nodes file systems do not exceed usage thresholds
        :param verbose:
        :type verbose: bool
        NAS fs checks are skipped if called by the perform_checks action of the
        RHEL7 upgrade script rh7_upgrade_enm.py
        """
        if self.is_healthcheck_excluded('node_fs_healthcheck',
                                        'Node Filesystem Healthcheck'):
            return

        self.logger.info('Checking if peer node filesystems do not exceed\n'
                         '{nas}\n'
                         '{db}% for versnt-neo4j, elasticsearch\n'
                         '{base}% for all other filesystems'
                         .format(
                              nas=self.usage_percentages[1] +
                              '% for NAS' if HealthCheck.NAS_RUN_FS_USAGE_CHECK
                                     else 'Skipping NAS',
                                 db=self.usage_percentages[2],
                                 base=self.usage_percentages[0]))

        try:
            nodes_fs_usage = self._get_node_fs_usage()
            node_fs_exceed_data, node_fs_exceed = \
                self._parse_exceed(nodes_fs_usage, verbose)

            if HealthCheck.NAS_RUN_FS_USAGE_CHECK:
                nas_fs_usage = self._get_nas_fs_usage()
                if self.nas_type == 'unityxt':
                    node_fs_exceed_data.update({'unity': nas_fs_usage})
                    fs_exceed_unity = self._parse_exceed_fs_unity(nas_fs_usage)
                    node_fs_exceed['unity'] = {}
                    if fs_exceed_unity:
                        node_fs_exceed['unity'] = \
                        {str((int(self.usage_percentages[1]))): \
                        fs_exceed_unity}
                else:
                    # NAS is not UnityXT
                    nodes_fs_usage.update(nas_fs_usage)
                    node_fs_exceed_data, node_fs_exceed = \
                        self._parse_exceed(nodes_fs_usage, verbose)

            errors_exceed = \
                self._get_fs_errors(node_fs_exceed)
        except (SystemExit, OSError, NasConsoleException, McoAgentException):
            raise

        if verbose:
            for node, fs_data in node_fs_exceed_data.items():
                report_tab_data(node.replace('_nas', ''), ['FileSystem',
                                                           'Use%'], fs_data)

        error_msg = ''

        if errors_exceed:
            error_msg = '\nFileystems exceed usage:\n{0}' \
                .format(errors_exceed)

        if error_msg:
            self.logger.error(error_msg)
            raise SystemExit(ExitCodes.ERROR)
        else:
            self.logger.info('Successfully Completed Node Filesystem '
                             'Healthcheck')

    def stale_mount_healthcheck(self, verbose=False):
        """
        Function Description:
        Check all nodes for stale mounts
        :param verbose:
        :type verbose: bool
        """
        if self.is_healthcheck_excluded('stale_mount_healthcheck',
                                        'Stale Mount Healthcheck'):
            return

        self.logger.info('Checking all nodes for stale mounts\n')

        try:
            stale_mounts = self._get_stale_mounts()
            stale_errors = self._get_stale_errors(stale_mounts, verbose)

        except (SystemExit, OSError, McoAgentException):
            raise

        error_msg = ''

        if stale_errors:
            error_msg = '\nStale Mounts:\n{0}' \
                .format(stale_errors)

        if error_msg:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error(error_msg)
            raise SystemExit(ExitCodes.ERROR)
        else:
            self.logger.info('Successfully Completed Stale Mounts '
                             'Healthcheck')

    @staticmethod
    def _get_stale_errors(node_stale_mounts, verbose=False):
        """
        Function Description:
        Get stale mounts errors string
        :return: string
        """
        stale_errors = ''

        if node_stale_mounts:
            for node, stale_mounts in node_stale_mounts.items():
                for mount in stale_mounts:
                    if mount:
                        if verbose:
                            stale_errors += '--------------------------\n'
                        stale_errors = '{0}Host \'{1}\' Stale Mounts: ' \
                                       '\'{2}\' \n'.format(stale_errors, node,
                                                           mount)

        return stale_errors

    def _get_fs_errors(self, node_fs_exceed):
        """
        Function Description:
        Get filesystem errors string
        :return: string
        """
        errors_exceed = ''

        if node_fs_exceed:
            for node, fs_data in node_fs_exceed.items():
                for usage in self.usage_percentages:
                    if fs_data.get(usage):
                        error_exceed = "Host '{0}' filesystem(s) " \
                                       "'{1}' exceed {2}% usage\n" \
                            .format(node.replace('_nas', ''),
                                    "', '".join(fs_data.get(usage)), usage)
                        if error_exceed not in errors_exceed:
                            errors_exceed += error_exceed
        return errors_exceed

    def _parse_exceed_fs_unity(self, nas_fs_usage):
        """
        Function Description:
        Parse fs that exceed thresholds on unity
        :param nodes_fs_usage:
        :param verbose:
        :return: list
        """
        filesystem_exceed = []
        for filesystem in nas_fs_usage:
            if filesystem['Use%']:
                usage = float(filesystem['Use%'][:-1])
                if usage > (int(self.usage_percentages[1])):
                    filesystem_exceed. \
                    append(filesystem['FileSystem'])

        return filesystem_exceed

    def _parse_exceed(self, nodes_fs_usage, verbose):
        """
        Function Description:
        Parse fs that exceed thresholds
        :param nodes_fs_usage:
        :param verbose:
        :return: tuple
        """
        node_fs_exceed_data = dict()
        node_fs_exceed = dict()
        for node, fs_data in nodes_fs_usage.items():
            fs_node = list()
            exceed_node = list()
            node_fs_exceed[node] = dict()
            for line in fs_data:
                s_line = line.split()
                if len(s_line) == 7 and s_line[1] not in self.fs_exclude:
                    if verbose:
                        if '_nas' not in node:
                            fs_node.append({'FileSystem': s_line[0],
                                            'Use%': s_line[5]})
                            node_fs_exceed_data[node] = fs_node
                        elif ('_nas' in node and
                              self.nas_pool_name.lower() in s_line[0].lower()):
                            fs_node.append({'FileSystem': s_line[0],
                                            'Use%': s_line[5]})
                            node_fs_exceed_data[node] = fs_node

                    node_fs_exceed = self._usage_conditions(node,
                                                            s_line,
                                                            node_fs_exceed,
                                                            exceed_node)

        return node_fs_exceed_data, node_fs_exceed

    def _usage_conditions(self, node, s_line, node_fs_exceed, exceed_node):
        """
        Function Description:
        Check filesystem usages against defined thresholds
        :param node:
        :param s_line:
        :param node_fs_exceed:
        :param exceed_node:
        :return: dict
        """
        usage_value = s_line[5].rstrip('%')

        if not usage_value.isdigit():
            error = 'File system {0} might be corrupted as' \
                    'there is no usage value reported by the df ' \
                    'command'.format(s_line[0])
            self.logger.exception(error)
            raise OSError(error)

        base_exceed = (not ('dbgeneric' in s_line[0] or
                            'versant' in s_line[0] or
                            'neo4j' in s_line[0] or
                            'elastic' in s_line[0]) and
                       ('_nas' not in node)) and \
                      int(usage_value) > int(self.usage_percentages[0])

        nas_exceed = ('_nas' in node and
                      self.nas_pool_name.lower() in s_line[0].lower()) and \
                     int(usage_value) > int(self.usage_percentages[1])

        dbgeneric_elastic_exceed = (('dbgeneric' in s_line[0] or
                                     'versant' in s_line[0] or
                                     'neo4j' in s_line[0] or
                                     'elastic' in s_line[0]) and
                                    ('_nas' not in node)) and \
                                   int(usage_value) > int(
            self.usage_percentages[2])

        if base_exceed:
            exceed_node.append(s_line[0])
            node_fs_exceed[node][str(self.usage_percentages[0])] \
                = exceed_node

        if nas_exceed:
            exceed_node.append(s_line[0])
            node_fs_exceed[node][str(self.usage_percentages[1])] \
                = exceed_node

        if dbgeneric_elastic_exceed:
            exceed_node.append(s_line[0])
            node_fs_exceed[node][str(self.usage_percentages[2])] \
                = exceed_node

        return node_fs_exceed

    def _get_nas_fs_usage(self):
        """
        Function Description:
        Return NAS disk usage
        :return: tuple
        """
        nas_info = self._get_nas_info()
        nas_fs_usage = dict()

        for nas in nas_info:
            nas_pwd = self._get_psw(nas_info[nas][2],
                                    nas_info[nas][1],
                                    sanitise=False)

            if self.nas_type == 'unityxt':
                nas_console = NasConsole(nas_info[nas][0], nas_info[nas][1],
                                             nas_pwd, nas_type="unityxt")

                nas_pool = self.rest.get_items_by_type(self.STORAGE_POOL_PATH,
                                                       'sfs-pool', [])
                self.nas_pool_name = nas_pool[0]['data']['properties']['name']
                fs_usage = nas_console.fs_usage(self.nas_pool_name)

                # Filtering filesystems from model
                fs_in_model = nas_info[nas][3]
                fs_in_model_filtered = []
                unity_fs_usage = []

                for fs_data in fs_in_model:
                    fs_filtered = re.search(r'' + \
                    re.escape(self.nas_pool_name) + r'.*', fs_data)
                    fs_in_model_filtered.append(fs_filtered.group())

                for fs_data in fs_usage:
                    if fs_data['FileSystem'] in fs_in_model_filtered:
                        unity_fs_usage.append(fs_data)

                return unity_fs_usage

            nas_console = NasConsole(nas_info[nas][0], nas_info[nas][1],
                                     nas_pwd)
            try:
                output = nas_console.exec_nas_command(self.NAS_CMD_USAGE,
                                                      as_master=False)
                if output:
                    nas_fs_usage[nas + '_nas'] = output
            except NasConsoleException as error:
                self.logger.exception(error)
                raise SystemExit(ExitCodes.ERROR)

        return nas_fs_usage

    def _get_nas_info(self):
        """
        Function Description:
        Obtain sfs service with a list of file system from the model
        :return: dict
        """
        self.logger.info('Obtaining NAS information from the LITP model')
        nas_info = {}
        nas_service = self.rest.get_items_by_type(self.STORAGE_PATH,
                                                  'sfs-service', [])

        nas_pool = self.rest.get_items_by_type(self.STORAGE_POOL_PATH,
                                               'sfs-pool', [])
        self.nas_pool_name = nas_pool[0]['data']['properties']['name']

        if not nas_service:
            self.logger.info('Cannot find NAS filesystems in Applied state')
        else:
            for item in nas_service:
                nas_info[item['data']['id']] = [
                    item['data']['properties']['management_ipv4'],
                    item['data']['properties']['user_name'],
                    item['data']['properties']['password_key'],
                    item['path']]

        for sfs_id in nas_info:
            fs_list = []
            nas_fs = self.rest.get_items_by_type(
                nas_info[sfs_id][-1], 'sfs-filesystem', [])
            if not nas_fs:
                self.logger.info('Cannot find NAS filesystems '
                                 'in Applied state')
            else:
                for item in nas_fs:
                    fs_list.append(item['data']['properties']['path'])
                nas_info[sfs_id][-1] = fs_list
        return nas_info

    def _get_fc_switches(self):
        """
        Function Description:
        Obtain fc_switches info from the model
        :return: fc_switchs_value string
        """
        self.logger.info('Obtaining fc_switches info from the LITP model')
        sans = self.rest.get_all_items_by_type(self.STORAGE_PATH,
                                                  'san-emc', [])
        try:
            fc_switches_value = sans[0]['data']['properties']['fc_switches']
        except KeyError:
            self.logger.error('Failed to find fc_switches information '
                              'in the LITP model')
            raise SystemExit()
        return fc_switches_value

    @staticmethod
    def _decode_nas_audit_output(stdout):
        """
        Function Description:
        Decodes the output from the audit report and return a tuple containing
        the report_location and failure_location
        :param stdout: NAS Audit stdout
        :return: tuple
        """
        failure_location = None
        report_location = None

        for line in stdout:
            if HealthCheck.NAS_AUDIT_REPORT_LINE in line:
                report_location = line.split(
                    HealthCheck.NAS_AUDIT_REPORT_LINE)[1]
            elif HealthCheck.NAS_AUDIT_FAILURE in line:
                failure_location = line.split(HealthCheck.NAS_AUDIT_FAILURE)[1]

        return report_location, failure_location

    @staticmethod
    def _get_audit_check_msg(retcode, stdout, nas, report_location,
                             audit_retcode):
        """
        Function Description:
        Returns message for logging with information from NAS audit check
        :param retcode: Return code from NAS audit check
        :param stdout: Stdout from NAS audit check
        :param nas: Info on NAS
        :param report_location: Location of audit report from NAS audit output
        :param audit_retcode: Return code from NAS Audit
        :return: string
        """
        num_err = None
        num_warn = None
        if retcode == 0:
            for line in stdout:
                if 'Errors: ' in line:
                    num_err = line.split('Errors: ')[1]
                elif 'Warnings: ' in line:
                    num_warn = line.split('Warnings: ')[1]
                elif 'Report: ' in line:
                    report_location = line.split('Report: ')[1]
            location_msg = HealthCheck.NAS_AUDIT_INFO_LOC_MSG.format(
                nas, report_location)
            log_msg = ('{0} Error(s) and {1} warning(s) detected on the NAS. '
                       '{2}').format(num_err, num_warn, location_msg)
        else:
            # If NAS Audit Check fails then use info from NAS Audit output
            # for report location, and from return code as to whether the
            # audit reported errors or warnings. BUT we will not know the
            # number of errors or warnings
            log_msg = HealthCheck.NAS_AUDIT_INFO_LOC_MSG.format(
                nas, report_location)
            if HealthCheck._get_audit_result(audit_retcode) == \
                    HealthCheck.NAS_AUDIT_WARNING:
                log_msg = ('Warnings were detected in NAS audit report. '
                           '{0}').format(log_msg)
            elif HealthCheck._get_audit_result(audit_retcode) == \
                    HealthCheck.NAS_AUDIT_ERROR:
                log_msg = ('Errors were detected in NAS audit report. '
                           '{0}').format(log_msg)
        return log_msg

    @staticmethod
    def _get_psw(psw_key, user, sanitise=True):
        """
        Function Description:
        Derive password string from key
        :return: tuple
        """
        decrypt = Decryptor()
        if sanitise:
            return sanitize(decrypt.get_password(psw_key, user))
        return decrypt.get_password(psw_key, user)

    @staticmethod
    def _get_node_fs_usage():
        """
        Function Description:
        For each node check the % usage for each filesystem
        :return: dict
        """
        enminst_agent = EnminstAgent()
        node_fs_usage = enminst_agent.get_fs_usage()

        for node, fs_use in node_fs_usage.items():
            node_fs_usage[node] = fs_use.split('\n')

        return node_fs_usage

    @staticmethod
    def _get_stale_mounts():
        """
        Function Description:
        For each node check for stale mounts
        :return: dict
        """
        enminst_agent = EnminstAgent()
        node_stale_mounts = enminst_agent.get_stale_mounts()

        for node, stale_mounts in node_stale_mounts.items():
            node_stale_mounts[node] = []
            for stale in stale_mounts.split('\n'):
                if stale:
                    node_stale_mounts[node].append(re.sub("[ `']", '', stale))

        return node_stale_mounts

    @staticmethod
    def _get_audit_result(audit_retcode):
        """
        Function Description:
        Returns whether return code from audit indicates success, warning or
        error
        :return: True if success, False otherwise
        """
        if audit_retcode == 0:
            return HealthCheck.NAS_AUDIT_SUCCESS
        elif audit_retcode == 3:
            return HealthCheck.NAS_AUDIT_WARNING
        elif audit_retcode == 1 or audit_retcode == 2:
            return HealthCheck.NAS_AUDIT_ERROR
        else:
            return HealthCheck.NAS_AUDIT_UNKNOWN

    def storagepool_healthcheck(self, verbose=False):
        """
        Function Description:
        san_pool_healthcheck checks the state of the SAN Storage Pool

        :param verbose: Turn on verbose logging
        :type verbose: bool
        """
        if self.is_healthcheck_excluded('storagepool_healthcheck',
                                        'SAN Storage Healthcheck'):
            return

        self.logger.info("Checking SAN Storage ...")
        try:
            SanHealthChecks(verbose).healthcheck_san()
            self.logger.debug('SAN Storage Status: PASSED')
        except SystemExit:
            self.logger.error('Healthcheck status: FAILED. ')
            self.logger.error('There appears to be a fault with '
                              'the SAN Storage.')
            raise
        self.logger.info("Successfully Completed SAN Storage Healthcheck")

    def ombs_backup_healthcheck(self, verbose=False):
        """
        Function Description:
        Health check to verify if there are available
        ombs backups, not older than a week and on the
        same release as the ENM
        :param verbose: turn on verbose logging
        """

        self.logger.info('OMBS Backup Verification:')
        try:
            ombs_hc = OmbsHealthCheck(verbose)
            ombs_hc.ombs_backup_healthcheck()
        except(IOError, OSError):
            self.logger.error('Problem Running ombs healthcheck')
            raise

    def run_fcaps_healthcheck(self, verbose):
        """
        Function Description:
        Health check to check FCAPS Summary per Node Types.
        Invokes common fcaps health check module
        :param verbose: turn on verbose logging
        """
        self.logger.info('Checking FCAPS Summary per Node Types:')
        fcaps_hc = FCAPSHealthCheck(logger_name=self.logger_name,
                                    verbose=verbose)
        fcaps_hc.fcaps_healthcheck()

    def fcaps_healthcheck(self, verbose=False):
        """
        Function Description:
        Health check to checking FCAPS Summary per Node Types
        :param verbose: turn on verbose logging
        """
        try:
            self.run_fcaps_healthcheck(verbose)
        except(Exception, SystemExit) as err:
            self.logger.error('Problem Running FCAPS healthcheck: {0}'
                              .format(err))
            raise SystemExit(ExitCodes.ERROR)

    def lvm_conf_filter_healthcheck(self, verbose=False):
        """
        Function Description:
        Health check to determine if the lvm.conf filter
        and global_filter settings are correct on Rackmount
        servers
        :param verbose: turn on verbose logging
        :return: None if env not Rackmount
        :raises: SystemExit if incorrect lvm.conf entry
        """
        if self.is_healthcheck_excluded('lvm_conf_filter_healthcheck',
                                        'lvm.conf filter Healthcheck'):
            return

        if not is_env_on_rack():
            self.logger.info('Skipping check. '
                             'Only applicable to ENM on Rackmount Servers')
            return

        self.logger.info('Beginning of lvm.conf filter check')
        try:
            self.report_lvm_conf_filter_settings(verbose)
            self.logger.info('lvm.conf filter healthcheck status: PASSED.')
        except SystemExit:
            self.logger.error('One or more nodes have incorrect '
                              'filter or global_filter in lvm.conf entries.\n'
                              'For SVC nodes the filter should be {0}.\n'
                              'For DB nodes the filter should be {0}, or '
                              '{1} after VRTSvxvm has been upgraded'.format(
                                        self.LVM_CONF_FILTER_EXPECTED_VALUE,
                                        self.LVM_CONF_GLOBAL_FILTER_ALT_VAL))
            self.logger.error('lvm.conf healthcheck status: FAILED.')
            raise
        self.logger.info("Successfully Completed lvm.conf Healthcheck")

    def report_lvm_conf_filter_settings(self, verbose):
        # pylint: disable=R0914
        """
        Function Description:
        Generates a report with the results of the lvm.conf healthcheck
        :param verbose: turn on verbose logging
        :raises: SystemExit if errors in filter and global
        filter report
        """

        enminst_agent = EnminstAgent()
        node_objects = self.get_nodes_in_clusters('db_cluster', 'svc_cluster')
        results = []
        report_headers = ['Node', 'filter Value', 'filter State', \
                          'global_filter Value', 'global_filter State']
        errors_exist = False

        is_openstack_env = self.is_openstack_deployment()

        for node in node_objects:
            hostname = node.get_property('hostname')
            filter_value = str(
                enminst_agent.get_lvm_conf_filter(hostname)
                ).strip()

            global_filter_value = str(
                enminst_agent.get_lvm_conf_global_filter(hostname)
                ).strip()

            filter_report = self.create_lvm_conf_entry_report(
                                        hostname, 'filter',
                                        filter_value, is_openstack_env)

            global_filter_report = self.create_lvm_conf_entry_report(
                                hostname, 'global_filter',
                                global_filter_value, is_openstack_env)

            if filter_report['filter State'] == 'ERROR' or \
                global_filter_report['global_filter State'] == 'ERROR':
                errors_exist = True

            lvm_conf_report = filter_report.copy()
            lvm_conf_report.update(global_filter_report)

            results.append(lvm_conf_report)
        if verbose:
            report_tab_data(None, report_headers, results)

        if errors_exist:
            raise SystemExit(ExitCodes.ERROR)

    def get_nodes_in_clusters(self, *cluster_names):
        """
        Function Description:
        Gets nodes for the clusters passed as parameters.
        If no clusters passed in, all nodes in a deployment
        are returned.
        :param: *cluster_names: The names of the clusters whose
        nodes should be retrieved.
        :return: A list of nodes in their LitpObject
        representation
        """
        all_clusters = self.rest.get_cluster_nodes()
        node_litp_objects = []

        for cluster in all_clusters:
            if not cluster_names or cluster in cluster_names:
                cluster_litp_nodes = all_clusters[cluster].values()
                node_litp_objects.extend(cluster_litp_nodes)
        return node_litp_objects

    def create_lvm_conf_entry_report(self,
                                node,
                                entry,
                                actual_value,
                                openstack_env=False):
        """
        Function Description:
        Creates a report for individual lvm.conf entries
        :param node: the node to check the lvm.conf on
        :param entry: the name of the entry in the lvm.conf
        :param actual_value: the actual_value in the lvm.conf
        :param openstack_env: boolean indicating if this is an OpenStack env
        :return: state_report dict
        """

        state_report = {'Node': node}
        state_report['{0} Value'.format(entry)] = actual_value

        # TORF-641282 VRTSvxvm RPM will update the LVM filter on DB nodes
        if (not openstack_env and
            (self.LVM_CONF_FILTER_EXPECTED_VALUE != actual_value and \
             self.LVM_CONF_GLOBAL_FILTER_ALT_VAL != actual_value)) or \
           (openstack_env and
            (self.LVM_CNF_GFLTR_OPNSTCK_VAL != actual_value and
             self.LVM_CNF_GFLTR_OPNSTCK_ALT_VAL != actual_value)):
            if actual_value == '':
                state_report['{0} Value'.format(entry)] = 'DOES NOT EXIST'
            state_report['{0} State'.format(entry)] = 'ERROR'
        else:
            state_report['{0} State'.format(entry)] = 'OK'
        return state_report

    def grub_cfg_healthcheck(self, verbose=False):
        """
        Function Description:
        Health check to check if LVs in the model are
        present in grub.cfg on Blade servers
        :param verbose: turn on verbose logging
        :return: None if env not Blade or check is excluded
        :raises: SystemExit if mismatch between LVs in the model and grub.cfg
        """
        table_headers = ['Cluster', 'Node', 'VG', 'Grub State',
                         'Missing LV', 'Extra LV']
        if self.is_healthcheck_excluded('grub_cfg_healthcheck',
                                        'grub.cfg Healthcheck'):
            return
        if is_env_on_rack():
            self.logger.info('Skipping grub.conf healthcheck. '
                             'NOT applicable to ENM on Rackmount Servers.')
            return

        self.logger.info('Beginning of checking LVs in the grub.conf')
        grub_conf_check = GrubConfCheck()
        detailed_report = grub_conf_check.report_lvs()
        check_failed = grub_conf_check.grub_lvs_check_failed
        if verbose:
            report_tab_data(None, table_headers, detailed_report)
        if not check_failed:
            self.logger.info('grub.cfg healthcheck status: PASSED.')
        else:
            self.logger.error('There is one or more mismatch between LVs in'
            ' the model and LVs in grub.cfg ')
            self.logger.error('LVs in the grub.conf healthcheck Status: '
                              'FAILED.')
            raise SystemExit(ExitCodes.ERROR)
        self.logger.info("Successfully Completed grub.cfg Healthcheck")

    def network_bond_healthcheck(self, verbose=False):
        """
        Health check to determine if the network bond
        is in a healthy state.
        :param verbose: Turn on verbose logging
        :return: None if env not Rackmount
        :raises: SystemExit if network bond MII status
        is down
        """

        if self.is_healthcheck_excluded('network_bond_healthcheck',
                                        'Network Bond Healthcheck'):
            return

        if not is_env_on_rack():
            self.logger.info('Skipping check. '
                            'Only applicable to ENM on Rackmount Servers')
            return

        self.logger.info('Beginning of network bond check')

        all_nodes = self.get_nodes_in_clusters()
        all_nodes.append(self.rest.get_lms())
        try:
            self.run_network_bond_healthcheck(all_nodes, verbose)
        except SystemExit:
            self.logger.error('The network bond is not in a healthy state. '
                              'MII status of every member on all nodes '
                              'should be up.')
            self.logger.error('Network bond check: FAILED.')
            raise SystemExit(ExitCodes.ERROR)
        self.logger.info('Successfully completed network bond check')

    def run_network_bond_healthcheck(self, nodes, verbose):
        # pylint: disable=R0914
        """
        Checks the bond file on the passed in nodes and
        generates a report displaying the health of the
        network bond on each node. Outputs warnings if
        the active and primary members are not equal or
        if the member speed is not 25000 Mbps.
        :param nodes: Nodes to check the bond health on
        :param verbose: Turn on verbose logging
        :raises: SystemExit if member MII status
        is down
        """
        enminst_agent = EnminstAgent()
        report_table = []
        errors_exist = False
        warn_msgs = set()

        is_openstack_env = self.is_openstack_deployment()

        for node in nodes:
            hostname = node.get_property('hostname')
            report_row = OrderedDict([('Node', hostname)])

            member_info = enminst_agent.get_active_and_prime_bond_mbr(
                hostname)

            interfaces_info = enminst_agent.get_bond_interface_info(hostname)

            member_info['Active Member State'] = self.check_active_bond_member(
                member_info)

            if member_info['Active Member State'] == 'WARNING':
                warn_msgs.add(('WARNING: The active member is not equal '
                               'to the primary member on one or more '
                               'nodes.'))

            report_row.update(member_info)

            for interface in interfaces_info:
                if interface['MII Status'] == 'down':
                    interface['Speed State'] = self.NETWORK_BOND_ERROR_MSG
                    errors_exist = True

                elif not is_openstack_env:

                    interface['Speed State'] = self.check_bond_interface_speed(
                        interface)

                    if interface['Speed State'] == 'WARNING':
                        warn_msgs.add(('WARNING: Not every member interface '
                                       'has a speed of 25000Mbps on one or '
                                       'more nodes.'))

                interf_headers = "{0} MII Status,{0} Speed,{0} Speed State" \
                    .format(interface['Member Interface']).split(',')

                interface_report = OrderedDict(zip(interf_headers,
                    interface.values()[1:]))

                report_row.update(interface_report)
            report_table.append(report_row)
        if verbose:
            report_tab_data(None, report_table[0].keys(), report_table)
        map(self.logger.warning, warn_msgs)
        if errors_exist:
            raise SystemExit

    def check_active_bond_member(self, member_info):
        """
        Checks if the active and primary bond members
        are equal.
        :param member_info: A dict with the primary and
        active member information.
        :returns: 'OK' if the primary and active
        members are equal, 'WARNING' otherwise
        """
        primary_member = member_info['Primary Member']
        active_member = member_info['Active Member']

        if primary_member != active_member:
            return self.NETWORK_BOND_WARNING_MSG
        return self.NETWORK_BOND_SUCCESS_MSG

    def check_bond_interface_speed(self, interface_info):
        """
        Checks if the speed of a bond interface is equal
        to 25000 Mbps
        :param interface_info: The parsed information of a member
        interface from the network bond file.
        :returns: 'OK' if the member interface speed is equal to
        25000 Mbps, 'WARNING' otherwise
        """
        expected_speed = 25000
        actual_speed = int(interface_info['Speed'].split(' ')[0])

        if actual_speed < expected_speed:
            return self.NETWORK_BOND_WARNING_MSG
        return self.NETWORK_BOND_SUCCESS_MSG


def configure_logging(verbose=False, logger_name='enmhealthcheck'):
    """
    Function Description:

    This function is used to initialise logging. If the verbose parameter is
    used the logging level is set to 'debug', otherwise default (info) is used.

    :param verbose: Turn on verbose logging
    :param logger_name: logger name to be used to log messages
    """
    global _LOGGER  # pylint: disable=W0603
    # get logger
    _LOGGER = init_enminst_logging(logger_name)
    try:
        log_level = get_env_var('LOG_LEVEL')
        if verbose:
            set_logging_level(_LOGGER, 'DEBUG')
        else:
            set_logging_level(_LOGGER, log_level)
    except KeyError:
        pass


def get_logger():
    """
    Get the logger instance
    :return:
    """
    global _LOGGER  # pylint: disable=W0602,W0603
    return _LOGGER


def interrupt_handler():
    """
    Function Description:
    Displays warning how to handle situation if the healthcheck was
    interrupted by user
    """
    get_logger().warning('CTRL-C: Healthcheck interrupted, re-run again to '
                         'ensure everything is completed.')


@keyboard_interruptable(callback=interrupt_handler)
def main(args):
    """
    Main function
    :param args: sys args
    :return:
    """
    exclude_function_list = [f for f in ACTION_FUNCTION_LIST if
                             f not in ["enminst_healthcheck",
                                       "ombs_backup_healthcheck",
                                       "fcaps_healthcheck"]]

    parser = argparse.ArgumentParser(prog="enm_healthcheck.sh",
                                     formatter_class=argparse.
                                     RawTextHelpFormatter, epilog=EPILOG_HC)
    parser.add_argument('--action', nargs='+', default=['enminst_healthcheck'],
                        choices=ACTION_FUNCTION_LIST, metavar='action',
                        help='Where action can be:\n'
                             '- {0}'.format('\n- '.join(ACTION_FUNCTION_LIST)))
    parser.add_argument('--exclude', nargs='+', default=[],
                        choices=exclude_function_list, metavar='exclude',
                        help='Where exclude can be:\n'
                            '- {0}'.format('\n- '.join(exclude_function_list)))
    parser.add_argument('--verbose', '-v',
                        action='store_true', default=False,
                        help="Enable debug logging")

    arguments = parser.parse_args(args)
    if not arguments.action:
        parser.print_help()
        raise SystemExit(2)

    verbose = arguments.verbose
    configure_logging(verbose)
    health_checks = HealthCheck()
    try:
        health_checks.pre_checks(verbose)
    except LitpException as litp_exc:
        if litp_exc.litp_in_maintenance_mode():
            msg = 'LITP is in maintenance mode. This may have been caused ' \
                  'by a previously failed upgrade. Please check what went ' \
                  'wrong, and when everything is ready run ' \
                  'litp update -p /litp/maintenance -o enabled=false ' \
                  'before running the script again'
            get_logger().error(msg)
            raise SystemExit(ExitCodes.ERROR)
    health_checks.set_exclude(arguments.exclude)
    for act in arguments.action:
        if act in ACTION_FUNCTION_LIST:
            funct = getattr(health_checks, act)
            args, _, _, _ = inspect.getargspec(funct)
            if 'verbose' in args:
                funct(verbose)
            else:
                funct()


if __name__ == '__main__':
    main(sys.argv[1:])
