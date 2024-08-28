#!/bin/bash
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2020 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : enc_expansion.sh
# Purpose : Wrapper script calling enc_expansion.py
#
# ********************************************************************

BASENAME=/bin/basename
DIRNAME=/usr/bin/dirname
ECHO=/bin/echo
PYTHON=/usr/bin/python

_dir_=$(${DIRNAME} $0)
export ENMINST_HOME=$(cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_})
export ENMINST_LIB=${ENMINST_HOME}/lib
export ENMINST_CONF=${ENMINST_HOME}/conf
export ENMINST_RUNTIME=${ENMINST_HOME}/runtime

export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}
${PYTHON} ${ENMINST_LIB}/enc_expansion.py "$@" 2>&1
exit $?
