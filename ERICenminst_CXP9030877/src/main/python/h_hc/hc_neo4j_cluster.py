"""
Neo4j Cluster Overview
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2019
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************
#
# ********************************************************************
# Name    : hc_neo4j_cluster.py
# Purpose : The purpose of this script is to fetch Neo4j cluster data,
# check the state of Neo4j cluster formation and availability.
# ********************************************************************
import json
import os
import socket

import yaml
from paramiko import AuthenticationException
from yaml.parser import ParserError

from h_logging.enminst_logger import init_enminst_logging
from h_puppet.mco_agents import Neo4jClusterMcoAgent, McoAgentException, \
    Neo4jFilesystemMcoAgent
from h_util.h_collections import ExceptHandlingDict
from h_util.h_decorators import retry_if_fail, cached_property, cached_method
from h_util.h_ssh.client import SuIncorrectPassword, SshClient
from h_util.h_units import Size
from h_util.h_utils import Sed, ExitCodes, exec_process, is_env_on_rack

from h_vcs.vcs_cli import Vcs

from sanapi import api_builder

from distutils.version import LooseVersion
from h_xml.xml_utils import load_xml, xpath

ERICSSON_TOR_DATA = "/ericsson/tor/data"
FORCE_SSH_KEY_ACCESS_FLAG_PATH = os.path.join(ERICSSON_TOR_DATA,
                                              'pyu_force_ssh_key_access')


class Neo4jClusterOverviewException(Exception):
    """
    Neo4j Cluster Overview exception
    """


class Neo4jClusterHCException(Neo4jClusterOverviewException):
    """
    Neo4j Health Check exception
    """


class Neo4jClusterDownException(Neo4jClusterOverviewException):
    """
    Neo4j Cluster Down Exception
    """


class Neo4jServerSideException(Neo4jClusterOverviewException):
    """
    Generic Neo4j Server Side exception
    """


class InternalNeo4jErrorException(Neo4jServerSideException):
    """
    Internal Neo4j Server Side exception
    """


class Neo4jHCNotSupportedException(Neo4jServerSideException):
    """
    Neo4j Health Check is not supported exception
    """


class Neo4jClusterCriticalRaftIndexLagException(Exception):
    """
    Raised if raft index lag between a leader and followers
    is higher than 50k
    """


class Neo4jUpliftSpaceCheckException(Neo4jClusterOverviewException):
    """
    Raised if error encountered during uplift space check
    """


class Neo4jClusterOverview(object):
    """
    Class to fetch and store Neo4j cluster data.
    """

    MAX_RAFT_INDEX_LAG = 50000
    logger = init_enminst_logging()

    @cached_property(5)
    def _cluster_overview(self):
        """
        Private getter for cluster overview. Raises exception if overview
        is not initialized.
        :return: dictionary representing Neo4j cluster
        :rtype: dict
        """
        try:
            json_str = self._neo4j_cluster_agent.get_cluster_overview()
        except McoAgentException as mco_err:
            msg = ""
            if isinstance(mco_err[0], dict):
                error = mco_err[0]
                if error.get(self._neo4j_cluster_agent.host):
                    raise Neo4jClusterHCException(error.get(
                        self._neo4j_cluster_agent.host))

                if error['retcode'] == 77:
                    msg = "%s on Neo4j host %s. Neo4j HC is not supported." \
                          % (error['err'],
                             self._neo4j_cluster_agent.host)
                    raise Neo4jHCNotSupportedException(msg)

                if error['retcode'] == 1:
                    msg = "Neo4j host %s server encountered internal error. " \
                          "Details: %s" % (self._neo4j_cluster_agent.host,
                                           mco_err)
                    raise InternalNeo4jErrorException(msg)
                if error['retcode'] == 2:
                    msg = "Neo4j Cluster is fully down. Details: %s" % mco_err
                    raise Neo4jClusterDownException(msg)

            else:
                msg = "Unexpected error occurred while trying to fetch " \
                      "Neo4j cluster overview. Details: %s " % mco_err
            raise Neo4jServerSideException(msg)

        try:
            resp_dict = json.loads(json_str)
        except ValueError as val_err:
            val_err = "Failed to load json response. Details: %s" % val_err
            raise Neo4jClusterOverviewException(val_err)

        # Wrapping response dictionary into custom KeyError exception handling
        # dictionary. Clients of this class have to be aware of
        # Neo4jClusterOverviewException and handle that instead when calling
        # properties.
        return ExceptHandlingDict.get_dict(resp_dict,
                                           Neo4jClusterOverviewException)

    @cached_property(5)
    def _neo4j_cluster_agent(self):  # pylint: disable=R0201
        """
        Cached Mco agent
        :return: Neo4jClusterMcoAgent
        """
        dps_sg_name = 'sg_neo4j_clustered_service'
        sg_status, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                                    dps_sg_name,
                                                    verbose=False)

        neo4j_hosts = [value[Vcs.H_SYSTEM] for value in sg_status
                       if value[Vcs.H_SERVICE_STATE] == 'ONLINE']

        if not neo4j_hosts:
            raise Neo4jClusterDownException("All Neo4j Service Groups "
                                            "are offline.")

        return Neo4jClusterMcoAgent(neo4j_hosts[0])

    @property
    def instances(self):
        """
        Property storing list of Neo4j instances details
        :return: list of dictionaries representing each instance
        :rtype: list
        :raises Neo4jClusterOverviewException
        """
        return self._cluster_overview['instances']

    @property
    def version(self):
        """ Neo4j server version
        :return: str
        """
        return self.instances[0]["version"]

    @property
    def cluster_metadata(self):
        """
        Data about cluster
        :return: dictionary
        :raises Neo4jClusterOverviewException
        """
        return self._cluster_overview['cluster']

    def is_single_mode(self):
        """
        Check if Neo4j running in single or cluster mode
        :return: Boolean
        :raises Neo4jClusterOverviewException
        """
        return self.cluster_metadata['mode'] == 'single'

    @property
    def expected_cluster_size(self):
        """
        Property storing expected cluster size.
        :return: expected cluster size
        :rtype: int
        :raises Neo4jClusterOverviewException
        """
        default = 1 if self.is_single_mode() else 3

        return self.cluster_metadata.get('size', default)

    def is_cluster_fully_formed(self):
        """
        Checks if number of online instances matches expected cluster size.
        :return: bool
        :raises Neo4jClusterOverviewException
        """
        return len(self.instances) == self.expected_cluster_size

    @property
    def unavailable_instances(self):
        """
        Filters and returns a list of of each instance
        that is not available for receiving connections.
        :return: list
        :raises Neo4jClusterOverviewException
        """
        # if 'available' does not exist, try default 'cypher_available' key
        # fix for the bug: TORF-347530
        return [inst for inst in self.instances
                if not (inst.get('available')
                        if inst.get('available') is not None
                        else inst['cypher_available'])]

    @property
    def unavailable_instances_hosts(self):
        """
        Returns a list of hostnames + [aliases] of each instance
        that is not available for receiving connections.
        :return: list
        :raises Neo4jClusterOverviewException
        """
        unavailable = ["%s %s" % (inst["host"]["hostname"],
                                  inst["host"]["aliases"])
                       for inst in self.unavailable_instances]
        return unavailable

    @property
    def raft_index_lagging_instances(self):
        """ Returns a list of instances that are behind a leader
        :return: list
        """
        return [inst for inst in self.instances if inst["lag"] > \
                self.MAX_RAFT_INDEX_LAG]

    @property
    def raft_index_lagging_hosts(self):
        """ Returns a list of lagging hosts and it's lag in logable format
        :return: list
        """
        lagging = ["%s is %s raft indexes behind" %
                   (inst["host"]["hostname"], inst["lag"])
                   for inst in self.raft_index_lagging_instances]
        return lagging

    @retry_if_fail(retries=5, interval=30,
                   exception=Neo4jClusterHCException, stdout=True)
    def health_check(self):
        """
        Method to check if Neo4j cluster is healthy.
        Raises Neo4jClusterHCException exception if not healthy. Method is
        decorated with retry if fail mechanism and will try up to 5 times
        with interval of 30 seconds.
        :raises Neo4jClusterHCException
        """
        if not self.is_cluster_fully_formed():
            raise Neo4jClusterHCException("Neo4j Cluster is not well "
                                          "formed. Expected cluster "
                                          "size is %s, but actual size "
                                          "is %s." %
                                          (self.expected_cluster_size,
                                           len(self.instances)))

        if self.unavailable_instances:
            raise Neo4jClusterHCException("Neo4j is not available for "
                                          "connections on %s" % ', '.join(
                self.unavailable_instances_hosts))

    def raft_index_lag_check(self):
        """ Checks raft index lag between a leader and followers.
        If lag is over MAX_RAFT_INDEX_LAG, it raises exception.
        :raises Neo4jClusterCriticalRaftIndexLagException,
                Neo4jHCNotSupportedException
        :return: None
        """
        if self.instances[0].get("lag") is None:
            raise Neo4jHCNotSupportedException("Raft index lag check is not "
                                               "supported. Skipping.")
        if self.raft_index_lagging_instances:
            raise Neo4jClusterCriticalRaftIndexLagException("Neo4j have high "
             "raft index lag on %s" % ', '.join(self.raft_index_lagging_hosts))

    def need_uplift(self):
        """ Check if current major Neo4j version is lower than 4
        :return: bool
        """
        self.logger.info("Neo4j version: {0}".format(self.version))
        maj_min = self.version.split(".")
        return float(maj_min[0]) < 4

    def _get_neo4j_version_from_dd(self, cfg):
        """ Get Neo4j version configured in DD
        :param: DD xml provided for Upgrade
        :return: string
        """
        self.logger.info("_get_neo4j_version_from_dd")
        version = None
        root = load_xml(cfg.model_xml).getroot()
        try:
            version = xpath(root, \
                    'neo4j-config_entry[@id="server_version"]/value')[0].text
        except IndexError:
            self.logger.info("Get Neo4j version from DD: not found")
        return version

    def need_uplift_4x(self, cfg):
        """ Check if current  Neo4j version is lower than the one from DD
        :param: DD xml provided for Upgrade
        :return: bool
        """
        self.logger.info("need_uplift_4x Neo4j version: {0}".format(
            self.version))

        neo4j_dd_version = self._get_neo4j_version_from_dd(cfg)
        if not neo4j_dd_version:
            self.logger.info("Neo4j 4.x server_version parameter not in DD")
            return False

        # Get major versions to compare, i.e., 4.4 out of 4.4.11
        current_version_major = self.version.rsplit('.', 1)[0]
        dd_version_major = neo4j_dd_version.rsplit('.', 1)[0]
        self.logger.info("Current Neo4j version: {0}, major: {1}; "\
                        "From DD: {2}, major: {3}".format(
                        self.version, current_version_major,
                        neo4j_dd_version, dd_version_major))
        return LooseVersion(current_version_major) < \
               LooseVersion(dd_version_major)

    def is_neo4j_4_in_dd(self, cfg):
        """ Check if Neo4j 4.0 items is in provided DD
         Needed for Upgrade to find out if this is Uplift
        :return: bool
        """
        self.logger.info("is_neo4j_4_in_dd")
        neo4j_grep_cmd = "/bin/grep "\
                "\"<package_name>ERICneo4j4server_CXP9038634\" "\
                "{0}".format(cfg.model_xml)
        try:
            exec_process(neo4j_grep_cmd, use_shell=True).strip()
        except IOError as result:
            self.logger.info("Neo4j 4.0 rpm not provided in DD: {0}".format(
                result))
            return False
        self.logger.info("Neo4j 4.0 rpm is provided in DD.")
        return True

    def check_sed_credentials(self, cfg):  # pylint: disable=invalid-name
        """ Create dict with users credentials for 3 db nodes
         for Neo4j cluster; Passwords provided in SED file
        :return: dict
        """
        self.logger.info("Check SED file {0} for credentials.".format(
            cfg.sed_file))
        sed = Sed(cfg.sed_file)

        if is_env_on_rack():
            db_node_numbers = ['1', '2', '3']
        else:
            db_node_numbers = ['2', '3', '4']

        if int(self.version.split(".")[0]) < 4:
            # Properties names for nodes credentials in SED for Neo4j 3.X
            litp_admin_name_1 = 'DB_%s-LITPAdmin' % db_node_numbers[0]
            root_name_1 = 'DB_%s-Root' % db_node_numbers[0]
            litp_admin_name_2 = 'DB_%s-LITPAdmin' % db_node_numbers[1]
            root_name_2 = 'DB_%s-Root' % db_node_numbers[1]
            litp_admin_name_3 = 'DB_%s-LITPAdmin' % db_node_numbers[2]
            root_name_3 = 'DB_%s-Root' % db_node_numbers[2]
        else:
            # Properties names for nodes credentials in SED for Neo4j 4.X
            litp_admin_name_1 = 'db_node%s_litp-admin' % db_node_numbers[0]
            root_name_1 = 'db_node%s_root' % db_node_numbers[0]
            litp_admin_name_2 = 'db_node%s_litp-admin' % db_node_numbers[1]
            root_name_2 = 'db_node%s_root' % db_node_numbers[1]
            litp_admin_name_3 = 'db_node%s_litp-admin' % db_node_numbers[2]
            root_name_3 = 'db_node%s_root' % db_node_numbers[2]

        try:
            nodes_user_cred = {
                'db-%s' % db_node_numbers[0]:
                    {"litp-admin": sed.get_value(litp_admin_name_1,
                                                 error_if_not_set=True),
                     'root': sed.get_value(root_name_1,
                                           error_if_not_set=True)},
                'db-%s' % db_node_numbers[1]:
                    {"litp-admin": sed.get_value(litp_admin_name_2,
                                                 error_if_not_set=True),
                     'root': sed.get_value(root_name_2,
                                           error_if_not_set=True)},
                'db-%s' % db_node_numbers[2]:
                    {"litp-admin": sed.get_value(litp_admin_name_3,
                                                 error_if_not_set=True),
                     'root': sed.get_value(root_name_3,
                                           error_if_not_set=True)}}
        except (KeyError, ValueError) as error:
            self.logger.error("DB nodes credentials error: {0}".format(
                error))
            raise SystemExit(ExitCodes.ERROR)
        return nodes_user_cred

    @retry_if_fail(retries=2, interval=30,
            exception=Neo4jUpliftSpaceCheckException, stdout=True)
    def _get_fs_status(self, hostname, san_args):  # pylint: disable=R0201
        """ Makes MCO call to Neo4j database host to retrieve space status
        response = {
            "enough_space": enough_space,
            "avail_space": avail_space,
            "can_free": {
                "labels_scan": labelscanstore_size,
                "transactions": transactions_size,
                "logs": logs_size,
                "schema": schema_size,
                "total": space_can_free
            },
            "extension": extension_size,
            "required": required,
            "reserved": reserved_space,
        }
        :param hostname: database hostname
        :param san_args: san arguments to access LUN details
        :return: dict
        """
        fs_agent = Neo4jFilesystemMcoAgent()
        try:
            resp_dict = fs_agent.get_filesystem_status(hostname, san_args)
        except McoAgentException as mco_err:
            mco_err = "Failed to fetch Neo4j space status. " \
                      "Details: %s" % mco_err
            raise Neo4jUpliftSpaceCheckException(mco_err)

        return ExceptHandlingDict.get_dict(resp_dict,
                                           Neo4jUpliftSpaceCheckException)

    @property
    def _fs_status(self):
        """ Property that stores neo4j filesystem status in dict.
        Prepares sed parameters and neo4j host to fetch store data.
        For single instance cluster check ONLINE system.
        For Causal Cluster, check db-2
        :return: dict
        """
        # Determine target host and LUN name
        if self.is_single_mode():
            neo4j_host = self.instances[0]['host']['hostname']
        else:
            neo4j_host = [inst['host']['hostname'] for inst in self.instances
                          if 'db-2' in inst['host']['aliases']][0]

        neo4j_lun = Neo4jLun(self.is_single_mode())
        try:
            lun_size = neo4j_lun.size.num_bytes
        except Exception as error:  # pylint: disable=W0703
            raise Neo4jUpliftSpaceCheckException("Failed to get Neo4j lun "
                                                 "size using SAN API. "
                                                 "Details: %s" % error)
        return self._get_fs_status(neo4j_host,
                                   ["lun_size=%s" % lun_size])

    def get_pre_uplift_space_report(self):
        """ Prepares report for Neo4j pre uplift space check
        :return: dict
        """
        space_status = self._fs_status

        # convert size values from bytes to human readable format
        for key1, val1 in space_status.items():
            if isinstance(val1, dict):
                for key2, val2 in val1.items():
                    val1[key2] = Size("%sb" % val2)
                continue
            if key1 not in ["enough_space", "expansion_error"]:
                space_status[key1] = Size("%sb" % val1)

        return space_status


class Neo4jLun(object):  # pylint: disable=R0903
    """ Neo4j LUN information"""
    def __init__(self, neo4j_mode_single):
        """ Constructor """
        self.neo4j_mode_single = neo4j_mode_single

    @property
    def lun_name(self):
        """ Neo4j lun name based on Neo4j mode (single or cluster)
        :return: str
        """
        if self.neo4j_mode_single:
            return "neo4jlun"
        return "neo4j_2"

    @property
    def size(self):
        """ Neo4j lun Size object
        :return: Size
        """
        return Size("%smb" % self._lun_info.size)

    @cached_property()
    def _lun_info(self):
        """ Fetch Neo4j lun data using sanapi from litp package
        :return: LunInfo
        """
        san_args = self._get_san_details()
        sanapi = api_builder(san_args['san_type'])
        sanapi.initialise([san_args['san_spaIP']], san_args['san_user'],
                          san_args['san_pass'], 'global')

        lun = sanapi.get_lun(lun_name=san_args['lun_name'])
        return lun

    @cached_method()
    def _get_san_details(self):
        """ Fetch san details from SED file
        :return: dict
        """
        # Get last applied deployment SED file path
        try:
            last_applied_sed = Sed.get_last_applied_sed()
        except IOError as sed_err:
            sed_err = "Failed to get the last applied SED. Error: %s" % sed_err
            raise Neo4jUpliftSpaceCheckException(sed_err)
        except ValueError as sed_err:
            sed_err = "Failed to get sed parameter in upgrade command. " \
                      "Error: %s" % sed_err
            raise Neo4jUpliftSpaceCheckException(sed_err)

        sed = Sed(last_applied_sed)

        try:
            site_id = sed.get_value('san_siteId')
            san_args = {'san_user': sed.get_value('san_user'),
                        'san_pass': sed.get_value('san_password'),
                        'san_spaIP': sed.get_value('san_spaIP'),
                        'lun_name': 'LITP2_%s_%s' % (site_id, self.lun_name),
                        'san_type': sed.get_value('san_type')}
        except (KeyError, ValueError) as sed_err:
            sed_err = "Failed to get SAN values from the SED. " \
                      "Error: %s " % sed_err
            raise Neo4jUpliftSpaceCheckException(sed_err)

        return san_args


class DbNodesSshCredsException(Exception):
    """ Exception raised if credentials specified in yaml file are invalid """


class DbNodesSshCredentials(object):
    """ Class to parse database credentials file and access credentials.
    Class considered to be Singleton and will be constructed only once.
    """
    def __init__(self):
        self.creds_file = "/ericsson/tor/data/neo4j/dbcreds.yaml"
        self.litp_user = "litp-admin"
        self.root_user = "root"
        self.logger = init_enminst_logging()

    @cached_property()
    def _db_hosts(self):  # pylint: disable=R0201
        """ Db hosts where Neo4j cluster deployed
        :return: list
        """
        if is_env_on_rack():
            return ['db-1', 'db-2', 'db-3']
        else:
            return ['db-2', 'db-3', 'db-4']

    @cached_property()
    def _db_hostnames_map(self):
        """ Return actual hostnames
        :return: list
        """
        return dict([(d, socket.gethostbyaddr(d)[0]) for d in self._db_hosts])

    def remove_cred_file(self):
        """ Remove credentials file """
        if os.path.exists(self.creds_file):
            self.logger.info("Removing %s " % self.creds_file)
            os.remove(self.creds_file)

    @cached_property(5)
    def _credentials_dict(self):
        """ Parsed yaml file cached for 5 seconds
        :return: dict
        """
        if not os.path.exists(self.creds_file):
            raise DbNodesSshCredsException("Credentials file %s not found"
                                           % self.creds_file)

        with open(self.creds_file) as db_creds:
            try:
                parsed_yaml = yaml.load(db_creds)
            except ParserError as error:
                raise DbNodesSshCredsException("Failed to read credentials "
                                               "file %s. \n File syntax "
                                               "error details: %s" %
                                               (self.creds_file, error))

        hosts = sorted(self._db_hosts)
        keys = sorted(parsed_yaml.keys())
        if keys != hosts:
            raise DbNodesSshCredsException('Expected %s in "%s" but got %s' %
                                           (', '.join(hosts), self.creds_file,
                                            ', '.join(keys)))
        return ExceptHandlingDict.get_dict(parsed_yaml,
                                           DbNodesSshCredsException,
                                           msg="value not found in %s. "
                                               "\nMake sure file has correct "
                                               "values." % self.creds_file)

    def validate_credentials(self):
        """ Validate that database blades password file present, in correct
        format and passwords are valid.
        :return: None
        """
        errors = []
        required_users = [self.litp_user, self.root_user]
        for host in self._db_hosts:
            for required_user in required_users:
                if required_user not in self._credentials_dict[host]:
                    errors.append('Expected "%s" key in dbcreds.yaml file' %
                                  required_user)
        if errors:
            raise DbNodesSshCredsException('. '.join(errors))

        for host in self._db_hosts:
            litp_pass = self._credentials_dict[host][self.litp_user]
            client = SshClient(host, self.litp_user, litp_pass)

            try:
                client.connect()
            except AuthenticationException:
                raise DbNodesSshCredsException("Connection to %s failed. "
                                               "Invalid password provided "
                                               "for user '%s'"
                                               % (host, self.litp_user))
            else:
                root_pass = self._credentials_dict[host][self.root_user]
                try:
                    client.run("ls", su_user=self.root_user,
                               su_password=root_pass)
                except SuIncorrectPassword:
                    raise DbNodesSshCredsException("Connection to %s "
                                                   "failed. Invalid "
                                                   "password provided for "
                                                   "user '%s'"
                                                   % (host, self.root_user))
            finally:
                client.close()
            self.logger.info("validate_credentials done for host %s" % host)

    # pylint: disable=C0103,R0912,R0914
    def validate_credentials_for_key_access(self):
        """ Validate that database blades password file present, in correct
        format and passwords are valid.
        :return: None
        """
        errors = []
        agent = Neo4jFilesystemMcoAgent()
        key_filename = '/home/litp-admin/.ssh/id_rsa'
        creds = None
        try:
            creds = self._credentials_dict
        except DbNodesSshCredsException as err:
            self.logger.warning("dbcreds.yaml check failed: %s. Attempting via"
                                " key /home/litp-admin/.ssh/id_rsa" % str(err))
            for host, hostname in self._db_hostnames_map.items():
                has_key = agent.has_file(hostname, key_filename) == 'true'
                if not has_key:
                    self.logger.error('Tried to find key "%s" on %s but '
                                      'was not found' % (key_filename, host))
                    errors.append(host)
            if errors:
                # raise parent exception
                raise
        else:
            required_users = [self.litp_user]
            for host in self._db_hosts:
                for required_user in required_users:
                    if required_user not in creds[host]:
                        errors.append('Expected "%s" key in dbcreds.yaml for '
                                      'host %s' % (required_user, host))
                        continue
                    key_file = creds[host][required_user]
                    if not os.path.exists(key_file):
                        errors.append('Expected key file path in dbcreds.yaml '
                                      ' for host %s user %s' %
                                      (host, required_user))
            if errors:
                raise DbNodesSshCredsException('.\n '.join(errors))

        for host, hostname in self._db_hostnames_map.items():
            for to_host in self._db_hosts:
                if to_host == host:
                    continue
                if creds:
                    key_filename = creds[host][self.litp_user]
                try:
                    agent.check_ssh_connectivity(hostname, to_host,
                                                 self.litp_user,
                                                 key_filename=key_filename,
                                                 sudo=True)
                except McoAgentException as mco_err:
                    msg = "SSH connectivity check failed from %s to " \
                          "%s with key %s." % (host, to_host, key_filename)
                    self.logger.error(msg)
                    mco_err = "%s Details: %s" % (msg, mco_err.err)
                    errors.append(mco_err)
                else:
                    self.logger.info("SSH connection successfully established "
                                     "from host %s to %s" % (host, to_host))
        if errors:
            raise DbNodesSshCredsException('.\n '.join(errors))
