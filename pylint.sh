#!/usr/bin/env bash

MSG_TEMPLATE="--msg-template='{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}'"
SRC_DIR=${PWD}/ERICenminst_CXP9030877/src/main/python
TEST_DIR=${PWD}/ERICenminst_CXP9030877/test
REPORTS="--reports=n"
REPORT_TYPE="text"
REPORT_FILE=${PWD}/pylint_report.${REPORT_TYPE}
pushd ${SRC_DIR} > /dev/null
export PYTHONPATH=${SRC_DIR}:${TEST_DIR}:${PYTHONPATH}

DISABLED_CHECKS="-drelative-import -dlocally-disabled"
BAD_FUNCTIONS="--bad-functions=\"[filter]\""
MIN_DUP_LINES="--min-similarity-lines=5"
pylint ${DISABLED_CHECKS} ${MIN_DUP_LINES} ${BAD_FUNCTIONS} -rn \
    "${MSG_TEMPLATE}" \
    agent h_hc h_infra h_litp h_logging h_puppet h_util h_vcs h_xml \
    workarounds h_snapshots h_rackinit *.py 2>&1
_rc_=$?
popd > /dev/null
echo "Exiting: ${_rc_}"
exit ${_rc_}
