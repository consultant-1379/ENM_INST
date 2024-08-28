"""
This module is used to clean up SAN snapshots. It removes snapshots
(if any exist) from a particular storage pool.
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************
#
# ********************************************************************
# Name    : cleanup_san.py
# Purpose : The purpose of this script is to remove SAN snapshots
# ********************************************************************
import logging
import sys
from datetime import datetime
from optparse import OptionParser
from os.path import basename

from defrag_nas_fs import NasLitpModel
from h_litp.litp_rest_client import LitpRestClient
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_util.h_utils import exec_process, Sed, get_env_var, wstderr

from sanapi import api_builder
from h_snapshots.snapshots_utils import SAN_TYPE_VNX

SK_SAN_SPA_IP = 'san_spaIP'
SK_SAN_SPB_IP = 'san_spbIP'
SK_SAN_USER = 'san_user'
SK_SAN_PASSWORD = 'san_password'
SK_SAN_POOOLNAME = 'san_poolName'
SK_SAN_LOGIN_SCOPE = 'san_loginScope'
SK_SAN_TYPE = 'san_type'

NAVI_RPM = 'NaviCLI-Linux-64-x86-en_US'


def format_msg(levelstr, msg):
    """
    Format a message
    :param levelstr: The level being logged at
    :type levelstr: str
    :param msg: The log message
    :type msg: str
    :return: Formatted log message including level and timestamp
    :rtype: str
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return '{0} {1:<5} {2:<20}: {3}'.format(timestamp, levelstr,
                                            "san_snap_cleanup", msg)


class SanSnapException(Exception):
    """
    Simple SAN SNAP exception
    """
    pass


