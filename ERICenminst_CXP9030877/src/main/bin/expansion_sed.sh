#!/bin/bash
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2017 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : expansion_sed.sh
# Purpose : Wrapper shell script to run the expansion workaround
#
# ********************************************************************

BASENAME=/bin/basename
DIRNAME=/usr/bin/dirname
ECHO=/bin/echo
PYTHON=/usr/bin/python

_dir_=`${DIRNAME} $0`
export EXPANSION_SED_HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export EXPANSION_SED_LIB=${EXPANSION_SED_HOME}/lib/workarounds
export EXPANSION_SED_CONF=${EXPANSION_SED_HOME}/conf
export EXPANSION_SED_RUNTIME=${EXPANSION_SED_HOME}/runtime

unset _dir_

# export LOG_TAG=`${BASENAME} $0 .bsh`
export PYTHONPATH=${PYTHONPATH}:${EXPANSION_SED_LIB}

${PYTHON} ${EXPANSION_SED_LIB}/expansion_sed.py $* 2>&1
exit $?
