"""
Class handling LMS disk UUIDs
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
from subprocess import PIPE

from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import exec_process, read_enminst_config, EnminstWorking


def get_ms_disk_uuid(log, vg_name='vg_root'):
    """
    Obtain root disk UUID.
    :param log: Reference to logger
    :type log: Logger
    :param vg_name: name of the vg
    :type vg_name: str
    :return: UUID of the root disk
    :rtype: str
    """

    id_serial = 'ID_SERIAL_SHORT'
    command_pvscan = 'pvs --noheadings --separator=, -o pv_name,vg_name'
    disk_path = ''
    uuid = ''
    output = exec_process(command_pvscan.split(), stderr=PIPE)
    for line in output.split('\n'):
        if ',' + vg_name in line:
            disk_path = line.split(',')[0]
            break

    if disk_path:
        disk_path = disk_path.strip()
        command_udevadm = 'udevadm info --query=all --name=' + disk_path
        output = exec_process(command_udevadm.split())
    else:
        log.exception('Failed to get {0}'.format(vg_name))
        raise ValueError('Failed to get {0}'.format(vg_name))

    for line in output.splitlines():
        if id_serial in line:
            uuid = line.split('=')[1]
            break

    if len(uuid) == 0:
        log.exception("Failed to get valid UUID.")
        raise ValueError("Failed to get valid UUID.")

    return uuid


def update_enminst_working(params_file, log):
    """
    Update the enminst_working.cfg file with the UUID.
    :param params_file: Path to the enminst_working.cfg
    :type params_file: str
    :param log: Logger instance
    """
    log.info('-' * 65)
    log.info('Getting UUID of root disk')
    log.info('-' * 65)
    uuid = get_ms_disk_uuid(log)
    ms_uuid_param = "uuid_ms_disk0"
    cfg = EnminstWorking(params_file)
    cfg.set_site_key(ms_uuid_param, uuid)
    cfg.write()
    log.info('UUID successfully fetched.')


def update_uuid():
    """
    Update the enminst_working.cfg file with the UUID.
    """
    log = init_enminst_logging()
    config = read_enminst_config()
    update_enminst_working(config['enminst_working_parameters'], log)


if __name__ == '__main__':
    main_exceptions(update_uuid, None)
