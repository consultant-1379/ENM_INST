#!/bin/bash
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : ms_relayout.sh
# Purpose : Re-layout the MS filesystem.
#
# Usage   : See usage function below.
#
# ********************************************************************
#   ensure new vol size is bigger then data it will hold, PV have enough space for the new volume
#

function sanity_check() {
    logger -s ${LOGGER_TAG} "Performing sanity check. Please wait."
    VAR_LIBVIRT_USAGE=$(get_fs_usage "/var/lib/libvirt/")
    REPO_USAGE=$(get_fs_usage "/var/www/")
    VAR_LOG_USAGE=$(get_fs_usage "/var/log")
    AVILABLE_PV_FREE_SIZE=$(get_pv_free_size vg_root)
    LV_VAR_USAGE=$((LV_VAR_USAGE-VAR_LOG_USAGE-REPO_USAGE-VAR_LIBVIRT_USAGE))
    RETURN_VAL=0
    logger -s ${LOGGER_TAG} "Usage of /var/www [${REPO_USAGE} MB] ."
    CALC_VAR_WWW_HTML_FS_SIZE=$(calc_fs_space ${VAR_WWW_HTML_VOL_SIZE})
    [[ ${REPO_USAGE} -ge ${CALC_VAR_WWW_HTML_FS_SIZE} ]] && { logger -s ${LOGGER_TAG} "[ERROR] - /var/www usage [${REPO_USAGE} MB] is more than volume size [${CALC_VAR_WWW_HTML_FS_SIZE} MB]."; RETURN_VAL=1; }
    logger -s ${LOGGER_TAG} "Usage of /var/log [${VAR_LOG_USAGE} MB]."
    CALC_VAR_VOL_SIZE=$(calc_fs_space ${VAR_VOL_SIZE})
    [[ ${VAR_LOG_USAGE} -ge ${CALC_VAR_VOL_SIZE} ]] && { logger -s ${LOGGER_TAG} "[ERROR] - /var usage [${VAR_LOG_USAGE} MB] is more than volume size [${CALC_VAR_VOL_SIZE} MB]."; RETURN_VAL=1; }
    logger -s ${LOGGER_TAG} "Space available in physical volume [${AVILABLE_PV_FREE_SIZE} MB], space required [${REQUIRED_PV_FREE_SIZE} MB]."
    [[ ${REQUIRED_PV_FREE_SIZE} -ge ${AVILABLE_PV_FREE_SIZE} ]] && { logger -s ${LOGGER_TAG} "[ERROR] - Not enough space available in PV [${REQUIRED_PV_FREE_SIZE} MB (Required)/${AVILABLE_PV_FREE_SIZE} MB (Avilable)]."; RETURN_VAL=1; }
    logger -s ${LOGGER_TAG} "Usage of / [${LV_ROOT_USAGE} MB]."
    REQUIRED_SIZE=$(calc_fs_space ${FINAL_ROOT_VOL_SIZE})
    [[ ${LV_ROOT_USAGE} -ge ${REQUIRED_SIZE} ]] && { logger -s ${LOGGER_TAG} "[ERROR] - / usage [${LV_ROOT_USAGE} MB] is more than [${REQUIRED_SIZE} MB]."; RETURN_VAL=1; }
    REQUIRED_SIZE=$(calc_fs_space ${FINAL_VAR_VOL_SIZE})
    [[ ${LV_VAR_USAGE} -ge ${REQUIRED_SIZE} ]] && { logger -s ${LOGGER_TAG} "[ERROR] - /var usage [${LV_VAR_USAGE} MB] is more than [${REQUIRED_SIZE} MB]."; RETURN_VAL=1; }
    if [[ $(mount | grep vg1_fs_data) ]]; then
        FS_DATA_MNT_POINT=$(get_mount_point vg1_fs_data)
        if [[ ${FS_DATA_MNT_POINT} == "ERR0R" ]]; then
            logger -s ${LOGGER_TAG} "Failed to get the mount point of vg1_fs_data."
            exit 1
        fi    
        FS_DATA_USAGE=$(get_fs_usage ${FS_DATA_MNT_POINT})
        logger -s ${LOGGER_TAG} "Usage of ${FS_DATA_MNT_POINT} [${FS_DATA_USAGE} MB]."
        if [[ "${MODIFY_FS_DATA}" == "TRUE" ]]; then
            REQUIRED_SIZE=$(calc_fs_space ${FINAL_FS_DATA_SIZE})
            REQUIRED_SIZE=$((REQUIRED_SIZE-500))
            [[ ${FS_DATA_USAGE} -ge ${REQUIRED_SIZE} ]] && { logger -s ${LOGGER_TAG} "[ERROR] - ${FS_DATA_MNT_POINT} usage [${FS_DATA_USAGE} MB] is more than [${REQUIRED_SIZE} MB]."; RETURN_VAL=1; }
        fi
    else
        logger -s ${LOGGER_TAG} "LV vg1_fs_data is not mounted on LMS."
        exit 1
    fi
    if [[ ${RETURN_VAL} -eq 0 ]]; then
        logger -s ${LOGGER_TAG} "Sanity check PASSED."
    else
        logger -s ${LOGGER_TAG} "Sanity check FAILED."
    fi
    if [[ ${RETURN_VAL} -ne 0 ]]; then
        exit ${RETURN_VAL}
    fi
}

