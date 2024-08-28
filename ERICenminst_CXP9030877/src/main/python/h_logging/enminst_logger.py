"""
 Logging helper functions
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
import logging
import logging.config
import sys
from ConfigParser import NoSectionError
from h_util.h_utils import read_enminst_config


def init_enminst_logging(logger_name='enminst', logger_config=None):
    """
    Initialise logging functionality for ENM_INST.
    Configure and return a Logger from the provided logging configuration file.
    :param logger_config: Logging configuration file
    :param logger_name: Name of logger
    :return: loggin.Logger object
    """
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        # Logger already configured
        return logger

    if not logger_config:
        enminst_config = read_enminst_config()
        logger_config = enminst_config.get('enminst_log_config', '')

    try:
        logging.config.fileConfig(logger_config)
    except NoSectionError:
        sys.stdout.write('Can not process logging configuration file: {0}. '
                         'Using basicConfig.\n'.format(logger_config))
        logging.basicConfig(level=logging.DEBUG)
    return logger


def set_logging_level(logger, level):
    """
    Set the logging level for all handles of the logger
    :param logger: a logger object
    :param level: logging level
    :return: None
    """

    log_levels = logging._levelNames  # pylint: disable=protected-access

    for handler in logger.handlers:
        handler.setLevel(log_levels.get(level, handler.level))


def log_header(logger, message):
    """
    Log a header formatted message
    :param logger: The logger instance to log with.
    :param message: The message to wrap in header lines
    :return:
    """
    logger.info('-' * 65)
    logger.info(message)
    logger.info('-' * 65)


def log_cmdline_args(calling_script, args):
    """
    A function to update cmd_arg.log after arg validation and
    and log install/upgrade command to enminst.log file
    :param calling_script: bash script invoked by the end user
    :param args: command line args passed to the calling script
    :return:
    """
    log = init_enminst_logging()
    enminst_config = read_enminst_config()
    cmd_arg_log = enminst_config.get('enm_cmd_arg_file')

    log_header(log, 'Logging Command Line Arguments')

    if isinstance(args, basestring):
        args = args.split()

    command_str = './' + calling_script + ' ' + " ".join(args[1:])
    log.info(command_str)

    with open(cmd_arg_log, 'a') as _writer:
        _writer.write(command_str + '\n')
