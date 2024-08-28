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
# Name    : substituteParams.sh
# Purpose : Fully substituting all parameters needed for a complete
#           deployment description xml.
# Usage   : substituteParams.sh --sed=<SED location>
#           --xml_template=<xml_template location>
#            eg../substituteParams.sh --sed=/var/tmp/ENM/SED_ieatlms4352-1.txt
#               --xml_template=/opt/ericsson/enminst/etc/xml_templates
#               /enminst_blade_install.xml.template
#
# ********************************************************************

BASENAME=/bin/basename
DIRNAME=/usr/bin/dirname
ECHO=/bin/echo
PYTHON=/usr/bin/python

_dir_=`${DIRNAME} $0`
export ENMINST_HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export ENMINST_LIB=${ENMINST_HOME}/lib
export ENMINST_CONF=${ENMINST_HOME}/conf
export ENMINST_RUNTIME=${ENMINST_HOME}/runtime

unset _dir_

export LOG_TAG=`${BASENAME} $0 .bsh`
export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}

${PYTHON} ${ENMINST_LIB}/substitute_parameters.py $* 2>&1
exit $?