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
# Name    : patch_rhel.sh
# Purpose : Automatic deployment of RHEL patches on Management Server
#           and/or Peer Servers.
#
# Usage   : See usage function below.
#
# ********************************************************************

SED='/bin/sed'
RM='/bin/rm'
PYTHON='/usr/bin/python'
LN='/usr/bin/ln -sf'
UNLINK='/usr/bin/unlink'
MKDIR='/usr/bin/mkdir -p'

export ENMINST_VERSION="$(rpm -qa | awk -F- '/^ERICenminst_/{print $2}')"
export ENMINST_SCRIPT="$(readlink -f $0)"
export ENMINST_HOME="$(readlink -e ${ENMINST_SCRIPT%/*}/..)"
export ENMINST_LIB=${ENMINST_HOME}/lib
export PYTHONPATH=${ENMINST_LIB}:${PYTHONPATH}
export ENMINST_LOG="${ENMINST_HOME}/log"
export ENMINST_ETC="${ENMINST_HOME}/etc"
export ENMINST_CFG_FILE="${ENMINST_ETC}/enminst_cfg.ini"
export ENMINST_ARGS=""

function getConfigParameter() {
   configValueName=$1
   ${SED} -n "s/${configValueName}=\(.*\)/\1/p" "${ENMINST_CFG_FILE}"
}

export PATCH7_VERS_FILE=$(getConfigParameter RHEL7_VERSION_FILENAME)
export PATCH7_HIST_FILE=$(getConfigParameter RHEL7_HISTORY_FILENAME)
export RHEL7_CXP_TGZ=$(getConfigParameter RHEL7_OS_PATCH_CXP_TGZ)
export RHEL7_CXP_ISO=$(getConfigParameter RHEL7_OS_PATCH_CXP_ISO)
export PATCH8_VERS_FILE=$(getConfigParameter RHEL8_VERSION_FILENAME)
export PATCH8_HIST_FILE=$(getConfigParameter RHEL8_HISTORY_FILENAME)
export RHEL8_CXP_ISO=$(getConfigParameter RHEL8_OS_PATCH_CXP_ISO)

export LOG_FILE="patch_rhel.log"
export STAGE_FILE="$ENMINST_HOME/etc/patches.stage"
export RHEL7_VERSION=$(getConfigParameter RHEL7_VER)
export RHEL8_VERSION=$(getConfigParameter RHEL8_VER)
export RHEL7_dir="/var/www/html/${RHEL7_VERSION}/updates/x86_64/Packages"
export RHEL8_BaseOS_dir="/var/www/html/${RHEL8_VERSION}/updates_BaseOS/x86_64/Packages"
export RHEL8_AppStream_dir="/var/www/html/${RHEL8_VERSION}/updates_AppStream/x86_64/Packages"
export RHEL7_JSON="/etc/ericrhel79-release"
export RHEL8_JSON="/etc/ericrhel88-release"

export AUTO_REBOOT=yes
export DEP_TYPE=ms
export ENMDEP_NAME=ENM
export LITP_TIMEOUT=30 # Seconds
export PATCHES=()

# ------------------------------------------------------------------------------
# Arguments processing functions, copied shamelessly from deploy_enm.sh
# ------------------------------------------------------------------------------
function usage() {
cat<<-EOF

    RedHat patching.  Version: $ENMINST_VERSION

    Command Arguments

             -t, --type
                 Optional argument.  "ms" or "peer", default to "ms"
                 What should be upgraded.

             -d, --deployment
                 Optional argument.  Default to "ENM"
                 Name of LITP deployment to upgrade (for peer servers).

             -p, --patch Patch File
                 Mandatory argument.  Full path of patches file.
                 Can accept up to 3 patch files, must be seperated by a comma.

             -R, --noreboot
                 Optional argument.  Avoid automatic reboot.

             -v, --verbose
                 Optional argument.  Verbose logging.

             -h, --help
                 Optional argument.  Display this usage.

             -V, --version
                 Optional argument.  Display both script and ERICenminst package versions.

    Examples:

    # ${ENMINST_SCRIPT##*/} --type ms --patch /var/tmp/Patches.iso --noreboot --verbose
    # ${ENMINST_SCRIPT##*/} -p /var/tmp/Patches.iso
    # ${ENMINST_SCRIPT##*/} -p /var/tmp/Patch_1.iso,/var/tmp/Patch_2.iso

EOF
exit 2
}

