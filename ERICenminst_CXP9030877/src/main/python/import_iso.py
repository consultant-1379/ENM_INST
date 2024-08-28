"""
This script uses litp import_iso command to import all repos and images
from ERICenm iso.
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
import fileinput
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from glob import glob
from os import listdir, makedirs
from os.path import join, exists, dirname, basename
from platform import node

from argparse import ArgumentParser

from h_litp.litp_maintenance import LitpMaintenance, JOB_STATE_FAILED, \
    JOB_STATE_DONE
from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import init_enminst_logging, \
    set_logging_level, log_header
from h_util.h_utils import exec_process, read_enminst_config, \
    keyboard_interruptable, ExitCodes, EnminstWorking
from import_iso_version import import_enm_version

MONITORING_SLEEP_SECONDS = 2
WAIT_AFTER_IMPORT_ISO_STARTED = 10

IMPORT_TIMEOUT = 7200
IMPORT_PROGRESS_RESOLUTION_IN_SECONDS = 15

ISO_CONTENTS_IMAGES = 'images'
ISO_CONTENTS_YUM = 'yum'

MAINTENANCE_READ_WAIT_SECONDS = 10

_IMPORT_PROCESS_ACTIVE = False
_LOGGER = None
_CONFIG = None
_ISO_IMPORT_LABEL = None


def get_config():
    """
    Get the current config
    :return:
    """
    global _CONFIG  # pylint: disable=W0602,W0603
    return _CONFIG


def read_config():
    """
    Get enminst_cfg
    :return:
    """
    global _CONFIG  # pylint: disable=W0603
    _CONFIG = read_enminst_config()


def get_log():
    """
    Get the logger instance
    :return:
    """
    global _LOGGER  # pylint: disable=W0602,W0603
    return _LOGGER


def configure_logging(verbose):
    """
    Configures logging
    :param verbose: Enable debug logging
    :return: logger instance
    :rtype logger
    """
    global _LOGGER  # pylint: disable=W0603
    _LOGGER = init_enminst_logging()
    if verbose:
        set_logging_level(_LOGGER, 'DEBUG')
    return _LOGGER


def is_importing():
    """
    Check if the import process was called.
    :return:
    """
    global _IMPORT_PROCESS_ACTIVE  # pylint: disable=W0602,W0603
    return _IMPORT_PROCESS_ACTIVE


def set_importing(importing):
    """
    Set a flag indicating the import process has been called or not
    :param importing: if `True` the import is now active, `False` otherwise
    :return:
    """
    global _IMPORT_PROCESS_ACTIVE  # pylint: disable=W0603
    _IMPORT_PROCESS_ACTIVE = importing


def get_import_iso_label():
    """
    Get the ISO id
    :return:
    """
    global _ISO_IMPORT_LABEL  # pylint: disable=W0602,W0603
    return _ISO_IMPORT_LABEL


def set_import_iso_label(label):
    """
    Set the ISO id
    :param label: ID for logging info
    :return:
    """
    global _ISO_IMPORT_LABEL  # pylint: disable=W0603
    _ISO_IMPORT_LABEL = label


def get_mountpoint(mid):
    """
    Get a mount point for the ISO import
    :param mid: An ID for the mount e.g. the current process ID
    :returns: A mount point path
    :rtype: str
    """
    return join(tempfile.gettempdir(), 'enminst_isoimport_{0}_{1}'
                .format(get_import_iso_label(), mid))


def create_mnt_dir():
    """
    Creates a temporary directory to mount the ERICenm iso
    :return: path to the created directory
    """
    mnt_point = get_mountpoint(os.getpid())
    try:
        if not os.path.isdir(mnt_point):
            os.makedirs(mnt_point)
    except Exception:
        raise

    return mnt_point


def mount(mnt_point, iso=None):
    """
    Mounts a device to mount point
    :param mnt_point: path to mount point
    :param iso: path to an iso file
    :return: Returns silently. Raises IOError on failure.
    """
    log_msg = 'Mount {mp} ISO: {iso}'\
        .format(mp=mnt_point, iso=get_import_iso_label())\
        if iso else 'Mount {mp}'.format(mp=mnt_point)

    error_msg = 'Failed to mount {mp} ISO: {iso}'\
                .format(mp=mnt_point, iso=get_import_iso_label())\
                if iso else 'Failed to mount {mp}'.format(mp=mnt_point)

    if os.path.ismount(mnt_point):
        get_log().debug('Mount point {0} already exists. Unmounting {0}'
                        .format(mnt_point))
        umount(mnt_point, force=True, ignore_errors=True)

    cmd = ['mount']
    if iso:
        cmd.extend(['-o', 'loop', iso, mnt_point])
    else:
        cmd.append(mnt_point)

    get_log().debug(log_msg)

    try:
        exec_process(cmd)
    except IOError:
        get_log().exception(error_msg)
        raise SystemExit(ExitCodes.ERROR)


def umount(mnt_point, iso=None, force=False, ignore_errors=False):
    """
    Un-mounts a device from a mount point
    :param mnt_point: path to a mount point
    :param iso: path to an iso file
    :param force: force unmount
    :param ignore_errors: ignore errors
    :return: Returns silently. Raises IOError on failure.
    """
    if not os.path.ismount(mnt_point):
        log_msg = 'Mount point {mp} is already Unmounted'.format(mp=mnt_point)
        get_log().debug(log_msg)
        return
    log_msg = 'Un-mount {mp} ISO: {iso}'\
        .format(mp=mnt_point, iso=get_import_iso_label())\
        if iso else 'Un-mount {mp}'.format(mp=mnt_point)

    error_msg = 'Failed to un-mount {mp} ISO: {iso}'\
                .format(mp=mnt_point, iso=get_import_iso_label())\
                if iso else 'Failed to un-mount {mp}'.format(mp=mnt_point)

    if force:
        cmd = ['umount', '-f', mnt_point]
    else:
        cmd = ['umount', mnt_point]

    get_log().debug(log_msg)

    try:
        exec_process(cmd)
    except IOError:
        if not ignore_errors:
            get_log().exception(error_msg)
            raise


def remount_fs(fs_remount_paths):
    """
    Unmount and mount the specified filesystems
    :param fs_remount_paths: list of filesystems to remount
    """
    for mnt_path in fs_remount_paths:
        if not os.path.ismount(mnt_path):
            msg = "Path {0} is not a mount path. Remount "\
                  "operation to ensure NFS "\
                  "share is available could fail.".format(mnt_path)
            get_log().warning(msg)
        else:
            umount(mnt_path)
        mount(mnt_path)

    get_log().info("Successfully remounted NFS share(s): {0}"
                   .format(', '.join(fs_remount_paths)))


def cleanup_mnt_points():
    """
    Clean up mount points - umount and remove directories
    :return:
    """
    for mountpath in glob(get_mountpoint('*')):
        umount(mountpath, ignore_errors=True)
        try:
            shutil.rmtree(mountpath)
        except OSError as ose:
            get_log().debug('Cant delete {0}: {1}'.format(mountpath,
                                                          str(ose)))


def litp_import_iso(mnt_point):
    """
    Runs 'litp import_iso' on the mount point and createrepo
    with a destination to /var/www/html/<found_directory_name>
    :param mnt_point: Location to import software from
    :return:
    """
    get_log().debug('Import {0} ISO using LITP import_iso command.'
                    .format(_ISO_IMPORT_LABEL))
    try:
        run_litp('import_iso {0}'.format(mnt_point))
    except Exception:
        error_msg = 'Failed to load {0} using ' \
                    'LITP import_iso ' \
                    'command.'.format(_ISO_IMPORT_LABEL)
        get_log().exception(error_msg)
        raise SystemExit(ExitCodes.ERROR)
    time.sleep(WAIT_AFTER_IMPORT_ISO_STARTED)

    monitor_import_progress(IMPORT_TIMEOUT)


def monitor_import_progress(max_wait_time):
    """
    Monitors import progress. Checks if LITP job state exists
    and if LITP state is different then Failed. Displays some statistics
    about duration of this process.
    :param max_wait_time:  maximum wait in seconds
    """
    max_wait_time_in_minutes = max_wait_time // 60

    start_time = datetime.now()

    last_elapsed_progress_time = -1

    litp = LitpRestClient()
    litp_maintenance = LitpMaintenance(client=litp)
    status = 'N/A'
    while True:
        try:
            status = litp_maintenance.get_status()

            if status == JOB_STATE_FAILED:
                get_log().error('Import ISO job failed.')
                raise SystemExit(ExitCodes.ERROR)

            if status == JOB_STATE_DONE and \
                    not litp_maintenance.is_maintenance_mode():
                return
        except ValueError:
            get_log().info('Waiting for response from LITP')
            time.sleep(MAINTENANCE_READ_WAIT_SECONDS)

        duration = datetime.now() - start_time
        if duration.seconds > max_wait_time:
            get_log().error(
                    'Timeout limit reached for LITP import_iso command.')
            import_timeout_handler()
            raise SystemExit(ExitCodes.TIMEOUT)

        elapsed_progress_time = \
            duration.seconds // IMPORT_PROGRESS_RESOLUTION_IN_SECONDS
        if elapsed_progress_time != last_elapsed_progress_time:
            last_elapsed_progress_time = elapsed_progress_time
            get_log().info(
                    'Import ISO is in progress. Current job state is - '
                    '{0}'.format(status))
            formatted_duration = str(duration).split('.')[0]
            remaining_time = max_wait_time_in_minutes - (
                duration.seconds // 60)
            get_log().info('Time elapsed [hh:mm:ss]: {0} . '
                           'Operation will timeout in about {1} minutes'
                           .format(formatted_duration, remaining_time))

        time.sleep(MONITORING_SLEEP_SECONDS)


def import_products(mnt_point):
    """
    Updates LMS hostname in LITP model with hostname of the host (was like
    that in old code. May not be required anymore). Imports the repos and
    images
    :param mnt_point: path to ISO mount point
    :return:
    """

    run_litp('update -p /ms -o hostname={0}'.format(node()))
    get_log().info('Create Yum Repos using LITP import_iso command.')
    litp_import_iso(mnt_point)


def update_images(mnt_point):
    """
    Updates the enm_working_parameters.cfg file with the copied .qcow2 images.
    :param mnt_point: path to ISO mount point.
    :return:
    """
    img_dest = join(mnt_point, 'images', 'ENM')
    img_list = listdir(img_dest)
    search_image_string = '_image'
    get_log().debug(
            'Updating file {0}'.format(
                    get_config()['enminst_working_parameters']))
    cfg_file = get_cfg_file()
    parent_dir = dirname(cfg_file)
    if not exists(parent_dir):
        makedirs(parent_dir)
    update_working_params(cfg_file, img_list)
    cleanup_redundant_images(cfg_file, search_image_string)


def get_cfg_file():
    """
    Gets enminst_working.cfg file path
    :returns: Returns the config file path
    :rtype: string
    """
    if not get_config():
        read_config()
    return get_config()['enminst_working_parameters']


def cleanup_redundant_images(cfg_file, search_image_string):
    """
    The function removes all redundant image key and value pairs,
    searches enminst config file for lines with "_image" and removes
    lines containing this string
    :param cfg_file: enminst_working.cfg
    :param search_image_string: "_image"
    """
    for line in fileinput.input(cfg_file, inplace=1):
        if search_image_string in line:
            line = line.replace(line, "")
        sys.stdout.write(line)


def create_image_var(img):
    """
    The function takes an image file name,
    ex. ERICrhel79lsbimage_CXP9041915-1.0.22.qcow2,
    strips the part after the '_', i.e. ERICrhel79lsbimage_CXP9041915
    to construct the variable name key 'ERICrhel79lsbimage' then adds
    the passed 'img' parameter as value.
    :param img: file name
    :returns: Returns a dict with ``ERICrhel79lsbimage``: ``img``
    :rtype: dict
    """
    key = img.split('_')[0]
    return {key: img}


def update_working_params(params_file, img_list):
    """
    Updates params_file with the .qcow2 images, assigning them to variables
    composed of the file name itself.
    :param params_file: path to config file
    :param img_list: list of file names
    :return:
    """
    images = [img for img in img_list if img.endswith('qcow2')]
    vars_images = map(create_image_var, images)
    cfg = EnminstWorking(params_file)
    for kvp in vars_images:
        for _key, _value in kvp.items():
            cfg.set_site_key(_key, _value)
    cfg.write()


def run_litp(cmd):
    """
    Executes 'litp cmd'
    :param cmd: parameters to the litp command
    :return: Standard output of the command
    """
    litp_cmd = 'litp {0}'.format(cmd)
    get_log().debug('Executing command: {0}'.format(litp_cmd))
    return exec_process(litp_cmd.split())


def get_iso_contents(mount_point):
    """
    Get the YUM and Image repos contained on the ISO being imported.

    :param mount_point: Directory the ISO is mounted on
    :returns: YUM and Image repos contained on the ISO
    :rtype: dict
    """
    iso_contents = {
        ISO_CONTENTS_IMAGES: {},
        ISO_CONTENTS_YUM: {}
    }

    images_path = join(mount_point, 'images')
    for image_proj in listdir(images_path):
        image_list = []
        proj_path = join(images_path, image_proj)
        for image in glob(join(proj_path, '*.qcow2')):
            image_list.append(basename(image))
        iso_contents[ISO_CONTENTS_IMAGES][image_proj] = image_list

    yums_path = join(mount_point, 'repos')
    for yum_proj in listdir(yums_path):
        if yum_proj == "3pp":
            rpm_list = []
            for image in glob(join(yums_path, yum_proj, '*.rpm')):
                rpm_list.append(basename(image))
            iso_contents[ISO_CONTENTS_YUM]["3pp_rhel7"] = rpm_list
        else:
            proj_path = join(yums_path, yum_proj)
            for proj_repo in listdir(proj_path):
                repo_name = '{0}_{1}_{2}'.format(yum_proj, proj_repo, "rhel7")
                rpm_list = []
                repo_path = join(proj_path, proj_repo)
                for image in glob(join(repo_path, '*.rpm')):
                    rpm_list.append(basename(image))
                iso_contents[ISO_CONTENTS_YUM][repo_name] = rpm_list

    return iso_contents


def interrupt_handler():
    """
    Displays warning how to handle situation if import was interrupted by user
    """
    get_log().warning('CTRL-C: Interrupting iso import')
    if is_importing():
        get_log().warning(
                'The import monitor was interrupted but the import '
                'process will continue in the backgroud. LITP will '
                'be in maintenance mode until the import is complete'
                'You can check the status of operation using command\n'
                'litp show -p /litp/maintenance\n'
                'CAUTION - If import process has failed LITP will stay'
                'in maintenance mode.')


def import_rpm(rpm, repo):
    """
    Import rpm into repo
    :param rpm: path to rpm
    :param repo: path to repo
    :return:
    """
    run_litp('import {0} {1}'.format(rpm, repo))


def import_timeout_handler():
    """
    Displays warning how to handle situation if import has timeouted
    """
    if is_importing():
        get_log().warning(
                'The import monitor has timeouted but the import '
                'process will continue in the backgroud. LITP will '
                'be in maintenance mode until the import is complete'
                'You can check the status of operation using command\n'
                'litp show -p /litp/maintenance\n'
                'CAUTION - If import process has failed LITP will stay'
                'in maintenance mode.')


@keyboard_interruptable(callback=interrupt_handler)
def main_flow(iso, verbose=False, iso_label='ENM'):
    """
    Main flow of the script. Mounts the iso, imports rpms and KVM
    images and unmounts the iso.
    :param iso: path to iso file
    :param verbose: if True enable verbose logging
    :param iso_label: label used for logging purposes
    """

    configure_logging(verbose)
    set_import_iso_label(iso_label)
    read_config()

    log_header(get_log(), 'Import {0} ISO'.format(_ISO_IMPORT_LABEL))
    check_litp_mode()
    # Remove old mounts e.g. the previous import got killed for some reason?
    cleanup_mnt_points()
    mnt_point = create_mnt_dir()
    # Flag used in the interrupt_handler
    set_importing(False)
    # Flag used to determine if a cleanup should be called
    do_cleanup = True
    try:
        mount(mnt_point, iso)
        iso_contents = get_iso_contents(mnt_point)
        import_enm_version(mnt_point)
        set_importing(True)
        import_products(mnt_point)
        set_importing(False)
        update_images(mnt_point)
        return iso_contents
    except KeyboardInterrupt:
        if is_importing():
            # Dont unmount/delete the dir as the import is still
            # ongoing in the background, we were only monitoring it...
            do_cleanup = False
        raise
    finally:
        if do_cleanup:
            cleanup_mnt_points()


def check_litp_mode():
    """
    Check if LITP is in maintenance mode.
    :return:
    """
    litp = LitpRestClient()
    litp_maintenance = LitpMaintenance(client=litp)
    maintenance_mode = litp_maintenance.is_maintenance_mode()
    if maintenance_mode:
        get_log().error('LITP is in maintenance mode. '
                        'Can not import an ISO in this mode.')
        raise SystemExit(ExitCodes.LITP_MAINT_MODE)


def create_argument_parser():
    """
    Creates and configures parser to process command line arguments
    :return: argument parser instance
    :rtype ArgumentParser
    """
    parser = ArgumentParser(prog='import_iso.py')
    parser.add_argument('--iso', dest='iso', required=True,
                        help='ENMINST iso file')
    parser.add_argument('-v', '--verbose', dest='verbose',
                        action='store_true', default=False)
    return parser


def main(args):
    """
    Process command arguments and runs main application flow
    :param args: sys args
    """
    parser = create_argument_parser()
    parsed_args = parser.parse_args(args[1:])
    main_flow(parsed_args.iso, parsed_args.verbose)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
