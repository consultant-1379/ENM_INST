"""
Script to facilitate the expansion of an ENM deployment to a second enclosure
"""
##############################################################################
# COPYRIGHT Ericsson AB 2020
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################
import os
import sys
import logging
from datetime import datetime
from argparse import ArgumentParser

from h_util.h_utils import is_valid_file, exec_process
from h_expansion.expansion_sed_utils import ExpansionSedHandler
from h_expansion.expansion_ilo_update import add_new_ilos_to_litp
from h_expansion.expansion_model_handler import ExpansionModelHandler
from h_expansion.validate_expansion_sed import ExpansionSedValidation
from h_expansion.expansion_utils import get_blade_info, LitpHandler, \
    report_file_ok
from h_expansion.expansion_boot_utils import freeze_and_shutdown_systems,\
    boot_systems_and_unlock_vcs, ExpansionException
from h_expansion.expansion_cleanup import cleanup_arp_cache, \
    cleanup_runtime_files, cleanup_source_oa
from h_expansion.expansion_settings import CALLING_SCRIPT, REPORT_FILE, \
    REPORT_HEADER, REPORT_BREAK, REPORT_ENTRY, HW_COMM

from h_logging.enminst_logger import init_enminst_logging, set_logging_level


TIME_STAMP = datetime.now().strftime('%d-%B-%Y %H:%M')

LOGGER = logging.getLogger("enminst")


def create_parser():  # pylint: disable=too-many-locals
    """
    Parse script arguments
    :return:
    """
    parser = ArgumentParser(prog='enc_expansion.sh')
    sub_parser = parser.add_subparsers()

    # Validate Expansion SED CLI Option
    validate_help = 'Validate the expansion SED'
    validate_descr = 'The SED will be validated to ensure the required ' \
                     'values are present'

    validate_sed = sub_parser.add_parser('validate-sed',
                                         help=validate_help,
                                         description=validate_descr)
    validate_sed.set_defaults(command='validate-sed')
    validate_sed.add_argument('--sed', help='SED file for the deployment.',
                              type=lambda x: is_valid_file(parser,
                                                           'SED', x),
                              required=True)

    # Generate Enclosure Report CLI Option
    report_help = 'Generate an enclosure report for the deployment'
    repot_descr = 'The report will show which blades need to be moved from ' \
                  'the source enclosure to the destination enclosure'

    enclosure_report = sub_parser.add_parser('enclosure-report',
                                             help=report_help,
                                             description=repot_descr)
    enclosure_report.set_defaults(command='enclosure-report')
    enclosure_report.add_argument('--sed', help='SED file for the deployment.',
                                  type=lambda x: is_valid_file(parser,
                                                               'SED', x),
                                  required=True)
    # Shutdown Blades CLI Option
    shutdown_help = 'Cleanly migrate VCS services then shut down the blades'
    shutdown_descr = 'The blades will be shut down in a controlled fashion ' \
                     'so that there is no loss of ENM service'

    shut_blades = sub_parser.add_parser('shutdown-blades',
                                        help=shutdown_help,
                                        description=shutdown_descr)
    shut_blades.set_defaults(command='shutdown-blades')
    shut_blades.add_argument('--sed', help='SED file for the deployment.',
                             type=lambda x: is_valid_file(parser, 'SED', x),
                             required=True)
    shut_blades.add_argument('--rollback',
                             help='To rollback to single enclosure.',
                             action='store_true')

    # Boot up Blades CLI Option
    boot_help = 'Boot blades and bring up VCS services'
    boot_descr = 'The blades will be booted and VCS service brought online'

    boot_blades = sub_parser.add_parser('boot-blades',
                                        help=boot_help,
                                        description=boot_descr)
    boot_blades.set_defaults(command='boot-blades')
    boot_blades.add_argument('--sed', help='SED file for the deployment.',
                             type=lambda x: is_valid_file(parser, 'SED', x),
                             required=True)
    boot_blades.add_argument('--rollback',
                             help='To rollback to single enclosure.',
                             action='store_true')

    # Update LITP iLO IPs CLI Option
    update_ilo_help = 'Update the iLO IPs in the LITP model.'
    update_ilo_descr = 'The iLO IPs will be updated in the LITP model for ' \
                       'each blade that has been moved.'

    update_ilo_ips = sub_parser.add_parser('update-ilo-ips',
                                           help=update_ilo_help,
                                           description=update_ilo_descr)
    update_ilo_ips.set_defaults(command='update-ilo-ips')
    update_ilo_ips.add_argument('--sed', help='SED file for the deployment.',
                                type=lambda x: is_valid_file(parser, 'SED', x),
                                required=True)

    # Expansion Cleanup CLI Option
    cleanup_help = 'Cleanup files created during the expansion procedure'
    cleanup_descr = 'Files generated at runtime will be deleted and the ARP ' \
                    'cache will be cleaned up.'

    cleanup = sub_parser.add_parser('cleanup',
                                    help=cleanup_help,
                                    description=cleanup_descr)
    cleanup.set_defaults(command='cleanup')
    cleanup.add_argument('--sed', help='SED file for the deployment.',
                         type=lambda x: is_valid_file(parser, 'SED', x),
                         required=True)
    cleanup.add_argument('--clean_src_oa',
                         help='Remove the iLO IPs from the moved source bays.',
                         action='store_true')

    return parser


