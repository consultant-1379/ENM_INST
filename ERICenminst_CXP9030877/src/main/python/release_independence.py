"""
The purpose of this script is to execute numerous functions seamlessly,
such as the repo backup, healthcheck, repo & model updates and executes
the LITP plan.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2016
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
# Name    : release_independence.py
# Purpose : The purpose of this script is to execute various functions
# automatically, such as the healthcheck, update repo and model
# directories, and runs the LITP plan.
##############################################################################
import os
import sys
import shutil
import tarfile
import argparse
from deployer import Deployer
from enm_healthcheck import HealthCheck
from h_litp.litp_utils import main_exceptions, LitpException
from h_util.h_utils import keyboard_interruptable, exec_process
from h_logging.enminst_logger import logging, log_header, init_enminst_logging

LOGGER = init_enminst_logging()
BACKUPDIR = '/software/release_independence_backup/'
TARFILE = BACKUPDIR + 'repodata_backup.tar'
CONFIG_MGT_PATH = '/ericsson/configuration_management/'
UPGRADE_MODEL_PATH = CONFIG_MGT_PATH + 'UpgradeIndependence/model_deploy/'
HTML_PATH = '/var/www/html/'
MODEL_DEPLOY_PATH = '/opt/ericsson/ERICmodeldeploymentclient/scripts/'
LITP_BIN = '/opt/ericsson/nms/litp/bin/'
STATUS_OK = 0
STATUS_ERROR = 1
STATUS_LOCK = 2


class ReleaseWrapper(object):
    """
    Class containing various functions to execute the release independently.
    """

    def __init__(self):
        """
        Initializes instances
        """
        super(ReleaseWrapper, self).__init__()
        self.model_script = MODEL_DEPLOY_PATH + \
                            'release_independence_model_deployment.sh'
        self.statusfile = UPGRADE_MODEL_PATH + 'releaseindependence.status'
        self.lockfile = UPGRADE_MODEL_PATH + 'releaseindependence.lock'
        self.litp_backup_script = LITP_BIN + 'litp_state_backup.sh'
        self.log = logging.getLogger('enminst')
        self.repo_list = self.repo_check()

    @staticmethod
    def repo_check():
        """
        Generate and return a list of repo directories
        :return : The full path of the required ENM repos
        :rtype : list
        """
        repo_name = ['ENM_services/', 'ENM_events/', 'ENM_asrstream/',
                     'ENM_ebsstream/', 'ENM_automation/']
        repo_check_list = []
        for repo in repo_name:
            repo_path = HTML_PATH + repo
            if not os.path.exists(repo_path):
                raise OSError('The repo: {0} is not accessible.'.
                              format(repo_path))
            repo_check_list.append(repo_path)
        return repo_check_list

    def pre_check(self):
        """
        Ensures filesystems are in place before executing anything
        """
        if not os.path.isfile(self.model_script):
            raise OSError('Error: {0} does not exist.'.
                          format(self.model_script))
        if not os.path.exists(UPGRADE_MODEL_PATH):
            raise OSError('Directory: {0} does not exist'.
                          format(UPGRADE_MODEL_PATH))
        if not os.path.isfile(self.litp_backup_script):
            raise OSError('Error: {0} does not exist.'.
                          format(self.litp_backup_script))
        if not os.path.isfile(self.lockfile):
            self.create_status_file(STATUS_LOCK)
        else:
            raise OSError('Release Independence appears to be ongoing. \n \
                 Lock file: {0} exists.'.format(self.lockfile))
        if os.path.exists(BACKUPDIR):
            self.cleanup()
        try:
            os.mkdir(BACKUPDIR)
            self.log.info('Creating backup directory')
        except OSError as err:
            raise OSError('Error: Unable to create directory', err)

    def litp_backup(self):
        """
        Creates a backup of litp and stores it
        as a compressed gzip file in a set location.
        """
        log_header(self.log, 'Executing litp backup')
        backup_litp_cmd = [self.litp_backup_script, BACKUPDIR]
        try:
            exec_process(backup_litp_cmd)
        except IOError as error:
            self.log.error('The following error occurred backing up litp: {0}'
                           .format(error))
            self.remove_lockfile()
            raise

    def repo_backup(self):
        """
        Creates a backup of the repo directories and stores it
        as a tar file in a set location.
        """
        log_header(self.log, 'Executing repo backup')
        repodata_path = []
        for repo in self.repo_list:
            repodata_path.append(repo + 'repodata')
        try:
            tar = tarfile.open(TARFILE, "w")
            for name in repodata_path:
                tar.add(name)
            tar.close()
            self.log.info('Repo backup completed successfully.')
        except SystemExit as error:
            self.log.error('The following error occurred backing up the repo'
                           .format(error))
            self.remove_lockfile()
            raise SystemExit(error)

    def exec_healthcheck(self):
        """
        Execute functions from enm_healthcheck
        """
        log_header(self.log, 'Executing Healthchecks')
        try:
            healthcheck = HealthCheck(logger_name='enminst')
            healthcheck.pre_checks()
            healthcheck.enminst_healthcheck()
            self.log.info('Healthchecks completed successfully.')
        except SystemExit as error:
            self.create_status_file(STATUS_ERROR)
            self.log.error('A failure occurred executing the healthcheck. \
                            Error: {0}'.format(error))
            self.remove_lockfile()
            raise

    def exec_mdt_check(self):
        """
        Execute MDT (model deployment) script
        """
        log_header(self.log, 'Executing MDT checks')
        try:
            self.log.info('Running MDT. \
                        This may take a few minutes to complete...')
            exec_process(self.model_script)
            self.log.info('MDT updates completed successfully.')
        except (IOError, OSError) as error:
            self.create_status_file(STATUS_ERROR)
            self.log.error('Error executing MDT script: {0}.'.
                           format(self.model_script))
            self.remove_lockfile()
            raise IOError(error)

    def exec_repo_update(self, action):
        """
        Execute the 'createrepo' function against a list of repos
        :param action: type of upgrade/restore we're carrying out
        :type: str
        """
        log_header(self.log, 'Executing repo update')
        for repo in self.repo_list:
            cmd = ('createrepo ' + repo)
            try:
                os.system(cmd)
                self.log.info('Repo: {0} update completed successfully'
                              .format(repo))
            except OSError as error:
                if action == 'model_update':
                    self.create_status_file(STATUS_ERROR)
                self.log.error('An error occurred updating the repo: {0}'
                               .format(repo))
                self.remove_lockfile()
                raise OSError(error)

    def exec_create_run_plan(self, action):
        """
        Execute the function to create, run and monitor the LITP plan
        :param action: type of upgrade/restore we're carrying out
        :type: str
        """
        try:
            deploy = Deployer()
            log_header(self.log, 'Executing create LITP plan.')
            deploy.create_plan()
            log_header(self.log, 'Executing run LITP plan.')
            deploy.run_plan()
            log_header(self.log, 'Executing monitor LITP plan.')
            deploy.wait_plan_complete()
            self.create_status_file(STATUS_OK)
            self.remove_lockfile()
        except LitpException as err:
            if action != 'error_recovery':
                self.create_status_file(STATUS_ERROR)
                self.remove_lockfile()
            raise LitpException(err)

    def create_status_file(self, arg):
        """
        Create two files. File one (statusfile) should include a
         success/failure message. File two (lockfile) will create
         an empty lock file.
        :param arg: integer based on success/failure
        :type integer
        """
        if arg == STATUS_OK:
            message = 'success'
            model_file = self.statusfile
        elif arg == STATUS_ERROR:
            message = 'failure'
            model_file = self.statusfile
        else:
            model_file = self.lockfile
        try:
            with open(model_file, "w") as _status:
                if model_file == self.statusfile:
                    _status.write('{0}\nstatus:{1}\n'.format(arg, message))
                    self.log.info("Status file updated.")
                elif model_file == self.lockfile:
                    self.log.info("Lock file created.")
        except IOError:
            self.log.error('Unable to create status file: {0}'.
                           format(self.statusfile))

    def remove_lockfile(self):
        """
        Removes lock file if it exists
        """
        if os.path.isfile(self.lockfile):
            try:
                os.remove(self.lockfile)
                self.log.info('Removed lock-file successfully.')
            except OSError as err:
                self.log.exception("An error occurred removing lock-file {0}."
                                   .format(self.lockfile))
                raise OSError(err)

    def cleanup(self):
        """
        Remove the newly created repo backup tar file
        """
        if os.path.exists(BACKUPDIR):
            try:
                shutil.rmtree(BACKUPDIR)
                self.log.info('Removed repo backup directory:{0}'
                              .format(BACKUPDIR))
            except OSError:
                self.log.warning("An error occurred cleaning up {0}."
                                 .format(BACKUPDIR))


def create_argument_parser():
    """
    Creates and configures parser to process command line arguments
    :return: argument parser instance
    :rtype ArgumentParser
    """
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--action', dest='action', required=True,
                            choices=['model_update', 'error_recovery',
                                     'rerun_plan'],
                            help='Release independence options are \
                            model_update, error_recovery or rerun_plan.')
    return arg_parser


def manage_release_actions(action):
    """
    manages various actions supplied to the user
    :param action: parameter passed from user
    :type str
    """
    indo = ReleaseWrapper()
    LOGGER.info("Beginning release independence {0}.".format(action))
    if action != "rerun_plan":
        indo.pre_check()
        if action == 'model_update':
            indo.exec_healthcheck()
        indo.repo_backup()
        indo.litp_backup()
        if action == 'model_update':
            indo.exec_mdt_check()
        indo.exec_repo_update(action)
    indo.exec_create_run_plan(action)
    LOGGER.info("Successfully completed release independence {0}."
                .format(action))


def interrupt_handler():
    """
    Callback for when CTRL-c is detected
    """
    LOGGER.warning('CTRL-C: Execution of script interrupted. \n\
        Please re-run again to ensure everything is completed.')


@keyboard_interruptable(callback=interrupt_handler)
def main(args):
    """
    Main function.
    Runs various functions to be executed throughout the wrapper script.
    :param args: action passed from user
    """
    arg_parser = create_argument_parser()
    options = arg_parser.parse_args(args)
    manage_release_actions(action=options.action)


if __name__ == '__main__':
    main_exceptions(main, sys.argv[1:])
