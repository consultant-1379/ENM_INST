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
# Name    : --
# Purpose : --
#
# ********************************************************************

BASENAME=/bin/basename
DIRNAME=/usr/bin/dirname
ECHO=/bin/echo
PYTHON=/usr/bin/python

_dir_=`${DIRNAME} $0`
export ENMINST_HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export ENMINST_LIB=${ENMINST_HOME}/lib

unset _dir_

export LOG_TAG=`${BASENAME} $0 .bsh`
export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}

pushd ${ENMINST_LIB} > /dev/null
${PYTHON} h_litp/litp_rest_client.py "--monitor_plan" 2>&1
_rc_=$?
popd > /dev/null
exit ${_rc_}

