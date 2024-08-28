#!/bin/bash
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2014 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : deploy_enm.sh
# Purpose : Automatic deployment of ENM.
#
# Usage   : See usage function below.
#
# ********************************************************************

LOGGER=/bin/logger

DEPLOYMENT_TYPES=(ENM_Deployment ENM_Deployment_Cloud)

# FUNCTIONS
# ---------

function usage()
{
   local _msg_="$@"

   local scriptname=$(basename $0)

cat<<-EOF

        Deploy ENM.  Version: $ENMINST_VERSION

        Command Arguments
           -r, --resume
              Optional Argument. Resumes LITP plan only if it is in Failed state.

           -t, --install_type
               Optional argument.  Install type can be, one of:  [${DEPLOYMENT_TYPES[@]}]
               ${DEPLOYMENT_TYPES[0]} is default deployment type.

           -s, --sed SED
               Mandatory argument for install.  Site engineering file to be used.

           -m, --model XML
               Mandatory argument for install.  Deployment Model XML file to be used.

           -e, --enm_iso ENM ISO
               Mandatory argument for install.  Full path of ENM ISO file.

           -v, --verbose
               Optional argument.  Verbose logging.

           -l, --thin
               Optional argument.  Enable thin provisioning on EMC storage.

           -y, --assumeyes
               Answer yes for all questions

           -h, --help
               Optional argument.  Display this usage.

        Examples:
        ${DEPLOYMENT_TYPES[0]} deployment type (4/6 Nodes).
        # $scriptname -s /var/tmp/sed.txt -m /var/tmp/deployment.xml -e /var/tmp/ERICenm_CXP9027091-1.1.16.iso

        ${DEPLOYMENT_TYPES[1]} deployment type.
        # $scriptname --install_type ${DEPLOYMENT_TYPES[1]} --sed /var/tmp/sed.txt --model /var/tmp/deployment.xml --enm_iso /var/tmp/ERICenm_CXP9027091-1.1.16.iso --verbose

        Resume Failed LITP Plan.
        # $scriptname --resume

EOF
   exit $_exit_
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
   local short_args="vlyhrt:s:e:m:"
   local long_args="verbose,thin,assumeyes,help,resume,install_type:,sed:,enm_iso:,model:"

   log INFO "Processing Options and Arguments"
   mkdir -p /opt/ericsson/enminst/log/ 2> /dev/null #It is good information so lets save it here as the install logs might get rotated by logrotate.

   # Set the Environment to be 'blade' as default
   export ENMINST_ENVIRONMENT=blade;
   export ENMINST_ACTION=install

   export VERBOSE=false

   args=$(getopt -o $short_args -l $long_args -n "$0"  -- "$@"  2>&1 )
   [[ $? -ne 0 ]] && invalid_arguments $( echo " $args"| head -1 )
   [[ $# -eq 0 ]] && invalid_arguments "No options provided"
   eval set -- "$args"
   cmd_arg="$0"

   while true; do
      case "$1" in
         -r|--resume)
            export ENMINST_ACTION=resume
            shift
            ;;
         -t|--install_type)
            export INSTALL_TYPE=$2
            val_in_array $2 ${DEPLOYMENT_TYPES[@]} || error "$1 ${INSTALL_TYPE} is not a valid action. Choose from: ${DEPLOYMENT_TYPES[@]}"
            [[ "${INSTALL_TYPE}" == "ENM_Deployment_Cloud" ]] && export ENMINST_ENVIRONMENT=cloud
            cmd_arg="${cmd_arg} $1 $2"
            shift 2 ;;
         -s|--sed)
            export ENMINST_SEDFILE=$2
            log INFO "SED option set to: $ENMINST_SEDFILE"
            read_file_ok $ENMINST_SEDFILE || error "Unable to read $ENMINST_SEDFILE"
            cmd_arg="${cmd_arg} $1 $(readlink -f $ENMINST_SEDFILE)"
            shift 2 ;;
         -m|--model)
            export ENMINST_XML_TEMPLATE=$2
            log INFO "Deployment Model XML option set to: $ENMINST_XML_TEMPLATE"
            read_file_ok $ENMINST_XML_TEMPLATE || error "Unable to read $ENMINST_XML_TEMPLATE"
            cmd_arg="${cmd_arg} $1 $(readlink -f $ENMINST_XML_TEMPLATE)"
            log DEBUG "Deployed XML will be $ENMINST_XML_DEPLOYMENT"
            shift 2 ;;
         -e|--enm_iso)
            export ENM_ISO=$2
            log INFO "ENM ISO option set to: $ENM_ISO"
            read_file_ok $ENM_ISO || error "Unable to read $ENM_ISO"
            cmd_arg="${cmd_arg} $1 $(readlink -f $ENM_ISO)"
            shift 2 ;;
         -v|--verbose)
            export VERBOSE=true
            log_debug
            cmd_arg="${cmd_arg} $1"
            shift
            ;;
         -y|--assumeyes)
            export ASSUMEYES=true
            cmd_arg="${cmd_arg} $1"
            shift
            ;;
         -l|--thin)
            export THIN=true
            cmd_arg="${cmd_arg} $1"
            shift
            ;;
         -h|--help)
            usage
            exit 0
            ;;
         --)
            shift
            break ;;
         *)
            echo BAD ARGUMENTS # perhaps error
            break ;;
      esac
   done

   # Ensure mandatory parameters are set
   [[ -z "${INSTALL_TYPE}" ]] && cmd_arg="${cmd_arg} -t ${DEPLOYMENT_TYPES[0]}"
   export INSTALL_TYPE=${INSTALL_TYPE:-${DEPLOYMENT_TYPES[0]}}

   if [[ "$ENMINST_ACTION" == "install" ]] ; then

      if [[ -z "$ENMINST_SEDFILE" ]] ; then
         invalid_arguments "-s | --sed must be specified with full path to SED file."
      fi

      get_sed_params $ENMINST_SEDFILE enm_deployment_type
      if [[ "$enm_deployment_type" == "ENM_On_Rack_Servers" ]]; then
         log INFO "Environment is set to: rack"
      else
         log INFO "Environment is set to: $ENMINST_ENVIRONMENT"
      fi

      if [[ -z "$ENM_ISO" ]] ; then
         invalid_arguments "-e | --enm_iso must be specified with full path to ENM ISO file."
      fi

      if [[ -z "$ENMINST_XML_TEMPLATE" ]] ; then
         invalid_arguments "-m | --model must be specified with full path to Deployment Model XML file."
      fi
   fi

   log INFO "Action is set to: $ENMINST_ACTION"

   # Ensure no extra parameters are added
   if [[ ${#@} -gt 0 ]]; then
      invalid_arguments "Unexpected positional arguments added: ${@}"
   fi

   log INFO "Arguments processed successfully"

   log INFO "Installation is going to start. All current settings and data will be removed"
   if [ "$ASSUMEYES" == "true" ]; then
      log INFO "Option -y|--assumeyes passed to the script. Skipped asking for confirmation."
   else
      ask_for_confirmation "Do you wish to continue?" continue_install
      if [ "$continue_install" != "y" ]; then
         log INFO "Installation stopped by the user"
         exit 1
      else
         log INFO "Installation was confirmed by the user"
      fi
   fi

   #log processed arg to cmd_arg.log and logfile.
   local scriptname=$(basename $0)
   /usr/bin/python -c "import h_logging.enminst_logger; h_logging.enminst_logger.log_cmdline_args('$scriptname', '$cmd_arg')"
      _rc_=$?
   if [ ${_rc_} -eq ${EXIT_INTERRUPTED} ]; then
     return ${EXIT_INTERRUPTED}
   elif [ ${_rc_} -ne 0 ]; then
       warning "Problem logging command line arguemnt to log file"
   fi

   return 0
}

# load stages file and any deployment specific configuration.
# The files to use are worked out from
# the script options, action and environment.
function initialise_enminst() {
   log_header "Initialising ENMInst"

   # Define environment and action variable, used later to locate stages file and XML template.
   env_action=enminst_${ENMINST_ENVIRONMENT}_${ENMINST_ACTION}

   # Check stages file, read contents into array, and ensure functions exist for each item
   local stages_file=${ENMINST_ETC}/${env_action}.stages
   read_file_ok $stages_file || error "Stage file $stages_file cannot be read"
   log DEBUG "Using stages file $stages_file"

   ENMINST_STAGES=( $(cat $stages_file 2> /dev/null | strip_comments_and_blanks) )
   [[ ${#ENMINST_STAGES[*]} -lt 1 ]] && error "Stage file $(basename $stages_file) contents could not be loaded"


   for fn in ${ENMINST_STAGES[@]}
   do
      function_exists $fn || error "No function exists for stage $fn defined in $(basename $stages_file)"
   done

   log INFO "Stages from $(basename $stages_file) loaded and verified"

   # Source any specific config file (this might not exist, so just log if not present)
   local config_file=${ENMINST_ETC}/${env_action}.cfg
   source $config_file 2>/dev/null

   if [[ $? -eq 0 ]] ; then
      log INFO "Sourced $config_file"
   else
      log WARN "No $(basename ${ENMINST_ETC}/${env_action}.cfg) file found to use"
   fi

# :<<"EOF"

# EOF

   cp $ENMINST_WORKING_PARAMETERS ${ENMINST_WORKING_PARAMETERS}.$(timestamp_suffix) 2>/dev/null

   file $ENMINST_SEDFILE | grep -q CRLF &&  dos2unix $ENMINST_SEDFILE

   # Ensure no Windows line endings in our files
   for file in $(find  $ENMINST_HOME -type f  -exec file  {} \;|grep CRLF,|cut -d: -f 1)
   do
      log DEBUG "$file has CRLF line endings.  Converting with dos2unix"
      dos2unix $file
   done

   log INFO "enminst initialisation complete"
   return 0
}


function execute_stages() {
   log_header "Executing Stages"

   # If resuming, then set things up...
   if [[ -n "$ENMINST_RESUMING" ]] ; then
      log INFO  "Attempting to resume $ENMINST_ACTION"
      read_file_ok $ENMINST_FAILED_STAGE_FILE || error "Unable to resume as failed stage file cannot be read: $ENMINST_FAILED_STAGE_FILE"
      log INFO "Failed stage file found"

      export PREV_ACTION=$(cut -d: -f 1 $ENMINST_FAILED_STAGE_FILE)
      export PREV_STAGE=$(cut -d: -f 2 $ENMINST_FAILED_STAGE_FILE)

      [[ "$ENMINST_ACTION" = "$PREV_ACTION" ]] || error "When resuming, the action, $ENMINST_ACTION must match the previous action $PREV_ACTION"
      [[ -z "$PREV_STAGE" ]] && error "No failed stage found in $ENMINST_FAILED_STAGE_FILE"

      grep -q $PREV_STAGE <<< ${ENMINST_STAGES[@]} || error "The stage to resume, $PREV_STAGE, does not exist"
      log INFO "Resuming from $PREV_STAGE"

   fi

   for fn in ${ENMINST_STAGES[@]}
   do
      log INFO "About to execute stages function: $fn"
      $fn
      _rc_=$?
      if [ ${_rc_} -eq ${EXIT_INTERRUPTED} ] ; then
         error "Function ${fn} interrupted (Error code: ${_rc_})"
      elif [ ${_rc_} -ne 0 ] ; then
         error "Function $fn failed (Error code: ${_rc_})"
      fi
      log INFO "Function $fn completed successfully"
   done

  log INFO "All functions completed successfully"
}

source_enminst_cfg() {
   # Source block from ini file
   BLOCK=$1
   if [[ -z "${BLOCK}" ]]; then
      BLOCK=ENM_INST_CONFIG
   fi
   _var_list_=$(misc_iniget ${BLOCK} ${ENM_INI})
   echo "${_var_list_}" > _ini_cfg_tmp_
   /usr/bin/perl -ni -e 's/(%\()(.*?)(\)s)/\$\{\2\}/g; print "export $_"' _ini_cfg_tmp_
   source _ini_cfg_tmp_
   if [ $? -ne 0 ]; then
      error "Failed to source ${ENM_INI}"
   fi
   /bin/rm _ini_cfg_tmp_
   if [ $? -ne 0 ]; then
      log WARN "Failed to delete _ini_cfg_tmp_"
   fi
}

# Main

# Check we are user root before we do anything else.
[[ "$EUID" -ne 0 ]] && { echo "Only root user can run this script." ; exit 1; }

# SOURCE ENMINST CONFIGURATION FILE
# ---------------------------------
# Need to set directory so we can find enminst config files etc
export ENMINST_HOME="$( cd "$( dirname "${BASH_SOURCE[0]}/" )/.." && pwd)"
export ENMINST_LIB=${ENMINST_HOME}/lib
export PYTHONPATH=${ENMINST_LIB}:${PYTHONPATH}
export ENM_INI=$ENMINST_HOME/etc/enminst_cfg.ini

source $ENMINST_HOME/lib/enminst_utils.lib
if [ $? -ne 0 ] ; then
   echo "Unable to source $ENMINST_HOME/lib/enminst_utils.lib" >&2
   exit 1
fi

DIR=$(pwd)
source_enminst_cfg
source_enminst_cfg MANAGED_DIRECTORIES

# Before we start the deployment, we must ensure the user
# is not in any particular directory (source: ini file for list)
# If the user is in this dir (or a child of this dir) we will
# error out of the script.
for path in ${ENMINST_MANAGED_DIRECTORIES}; do
   if [[ "${DIR}" =~ ^${path} ]]; then
       error "Please change directory. You cannot execute this script from ${DIR}"
   fi
done

log_init $ENMINST_LOG/$LOG_FILE || { echo "Cannot set up logging with $ENMINST_LOG/$LOG_FILE" >&2 ; exit 1; }

# ------------------------------------------------------------------------------
# SOURCE FUNCTIONS FROM FILES IN LIB DIR
# --------------------------------------
for file in $(ls ${ENMINST_LIB}/*.lib) ; do
   log DEBUG "Sourcing ${file}"
   source ${file}
   if [ $? -ne 0 ]; then
      error "Failed to source ${file}"
   fi
done
# ------------------------------------------------------------------------------
ENMINST_VERSION="$( rpm -qa | grep enminst | awk -F'-' '{print $2}' )"
log INFO "ENMInst started.  ENMInst version: $ENMINST_VERSION"
process_arguments $@
if [ $? -ne 0 ] ; then
   exit 1
fi
initialise_enminst
execute_stages
exit 0