function check_4_snapshots () {
    lvdisplay  2> /dev/null | grep  "LV snapshot status" 2> /dev/null | grep -i active > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        logger -s ${LOGGER_TAG} "[ERROR] snapshot exists. Exiting..."
        exit 1
    fi
}

function get_mount_point() {
    VM_NAME=$1
    MNT_POINT=$(mount | grep -w ${VM_NAME} | perl -pi -e 's|.+?\s+(\/.*?)\s+.+|$1|g')
    if [[ -d ${MNT_POINT} ]]; then
        echo "${MNT_POINT}"
    else
        echo "ERR0R"
    fi
}

#
#   Calc the space avilable in filesystem after 15% buffer size of a given LVM
#

function calc_fs_space () {
    LVM_SIZE=$1
    PERCENT_SPACE=$((BUFFER_SPACE*LVM_SIZE/100))
    if [[ ${PERCENT_SPACE} -gt 1 && ${PERCENT_SPACE} -lt ${LVM_SIZE} ]]; then
        FSSIZE=$((LVM_SIZE-PERCENT_SPACE))
        echo ${FSSIZE}
    else
        logger -s "Wrong number - LVM_SIZE=${LVM_SIZE}, ${BUFFER_SPACE}% is ${PERCENT_SPACE}"
        exit 1
    fi
}

#
#   Activate the LVM volume
#

function activate_lvm() {
    vol_name=$1
    logger -s ${LOGGER_TAG} "Activating Logical Volume [${vol_name}]"
    lvchange -ay vg_root/${vol_name}
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "[ERROR] - Failed to activate the Logical Volume [${vol_name}]."
        exit 1
    fi
}

#
#   return  the disk usage in MB.
#

function get_fs_usage() {
    DU=$(du -sm $1 2> /dev/null | awk '{print $1}')
    if [[ -z ${DU} ]]; then
        echo "ERROR"
    else
        echo ${DU}
    fi
}

#
#   Get the free space available in the PV in MB
#

function get_pv_free_size() {
    echo $(pvs --units m 2> /dev/null | grep $1 | awk '{print $NF}' | cut -d "." -f1)
}

#
#   check if disk0 size for MS disk is less than 600GB
#

function check_ms_hd_size(){
    CURRENT_SIZE=$(litp show -p /infrastructure/systems/management_server/disks/disk0/ 2> /dev/null | grep size: 2> /dev/null | perl -pi -e 's|.+?(\d+).|$1|g')
    if [[ ${CURRENT_SIZE} -le 599 ]]; then
        return 1
    fi
    return 0
}

#
#   Check if the /software FS is removed from model already
#

function check_software_in_model() {
    litp show -p /infrastructure/storage/storage_profiles/ms_storage_profile/volume_groups/vg1/file_systems/fs_software > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        return 1
    fi
    return 0
}

function add_fs_data_into_litp_plan() {
    #CHeck if this plan is required to execute and rutrn 0 if not required at this stage.
    logger -s ${LOGGER_TAG} "Adding fs_data VM back into LITP from model. Please wait."
    if [[ -f /etc/init.d/mysqld ]]; then
        CMD='litp create -t file-system -p /infrastructure/storage/storage_profiles/ms_storage_profile/volume_groups/vg1/file_systems/fs_data -o snap_size=100 -o mount_point=/var/lib/mysql -o type=ext4 -o size=25G'
    else
        CMD='litp create -t file-system -p /infrastructure/storage/storage_profiles/ms_storage_profile/volume_groups/vg1/file_systems/fs_data -o snap_size=100 -o mount_point=/var/esm-x65736D -o type=ext4 -o size=25G'
    fi
    logger ${LOGGER_TAG} "Executing - [${CMD}]"
    ${CMD}
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to run [${CMD}]. Exiting..."
        exit 1
    fi
    logger -s ${LOGGER_TAG} "Creating LITP plan. Please wait."
    litp create_plan 2>&1 | logger -s ${LOGGER_TAG} 
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to create LITP plan. Exiting..."
        exit 1
    fi
    logger -s ${LOGGER_TAG} "Running LITP plan. Please wait."
    litp run_plan
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "litp run_plan exit with non zero. Exiting..."
        exit 1
    fi
    /opt/ericsson/enminst/bin/monitor_plan.sh
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "LITP plan failed. Exiting..."
        exit 1
    fi
}

function update_mysql_class () {
    MYSQL_CLASS="/opt/ericsson/nms/litp/etc/puppet/modules/mysql/manifests/ms_server/install.pp"
    [[ -e ${MYSQL_CLASS}.backup ]] || /bin/cp -p ${MYSQL_CLASS} ${MYSQL_CLASS}.backup
    perl -pi -e 's|^(\s+)(require\s+=>\s+Mount.+)|$1#$2|g' ${MYSQL_CLASS}
    perl -pi -e 's|^(\s+)(ensure\s+=>\s+running,)|$1ensure   => stopped,|g' ${MYSQL_CLASS}
}