# Called when script is executed with invalid arguments
function invalid_arguments() {
   local scriptname=$(basename $0)
   echo "Missing or invalid option(s):"
   echo "$@"
   echo "Try $scriptname --help for more information"
   log ERROR "Invalid options passed to script ($@) "
   exit 1
}

# Process the options and arguments passed to the script and export relevant variables
function process_arguments() {
   local short_args="Vvhp:d:Rt:"
   local long_args="version,verbose,help,patch:,deployment:,noreboot,type:"
   declare -a values

   log INFO "Processing Options and Arguments"
   if [[ $# -eq 0 ]] ; then
      log ERROR "Missing mandatory arguments"
      echo "Missing mandatory arguments, see '${ENMINST_SCRIPT%%*/} --help'" >&2
      exit 2
   fi

   while [[ $# -gt 0 ]]; do
      case "$1" in
         -V|--version)
            log INFO "Versions required"
            echo "ENMinst version: ${ENMINST_VERSION}"
            echo "${ENMINST_SCRIPT##*/} date: $(date --ref ${ENMINST_SCRIPT} +%Y-%m-%d\ %H:%M:%S)"
            exit 0
            ;;

         -t|--type)
            values="=ms=peer="
            if [ "${values/=${2}=}" = "${value}" ] ; then
               log ERROR "${2} is not an acceptable value for ${1}"
               echo "'${2}' is not an acceptable value for '${1}', see '${ENMINST_SCRIPT%%*/} --help'" >&2
               exit 2
            fi
            export DEP_TYPE="$2"
            log INFO "Deployement Type option set to: $DEP_TYPE"
            ENMINST_ARGS="${ENMINST_ARGS} $1 $2"
            shift 2
            ;;

         -p|--patch)
            ENMINST_ARGS="${ENMINST_ARGS} $1 "
            shift

            PATCHES_STRING=""
            for i in $@; do
              [[ "$i" == -* ]] && break
              PATCHES_STRING+="$i"
              shift
            done

            IFS=',' read -a PATCHES_READ <<< "$PATCHES_STRING"
            PATCHES+=( "${PATCHES_READ[@]}" )
            if [[ "${#PATCHES[@]}" -eq 0 ]] ; then
                log ERROR "Missing patch file"
                echo "No patch file provided. At least one patch file must be provided with -p | --patch option, see '${ENMINST_SCRIPT%%*/} --help'" >&2
                exit 2
            fi
            for i in "${PATCHES[@]}" ; do
                if ! [[ -f "${i}" && -r "${i}" && -s "${i}" ]] ; then
                    log ERROR "'${i}' is not a valid file"
                    echo "'${i}' is not a valid file, see '${ENMINST_SCRIPT%%*/} --help'" >&2
                    exit 2
                fi
                log INFO "Patch File option set to: ${i}"
                ENMINST_ARGS="${ENMINST_ARGS} $(readlink -f ${i}),"
            done

            duplicates=$(printf '%s\n' "${PATCHES[@]}"|awk '!($0 in seen){seen[$0];next} 1')
            if [[ -n "$duplicates" ]] ; then
                log ERROR "Patch file(s) $duplicates are duplicated. Patch files must be different"
                echo "Patch file(s) $duplicates are duplicated. Patch files must be different"
                exit 2
            fi
            ;;

         -d|--deployment)
            export ENMDEP_NAME=$2
            log INFO "Deployment Name option set to: $ENMDEP_NAME"
            ENMINST_ARGS="${ENMINST_ARGS} $1 $2"
            shift 2
            ;;

         -v|--verbose)
            log_debug
            ENMINST_ARGS="${ENMINST_ARGS} $1"
            shift
            ;;

         -h|--help)
            usage
            exit 0
            ;;

         -R|--noreboot)
            export AUTO_REBOOT=no
            ENMINST_ARGS="${ENMINST_ARGS} $1"
            shift
            ;;

         --)
            shift
            break
            ;;

         *)
            invalid_arguments "${1}"
            ;;
      esac
   done

   log INFO "Arguments processed successfully"
   log INFO $ENMINST_ARGS
   return 0
}



