#!/bin/bash
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2021 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : rh7_upgrade_enm.sh
# Purpose : Automatic RHEL 7.9 uplift of ENM.
#           ENM Upgrade type determination.
#
# Usage   : See usage function below.
#
# ********************************************************************

# Main

ECHO=/bin/echo

# Check we are user root before we do anything else.
[[ "$EUID" -ne 0 ]] && { ${ECHO} "Only root user may run this script." ; exit 1; }

BASENAME=/bin/basename
DIRNAME=/usr/bin/dirname
PYTHON=/usr/bin/python

_dir_=`${DIRNAME} $0`
export ENMINST_HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export ENMINST_ETC=${ENMINST_HOME}/etc
export ENMINST_LIB=${ENMINST_HOME}/lib
export ENMINST_CONF=${ENMINST_HOME}/conf
export ENMINST_RUNTIME=${ENMINST_HOME}/runtime
export ENMINST_BIN=${ENMINST_HOME}/bin

export LITP_LIB="/opt/ericsson/nms/litp/lib"
unset _dir_

export LOG_TAG=`${BASENAME} $0 .sh`

if [ -d "${LITP_LIB}" ]; then
    export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}:${LITP_LIB}/sanapi:${LITP_LIB}
else
    export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}
fi

ENMINST_LOG="${ENMINST_HOME}/log"
if [ ! -d "${ENMINST_LOG}" ]; then
    mkdir -p "${ENMINST_LOG}" 2> /dev/null
fi

${PYTHON} "${ENMINST_LIB}/rh7_upgrade_enm.py" $* 2>&1
exit $?