function undo_update_mysql_class () {
    MYSQL_CLASS="/opt/ericsson/nms/litp/etc/puppet/modules/mysql/manifests/ms_server/install.pp"
    [[ -e ${MYSQL_CLASS}.backup ]] && /bin/cp -p ${MYSQL_CLASS}.backup ${MYSQL_CLASS}
}


function remove_software_from_litp_model() {
    check_software_in_model
    if [[ $? -eq 1 ]]; then
        logger -s ${LOGGER_TAG} "Updating LITP model for removing /software from model. Please wait."
        CMD="litp remove -p /infrastructure/storage/storage_profiles/ms_storage_profile/volume_groups/vg1/file_systems/fs_software"
        logger ${LOGGER_TAG} "Executing - [${CMD}]"
        ${CMD}
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to run [${CMD}]. Exiting..."
            exit 1
        fi
        PHASE_CREATE_PLAN="TRUE"
    fi
    if [[ "${PHASE_CREATE_PLAN}" == "TRUE" ]]; then
        logger -s ${LOGGER_TAG} "Creating LITP plan. Please wait."
        litp create_plan 2>&1 | logger -s ${LOGGER_TAG} 
        if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to create LITP plan. Exiting..."
            exit 1
        fi
        logger -s ${LOGGER_TAG} "Running LITP plan. Please wait."
        litp run_plan
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "litp run_plan exit with non zero. Exiting..."
            exit 1
        fi
        /opt/ericsson/enminst/bin/monitor_plan.sh
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "LITP plan failed. Exiting..."
            exit 1
        fi
    fi
}

function fs_data_handling() {
    litp show -p /infrastructure/storage/storage_profiles/ms_storage_profile/volume_groups/vg1/file_systems/fs_data > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        logger -s ${LOGGER_TAG} "Updating LITP model for removing ${FS_DATA_MNT_POINT} from model. Please wait."
        CMD="litp remove -p /infrastructure/storage/storage_profiles/ms_storage_profile/volume_groups/vg1/file_systems/fs_data"
        logger ${LOGGER_TAG} "Executing - [${CMD}]"
        ${CMD}
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to run [${CMD}]. Exiting..."
            exit 1
        fi
        logger -s ${LOGGER_TAG} "Creating LITP plan. Please wait."
        litp create_plan 2>&1 | logger ${LOGGER_TAG} 
        if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to create LITP plan. Exiting..."
            exit 1
        fi
        logger -s ${LOGGER_TAG} "Running LITP plan. Please wait."
        litp show_plan 2>&1 | logger ${LOGGER_TAG} 
        litp run_plan
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "litp run_plan exit with non zero. Exiting..."
            exit 1
        fi
        /opt/ericsson/enminst/bin/monitor_plan.sh
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "LITP plan failed. Exiting..."
            exit 1
        fi
    fi
}

#
#   Update the LITP model as required create/run the plan.
#

function fs_vms_handling () {
    CURRENT_DISK_SIZE=$(litp show -p /infrastructure/systems/management_server/disks/disk0 2> /dev/null | grep -w size: 2> /dev/null | awk '{print $NF}' 2> /dev/null )
    CURRENT_DISK_SIZE=${CURRENT_DISK_SIZE%?}
    if [[ ${CURRENT_DISK_SIZE} -lt 600 ]]; then
        CMD="litp update -p /infrastructure/systems/management_server/disks/disk0 -o size=600G"
        logger ${LOGGER_TAG} "Executing - ${CMD}"
        ${CMD}
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to execute - ${CMD}. Exiting..."
            exit 1
        fi
    fi
    CMD="litp create -t file-system -p /infrastructure/storage/storage_profiles/ms_storage_profile/volume_groups/vg1/file_systems/fs_vms -o snap_size=100 -o mount_point=/var/lib/libvirt -o type=ext4 -o size=20G"
    logger ${LOGGER_TAG} "Executing - ${CMD}"
    ${CMD}
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to execute - ${CMD}. Exiting..."
        exit 1
    fi
    logger -s ${LOGGER_TAG} "Creating LITP plan. Please wait."
    litp create_plan 2>&1 | logger ${LOGGER_TAG} 
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to create LITP plan. Exiting..."
        exit 1
    fi
    logger -s ${LOGGER_TAG} "Running LITP plan. Please wait."
    litp show_plan 2>&1 | logger ${LOGGER_TAG} 
    litp run_plan
    if [[ $? -ne 0 ]]; then
    logger -s ${LOGGER_TAG} "litp run_plan exit with non zero. Exiting..."
        exit 1
    fi
    /opt/ericsson/enminst/bin/monitor_plan.sh
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "LITP plan failed. Exiting..."
        exit 1
    fi
}

#
#   Move VM files into new LVM
#
 