# ------------------------------------------------------------------------------
# Patching functions
# ------------------------------------------------------------------------------



### Function: cleanup_autostart ###
#
# This function will disable and remove the patch_rhel service in order to avoid
# recalling endlessly the script.
#
#   Arguments: none
#
#   Return Values: None
#
function cleanup_autostart() {
   systemctl disable patch_rhel.service 2>/dev/null
   ${RM} /usr/local/lib/systemd/system/patch_rhel.service 2>/dev/null
   systemctl daemon-reload
}


### Function: init_autostart ###
#
# This function will create and enable systemd service in order to recall the
# script at the end of the reboot.
# It will create a service that will start the after litpd is up
#
#   Arguments: none
#
#   Return Values: None
#
function init_autostart() {
   cat > /usr/local/lib/systemd/system/patch_rhel.service <<EOF
[Unit]
Description=Runs ${ENMINST_SCRIPT} to continue patching
After=litpd.service
[Service]
Type=oneshot
ExecStart=${ENMINST_SCRIPT} ${ENMINST_ARGS}
[Install]
WantedBy=multi-user.target
EOF
   systemctl daemon-reload
   systemctl enable patch_rhel.service 2>/dev/null
}


### Function: manage_reboot ###
#
# This function is used to handle the script flow across the necessary reboot.
#
#   Arguments:
#       1 - one of:
#              INIT    : used at start to catch the environnement and prepare
#                        for controlling the script execution.
#              PREPARE : will setup everything to be able to automatically
#                        continue after the next reboot.
#                        The reboot must be executed manually.
#              REBOOT  : will setup like PREPARE and automatically
#                        reboot the server.
#              REMOVE  : cleanup anything, will delete the stages file, so
#                        must be called only at the end of script execution.
#              GET     : output the actual stage.
#
#   Return Values: None
#
function manage_reboot() {
   local rstage
   local reboot_delay=5  # Waiting time for the reboot

   case $(echo -n "$1"  | tr '[:lower:]' '[:upper:]') in
   INIT)
      if ! [ -r "$STAGE_FILE" ] ; then
         # Initial run: initialize the stage file and ensure rc.local is clean
         echo "init" > "$STAGE_FILE"
         cleanup_autostart
         log DEBUG "Starting, no reboot file found"
      else
         rstage=$(manage_reboot GET)
         log DEBUG "Starting, reboot stage is '$rstage'"
         case $rstage in
         init)
            # Do nothing, the script was aborted in an early stage
            ;;
         prepreboot)
            cleanup_autostart
            if [ /var/log/dmesg -nt "$STAGE_FILE" ] ; then
               # Reboot was executed manually.
               log INFO "Reboot was executed manually, continuing"
               echo "postreboot" > "$STAGE_FILE"
            else
               # Reboot still not done, ensure rc.local is set.
               log INFO "Reboot was prepared, but not executed manually."
               init_autostart
            fi
            ;;
         reboot)
            # Reboot just executed, clean rc.local and continue
            cleanup_autostart
            log INFO "Reboot was executed automatically, continuing"
            echo "postreboot" > "$STAGE_FILE"
            ;;
         postreboot)
            # Reboot has been done, ensure rc.local is clean
            log INFO "Reboot handling finished, continuing"
            cleanup_autostart
            ;;
         esac
      fi
      ;;

   PREPARE)
      # Prepare the reboot, but don't execute it. Will be executed outside.
      log DEBUG "Reboot preparation required"
      echo "prepreboot" > "$STAGE_FILE"
      init_autostart
      ;;

   REBOOT)
      # Execute the reboot now.
      log DEBUG "Rebooting in ${reboot_delay} sec!"
      echo "reboot" > "$STAGE_FILE"
      init_autostart
      sleep ${reboot_delay}
      shutdown -r now
      # Endlessly wait for the reboot to execute...
      while true; do sleep 1; done
      ;;

   REMOVE)
      # Final cleanup.
      log DEBUG "Cleaning up"
      cleanup_autostart
      ${RM} -f "$STAGE_FILE"
      log DEBUG "Clean up complete"
      ;;

   GET)
      # Return the current reboot stage.
      if [ -r "$STAGE_FILE" ] ; then
         echo $(sed $'/^[ \t]*#/d;s/ //g;q' "$STAGE_FILE")
      else
         echo "none"
      fi
      ;;

   esac
}


