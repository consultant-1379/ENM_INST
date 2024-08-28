"""
Update version and history files with contents of imported ISO.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from os.path import exists
import json
import os
import shutil
import time
import re

from h_logging.enminst_logger import init_enminst_logging
from h_util import h_utils
from h_util.h_utils import ExitCodes, touch

HISTORY_ACTION_INSTALLED = 'Installed with'
HISTORY_ACTION_UPGRADED = 'Upgraded to'
HISTORY_ACTION_PADDING = max(len(HISTORY_ACTION_INSTALLED),
                             len(HISTORY_ACTION_UPGRADED))

HISTORY_ENTRY_FORMAT = '{0:<' + str(HISTORY_ACTION_PADDING) + '} {1} on {2}\n'
HISTORY_ACTION_TIME_FORMAT = "%d/%m/%Y at %H:%M:%S"

ENM_RELEASE_TEMP_VERSION_FILE = '/var/tmp/enm-version'

LOG = init_enminst_logging()

ENM_VERSION_FILENAME = "/etc/enm-version"
COPIED_ENM_VERSION_FILE = '/ericsson/tor/data/.enm-version'
ENM_HISTORY_FILENAME = "/etc/enm-history"
LITP_RELEASE_FILENAME = "/etc/litp-release"
LITP_HISTORY_FILENAME = "/etc/litp-history"


def handle_litp_version_history(
        mnt_point,
        version_file=LITP_RELEASE_FILENAME,
        history_file=LITP_HISTORY_FILENAME):
    """
    Handles import of ISO version file from the LITP ISO
    and updates LITP release version file and history of upgrades
    on the system
    :param mnt_point: path to mounted ISO
    :type mnt_point: str
    :param version_file: path to version / release file
    :type version_file: str
    :param history_file: path to history of version changes
    :type history_file: str
    """
    create_litp_history(history_file=history_file,
                        version_file=version_file)
    import_version(mnt_point, temp_version_file=version_file)
    update_history(history_file=history_file, version_file=version_file)


def import_enm_version(mnt_point,
                       temp_version_file=ENM_RELEASE_TEMP_VERSION_FILE):
    """
    Import ISO version file to ENM version specific temporary file
    :param mnt_point: path to mounted ISO
    :type mnt_point: str
    :param temp_version_file: path to temporary version file
    :type temp_version_file: str
    """
    import_version(mnt_point, temp_version_file)


def import_version(mnt_point, temp_version_file):
    """Copy .version file located in mount point to /var/tmp/enm-version.
    :param mnt_point: path to ISO mount point.
    :type mnt_point: str
    :param temp_version_file: path to temporary version file
    :type temp_version_file: str
    """

    version_input_file = os.path.join(mnt_point, '.version')
    if not exists(version_input_file):
        LOG.error('No version file found on the iso')
        raise SystemExit(ExitCodes.ERROR)

    try:
        shutil.copy(version_input_file, temp_version_file)
        LOG.debug("Created file {0}".format(temp_version_file))
    except IOError as ioe:
        LOG.exception("Unable to create {0} file: {1}"
                      .format(temp_version_file, str(ioe)))


def update_enm_version_and_history(
        temp_version_file=ENM_RELEASE_TEMP_VERSION_FILE,
        version_file=ENM_VERSION_FILENAME,
        history_file=ENM_HISTORY_FILENAME):
    """
    Updates ENM version file and removes the temp file
    used to store content of .version file from the iso.
    Updates history of changes.
    :param temp_version_file: path to temporary version file
    :type temp_version_file: str
    :param version_file: path to version / release file
    :type version_file: str
    :param history_file: path to history of version changes
    :type history_file: str
    """
    if not exists(temp_version_file):
        return
    try:
        shutil.copyfile(temp_version_file, version_file)
        update_copied_enm_version()
    except IOError as ioe:
        LOG.exception('Unable to update version ' + str(ioe))
        raise
    finally:
        try:
            os.remove(temp_version_file)
        except OSError:
            LOG.error("Unable to remove temporary version file: {0}"
                      .format(temp_version_file))
    update_history(history_file=history_file, version_file=version_file)


def update_copied_enm_version(
        version_file=ENM_VERSION_FILENAME,
        copied_file=COPIED_ENM_VERSION_FILE):
    """
    Copies ENM version file to /ericsson/tor/data/.enm-version
    :param version_file: path to version file
    :type version_file: str
    :param copied_file: path to copied version file
    :type copied_file: str
    """
    with open(version_file, 'r') as version_f:
        data = version_f.readline()
    str_data = re.search(r'.+(AOM.+)', data)
    if str_data:
        str_to_write = str_data.group(1).strip()
    else:
        error_message = 'Version file {0} is incorrect'.format(version_file)
        LOG.exception(error_message)
        raise KeyError(error_message)
    with open(copied_file, 'w') as enm_cp_file:
        enm_cp_file.write(str_to_write)


def update_history(history_file, version_file):
    """
    Creates / updates history file.
    Appends content of version file to history file adding time stamp.
    Adds information if version was used for Install or Upgrade
    :param history_file: path to history file
    :type history_file: str
    :param version_file: path to version file
    :type version_file: str
    """
    try:
        history_entry = create_history_entry(history_file, version_file)
        with open(history_file, 'a') as hfp:
            hfp.write(history_entry)

    except IOError as ioe:
        LOG.exception('Unable to history files! ' + str(ioe))
        raise


def create_history_entry(history_file, version_file):
    """
    Creates history entry based on history and version files.
    If history files is missing the entry will be created based
    on version file.
    Existence of history_file determines type of entry - Upgrade
    Not existence of histroy file determines type of entry - Install
    :param history_file: path to history file
    :type history_file: str
    :param version_file: path to version file
    :type version_file: str
    :return: history entry
    :rtype: str
    """
    if exists(history_file):
        action = HISTORY_ACTION_UPGRADED
    else:
        action = HISTORY_ACTION_INSTALLED
    with open(version_file, 'r') as vfp:
        version_info = vfp.readline().strip()
    file_time = h_utils.file_modification_date(version_file)
    cur_time = time.strftime(HISTORY_ACTION_TIME_FORMAT, file_time.timetuple())
    history_entry = HISTORY_ENTRY_FORMAT \
        .format(action, version_info, cur_time)
    return history_entry


def create_litp_history(version_file=LITP_RELEASE_FILENAME,
                        history_file=LITP_HISTORY_FILENAME):
    """
    Creates LITP history file
    :param history_file: path+filename of history file
    :type history_file: str
    :param version_file: path+filename of version file
    :type version_file: str
    """
    if exists(history_file):
        return
    if not exists(version_file):
        return
    update_history(history_file=history_file, version_file=version_file)


def update_rhel_version_and_history(input_json_file, version_file,
                                    history_file, create_empty_hist=False):
    """
    Create human readable RHEL patch set version file based on CXP number
    :param input_json_file: json file with the OS patches version
    :type input_json_file: str
    :param version_file: RHEL version filename
    :type version_file: str
    :param history_file: RHEL history filename
    :type history_file: str
    :param create_empty_hist: create empty dir flag
    :type create_empty_hist: bool

    """
    try:
        with open(input_json_file) as str_data:
            json_data = json.load(str_data)
        if 'R-state' in json_data:
            version_value = json_data["R-state"]
            version_name = ' R-state '
        elif 'gask_candidate' in json_data:
            version_value = json_data["gask_candidate"]
            version_name = ' Revision '
        else:
            LOG.exception('Missing patch information from release file!')
            raise ValueError

        str_to_write = 'RHEL version ' + json_data["rhel_version"] + \
                       ' CXP ' + json_data["cxp"] + \
                       version_name + version_value + '\n'
        update_version_files(version_file,
                             history_file,
                             str_to_write,
                             create_empty_hist)

    except IOError as ioe:
        LOG.exception('Unable to create RHEL version file! ' + str(ioe))
        raise
    except ValueError as v_error:
        LOG.exception('Unable to parse file {0}! '.format(input_json_file) +
                      str(v_error))
        raise


def update_version_files(version_file, history_file, str_to_write,
                         create_empty_hist):
    """
    Write version to and history information to files
    :param input_json_file: json file with the OS patches version
    :param version_file: str
    :param history_file: str
    :param str_to_write: str
    :param create_empty_hist: bool
    """
    with open(version_file, 'w') as rhel_version_file:
        if not exists(history_file) and create_empty_hist:
            touch(history_file)
        rhel_version_file.write(str_to_write)

    update_history(history_file, version_file)
