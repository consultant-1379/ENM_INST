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
# Name    : storage_default_route.py
# Purpose : See usage
#
# Usage   : See usage
#
# ********************************************************************
BASENAME=/bin/basename
DIRNAME=/usr/bin/dirname
ECHO=echo
PYTHON=/usr/bin/python
PWD_=/bin/pwd

_dir_=`${DIRNAME} $0`
export ENMINST_HOME=`cd ${_dir_}/../ 2>/dev/null && ${PWD_} || ${ECHO} ${_dir_}`
export ENMINST_LIB=${ENMINST_HOME}/lib
unset _dir_
export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}

${PYTHON} ${ENMINST_LIB}/workarounds/storage_default_route/storage_default_route.py "$@" 2>&1
exit $?