### Function: _litp ###
#
# This function is used internally to execute litp commands.
# It is a wrapper to handle a possible running plan, before command execution
# and optionnaly wait for the created plan to complete.
#
#   Arguments:
#       1 - a litp command
#
#       2 - timeout: the time in seconds to wait for an existing
#                    plan execution to finish
#
#       3 - maxwait time: the time (in seconds) to wait for
#                         the snapshot command to complete
#
#   Return value: None
#
function _litp() {
   local timeout=${2:-${LITP_TIMEOUT}}
   local maxwait=${3:-0}
   local starttime=$(date +%s)
   local status

   log DEBUG "Looking for an existing plan"
   status=$(litp show_plan --active 2>&1 | tail -1 | sed 's/^ *\([^ ]*\).*$/\1/')
   if [ "$status" != "InvalidLocationError" ] ; then
      # A plan exists, so we need to check the status
      log DEBUG "Checking existing plan status"
      while [ $(( $(date +%s)-$starttime )) -lt $timeout ] ; do
         status="$(litp show --path /plans/plan/ --options state)"
         [ "$status" != "running" ] && break
         sleep 1
      done
      if [ "$status" = "running" ] ; then
         error "Timeout waiting to send snapshot command: ${1}, check status of LITP plan"
      fi
   fi

   # Ready to execute the litp command
   log DEBUG "Executing 'litp ${1}'"
   if ! result=$(litp ${1} 2>&1) && [ "$result" = "${result/DoNothingPlanError}" ] ; then
      error "'${1} snapshot' fails: ${result}"
   fi

   # If requested, wait for the litp command to finish
   if [ "$maxwait" -gt 0 ] ; then
      status=$(litp show_plan --active 2>&1 | tail -1 | sed 's/^ *\([^ ]*\).*$/\1/')
      if [ "$status" != "InvalidLocationError" ] ; then
         log DEBUG "Waiting for plan to execute..."
         starttime=$(date +%s)
         sleep 3 # ensure the plan is running
         while [ $(( $(date +%s)-$starttime )) -lt $maxwait ] ; do
            sleep 1
            status="$(litp show --path /plans/plan/ --options state)"
            [ "$status" != "running" ] && break
         done
         if [ "$status" = "running" ] ; then
            error "Timeout waiting snapshot command ${1} to finish, check status of LITP plan"
         fi
      fi
   fi
}


### Function: createLitpSnapshot ###
#
# This function will create a litp snapshot, waiting for the plan execution
# to finish
#
#   Arguments: None
#
#   Return Values: None
#
function createLitpSnapshot() {
   log DEBUG "Creating snapshots"
   _litp create_snapshot "" 60
}


### Function: removeLitpSnapshot ###
#
# This function will remove a possible existing litp snapshot
#
#   Arguments: None
#
#   Return Values: None
#
function removeLitpSnapshot() {
   log DEBUG "Removing snapshots"
   _litp remove_snapshot "" 60
}