function moving_in_esm_data() {
    virsh list --all | grep esmon | grep shut > /dev/null 2>&1 
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "esmon VM is still running. Exiting..."
        exit 1
    fi
    if [[ -d /var/lib/libvirt.ms_relayout ]]; then
        logger -s ${LOGGER_TAG} "Moving esmon VM to new Logical Volume. Please wait..."
        sleep 10
        mount /var/lib/libvirt/ > /dev/null 2>&1
        if [ "$(ls -A /var/lib/libvirt.ms_relayout/)" ]; then
            rm -f /var/lib/libvirt/* > /dev/null 2>&1
            /bin/cp -pR /var/lib/libvirt.ms_relayout/* /var/lib/libvirt/
            if [[ $? -ne 0 ]]; then
                logger -s ${LOGGER_TAG} "Failed to move esmon VM. Exiting..."
                exit 1
            fi
            restorecon -R /var/lib/libvirt > /dev/null 2>&1
            rm -f /var/lib/libvirt.ms_relayout > /dev/null 2>&1
        fi
    fi
}


#
#   Check if the FS is mounted on a given mount point.
#

function is_mounted () {
    fsname=$1
    mount  | grep "on ${fsname} " > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        echo "M0UNTED"
    else
        echo "NOT_MOUNTED"
    fi
}

#
#   Un-Mount the FS
#

function umount_fs() {
    fsname=$1
    IS_MNT=$(is_mounted ${fsname})
    if [[ ${IS_MNT} != "M0UNTED" ]]; then
        logger -s ${LOGGER_TAG} "${fsname} is not mounted."
        return 0
    fi
    logger -s ${LOGGER_TAG} "un-mount ${fsname}."
    #fuser -k ${fsname} > /dev/null 2>&1
    umount ${fsname} 2>&1 | logger ${LOGGER_TAG} 
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to umount ${fsname}."
        exit 1
    fi
}

#
#   Re-name the LVM volume
#

function rename_lvm() {
    OLD_NAME=$1; NEW_NAME=$2
    lvscan | egrep "/${NEW_NAME}" > /dev/null 2>&1
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Logical Volume with new name already exists."
        return
    fi
    lvscan | egrep "/${OLD_NAME}" > /dev/null 2>&1
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "No Logical Volume found [${OLD_NAME}]. Exiting..."
        exit 1
    fi
    logger -s ${LOGGER_TAG} "Re-name the Logical Volume. [${OLD_NAME}->${NEW_NAME}]."
    lvrename vg_root ${OLD_NAME} ${NEW_NAME} | logger ${LOGGER_TAG} 
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to rename the Logical Volume. Exiting..."
        exit 1
    fi
}

#
#   Update the fstab after LVM rename
#

function update_fstab() {
    logger -s ${LOGGER_TAG} "Updating fstab."
    /bin/cp /etc/fstab /etc/fstab.$$
    /usr/bin/perl -pi -e 's|vg1_fs_software|lv_software|g' /etc/fstab
    grep lv_software /etc/fstab > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        mount /software 2>&1 | logger ${LOGGER_TAG} 
        if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to mount the Logical Volume."
            exit 1
        fi
    else
        logger -s ${LOGGER_TAG} "Failed to update the fstab."
        exit 1
    fi
}

#
#   Check if the LVM for software FS is rlready renamed
#


function is_software_lvm_rename_required() {
    REQUIRED=1
    lvs | grep -w lv_software > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        REQUIRED=0
    fi
    return ${REQUIRED}
}

#
#   Check if the fstab is already updated for /software
#


function is_fstab_update_for_software_required() {
    REQUIRED=1
    cat /etc/fstab | grep -w lv_software > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        REQUIRED=0
    fi
    return ${REQUIRED}
}

function stop_lsb_service() {
    LSB_NAME=$1
    if [[ -f /etc/init.d/${LSB_NAME} ]]; then
        logger -s ${LOGGER_TAG} "Stopping ${LSB_NAME}."
        sh /etc/init.d/${LSB_NAME} stop > /dev/null 2>&1
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to stop ${LSB_NAME}."
            exit 1
        fi
    else
        logger ${LOGGER_TAG} "unknown service ${LSB_NAME}."
        exit 1
    fi
}

function start_lsb_service() {
    LSB_NAME=$1
    sh /etc/init.d/${LSB_NAME} status > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        logger -s ${LOGGER_TAG} "Service already running ${LSB_NAME}."
        return 0
    fi
    #service ${LSB_NAME} start > /dev/null 2>&1
    if [[ -f /etc/init.d/${LSB_NAME} ]]; then
        logger -s ${LOGGER_TAG} "Starting ${LSB_NAME}."
        sh /etc/init.d/${LSB_NAME} start > /dev/null 2>&1
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to start ${LSB_NAME}."
            exit 1
        fi
        sleep 5
        sh /etc/init.d/${LSB_NAME} status > /dev/null 2>&1
        if [[ $? -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to start ${LSB_NAME}."
            exit 1
        fi
    else
        logger ${LOGGER_TAG} "unknown service ${LSB_NAME}."
    fi
}


#
#   Moving the ESM data out
#

function moving_out_esm_data() {
    if [[ -d /var/lib/libvirt ]]; then
        if [[ ! -d /var/lib/libvirt.ms_relayout/ ]]; then
            logger -s ${LOGGER_TAG} "Saving esmon VM data. Please wait..."
            fuser -ak /var/lib/libvirt/ > /dev/null 2>&1
            /bin/mv /var/lib/libvirt/ /var/lib/libvirt.ms_relayout/
            if [[ $? -ne 0 ]]; then
                logger -s ${LOGGER_TAG} "Failed to move esmon VM data files. Exiting..."
                exit 1
            fi
        fi
    fi
}

function update_for_stop_esmon() {
    adaptor="/opt/ericsson/nms/litp/lib/litpmnlibvirt/litp_libvirt_adaptor.py"
    adaptor_backup=${adaptor}.ms_relayout_backup
    [[ -e ${adaptor_backup} ]] || /bin/cp -p ${adaptor} ${adaptor_backup}
    echo "exit 0" > $adaptor
}

function update_for_start_esmon() {
    adaptor="/opt/ericsson/nms/litp/lib/litpmnlibvirt/litp_libvirt_adaptor.py"
    adaptor_backup=${adaptor}.ms_relayout_backup
    [[ -e ${adaptor_backup} ]] && /bin/mv ${adaptor_backup} ${adaptor}
}

#
#   Main script for phase_1 option
#

function phase_one() {
    logger -s ${LOGGER_TAG} "Executing script with --phase_1 option, Please wait."
    timeout 30s mount -a > /dev/null 2>&1
    sanity_check
    logger -s ${LOGGER_TAG} "Please wait..."
    check_4_snapshots
    litp export -f /var/tmp/previous_model.$$ -p /
    litpd_wa
    puppet_wa
    fs_data_handling
    puppet_wa 
    stop_lsb_service esmon
    update_for_stop_esmon
    [[ -f /etc/init.d/hyperic-server ]] && stop_lsb_service hyperic-server
    if [[ -f /etc/init.d/mysqld ]]; then
        stop_lsb_service mysqld;
        update_mysql_class;
    fi
    umount_fs ${FS_DATA_MNT_POINT}
    sleep 10
    shrink_fs vg1_fs_data ${FINAL_FS_DATA_SIZE}
    #fs_data_handling
    add_fs_data_into_litp_plan
    puppet_wa
    if [[ -f /etc/init.d/mysqld ]]; then
        undo_update_mysql_class
        start_lsb_service mysqld
    fi
    [[ -f /etc/init.d/hyperic-server ]] && start_lsb_service hyperic-server    
    moving_out_esm_data
    STATE=$(litp show -p /infrastructure/storage/storage_profiles/ms_storage_profile/volume_groups/vg1/file_systems/fs_vms 2> /dev/null | grep -w state: | awk '{print $NF}')
    if [[ "${STATE}" != "Applied" ]]; then
        fs_vms_handling
        puppet_wa
    else
        logger -s ${LOGGER_TAG} "fs_vms LV creation not required..."
    fi
    moving_in_esm_data
    update_for_start_esmon
    start_lsb_service esmon
    #start_lsb_service puppet
    remove_software_from_litp_model
    #puppet_wa_undo
    is_software_lvm_rename_required
    if [[ $? -ne 0 ]]; then
        umount_fs "/software"
        rename_lvm vg1_fs_software lv_software
    fi
    is_fstab_update_for_software_required
    if [[ $? -eq 1 ]]; then
        update_fstab
    fi
    mount | grep "on /software" > /dev/null 2>&1 || mount /software > /dev/null 2>&1
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to mount /software. Exiting..."
        exit 1
    fi
    litpd_wa_undo
    logger -s ${LOGGER_TAG} "Script finished successfully."
}


function usage () {
   local _msg_="$@"
   local scriptname=$(basename $0)

    cat<<-EOF
        Usage -
        Command Arguments:

            -h|--help
                Display the usage message.

            --sanity_check
                 Perform the senity check to ensure the successful execution of this script.

            --phase_1
                Remove the /software from LITP model.
                Rename the Logical Volume for /software and update the fstab.
                Shrink fs_data.
                Add the new Logical Volume for esmon VM.
                Note : During Logical Volume rename the filesystem will be umounted [/software, /varlib/mysql].
                Note : puppet, hyperic-server, mysqld and esmon VM will be shutdown during this phase.

            --phase_2
                Shrink lv_root and lv_var.
                Add extra volume(s) [lv_var_log, lv_var_www]
                Transfer that data into new volumes.
                SELINUX relabel.

EOF
    exit 1
}

#
#   Create a new LVM on vg_root
#

function create_lvm(){
    LVM_NAME=$1
    SIZE=$2
    logger -s ${LOGGER_TAG} "Creating logical volume [${LVM_NAME}/${SIZE}]."
    lvs | grep -w ${LVM_NAME} 2>&1 | logger ${LOGGER_TAG}
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Logical volume already exist. Skipping..."
        return 0
    fi
    lvcreate -n ${LVM_NAME} -L${SIZE}M vg_root | logger ${LOGGER_TAG}
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to create logical volume [${LVM_NAME}/${SIZE}]."
        exit 1
    fi
}

#
#   Create the new filesystem on newly created LVM on vg_root
#

function mkfs() {
    VOL_NAME=$1
    FS_TYPE=$2
    logger -s ${LOGGER_TAG} "Creating filesystem [${VOL_NAME}/${FS_TYPE}]."
    mkfs.${FS_TYPE} /dev/vg_root/${VOL_NAME} 2>&1 | logger ${LOGGER_TAG}
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to create filesystem [${VOL_NAME}/${FS_TYPE}]."
        exit 1
    fi
}

#
#   Perform filesystem check
#

function fsck(){
    VOL_NAME=$1
    FS_TYPE=$2
    activate_lvm ${VOL_NAME}
    logger -s ${LOGGER_TAG} "Running Filesystem check (fsck). Please wait. [${VOL_NAME}/${FS_TYPE}]."
    fsck.${FS_TYPE} -y -f /dev/vg_root/${VOL_NAME} > /tmp/fsck.err 2>&1
    fsck.${FS_TYPE} -p -f /dev/vg_root/${VOL_NAME} > /dev/null 2>&1
    fsck.${FS_TYPE} -p -f /dev/vg_root/${VOL_NAME} 2>&1 | logger ${LOGGER_TAG}
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        RETRY=1
        while [ ${RETRY} -le 5 ]
        do
            logger -s ${LOGGER_TAG} "Filesystem check (fsck) re-try (${RETRY}/5)  [${VOL_NAME}/${FS_TYPE}]."
            fsck.${FS_TYPE} -p -f /dev/vg_root/${VOL_NAME} 2>&1 | logger ${LOGGER_TAG}
            if [[ ${PIPESTATUS[0]} -eq 0 ]]; then
                logger -s ${LOGGER_TAG} "Filesystem check (fsck) is successful."
                return 0
            fi
            RETRY=$((RETRY+1))
        done
        logger -s ${LOGGER_TAG} "Filesystem check (fsck) failed with errors [${VOL_NAME}/${FS_TYPE}]."
        exit 1
    fi
}

#
#   Add the new LVM for automatic mount
#

function fstab_append() {
    VOL_NAME=$1
    FS_TYPE=$2
    NEW_FS_MNT_POINT=$3
    ROOT_MNT_POINT="/tmp/lvm_root"
    logger -s ${LOGGER_TAG} "Updating fstab for ${VOL_NAME}."
    mkdir -p ${ROOT_MNT_POINT} > /dev/null 2>&1
    activate_lvm lv_root
    mount -t ext4 /dev/vg_root/lv_root ${ROOT_MNT_POINT}
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to mount the lv_root filesystem. Exiting...."
        exit 1
    fi
    mkdir -p ${ROOT_MNT_POINT}/${NEW_FS_MNT_POINT} > /dev/null 2>&1
    mkdir -p ${NEW_FS_MNT_POINT} > /dev/null 2>&1
    echo "/dev/vg_root/${VOL_NAME}    ${NEW_FS_MNT_POINT}       ${FS_TYPE}    defaults        0       0" >> /etc/fstab
    mount ${NEW_FS_MNT_POINT}
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to mount the filesystem [${VOL_NAME} on ${NEW_FS_MNT_POINT}]. Exiting...."
        exit 1
    fi
    umount ${NEW_FS_MNT_POINT}
    grep -w "${NEW_FS_MNT_POINT}" ${ROOT_MNT_POINT}/etc/fstab > /dev/null 2>&1
    if [[ $? -ne 0 ]]; then
        OLD_FSTAB_LINES=$(wc -l ${ROOT_MNT_POINT}/etc/fstab | awk '{print $1}')
        cp ${ROOT_MNT_POINT}/etc/fstab ${ROOT_MNT_POINT}/etc/fstab.$$
        cat ${ROOT_MNT_POINT}/etc/fstab | egrep -v "^[ ]*[1-9].+:/vx/" > /tmp/local_fs
        cat ${ROOT_MNT_POINT}/etc/fstab | egrep "^[ ]*[1-9].+:/vx/" > /tmp/remote_fs
        echo "/dev/vg_root/${VOL_NAME}    ${NEW_FS_MNT_POINT}       ${FS_TYPE}    defaults        0       0" >> /tmp/local_fs
        cat /tmp/remote_fs >> /tmp/local_fs
        NEW_FSTAB_LINES=$(wc -l /tmp/local_fs | awk '{print $1}')
        OLD_FSTAB_LINES=$((OLD_FSTAB_LINES+1))
        if [[ ${OLD_FSTAB_LINES} -ne ${NEW_FSTAB_LINES} ]]; then
            logger -s ${LOGGER_TAG} "fstab not updated as expected. Exiting...."
            exit 1
        fi
        cp /tmp/local_fs ${ROOT_MNT_POINT}/etc/fstab
    fi
    umount ${ROOT_MNT_POINT}
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to un-mount '/' filesystem. Exiting...."
        exit 1
    fi

}

#
#   Migrate the data from old LVM to its new own LVMs
#

function migrate_data() {
    OLD_VOL_NAME=$1
    NEW_VOL_NAME=$2
    DATA_PATH=$3
    logger -s ${LOGGER_TAG} "Migrating data from ${OLD_VOL_NAME} logical volume path ${DATA_PATH} into new logical volume ${NEW_VOL_NAME}. Please wait."
    [[ ! -d /tmp/old_vol_mnt ]] && mkdir -p /tmp/old_vol_mnt 
    [[ ! -d /tmp/new_vol_mnt ]] && mkdir -p /tmp/new_vol_mnt 
    umount -f /tmp/old_vol_mnt > /dev/null 2>&1
    umount -f /tmp/new_vol_mnt > /dev/null 2>&1
    activate_lvm ${OLD_VOL_NAME}
    activate_lvm ${NEW_VOL_NAME}
    fsck ${OLD_VOL_NAME} ext4
    fsck ${NEW_VOL_NAME} ext4
    mount -t ext4 /dev/mapper/vg_root-${OLD_VOL_NAME} /tmp/old_vol_mnt
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to mount ${OLD_VOL_NAME}. Exiting...."
        exit 1
    fi
    mount -t ext4 /dev/mapper/vg_root-${NEW_VOL_NAME} /tmp/new_vol_mnt
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to mount ${NEW_VOL_NAME}. Exiting...."
        exit 1
    fi
    logger -s ${LOGGER_TAG} "Please wait, It can take a long time."
    move_files /tmp/old_vol_mnt/ /tmp/new_vol_mnt ${DATA_PATH}
    umount -f /tmp/new_vol_mnt > /dev/null 2>&1
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to un-mount [${NEW_VOL_NAME}]. Exiting...."
    fi
    umount -f /tmp/old_vol_mnt > /dev/null 2>&1
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to un-mount [${OLD_VOL_NAME}]. Exiting...."
        exit 1
    fi
}

#
#   move files
#

function move_files() {
    MOVE_FROM=$1
    MOVE_TO=$2
    DATA_PATH=$3
    logger -s ${LOGGER_TAG} "Moving files from [${MOVE_FROM}/${DATA_PATH} to ${MOVE_TO}], Please wait."
    MOVE_FROM_USAGE=$(get_fs_usage ${MOVE_FROM}/${DATA_PATH}/)
    MOVE_TO_SPACE_AVAILABLE=$(df -lm /tmp/new_vol_mnt/ | awk '{print $3}' | grep "[0-9]")
    if [[ ${MOVE_FROM_USAGE} -gt ${MOVE_TO_SPACE_AVAILABLE} ]]; then
        logger -s ${LOGGER_TAG} "mv -v ${MOVE_FROM}/${DATA_PATH}/* ${MOVE_TO}"
        logger -s ${LOGGER_TAG} "Unable to move the files, not enough space on target location. [${MOVE_FROM_USAGE} MB /${MOVE_TO_SPACE_AVAILABLE} MB]. Exiting..."
        exit 1
    fi
    echo "mv -v ${MOVE_FROM}/${DATA_PATH}/* ${MOVE_TO}" >> /tmp/mv_warnings 2>&1
    mv -v ${MOVE_FROM}/${DATA_PATH}/* ${MOVE_TO} >> /tmp/mv_warnings 2>&1
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to move data from ${MOVE_FROM} to ${MOVE_TO}. Exiting...."
        exit 1
    fi
}

#
#
#   Shrink the filesystem to the final required size
#

function shrink_fs () {
    LV_NAME=$1
    FINAL_SIZE=$2 #In MBs
    CURRENT_LV_SIZE=$(lvs --units m | grep -w ${LV_NAME} | awk '{print $NF}' | awk -F '.' '{print $1}')
    if [[ ${CURRENT_LV_SIZE} -gt ${FINAL_SIZE} ]]; then
        logger -s ${LOGGER_TAG} "Re-size Logical Volume [${LV_NAME}] to [${FINAL_SIZE}]"
        SIZE_B4_LV_RESIZE=$((FINAL_SIZE-BUFFER_SPACE))
        logger -s ${LOGGER_TAG} "Running fsck, Please wait...[${LV_NAME}]."
        fsck ${LV_NAME} ext4
        resize2fs /dev/vg_root/${LV_NAME} ${SIZE_B4_LV_RESIZE}M  2>&1 | logger  ${LOGGER_TAG}
        if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to re-size fs [${LV_NAME}/${SIZE_B4_LV_RESIZE}]. Exiting...."
            exit 1
        fi
        lvreduce -f -L ${FINAL_SIZE}M vg_root/${LV_NAME} 2>&1 | logger ${LOGGER_TAG}
        if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to re-size Logical Volume [${LV_NAME}/${FINAL_SIZE} MB]. Exiting...."
            exit 1
        fi
        fsck ${LV_NAME} ext4 > /dev/null 2>&1
        resize2fs /dev/vg_root/${LV_NAME} 2>&1 | logger ${LOGGER_TAG}
        if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
            logger -s ${LOGGER_TAG} "Failed to re-size fs [${LV_NAME}/${FINAL_SIZE}]. Exiting...."
            exit 1
        fi
        fsck ${LV_NAME} ext4 > /dev/null 2>&1
    fi
}


#
#   Main function for phase_2
#

function phase_two() {
    logger -s ${LOGGER_TAG} "Executing script with --phase_2 option, Please wait."
    check_4_snapshots
    fsck lv_var ext4
    fsck lv_root ext4
    create_lvm lv_var_log ${VAR_VOL_SIZE}
    create_lvm lv_var_www ${VAR_WWW_HTML_VOL_SIZE}
    mkfs lv_var_log ext4
    mkfs lv_var_www ext4
    fstab_append lv_var_log ext4 /var/log
    fstab_append lv_var_www ext4 /var/www
    migrate_data "lv_var" "lv_var_log" "/log"
    migrate_data "lv_var" "lv_var_www" "/www"
    shrink_fs lv_root ${FINAL_ROOT_VOL_SIZE}
    shrink_fs lv_var ${FINAL_VAR_VOL_SIZE}
    auto_lable
    logger -s ${LOGGER_TAG} "Script finished successfully."
}

#
#   Enable auto-relabel on next reboot
#

function auto_lable() {
    logger -s ${LOGGER_TAG} "SELinux relabel."
    activate_lvm lv_root
    mkdir -p /tmp/lvm_root > /dev/null 2>&1
    mount /dev/vg_root/lv_root /tmp/lvm_root
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to mount root LV. Exiting...."
        exit 1
    fi
    touch /tmp/lvm_root/.autorelabel
    if [[ $? -ne 0 ]]; then
        logger -s ${LOGGER_TAG} "Failed to touch file for autorelabel. Exiting...."
        exit 1
    fi
    #Add the syslog into the root disk
    cp /tmp/syslog ${ROOT_MNT_POINT}/root/
    cp /tmp/mv_warnings ${ROOT_MNT_POINT}/root/
    umount /tmp/lvm_root > /dev/null 2>&1
}


function process_arguments() {
   short_args="h"
   long_args="sanity_check,phase_1,help,phase_2"
   args=$(getopt -o $short_args -l $long_args -n "$0"  -- "$@"  2>&1 )
   [[ $? -ne 0 ]] && { echo "Invalid arguments, use --help for more details."; exit 1; }
   [[ $# -eq 0 ]] && { echo "Invalid arguments, use --help for more details."; exit 1; }
   eval set -- "$args"
   cmd_arg="$0"
   while true; do
          case "$1" in
            -h|--help)
                    usage
                    shift 1 ;;
             --phase_1)
                    phase_one
                    shift 1 ;;
            --sanity_check)
                    sanity_check
                    shift 1 ;;
             --phase_2)
                    phase_two
                    shift 1 ;; 
             --)
                    shift
                    break ;;
             *)
                    echo "BAD ARGUMENTS, Use --help for more Details" # perhaps error
                    break ;;
         esac
       done
}

function litpd_wa() {
    [[ ! -f /etc/litpd.conf_ms_relayout ]] && cp -p /etc/litpd.conf /etc/litpd.conf_ms_relayout
    sed -i 's/^puppet_poll_count = .*/puppet_poll_count = 15/' /etc/litpd.conf
    grep -q 'puppet_poll_count = 15' /etc/litpd.conf 
    [[ $? -ne 0 ]] && { echo "error modifying litpd.conf"; exit 1; }
    stop_lsb_service litpd
    start_lsb_service litpd
    
}

