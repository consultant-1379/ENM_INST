"""
File containing 'constants' used by the enclosure expansion modules.
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

from os import path

from h_util.h_utils import read_enminst_config

# FILE/DIR LOCATION CONSTANTS
CALLING_SCRIPT = 'enc_expansion.sh'
RUNTIME_DIR = read_enminst_config().get('enminst_runtime')
EXPANSION_MODEL_FILE = path.join(RUNTIME_DIR, 'expansion_model.json')
REPORT_FILE = path.join(RUNTIME_DIR, 'enclosure_report.txt')
HW_COMM = '/opt/ericsson/hw_comm/bin/hw_comm.sh'


# OA OUTPUT PARSING CONSTANTS
SERVER_BAY = 1
SERVER_POWER = -2
SERVER_SERIAL = -4
SERVER_ILO = -4

UNKNOWN_BAY = 'Unknown'

POWER_STATUS_ON = 'on'
POWER_STATUS_OFF = 'off'

ACTIVE_OA = 'Role:Active'

NETWORK_NETMASK = 'Netmask:'

EMPTY_BAY = '[Absent]'
UNKNOWN_SERIAL = '[Unknown]'


EBIPA_IP_ADDR = 2
EBIPA_NETMASK = 3
EBIPA_GATEWAY = 4
EBIPA_DNS = 5
EBIPA_DOMAIN = 6


# OA COMMANDS
SHOW_OA_STATUS = 'SHOW OA STATUS'
SHOW_SERVER_NAMES = 'SHOW SERVER NAMES'
SHOW_SERVER_LIST = 'SHOW SERVER LIST'
POWER_ON = 'POWERON SERVER {0}'
SHOW_EBIPA_SERVER = 'SHOW EBIPA SERVER'
SET_EBIPA_SERVER = 'SET EBIPA SERVER {0} {1} {2}'
SET_EBIPA_SERVER_GATEWAY = 'SET EBIPA SERVER GATEWAY {0} {1}'
SET_EBIPA_SERVER_DOMAIN = 'SET EBIPA SERVER DOMAIN {0} {1}'
ENABLE_EBIPA_SERVER = 'ENABLE EBIPA SERVER {0}'
SAVE_EBIPA = 'SAVE EBIPA'
SHOW_OA_NETWORK = 'SHOW OA NETWORK'
EFUSE_RESET = 'RESET SERVER {0}'


# SLEEP CONSTANTS
LOOP_SLEEP = 30
UNLOCK_NEXT_NODE_SLEEP = 300
WAIT_FOR_SERIAL_SLEEP = 600
BOOT_BLADE_SLEEP = 300
HW_COMM_SLEEP = 300
POST_ILO_SLEEP = 180

# TIMEOUT CONSTANTS
SHUTDOWN_TIMEOUT = 600
PING_TIMEOUT = 1800
VCS_TIMEOUT = 600
SVC_OFFLINE_TIMEOUT = 600
SERIAL_TIMEOUT = 600

# SED CONSTANTS
DNS_DOMAIN_NAME = 'dns_domainName'
# enclosure1, enclosure2  - or maybe not sed, just ENCLOSURE_1


# REPORT FILE FORMATTING
REPORT_HEADER = "%8s %12s %9s %10s %8s %8s %8s" % (
    "|System Name|", "|Serial Number|", "|Src iLO IP Address|",
    "|Dst iLO IP Address|", "|Src Bay|", "|Dst Bay|", "|Host Name|\n")
REPORT_BREAK = '=' * 103
REPORT_BREAK += '\n'
REPORT_ENTRY = '%8s %17s %19s %20s %9s %9s %16s\n'


# LOG CONSTANTS
LOGGER = 'enminst'
LOG_LEVEL = 'debug'
