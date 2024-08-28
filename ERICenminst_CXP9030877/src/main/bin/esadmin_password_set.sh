#!/usr/bin/env bash
##############################################################################
# COPYRIGHT Ericsson AB 2017
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
_GREP="/bin/grep"
_RM="/bin/rm"
_LOGGER="/bin/logger"
_PASSWD="/usr/bin/passwd"
_OPENSSL="/usr/bin/openssl"
GLOBAL_PROPERTIES_FILE="/ericsson/tor/data/global.properties"
CHECK_USER="/home/es_admin"
PASSKEY="/opt/ericsson/enminst/etc/esadmin_passkey"
encrypted_password="U2FsdGVkX1/caEO6rFQQW07hMY7j4rDxHLzOoo1x2og="

function log(){
    $_LOGGER -t "ElasticSearch Log Admin Post Install" $1
}

function check_if_cloud_deployment() {
    $_GREP -i "DDC_ON_CLOUD=TRUE" $GLOBAL_PROPERTIES_FILE 2>/dev/null
    ret_code=$?
    if [ $ret_code -ne 0 ];then
        log "setting password for es_admin on physical"
        check_if_password_exists
    fi
}

function check_if_password_exists() {
    log "Checking if es_admin user exists"
    $_GREP "es_admin" /etc/passwd 2>/dev/null
    ret_code=$?
    if [ $ret_code -eq 0 ];then
        log "es_admin user exists"
        log "Checking if password exists for es_admin user"
        $_PASSWD --status "es_admin" | $_GREP "Password set" 2>/dev/null
        ret_code=$?
        if [ $ret_code -ne 0 ];then
            log "Setting password for es_admin user"
            set_password
        else
            log "Password exists for es_admin user"
        fi
    fi
}

function set_password() {
    ADMIN_PASSWORD=$(echo ${encrypted_password} | ${_OPENSSL} enc -a -d -aes-128-cbc -salt -kfile ${PASSKEY} 2> /dev/null)
    echo "$ADMIN_PASSWORD" | passwd --stdin "es_admin" 2>/dev/null
    ret_code=$?
    if [ $ret_code -ne 0 ]; then
       log "Failed to set es_admin user password : return code: ${ret_code}. Output: ${ADMIN_PASSWORD}"
    else
        log "Password setting successfully implemented"
    fi
}
function delete_pass_key_file() {
    $_PASSWD --status "es_admin" | $_GREP "Password set" 2>/dev/null
    ret_code=$?
    if [ $ret_code -eq 0 ]; then
       $_RM -f $PASSKEY 2>/dev/null
       ret_code=$?
       if [ $ret_code -ne 0 ];then
          log "Failed removing passkey file"
       else
          log "Removed passkey file successsfully"
       fi
    fi
}

check_if_cloud_deployment
delete_pass_key_file
