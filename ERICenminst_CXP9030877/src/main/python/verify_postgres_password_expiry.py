# pylint: disable=E0012,W391,W391,W291
"""
Verify expiry of the postgres password
"""
##############################################################################
# COPYRIGHT Ericsson AB 2017
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################

import re
from datetime import datetime, date

from h_util.h_utils import exec_process, ExitCodes


class PostgresQueryFailed(Exception):
    """
    Exception to be raised in case a Postgres Query fails to execute
    """
    pass


class DateParserFailed(Exception):
    """
    Exception to be raised in case a Date fails to be Parsed
    """
    pass


class PostgresDBDoesNotExist(Exception):
    """
    Exception to be raised in case a Postgres Database does not exist
    """
    pass


class PostgresObjectDoesNotExist(Exception):
    """
    Exception to be raised in case a Postgres Object does not exist
    """
    pass


class PostgresExpiryNotRetrieved(Exception):
    """
    Exception to be raised in case a Postgres Expiry Date not retrieved
    """
    pass


class PostgresPasswordHasExpired(Exception):
    """
    Exception to be raised in case a Postgres Password has expired
    """
    pass


class VerifyPostgresPasswordExpiry(object):  # pylint: disable=W0612,R0903
    """
    Class to verify PostgreSQL user password expiry
    """
    global_props = '/ericsson/tor/data/global.properties'
    postgres_key = '/ericsson/tor/data/idenmgmt/postgresql01_passkey'
    openssl = '/usr/bin/openssl'
    psql = '/usr/bin/psql'
    pguser = "postgres"
    pghost = 'postgresql01'
    db_not_exist_regex = re.compile(r'FATAL\s*:\s+database\s+"\w+"\s+does'
                                    r'\s+not\s+exist')
    db_object_not_exist_regex = re.compile(r'relation\s+"\w+"\s+does\s+not'
                                         r'\s+exist')

    def __init__(self):
        """
        Initialize instance variables
        :return: None
        """
        self.encoded_password = ''
        self.decoded_password = ''
        self.password_expiry = ''
        self.current_date = date.today()

    def _get_encoded_password(self):
        """
        Gets the encoded password from the global properties
        :return: None
        """
        with open(self.global_props, 'r') as global_properties:
            for line in global_properties:
                if 'postgresql01_admin_password' in line:
                    self.encoded_password = \
                        line.split('postgresql01_admin_password=')[1].rstrip()

    def _decode_password(self):
        """
        Decodes the encoded password using the OpenSSL command
        :return: None
        """
        command = "echo {0} | {1} enc -a -d " \
                  "-aes-128-cbc -salt -kfile {2}".format(self.encoded_password,
                                                         self.openssl,
                                                         self.postgres_key)
        self.decoded_password = exec_process(command, use_shell=True).rstrip()

    def _set_expiry(self):
        """
        Set's the expiry value from the Postgres
        :return: None
        """
        command = "su - {0} -c \"PGPASSWORD={1} {2} -U {3} " \
                  "-h {4} -d admindb -qAt -c 'SELECT " \
                  "date_expiry FROM expiry_user WHERE " \
                  "current_password = true;'\"".format(self.pguser,
                                                       self.decoded_password,
                                                       self.psql,
                                                       self.pguser,
                                                       self.pghost)
        try:
            output = exec_process(command, use_shell=True).rstrip()
        except IOError as error:
            if self.db_not_exist_regex.search(str(error)):
                raise PostgresDBDoesNotExist("Admindb does not exist. %s "
                                             % str(error))
            if self.db_object_not_exist_regex.search(str(error)):
                raise PostgresObjectDoesNotExist("Admindb objects do not exist"
                                                 ". %s" % str(error))
            raise PostgresQueryFailed(
                'Failed to execute PostgreSQL Query %s: %s' % (
                    command, error))
        errors = []
        lines = output.splitlines()
        if not lines:
            raise PostgresExpiryNotRetrieved("Postgres Expiry Date not "
                                             "retrieved.")

        for line in lines:
            if line == 'infinity':
                self.password_expiry = 'infinity'
                break
            else:
                try:
                    self.password_expiry = datetime.strptime(line,
                                                             '%Y-%m-%d').date()
                    break
                except ValueError as error:
                    errors.append(error)

        if not self.password_expiry:
            raise DateParserFailed('Failed to Parse Date %s: %s' % (
                output, ', '.join(map(str, errors))))

    def _validate_expiry(self):
        """
        Calculates the expiry, if the expiry of the password
        is less then 2 days then the exception is raised
        :return: None
        """
        if self.password_expiry == 'infinity':
            return
        elif isinstance(self.password_expiry, date):
            days_remaining = self.password_expiry - self.current_date
            if days_remaining.days <= 2:
                raise PostgresPasswordHasExpired(ExitCodes.ERROR)

    def _check_connectivity(self):
        """
        Checks connectivity to postgresql in case of failure we return
        failed health check
        :return:
        """
        command = "su - {0} -c \"PGPASSWORD={1} {2} -U {3} -h {4} -qAt -c  " \
                  "'SELECT TRUE'\"".format(
            self.pguser,
            self.decoded_password,
            self.psql,
            self.pguser,
            self.pghost)
        try:
            exec_process(command, use_shell=True)
        except IOError as error:
            raise PostgresQueryFailed(
                'Failed to execute PostgreSQL Query %s: %s' % (
                    command, error))

    def check_expiry(self):
        """
        Method which implements the check expiry of the Postgres user
        :return: None
        """
        self._get_encoded_password()
        self._decode_password()
        self._check_connectivity()
        self._set_expiry()
        self._validate_expiry()