def report_generation(blades_to_move, enclosure_oa):
    """
    Generating the report about blades
    :return:
    """
    LOGGER.debug("Entered report_generation")
    contents = "Enclosure report generated at {0}\n\n".format(TIME_STAMP)
    contents += "DETAILS OF BLADES TO BE MOVED\n"
    contents += "==============================\n\n"
    contents += REPORT_HEADER
    contents += REPORT_BREAK

    for blade in blades_to_move:
        report_line = REPORT_ENTRY % (blade.sys_name, blade.serial_no,
                                      blade.src_ilo, blade.dest_ilo,
                                      blade.src_bay, blade.dest_bay,
                                      blade.hostname)
        contents += report_line

    server_names = enclosure_oa.show_server_names()
    contents += "\n\nDETAILS OF DESTINATION ENCLOSURE\n"
    contents += "================================\n"
    contents += server_names

    with open(REPORT_FILE, 'w') as report_file:
        report_file.write(contents)

    LOGGER.info('Wrote the following report to %s:\n\n%s\n\n',
                REPORT_FILE, contents)

    LOGGER.info('Making report file {0} immutable'.format(REPORT_FILE))
    try:
        command = 'chattr +i {0}'.format(REPORT_FILE)
        LOGGER.debug('Running command {0}'.format(command))
        exec_process(command.split())
    except IOError:
        LOGGER.error('Failed to make report file {0} immutable'
                     .format(REPORT_FILE))
        raise

    return contents


def validate_expansion_sed(args):
    """
    Driver function for the expansion SED validation functionality.
    :param args: Command line arguments passed in.
    :return: None
    """
    LOGGER.info('Verifying that ERIChwcomm_CXP9032292 is installed')
    if not os.path.exists(HW_COMM):
        raise Exception('ERIChwcomm_CXP9032292 is not installed, '
                        'install before proceeding')

    LOGGER.info('Validating the SED')
    litp_handler = LitpHandler()

    sed_handler = ExpansionSedHandler(args.sed)

    peer_nodes = litp_handler.enm_system_names
    ilo_dict = sed_handler.get_peer_node_ilo_ip_addresses(peer_nodes)
    serial_dict = sed_handler.get_peer_serials_for_nodes(peer_nodes)

    source_oa = sed_handler.get_enclosure_oa_info('enclosure1')

    blades = get_blade_info(source_oa, ilo_dict, serial_dict)

    sed_validator = ExpansionSedValidation(sed_handler)

    sed_validator.validate_sed(blades)

    sed_validator.write_model_file()


def generate_enclosure_report(args):
    """
    Driver function for the expansion report generation.
    :param args: Command line arguments passed in.
    :return: None
    """
    LOGGER.info('Creating enclosure report')

    litp_handler = LitpHandler()

    sed_handler = ExpansionSedHandler(args.sed)

    peer_nodes = litp_handler.enm_system_names
    ilo_dict = sed_handler.get_peer_node_ilo_ip_addresses(peer_nodes)
    serial_dict = sed_handler.get_peer_serials_for_nodes(peer_nodes)

    source_oa = sed_handler.get_enclosure_oa_info('enclosure1')
    target_oa = sed_handler.get_enclosure_oa_info('enclosure2')

    blades = get_blade_info(source_oa, ilo_dict, serial_dict)
    report_generation(blades, target_oa)


