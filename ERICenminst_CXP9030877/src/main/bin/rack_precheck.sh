#!/bin/bash

BASENAME=/bin/basename
DIRNAME=/usr/bin/dirname
ECHO=/bin/echo
PYTHON=/usr/bin/python

_dir_=`${DIRNAME} $0`
export _HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export _LIB=${_HOME}/lib
unset _dir_

export PYTHONPATH=${PYTHONPATH}:${_LIB}:/opt/ericsson/nms/litp/bin
${PYTHON} ${_LIB}/h_rackinit/hwc.py "$@" 2>&1
exit $?
