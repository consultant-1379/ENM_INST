#!/bin/bash
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2015 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : upgrade_enm.sh
# Purpose : Automatic upgrade of ENM.
#
# Usage   : See usage function below.
#
# ********************************************************************

# Main

# Check we are user root before we do anything else.
[[ "$EUID" -ne 0 ]] && { echo "Only root user can run this script." ; exit 1; }

BASENAME=/bin/basename
DIRNAME=/usr/bin/dirname
ECHO=/bin/echo
PYTHON=/usr/bin/python

_dir_=`${DIRNAME} $0`
export ENMINST_HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export ENMINST_ETC=${ENMINST_HOME}/etc
export ENMINST_LIB=${ENMINST_HOME}/lib
export ENMINST_CONF=${ENMINST_HOME}/conf
export ENMINST_RUNTIME=${ENMINST_HOME}/runtime
export ENMINST_BIN=${ENMINST_HOME}/bin

unset _dir_

export LOG_TAG=`${BASENAME} $0 .bsh`
export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}

ENMINST_LOG="${ENMINST_HOME}/log"
if [ ! -d "${ENMINST_LOG}" ]; then
    mkdir -p "${ENMINST_LOG}" 2> /dev/null
fi

${PYTHON} "${ENMINST_LIB}/upgrade_enm.py" $* 2>&1
exit $?