### Function: installPatchVersion_rpm ###
#
# This function will install RHEL version package based on patch
# target directory provided
#
#   Arguments:
#       1 - $package_target_directory
#       2 - JSON patch information file
#       3 - RHEL patch version file
#       4 - RHEL patch history file
#
#   Return Values: None
#
function installPatchVersion_rpm() {
   # Get package target directory and parse it for package name only
   pkgtarget=$1
   jsonfile=$2
   versionfile=$3
   historyfile=$4
   pkgpath=$(find ${pkgtarget}/ -name 'RHEL_OS_Patch_Set_CXP*' 2>&1)
   # Check pkgpath
   [[ -n "${pkgpath}" ]] || error "Could not find path to patch set package"
   [[ -f "${pkgpath}" ]] || error "Patch set package ${pkgpath} is not a file"
   pkgrpm=$(basename ${pkgpath})
   pkgname=${pkgrpm%%-*}

   # Parse through the patch provided to get the name only
   log INFO "Checking rpm ${pkgname} is installed"
   check_rpm_installed=$(yum list installed ${pkgname} 2>&1)
   if [ $? -eq 0 ] ; then
       remove_rpm=$(yum -y remove ${pkgname} 2>&1) || error "Unable to remove ${pkgname} packages. Reason: ${remove_rpm}"
       log INFO "Previous ${pkgname} successfully removed"
   fi
   # Install RHEL package version rpm
   log INFO "Installing ${pkgrpm}"
   install_rpm=$(yum -y install ${pkgpath} 2>&1) || error "Failed to install ${pkgrpm}"
   log INFO "${pkgrpm} successfully installed"
   # Update RHEL version and history based on the JSON file passed in
   $PYTHON -c "import import_iso_version; import_iso_version.update_rhel_version_and_history('${jsonfile}','${versionfile}', '${historyfile}')" || error $?

   log INFO "RHEL patch set version successfully updated"
}

### Function: importPackage ###
#
# This function will import RHEL packages using LITP
#
#
#   Arguments:
#       2 - $package_source_directory $package_target_directory
#
#   Return Values: None
#
function importPackage() {
   pkgsource=$1
   pkgtarget=$2
   # Check if they are valid directories
   [[ -d "${pkgsource}" ]] || error "Source directory for LITP import is missing"
   [[ -d "${pkgtarget}" ]] || error "Target directory for LITP import is missing"
   log DEBUG "Patch file is "${pkgtarget}""
   log INFO "Importing packages, please wait..."
   log DEBUG "Source is ${pkgsource}"
   log DEBUG "Target is ${pkgtarget}"
   if ! result=$(litp import "${pkgsource}" "${pkgtarget}" 2>&1) ; then
       error "LITP failed to import packages: ${result}"
   fi
}

### Function: importRhel7Patches ###
#
# This function will run LITP import on RHEL 7 packages
#
#   Arguments:
#       1 - $package_source_dir
#
#   Return Values: None
#
function importRhel7Patches() {
   # Get package source and target directory
   pkgsource=$1
   # Get RHEL 7 updates packages directory.
   # Directory structure is given from RedHat, uncertain is the case of "packages".
   pkgtarget="$(find /var/www/html -type d -name Packages | grep "/7" | grep updates | sort | tail -1)"
   [[ -n "${pkgtarget}" ]] || error "Patches directory does not exist, unable to continue"
   [[ -d "${pkgtarget}" ]] || error "Patches directory ${pkgtarget} is not a directory, unable to continue"
   # TORF-520465 - If system clock has been rolled back after LMS kickstart, the time disparity between
   # the directory metadata and timestamp can cause the package manager to think that no update is required
   createrepo "${pkgtarget}"
   yum --disablerepo="*" --enablerepo="UPDATES" clean all
   # Import packages
   importPackage $pkgsource $pkgtarget
   #Install package version rpm
   installPatchVersion_rpm "$pkgtarget" "$RHEL7_JSON" "$PATCH7_VERS_FILE" "$PATCH7_HIST_FILE"
}