class SanSnapCleanup(object):  # pylint: disable=too-many-instance-attributes
    """
    Class to cleanup the SAN snapshots
    """

    SP_PATH = '/infrastructure/storage/storage_providers'

    def __init__(self, sed):
        """
        :param sed: The SED handler
        """
        self._exclude_luns = None
        self.sed = sed
        self.logger = logging.getLogger('enminst')
        self.poolname = self.sed.get_value(SK_SAN_POOOLNAME)
        self.san_spa_ip = self.sed.get_value(SK_SAN_SPA_IP)
        # If Changes are made to the SED excel validation
        # SPB might not be present for Unity so will have to
        # refactor here TODO  # pylint: disable=fixme
        self.san_spb_ip = self.sed.get_value(SK_SAN_SPB_IP)
        self.san_user = self.sed.get_value(SK_SAN_USER)
        self.san_password = self.sed.get_value(SK_SAN_PASSWORD)
        self.san_login_scope = self.sed.get_value(SK_SAN_LOGIN_SCOPE)
        self.san_type = self.sed.get_value(SK_SAN_TYPE)
        self.rest = LitpRestClient()

        self.san_api = api_builder(self.san_type, self.logger)
        self.san_api.initialise((self.san_spa_ip, self.san_spb_ip),
                                 self.san_user,
                                 self.san_password,
                                 self.san_login_scope,
                                 True,
                                 False,
                                 esc_pwd=True)

    def get_lunids_for_snap(self, excludeluns=None):
        """
        Obtains a list of LUN ids for the storage pool
        :param excludeluns:
        :return: list of LunInfo Objects
        """
        if not excludeluns:
            excludeluns = self._exclude_luns
        self.logger.info("Building list of LUNs "
                         "in the storagepool"
                         " [{0}]".format(self.poolname))
        luns = self.san_api.get_luns("StoragePool", self.poolname)

        if excludeluns:
            lunlist = [l.id for l in luns if l.name not in excludeluns]
        else:
            lunlist = [l.id for l in luns]
        return lunlist

    def do_list_snapshots(self, lunlist, prnt=True):
        """
        Obtains the list of LUNs and their associated snapshots
        :param : lunlist
        :param : prnt
        :return : list of SnapInfo objects
        """
        self.logger.info("Getting snapshot(s) "
                         "for LUNS {0}".format(lunlist))
        snaplist = [s for s in self.san_api.get_snapshots()\
                    if s.resource_id in lunlist]
        if prnt:
            for snap in snaplist:
                self.logger.info("LUN [{0}] has snapshot(s) [{1}]"
                                 .format(snap.resource_name, snap.snap_name))
        return snaplist

    def do_destroy_snapshots(self, lunlist=None):
        """
        Deletes SAN snapshots on the LUNs
        :param : Lunlist list of luns
        """
        if not lunlist:
            lunlist = self.get_lunids_for_snap(self._exclude_luns)

        snaplist = self.do_list_snapshots(lunlist, True)
        if snaplist:
            self.logger.info("Destroying snapshot(s) on LUNs {0}"
                             .format(lunlist))
            for snap in snaplist:
                if "Destroying" not in snap.resource_id:
                    self.san_api.delete_snapshot(snap.snap_name)
                    self.logger.info("Destroying snapshot [{0}]"
                                     .format(snap.snap_name))
        else:
            self.logger.info("No snapshots found for LUNs in Pool"
                             " [{0}]".format(self.poolname))

    def do_check_vnx_snap_feature(self):
        """
        Check if VNX snap feature is installed
        :return : Boolean True or False
        """
        self.logger.info('Checking VNX Snapshot feature is installed')
        try:
            self.san_api.get_snapshots()
        except Exception:  # pylint: disable=W0703
            self.logger.info("Unable to locate VNX Snapshot feature")
            return False
        return True

    def check_navisec_feature(self):
        """
        Checks is NaviCLI feature is available for installation
        :return : Boolean True or False
        """
        self.logger.info('checking if navicli package is installed')
        try:
            exec_process(['yum', 'info', NAVI_RPM])
        except IOError:
            return False
        return True

    def install_navisec(self):
        """
        Installs Navisec
        """
        navicliavailable = self.check_navisec_feature()

        if navicliavailable:
            try:
                exec_process(['yum', 'install', NAVI_RPM, '-y'])
                self.logger.info('NaviCLI is now installed')
            except IOError as error:
                self.logger.error("Unable to install NaviCLI")
                raise SystemExit(error)
        else:
            raise SystemExit(
                    'NaviCLI package is not available for installation')

    def check_san_info(self):
        """
        Obtain SAN information from LITP model
        :return: Result of SAN Snapshot license check
        :rtype: Boolean
        """
        self.logger.info('Obtaining SAN information from the LITP model')
        items = self.rest.get_items_by_type(NasLitpModel.SP_PATH,
                                            'san-emc', [])
        if not items:
            msg = 'Cannot find [san-emc] ModelItem in Applied state'
            self.logger.info(msg)
            return False
        else:
            if self.san_type.upper().startswith(SAN_TYPE_VNX):
                self.install_navisec()
            return self.do_check_vnx_snap_feature()


def teardown_san(sedfile, logger):
    """
    Remove any existing SAN Snapshots that may reside on the LMS
    :param sedfile: SED file used for deployment
    :param logger: log file structure
    """
    logger.info("ENM INST cleanup_san.py")
    logger.info("SAN Snapshot cleanup starting")
    sed = Sed(sedfile)
    san = SanSnapCleanup(sed)
    san_exists = san.check_san_info()
    if san_exists:
        san.do_destroy_snapshots()
        logger.info("SAN Snapshot cleanup completed.")
    else:
        logger.info('Removal of SAN Snapshots not required. Continuing ...')


def main(args):
    """
    Main function.

    Loads a few OS environment variables, sets up logging can then calls
    the SAN Snapshot cleanup functions.
    :param args: sys args
    """
    try:
        logger = init_enminst_logging()
        log_level = get_env_var('LOG_LEVEL')
        set_logging_level(logger, log_level)
    except KeyError as keyerror:
        msg = "FATAL ERROR: '{0}' is unable to load the environment " \
              "{1} (started directly?), please correct before " \
              "restarting.".format(basename(__file__), str(keyerror))
        wstderr(msg)
        raise SystemExit(1)
    usage = ('usage: %prog '
             ' --sed <location to site engineering document>')
    arg_parser = OptionParser(usage)
    arg_parser.add_option('--sed', help='')
    (options, _) = arg_parser.parse_args(args)
    if not options.sed:
        arg_parser.print_help()
        raise SystemExit(2)
    teardown_san(options.sed, logger)


if __name__ == '__main__':
    main(sys.argv)