function puppet_wa() {
  
    puppet agent --disable
    while [[ -f $(puppet config print agent_catalog_run_lockfile) ]]
    do
        logger -s ${LOGGER_TAG} "Puppet Agent Running";
        sleep 5
    done
    logger -s ${LOGGER_TAG} "Puppet Agent Not Running"

    # Remove Cached Catalogue
    /bin/rm -f /var/lib/puppet/client_data/catalog/*
}

function litpd_wa_undo() {
    sed -i 's/^puppet_poll_count = .*/puppet_poll_count = 5/' /etc/litpd.conf
    grep -q 'puppet_poll_count = 5' /etc/litpd.conf
    [[ $? -ne 0 ]] && { echo "error setting back original value in litpd.conf"; exit 1; }
    stop_lsb_service litpd
    start_lsb_service litpd
    puppet agent --enable
}


#main 
LOGGER_TAG="-t [MS_DISK_RELAYOUT]"
BUFFER_SPACE=15 #Percent
VAR_VOL_SIZE=20480 #MB This is the variable  for the /var/log LVM size.
VAR_WWW_HTML_VOL_SIZE=71680 #MB
REQUIRED_PV_FREE_SIZE=$((VAR_VOL_SIZE+VAR_WWW_HTML_VOL_SIZE)) #MB
FINAL_ROOT_VOL_SIZE="15360"
FINAL_VAR_VOL_SIZE="15360"
LV_ROOT_USAGE=$(df -lm | grep -w "/$" | awk '{print $2}')
LV_VAR_USAGE=$(df -lm | grep -w "/var$" | awk '{print $2}')
CURRENT_FS_DATA_SIZE=$(lvdisplay /dev/vg_root/vg1_fs_data | grep "LV Size" | awk '{print $3}' | awk -F '.' '{print $1}')
CURRENT_FS_DATA_SIZE_IN_MB=$((CURRENT_FS_DATA_SIZE*1024))
FINAL_FS_DATA_SIZE=25600
MODIFY_FS_DATA="FALSE"
if [[ ${CURRENT_FS_DATA_SIZE_IN_MB} -gt ${FINAL_FS_DATA_SIZE} ]]; then
    MODIFY_FS_DATA="TRUE"
else
    logger -s ${LOGGER_TAG} "fs_data LV resize is not required."
fi
process_arguments "$@"
