#!/bin/bash
# ********************************************************************
# Ericsson LMI
# ********************************************************************
#
# (c) Ericsson LMI 2019 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : pre_upgrade_rpms.sh
# Purpose : Wrapper script calling pre_upgrade_rpms.py
#
# ********************************************************************
function usage()
{
cat<< EOF

        Pre-Upgrade RPMs

        Usage: pre_upgrade_rpms.sh [-h] ISO

        Required Argument:
           ISO            Path to the ENM ISO

        Optional Argument:
           -h             Display this help message

        Examples:
        # /opt/ericsson/enminst/bin/pre_upgrade_rpms.sh /software/ERICenm_CXP9027091-1.1.16.iso
        # /opt/ericsson/enminst/bin/pre_upgrade_rpms.sh -h

EOF
}


DIRNAME="/usr/bin/dirname"
ECHO="/bin/echo"
PYTHON="/usr/bin/python"
ENMINST_BIN="/opt/ericsson/enminst/bin/"

_dir_=`${DIRNAME} $0`
export ENMINST_HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export ENMINST_LIB=${ENMINST_HOME}/lib

unset _dir_

if [[ "$1" == "-h" ]]
then
    usage
    exit 0
elif [[ $# -eq 0 ]]
then
    echo "ENM ISO must be supplied as an argument, run with -h to see usage"
    exit 1
elif [[ $# -gt 1 ]]
then
    echo "Too many arguments, run with -h to see usage"
    exit 1
elif [[ "$1" != *.iso ]]
then
    echo "Incorrect parameter, run with -h to see usage"
    exit 1
elif [[ ! -e $1 ]]
then
    echo "ENM ISO $1 does not exist"
    exit 1
fi

export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}
${PYTHON} ${ENMINST_LIB}/pre_upgrade_rpms.py "$@" |& grep -v ^Installing
ret_code=${PIPESTATUS[0]}

if [[ "${ret_code}" -ne 0 ]]; then
    ${ECHO} "Failed to upgrade RPMs"
    exit ${ret_code}
fi

${ECHO} "Syncing Puppet post upgrade."
${ENMINST_BIN}/puppet.bsh --sync || { ${ECHO} "Failed to sync Puppet."; exit 1; }