function importRhel8Patches() {
   # Get package source and target directory
   BaseOS_pkgsource=$1
   AppStream_pkgsource=$2
   # Get RHEL 8 updates packages directory.
   # Directory structure is given from RedHat, uncertain is the case of "packages".
   ${MKDIR} ${RHEL8_BaseOS_dir} ${RHEL8_AppStream_dir}
   BaseOS_pkgtarget=${RHEL8_BaseOS_dir}
   AppStream_pkgtarget=${RHEL8_AppStream_dir}
   # TORF-520465 - If system clock has been rolled back after LMS kickstart, the time disparity between
   # the directory metadata and timestamp can cause the package manager to think that no update is required
   # Import packages
   createrepo "${BaseOS_pkgtarget}"
   importPackage $BaseOS_pkgsource $BaseOS_pkgtarget
   importPackage $AppStream_pkgsource $AppStream_pkgtarget
   #Install package version rpm
   installPatchVersion_rpm "$BaseOS_pkgtarget" "$RHEL8_JSON" "$PATCH8_VERS_FILE" "$PATCH8_HIST_FILE"
}

#
### Function: patch_ms ###
#
# This function will execute all steps to load one or more RedHat patches cluster
# on the management server. The server will be rebooted during the process.
#
#   Arguments:
#       1 - the patches cluster file (can be an ISO image or a tar file).
#
#   Return Values: None
#
function patch_ms() {
   local tempdir
   local filetype
   local pkgsource
   local pkgtarget
   local result

   result="$(manage_reboot GET)"
   log DEBUG "Reboot stage is ${result}"
   case "$result" in
   init)
      log HEADER "Patching RHEL in Management Server"
      ;;

   postreboot)
      removeLitpSnapshot
      log INFO "Continuing..."
      log_header "RHEL patching successfully executed on Management Server"
      return 0
      ;;

   *)
      log INFO "Skipping RHEL patches"
      return 0

   esac

   removeLitpSnapshot
   createLitpSnapshot

   # Directory structure is given from RedHat, root dir "/var/www/html" is from LITP configuration.
   # Loop through patch files
   for patch in ${PATCHES[@]} ; do
       tempdir=$(mktemp -d)
       filetype=$(file -b ${patch})
       if [ "${filetype}" != "${filetype/ISO 9660}" ] ; then
           # It is an iso image file
           log INFO "Mounting image on ${tempdir}"
           mount -o loop "${patch}" "${tempdir}" || error "Unable to mount the ISO image, check ${tempdir} and/or ${patch}"
       else
           # Assume it is a tar/gzip file
           log INFO "Extracting patches in ${tempdir}"
           tar --extract --directory="$tempdir" --file="${patch}" || error "Unable to extract the packages, check ${tempdir} and/or ${patch}"
       fi
       # Get RHEL patch CXP number
       patchcxp=$(find ${tempdir}/ -name 'RHEL_OS_Patch_Set_CXP*' | xargs rpm2cpio | cpio -i --to-stdout ./etc/ericrhel* | grep '"cxp":')
       # Check patchcxp
       [[ -n "${patchcxp}" ]] || error "Patch CXP is empty, unable to continue"
       # Clean up CXP number to just be the number
       eval cxpline=(${patchcxp})
       patchcxp=${cxpline[1]//[,]/}
       # Check if patch file is RHEL 7 or 8.
       if [ ${patchcxp} == ${RHEL7_CXP_ISO} ] ; then
           # Import RHEL 7 patches
           pkgsource="$(find $tempdir -type d -name packages | head -1)"
           # Check pkgsource
           [[ -n "${pkgsource}" ]] || error "Source directory does not exist, unable to continue"
           [[ -d "${pkgsource}" ]] || error "Source directory ${pkgsource} is not a directory, unable to continue"
           importRhel7Patches ${pkgsource}
       elif [ ${patchcxp} == ${RHEL8_CXP_ISO} ] ; then
           # Import RHEL 8 patches
           BaseOS_pkgsource="$(find $tempdir -type d -name Packages | grep "BaseOS" | head -1)"
           AppStream_pkgsource="$(find $tempdir -type d -name Packages | grep "AppStream" | head -1)"
           [[ -n "${BaseOS_pkgsource}" ]] || error "Source directory does not exist, unable to continue"
           [[ -d "${BaseOS_pkgsource}" ]] || error "Source directory ${BaseOS_pkgsource} is not a directory, unable to continue"
           [[ -n "${AppStream_pkgsource}" ]] || error "Source directory does not exist, unable to continue"
           [[ -d "${AppStream_pkgsource}" ]] || error "Source directory ${AppStream_pkgsource} is not a directory, unable to continue"
           importRhel8Patches ${BaseOS_pkgsource} ${AppStream_pkgsource}
       else
           error "No valid patch set determined. ${patchcxp}"
       fi
       # Clean up temp directories
       log DEBUG "Cleaning..."
       grep -q "$tempdir" /proc/mounts && umount "$tempdir"
       rm -rf "$tempdir"
   done

   log INFO "Activating patches, please wait..."
   result=$(yum -y --disablerepo=* --enablerepo=UPDATES upgrade 2>&1) || error "Failed to yum packages: $(echo; echo ${result} | tail -5)"

   log INFO "Ready for reboot"
   cat <<-EOT
    =============================================================
    RedHat patches have been loaded.
    In order to activate them, a reboot is necessary.

    The installation will continue automatically after the reboot.

    After the reboot, the progress of the installation can be
    followed in ${ENMINST_LOG}/${LOG_FILE}
    =============================================================
EOT
   if [ "$AUTO_REBOOT" = "yes" ] ; then
      manage_reboot REBOOT
   else
      manage_reboot PREPARE
      cat <<-EOT

          You have chosen to reboot manually, please do it now.
          =============================================================
EOT
      exit 3
   fi
}



