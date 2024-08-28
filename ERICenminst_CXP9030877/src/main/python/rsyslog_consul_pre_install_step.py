"""
The purpose of this script is to create a
rsyslog rule that changes the log level of
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

from h_litp.litp_utils import main_exceptions
import os

from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import exec_process, touch

LOGGER = init_enminst_logging()
SYSTEMCTL = '/usr/bin/systemctl'
CONSUL_RSYSLOG_CONF = '/etc/rsyslog.d/19_consul_log.conf'
CONSUL_LOG_RULE = """template(name="consulerr" type="string"
string="%TIMESTAMP% %HOSTNAME% %syslogtag%""" \
                  + """%$!msg:::sp-if-no-1st-sp%%$!msg:::drop-last-lf%\\n")
if (re_match($programname,'consul') and $msg contains "ERROR")
then {
    set $!msg = replace($msg, "ERROR", "WARN");
    action(type="omfile" file="/var/log/messages" template="consulerr")
    & stop
}
"""


def create_consul_rsyslog_rule():
    """
    Creates a rsyslog rule conf file that changes Consul log level
    from ERROR to WARN and restarts the rsyslog service
    return: Returns nothing
    """

    try:
        touch(CONSUL_RSYSLOG_CONF)
        os.chmod(CONSUL_RSYSLOG_CONF, 0755)
    except IOError as ioe:
        LOGGER.debug("Unable to create the file {0} with correct "
                     "permissions. Error: {1}".format(
                        CONSUL_RSYSLOG_CONF, ioe))
        raise SystemExit(ioe)

    else:
        LOGGER.info("Successfully created file %s", CONSUL_RSYSLOG_CONF)

    try:
        conf_file = open(CONSUL_RSYSLOG_CONF, "w")
        conf_file.write(CONSUL_LOG_RULE)
        conf_file.close()
    except IOError as ioe:
        LOGGER.debug("Unable to add Consul log rule to the file {0}. "
                     "Error: {1}".format(CONSUL_RSYSLOG_CONF, ioe))
        raise SystemExit(ioe)

    else:
        LOGGER.info("Successfully added Consul log Rule to "
                    "file %s", CONSUL_RSYSLOG_CONF)

    try:
        LOGGER.info('Restarting rsyslog ...')
        exec_process([SYSTEMCTL, 'restart', 'rsyslog.service'])
    except IOError as ioe:
        LOGGER.exception('rsyslog did not restart: '.format(str(ioe)))
        raise SystemExit(ioe)

    else:
        LOGGER.info("Successfully restarted rsyslog service")


if __name__ == '__main__':
    main_exceptions(create_consul_rsyslog_rule, None)