def shutdown_blades(args):
    """
    Driver function for shutting down blades during the expansion procedure.
    :param args: Command line arguments passed in.
    :return: None
    """
    LOGGER.info('Shutting down the blades')

    litp_handler = LitpHandler()

    sed_handler = ExpansionSedHandler(args.sed)

    peer_nodes = litp_handler.enm_system_names
    ilo_dict = sed_handler.get_peer_node_ilo_ip_addresses(peer_nodes)
    serial_dict = sed_handler.get_peer_serials_for_nodes(peer_nodes)

    oa1 = sed_handler.get_enclosure_oa_info('enclosure1')
    oa2 = sed_handler.get_enclosure_oa_info('enclosure2')

    source_oa = oa2 if args.rollback else oa1

    blades = get_blade_info(source_oa, ilo_dict, serial_dict)
    freeze_and_shutdown_systems(blades)


def power_on_blades(args):
    """
    Driver function for powering on blades during the expansion procedure.
    :param args: Command line arguments passed in.
    :return: None
    """
    LOGGER.info('Booting up the blades')

    litp_handler = LitpHandler()

    sed_handler = ExpansionSedHandler(args.sed)

    peer_nodes = litp_handler.enm_system_names
    ilo_dict = sed_handler.get_peer_node_ilo_ip_addresses(peer_nodes)
    serial_dict = sed_handler.get_peer_serials_for_nodes(peer_nodes)

    oa1 = sed_handler.get_enclosure_oa_info('enclosure1')
    oa2 = sed_handler.get_enclosure_oa_info('enclosure2')

    target_oa = oa1 if args.rollback else oa2

    blades = get_blade_info(target_oa, ilo_dict, serial_dict, args.rollback)
    boot_systems_and_unlock_vcs(blades, target_oa, args.sed, args.rollback)


# pylint: disable=W0613
def update_ilo_ips_in_litp_model(args):
    """
    Driver function for updating the LITP model iLO IPs.
    :param args: Command line arguments passed in.
    :return: None
    """
    LOGGER.info('Updating the iLO BMC entries in LITP')

    # Get source iLO IPs from the model.
    model_handler = ExpansionModelHandler()
    blades = model_handler.get_blades_in_model()
    add_new_ilos_to_litp(blades)


def expansion_cleanup(args):
    """
    Driver function for the expansion cleanup functionality.
    :param args: Command line arguments passed in.
    :return: None
    """
    if not report_file_ok():
        LOGGER.error('Report file is invalid, cannot proceed')
        raise ExpansionException('Invalid Report File!')

    LOGGER.info('Running expansion cleanup')
    if args.clean_src_oa:
        cleanup_source_oa(args.sed)

    cleanup_arp_cache()
    cleanup_runtime_files()


def main(input_args):
    """
    Main function called if module is ran directly
    :return:
    """
    # parse arguments
    parser = create_parser()
    args = parser.parse_args(input_args[1:])

    LOGGER.info("Script %s Started at: %s", CALLING_SCRIPT, TIME_STAMP)
    LOGGER.info("Called with %s", " ".join(sys.argv[1:]))

    cmd_func_mapping = {'validate-sed': validate_expansion_sed,
                        'enclosure-report': generate_enclosure_report,
                        'shutdown-blades': shutdown_blades,
                        'boot-blades': power_on_blades,
                        'update-ilo-ips': update_ilo_ips_in_litp_model,
                        'cleanup': expansion_cleanup}

    if args.command in ['shutdown-blades', 'boot-blades'] \
            and not args.rollback:
        LOGGER.debug('Checking the report file')
        if not report_file_ok():
            LOGGER.error('Report file is invalid, cannot proceed')
            raise ExpansionException('Invalid Report File!')

    try:
        cmd_func = cmd_func_mapping[args.command]
    except KeyError as exc:
        LOGGER.error('Missing command mapping for {0}'.format(exc))
        raise

    cmd_func(args)


if __name__ == "__main__":
    init_enminst_logging()
    LOGGER = logging.getLogger('enminst')
    set_logging_level(LOGGER, 'DEBUG')

    try:
        main(sys.argv)
    except Exception as err:
        LOGGER.error('Enclosure Expansion %s failed with %s: %s', sys.argv[1],
                     type(err), err)
        raise SystemExit(1)
    LOGGER.info('%s %s Completed Successfully', CALLING_SCRIPT, sys.argv[1])

    raise SystemExit(0)
