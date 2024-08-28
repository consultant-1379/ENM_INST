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
# Name    : fallback_rollback_check.sh
# Purpose : Wrapper script calling enm_upgrade_prechecks.py
#
# ********************************************************************

DIRNAME="/usr/bin/dirname"
ECHO="/bin/echo"
PYTHON="/usr/bin/python"

_dir_=`${DIRNAME} $0`
export ENMINST_HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export ENMINST_LIB=${ENMINST_HOME}/lib

unset _dir_

export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}
${PYTHON} ${ENMINST_LIB}/enm_upgrade_prechecks.py --action check_fallback_status
exit $?