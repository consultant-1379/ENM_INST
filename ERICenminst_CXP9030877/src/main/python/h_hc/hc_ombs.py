"""
Healthcheck script for OMBS backup verification
"""
# ********************************************************************
# Ericsson LMI SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2018 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : hc_ombs.py
# Purpose : The purpose of this script is to check whether a good backup
# is present in the system, its on same release level as the ENM running,
# and its not older than 7days
# ********************************************************************

import re
import sys
import getpass
from datetime import datetime
from h_util.h_utils import create_ssh_client
from h_logging.enminst_logger import init_enminst_logging

BPCONF_FILE = '/usr/openv/netbackup/bp.conf'
ENM_VERSION_FILE = '/etc/enm-version'
CUTOFF_DAYS = 7


# pylint: disable=W0613
def _exception_handler(ex_type, ex_value, ex_traceback):
    """
    Exception handler for ENMsessionConnection.
    Suppresses stacktrace from enmscripting module if
    wrong login credentials provided.
    :param ex_type:
    :param ex_value:
    :param ex_traceback:
    """
    pass


class OmbsHealthCheck(object):  # pylint: disable=R0903
    """
    Class containing health check for OMBS Backup
    """
    def __init__(self, verbose=False):
        self.logger = init_enminst_logging(logger_name='enmhealthcheck')
        self.verbose = verbose
        sys.excepthook = _exception_handler

    def _get_localhost(self):
        """
        Get LMS backup hostname from BPCONF_FILE
        """
        try:
            with open(BPCONF_FILE, 'r') as bpconf_file:
                for line in bpconf_file:
                    hostline = line.split()
                    if hostline[0] == 'CLIENT_NAME':
                        return hostline[2]
        except(OSError, IOError):
            self.logger.error('Could not read file:' + BPCONF_FILE)
            raise
        return ''

    def _get_enm_version(self):
        """
        Get ENM version number from /etc/enm-version file
        """
        try:
            with open(ENM_VERSION_FILE, 'r') as ver_file:
                for line in ver_file:
                    verline = line.split()
                    if len(verline) > 1 and verline[0] == 'ENM':
                        return ' '.join(verline[:2])
        except (OSError, IOError):
            self.logger.error('Could not read file: ' + ENM_VERSION_FILE)
            raise
        return ''

    def _get_backup_date_and_ver(self, ombs_output):
        """
        Return the latest backup date and version from the OMBS output.
        :param ombs_output string returned from OMBS command
        """
        backupdate, backupver = None, ''
        date_match = re.search(r'(\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d)',
                               ombs_output)
        ver_match = re.search(r'(ENM[:space:]? \d\d.\d\d)', ombs_output)
        if date_match:
            backupdate = datetime.strptime(date_match.group(1),
                                           '%Y-%m-%d %H:%M:%S')
        else:
            self.logger.error("Last backup date cannot be fetched from OMBS, "
                              "please double check if thats the right OMBS IP")
        if ver_match:
            backupver = ver_match.group(1)
        else:
            self.logger.error("ENM Version cannot be fetched from OMBS, "
                              "please try manually.")

        return backupdate, backupver

    def ombs_backup_healthcheck(self):
        """
        Check OMBS backup version and date.
        Backup should be  less than 7 days old
        """
        ombs_output = self._ombs_login()
        self.logger.info(ombs_output)

        backupdate, backupver = self._get_backup_date_and_ver(ombs_output)
        if not backupdate or not backupver:
            sys.exit()

        enmver = self._get_enm_version()

        if backupver == enmver:
            if (datetime.now() - backupdate).days <= CUTOFF_DAYS:
                self.logger.info("Last successful OMBS backup was taken on"
                                 " {0}".format(
                                 backupdate.strftime("%Y-%m-%d")))
            else:
                self.logger.warning("Last successful OMBS backup was taken"
                                 " on {0} and its more than {1} days old."
                                 "\nPlease run a new OMBS backup.".format(
                                 backupdate.strftime("%Y-%m-%d"), CUTOFF_DAYS))
        else:
            self.logger.warning("Current release is {0}, but the OMBS "
                                "backup is on {1}."
                                "\nPlease run a new OMBS backup.".format(
                                enmver, backupver))

    def _ombs_login(self):
        """
        Log in and execute command on OMBS
        """
        ombs_ip = raw_input('Enter OMBS IP Address:')
        ombs_pwd = getpass.getpass('Enter OMBS root pass:')
        command = ('/ericsson/ombss_enm/bin/manage_backup_images.bsh'
                   ' -M {0} -s'.format(self._get_localhost()))

        try:
            ssh = create_ssh_client(host=ombs_ip, username='root',
                                    password=ombs_pwd)
            # pylint: disable=W0612
            _stdin, stdout, stderr = ssh.exec_command(command)
            retcode = stdout.channel.recv_exit_status()
            if retcode == 0:
                output = stdout.read()
            else:
                output = ''
                self.logger.error('OMBS server connection error : {0}'.format(
                                                                       stderr))
            ssh.close()
            return output
        except Exception as err:
            self.logger.error('OMBS server connection error : {0}'.format(err))
            raise