### Function: patch_peer ###
#
# This function will execute all steps to load a RedHat patches cluster on the
# peer server. These servers will be rebooted if any kernel patche is present.
#
#   Arguments:
#       None
#
#   Return Values: None
#
function patch_peer() {
   local deployments d
   local result

   log HEADER "Patching RHEL in Peer Servers"

   # Do nothing, placeholder
   log FATAL "Peers patching not implemented, please try again with the next release..."
   exit 99

   removeLitpSnapshot
   createLitpSnapshot

   # Search for the current deployment name
   deployments="$(litp show -p /deployments -l | sed '/deployments$/d;s/^.*deployments\///')"
   for d in $deployments; do
      [ "$ENMDEP_NAME" = "$d" ] && break
   done
   [ "$ENMDEP_NAME" != "$d" ] && error "Unable to find the deployment \"${ENMDEP_NAME}\", check the arguments!"

   # This command will upgrade all nodes included in the deployment.
   # In future, we may may have to upgrade only selected nodes,
   # to do so we will have to go deeper in the path...
   log DEBUG "Setting the environnement to upgrade to ${ENMDEP_NAME}"
   if ! result=$(litp upgrade -p "/deployments/${ENMDEP_NAME}/") ; then
      error "Upgrading /deployments/${ENMDEP_NAME} fails, unable to continue: ${result}"
   fi

   log DEBUG "Creating plan"
   if ! result=$(litp create_plan 2>&1) ; then
      error '"litp create_plan"'"fails, unable to continue: ${result}"
   fi

   log DEBUG "Running plan"
   if ! result=$(litp run_plan 2>&1) ; then
      error '"litp run_plan"'"fails, unable to continue: ${result}"
   fi

   removeLitpSnapshot
}


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

source "${ENMINST_LIB}/enminst_utils.lib" || { echo "Unable to source ${ENMINST_LIB}/enminst_utils.lib" >&2; exit 1; }
log_init "$ENMINST_LOG/$LOG_FILE" || { echo "Cannot set up logging with $ENMINST_LOG/$LOG_FILE" >&2 ; exit 1; }

log_to_screen false
process_arguments $@
log_to_screen true

log INFO "ENMInst started.  ENMInst version: $ENMINST_VERSION"

case $DEP_TYPE in
ms)
   manage_reboot INIT
   patch_ms
   manage_reboot REMOVE
   log INFO "RHEL patching on Management Server complete"
   ;;

peer)
   patch_peer
   ;;

esac
exit 0
