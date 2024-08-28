"""
This module is to provide logging functionality to the SED expansion script.
"""
import sys
import logging
import os
import time
import expansion_sed_constants


def setup_logger(log_level=logging.INFO):
    """
    Creates a logger to log the script's execution

    :param: None
    :return: None
    :throw: None
    """
    if not os.access(expansion_sed_constants.DEFAULT_LOG_DIR, os.W_OK):
        log_dir = expansion_sed_constants.FAILSAFE_LOG_DIR
    else:
        log_dir = expansion_sed_constants.DEFAULT_LOG_DIR
    log_filename = '{0}/expansion_sed_{1}_{2}.log' \
        .format(log_dir, time.strftime('%Y%m%d'), os.geteuid())
    log_format_file = \
        logging.Formatter('%(asctime)s %(levelname)s: %(message)s',
                          datefmt='%Y-%m-%d %H:%M:%S')

    log_format_screen = \
        logging.Formatter('%(levelname)s: %(message)s')
    logger = logging.getLogger('app')

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(log_format_screen)

    # Always log DEBUG messages to the log file
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format_file)

    # remove any existing handlers
    logger.handlers = []

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.DEBUG)

    return logger
