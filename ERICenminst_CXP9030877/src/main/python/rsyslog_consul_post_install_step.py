"""
The purpose of this script is to remove the
rsyslog rule conf file that changed the log level of
Consul ERROR to WARN.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2024
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################
import os
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import exec_process, exists

LOGGER = init_enminst_logging()

SYSTEMCTL = '/usr/bin/systemctl'
CONSUL_RSYSLOG_CONF = '/etc/rsyslog.d/19_consul_log.conf'


def remove_consul_rsyslog_rule():
    """
    Removes the rsyslog rule conf file that changed the Consul
    log level from ERROR to WARN
    return: Returns nothing
    """
    if exists(CONSUL_RSYSLOG_CONF):
        try:
            os.remove(CONSUL_RSYSLOG_CONF)
            LOGGER.info('Removed {0}'.format(CONSUL_RSYSLOG_CONF))
        except OSError as ioe:
            LOGGER.debug("Unable to delete the file {0}. "
                         "Error: {1}".format(CONSUL_RSYSLOG_CONF, ioe))
            raise SystemExit(ioe)

    try:
        LOGGER.info('Restarting rsyslog ...')
        exec_process([SYSTEMCTL, 'restart', 'rsyslog.service'])
    except Exception as error:
        LOGGER.exception("An error occurred restarting service")
        raise Exception(error)

    else:
        LOGGER.info("Successfully restarted rsyslog service")


if __name__ == '__main__':
    main_exceptions(remove_consul_rsyslog_rule, None)
