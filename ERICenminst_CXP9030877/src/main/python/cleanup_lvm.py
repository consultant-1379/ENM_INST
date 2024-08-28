"""
Cleanup_lvm checks for LVM snapshots stored on the LMS and removes
them, if they exist.
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
# ********************************************************************
# Name    : cleanup_lvm.py
# Purpose : cleanup_lvm checks for LVM snapshots stored on the
#           system and removes them, if they exist.
# Date    : 24-03-2015
# Revision: A2
# ********************************************************************
from h_util.h_utils import exec_process
from h_logging.enminst_logger import init_enminst_logging
import logging


class CleanupLVMSnapshot(object):
    """
    Cleanup LVM snapshots on the MS.
    """
    def __init__(self):
        self.log = logging.getLogger('enminst')

    @staticmethod
    def snapshot_list():
        """
        Function Description:
        snapshot_list generates a list of LVM snapshots and returns all
        snaps on the MS.
        :param - none
        :type - none
        """
        command = ['/sbin/lvs', '--separator', ':', '--noheadings',
                   '--options', 'lv_attr,origin,lv_name,snap_percent,vg_name']
        results = exec_process(command)
        return results

    def delete_snapshots(self):
        """
        Function Description:
        delete_snapshots removes all snapped filesystems on the MS.
        :param - none
        :type - none
        """
        results = self.snapshot_list()
        for line in results.split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split(':')
            if parts[0].startswith('s'):
                dev_path = '/dev/'
                lv_name = parts[2]
                vg_name = parts[4]
                lvsnappath = dev_path + vg_name + '/' + lv_name
                lvremove = ['/sbin/lvremove', '--force', '--verbose',
                            lvsnappath]
                self.log.info('Removing LVM snapshot {0} {1}'
                              .format(vg_name, lv_name))
                try:
                    exec_process(lvremove)
                except IOError as error:
                    self.log.exception('An error occurred removing LVM '
                                       'snapshots')
                    raise SystemExit(error)
                else:
                    self.log.info('Successfully removed LVM snapshot {0}/{1}'.
                                  format(vg_name, lv_name))
            else:
                self.log.info('Current LVM is not a snapshot, skipping ...')


def main():
    """
    Main function
    """
    init_enminst_logging()
    clean = CleanupLVMSnapshot()
    clean.delete_snapshots()


if __name__ == '__main__':
    main()
