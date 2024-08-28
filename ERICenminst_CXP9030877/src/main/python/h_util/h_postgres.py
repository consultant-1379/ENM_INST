"""
Postgres Service interface
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
# Name    : hc_postgres.py
# Purpose : Provides interface to a Postgres service
# ********************************************************************
import os

from h_logging.enminst_logger import init_enminst_logging
from h_puppet.mco_agents import McoAgentException, PostgresMcoAgent
from h_util.h_decorators import cached_property
from h_util.h_utils import exec_process
from h_vcs.vcs_cli import Vcs


class PostgresCredentialsException(Exception):
    """ Postgres Credentials Exception """


class PostgresCredentials(object):
    """ Class to obtain and hold postgres credentials """

    def __init__(self):
        self._username = 'postgres'
        self._tor_data = '/ericsson/tor/data'

    @property
    def username(self):
        """Postgres super user
        :return: postgres username
        :rtype: str
        """
        return self._username

    @cached_property()
    def password(self):
        """ Postgres password. It is cached for duration of
            program once decrypted
        :return: decrypted postgres password
        :rtype: str
        :raise: PostgresCredentialsException
        """
        return self._decrypt_password().strip()

    @property
    def _enc_pass(self):
        """Postgres encrypted password
        :return: encrypted postgres password read from a file
        :rtype: str
        :raise: PostgresCredentialsException
        """
        pass_prop = "postgresql01_admin_password"
        enc_pass = None
        global_props = os.path.join(self._tor_data, "global.properties")

        if not os.path.exists(global_props):
            raise PostgresCredentialsException("Failed to retrieve %s "
                                               "password. Could not find "
                                               "global properties file."
                                               % self.username)

        with open(global_props, 'r') as global_props:
            for line in global_props:
                if line.startswith(pass_prop):
                    enc_pass = line.split('=', 1)[1].strip()
                    break
        if not enc_pass:
            raise PostgresCredentialsException("Could not find encrypted "
                                               "%s password." % self.username)
        return enc_pass

    @property
    def _pg_passkey(self):
        """Postgres decrypting passkey
        :return: postgres passkey read from a file
        :rtype: str
        :raise: PostgresCredentialsException
        """
        passkey_path = os.path.join(self._tor_data,
                                    "idenmgmt/postgresql01_passkey")
        if not os.path.exists(passkey_path):
            raise PostgresCredentialsException("Failed to retrieve %s "
                                               "password. Could not find "
                                               "passkey file." % self.username)
        with open(passkey_path, 'r') as pass_key_file:
            return pass_key_file.readline().strip()

    def _decrypt_password(self):
        """ Decrypt postgres password
        :return: decrypted postgres password
        :rtype: str
        :raise: PostgresCredentialsException
        """
        try:
            cmd = "/bin/echo %s | /usr/bin/openssl enc -aes-128-cbc " \
                  "-d -a -k %s" % (self._enc_pass, self._pg_passkey)
            return exec_process(cmd, use_shell=True)
        except (OSError, IOError) as err:
            raise PostgresCredentialsException("Failed to decrypt %s password."
                                               " Details: %s" % (self.username,
                                                                 err))


class PostgresServiceException(Exception):
    """ Postgres Service Exception """


class PostgresService(object):
    """ Class representing an interface to a remote Postgres service """

    def __init__(self):
        """ Constructor """
        self.psql = '/usr/bin/psql'
        self.host = 'postgresql01'
        self.pg_mount = '/ericsson/postgres/data'
        self.credentials = PostgresCredentials()
        self.logger = init_enminst_logging()

    @cached_property(5)
    def _postgres_cluster_agent(self):  # pylint: disable=R0201
        """
        Cached Mco agent
        :return: PostgresAgent
        """
        postgres_sg_name = 'postgres_clustered_service'
        sg_status, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                                    postgres_sg_name,
                                                    verbose=False)

        postgres_hosts = [value[Vcs.H_SYSTEM] for value in sg_status
                          if value[Vcs.H_SERVICE_STATE] == 'ONLINE']

        if not postgres_hosts:
            raise PostgresServiceException("Postgres Service Group "
                                           "is offline.")

        return PostgresMcoAgent(postgres_hosts[0])

    def _execute_query(self, query, database="postgres"):
        """ Execute a Postgres query via shell.
        :return: result of an executed postgres query
        :rtype: str
        :raise: IOError, OSError
        """
        username = self.credentials.username
        password = self.credentials.password
        command = "su - %s -c \"PGPASSWORD=%s %s -h %s -d %s -U %s " \
                  "-qAt -c '%s'\"" % (username, password, self.psql, self.host,
                                      database, username, query)
        return exec_process(command, use_shell=True)

    @cached_property()
    def version(self):
        """ Current Postgres server version
        :rtype: float
        :raise: IOError, OSError
        """
        self.logger.info("Checking PostgreSQL version")
        version = self._execute_query("SHOW server_version;")
        maj_min = version.strip().split('\n')[-1].split(".")
        return float(".".join(maj_min[:2]))

    @cached_property()
    def perc_space_used(self):
        """ Percentage of mount space used represented in integer
        :rtype: float
        :raise: PostgresServiceException
        """
        try:
            result = self._postgres_cluster_agent.get_postgres_mnt_perc_used()
        except McoAgentException as mco_err:
            msg = ""
            if isinstance(mco_err[0], dict):
                error = mco_err[0]

                if error.get(self._postgres_cluster_agent.host):
                    raise PostgresServiceException(error.get(
                        self._postgres_cluster_agent.host))

                if error['retcode'] == 77:
                    msg = "%s on Postgres host %s. " \
                          "%s is not mounted." % \
                          (error['err'], self._postgres_cluster_agent.host,
                           self.pg_mount)
                    raise PostgresServiceException(msg)

                if error['retcode'] == 1:
                    msg = "Postgres host %s encountered internal error. " \
                          "Details: %s" % (self._postgres_cluster_agent.host,
                                           mco_err)
                    raise PostgresServiceException(msg)
            else:
                msg = "Unexpected error occurred while trying to get " \
                      "Postgres version. Details: %s " % mco_err
            raise PostgresServiceException(msg)

        return float(result.replace("%", ""))

    def is_contactable(self):
        """ Checks if Postgres service is contactable
        :rtype: bool
        :raise OSError
        """
        try:
            self._execute_query("SELECT TRUE;")
            return True
        except IOError:
            return False

    def need_uplift(self):
        """ Checks if the Postgres version is lower than desired version
        :rtype: bool
        :raise IOError, OSError
        """
        return self.version < 13

    def can_uplift(self):
        """ Checks if postgres mount has enough space to run version uplift
        :rtype: bool
        :raise IOError, OSError
        """
        return self.perc_space_used < 50

    def pg_pre_uplift_checks(self):
        """
        Check if Postgres needs a version uplift and /ericsson/postgres
        has enough space for uplift.
        """
        if not self.is_contactable():
            self.logger.info("Check Status: FAILED. Postgres service is "
                             "not contactable.")
            raise SystemExit()
        if not self.need_uplift():
            self.logger.info("PostgreSQL server version {0} and is up-to-date."
                             .format(self.version))
            return
        self.logger.info("PostgreSQL server version {0}. Version uplift "
                         "is required.".format(self.version))
        if not self.can_uplift():
            self.logger.error("Check Status: FAILED. Not enough space on "
                              "mount {0} for uplift to newer version. "
                              "Need at least 50% free, there is currently "
                              "{1}% free."
                              .format(self.pg_mount,
                                      100 - self.perc_space_used))
            raise SystemExit()
        self.logger.info("Mount %s has enough space to uplift Postgres "
                         "to newer version." % self.pg_mount)
