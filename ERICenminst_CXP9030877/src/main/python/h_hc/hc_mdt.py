"""
Healthcheck script for model deployment
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
# Name    : hc_mdt.py
# Purpose : The purpose of this script is to verify if the
# size available in volume "/etc/opt/ericsson/ERICmodeldeployment" is
# enough to execute model deployment during an ENM install or not.
# ********************************************************************
from h_util.h_utils import ExitCodes
from h_logging.enminst_logger import init_enminst_logging
from collections import namedtuple
import os


class MdtHealthCheck(object):
    """
    Class containing health check for model deployment
    """

    MDT_NAS_FS = '/etc/opt/ericsson/ERICmodeldeployment/'
    MODEL_FILES_FOR_DELETION_XML = MDT_NAS_FS \
                               + 'data/' \
                                 '/modelFilesAvailableForDeletion' \
                                 '/modelFilesAvailableForDeletion.xml'
    MDT_NFS_SAFETY_THRESHOLD = 0.5 * 1024 * 1024 * 1024

    def __init__(self, verbose=False):
        self.logger = init_enminst_logging(logger_name='enmhealthcheck')
        self.verbose = verbose

        # The overhead of deploying models in an ENM upgrade must be
        # considered when determining the MDT NFS volume health. The worst
        # case scenario is all the current models overwritten AND the extra
        # models being deployed by the upgrade TO path. This then effectively
        # equates to the projected size of models in 18 months time
        # (As of 15/02/2022), which is 6.9 for UnityXT and VA.

        # The overhead to deploy models during an ENM upgrade in a VA NAS
        # deployment.
        self.upgrade_overhead_for_va_bytes = 0.8 * 6.9 * pow(10, 9)

        # The overhead to deploy models during an ENM upgrade in a UnityXT
        # NAS deployment.
        self.upgrade_overhead_for_xt_bytes = 0.8 * 6.9 * pow(10, 9)

    def mdt_nfs_volume_healthcheck(self, is_nas_va):
        """
        Verifies that the size available in volume
        "/etc/opt/ericsson/ERICmodeldeployment"
        is enough to execute model deployment
        during an ENM install/upgrade or not.
        Note: Figures used in the function are defined in TORF-270979

        :param is_nas_va: indicates if the NAS is VA (True)
                          or UnityXT (False).
        """
        if not self.sfs_above_min_expected_size():
            self.logger.warn("Size of MDT NFS: %s is less than expected "
                             "22GB.", self.MDT_NAS_FS)
            return

        if is_nas_va:
            mdt_nfs_avail_space = self.get_mdt_nfs_avail_space(
                self.upgrade_overhead_for_va_bytes)
        else:
            mdt_nfs_avail_space = self.get_mdt_nfs_avail_space(
                self.upgrade_overhead_for_xt_bytes)

        if mdt_nfs_avail_space < self.MDT_NFS_SAFETY_THRESHOLD:
            raise SystemExit(ExitCodes.ERROR)

    def get_mdt_nfs_avail_space(self, upgrade_overhead):
        """
        Returns the size available in volume
        "/etc/opt/ericsson/ERICmodeldeployment"
        when supplied average model size and upgrade
        overhead is considered.

        :param upgrade_overhead: the predicted size of new and
        overridden models during a model deployment
        depending on the type of NAS
        :returns: the available space (in bytes) in the MDT NFS volume
        """

        # Size of model jars processed during model deployment
        model_jars_size = 2 * pow(10, 9)

        sfs_usage = self.dir_usage(self.MDT_NAS_FS)

        # Disk space required for model deployment. This space includes the
        # space required for new and overridden models being deployed and
        # the size of model jars processed during model deployment
        headroom_required = upgrade_overhead + model_jars_size

        return sfs_usage.free - headroom_required

    def sfs_above_min_expected_size(self):
        """
        Checks if the MDT NAS file system has a minimum
        expected size or not

        :return: True, if the size of MDT NAS file system is above
        the expected minimum, False otherwise.
        """
        sfs_usage = self.dir_usage(self.MDT_NAS_FS)
        min_expected_model_sfs_size = 22 * pow(2, 30)
        if sfs_usage.total >= min_expected_model_sfs_size:
            return True
        else:
            return False

    def dir_usage(self, path):
        """
        Returns disk usage statistics about the given path.

        :param path: the path of a directory.
        :returns: a named tuple with attributes 'total', 'used' and
        'free', which are the amount of total, used and free space, in bytes.
        """
        usage = namedtuple('usage', 'total used free')
        statvfs = os.statvfs(path)
        free = statvfs.f_bavail * statvfs.f_frsize
        total = statvfs.f_blocks * statvfs.f_frsize
        used = (statvfs.f_blocks - statvfs.f_bfree) * statvfs.f_frsize
        usage_info = usage(total, used, free)
        if self.verbose:
            self.logger.info('Total space: %s, Used Space: %s, '
                             'Free Space: %s', usage_info.total,
                             usage_info.used, usage_info.free)
        return usage_info
