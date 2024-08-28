#!/bin/bash

DIRNAME=/usr/bin/dirname
ECHO=/bin/echo
PYTHON=/usr/bin/python

_dir_=`${DIRNAME} $0`
export ENMINST_HOME=`cd ${_dir_}/../ 2>/dev/null && pwd || ${ECHO} ${_dir_}`
export ENMINST_LIB=${ENMINST_HOME}/lib
export PYTHONPATH=${PYTHONPATH}:${ENMINST_LIB}

db_in_use_name=sg_neo4j_clustered_service
vcs_cmd=/opt/ericsson/enminst/bin/vcs.bsh
cluster_field=0
group_field=1
system_field=2
hatype_field=3
servicetype_field=4
servicestate_field=5
groupstate_field=6
frozen_field=7

log(){
    /bin/logger -s -i  $(date +"%Y-%m-%d %H:%M:%S.%3N")  "$1"
}

check_db_in_use(){
   grep 'dps_persistence_provider=neo4j' /ericsson/tor/data/global.properties
   if [ $? -ne 0 ]; then
        log  "The neo4j database not in use, exiting.."
        exit 0
    fi
}

get_check_database_group(){
    neo4j_array=()
    check_db_in_use
    while IFS= read -r line; do
        neo4j_array+=( "$line" )
    done < <($vcs_cmd --groups -c db_cluster | grep -i $db_in_use_name )

    for i in "${neo4j_array[@]}";   do
        neo4j_arr=(${i// / })
        if [[ ${neo4j_arr[servicestate_field]}  == *"FAULTED"*   ]]  && [[  ${neo4j_arr[servicestate_field]}  != *"STARTING"*  && ${neo4j_arr[servicestate_field]}  != *"STOPPING"* ]]
        then
            log  "Database SG group ${neo4j_arr[group_field]} on ${neo4j_arr[system_field]} is Faulted; Need to check SG before proceeding."
            exit 1
        fi
        if [[ ${neo4j_arr[servicestate_field]} != "OFFLINE" && ${neo4j_arr[servicestate_field]} != "ONLINE" ]]; then
            log  "Database SG group ${neo4j_arr[group_field]} on ${neo4j_arr[system_field]}  not online yet; Waiting 90 mins until it gets online"
            wait_neo4j_instance_online ${neo4j_arr[group_field]} ${neo4j_arr[system_field]} ${neo4j_arr[hatype_field]}
        fi

    done
}

get_check_clear_non_dbcluster_groups(){
    log  "Check, clear faulted, and restart non dbcluster groups"
    cluster_array=()
    while IFS= read -r line; do
        cluster_array+=( "$line" )
    done < <($vcs_cmd --groups | grep Grp_CS | grep -v db_cluster)

    is_faulted=0
    for i in "${cluster_array[@]}";   do
       cluster_arr=(${i// / })
        if [[ ${cluster_arr[servicestate_field]}  == *"FAULTED"*   ]]  && [[  ${cluster_arr[servicestate_field]}  != *"STARTING"*  && ${cluster_arr[servicestate_field]}  != *"STOPPING"* ]]
        then
            log "SG group ${cluster_arr[group_field]} on ${cluster_arr[system_field]}  is Faulted; Going to restart"
            is_faulted=1
            restart_sg ${cluster_arr[group_field]} ${cluster_arr[system_field]}
        fi

    done
    return $is_faulted
}

restart_sg(){
    sg_name=$1
    sg_node=$2
    log "Clear SG $sg_name on $sg_node"
    $vcs_cmd --clear -g ${sg_name} -s ${sg_node}
    log "SG $sg_name on $sg_node cleared"
    $vcs_cmd --restart -g ${sg_name} -s ${sg_node} &
    log "Restart of SG $sg_name on $sg_node been kicked..."
}

# This running last, and check SGs states only
monitor_non_db_cluster_groups(){
    time_out=$1
    attempts_number=$(expr $time_out / 180)
    attempt=0
    while [ $attempt -le $attempts_number ]; do
        cluster_array=()
        while IFS= read -r line; do
            cluster_array+=( "$line" )
        done < <($vcs_cmd --groups | grep  Grp_CS | grep -v db_cluster)

        sg_completed=true
        for i in "${cluster_array[@]}";   do
           cluster_arr=(${i// / })
           # Check if SG is in final state
            if [[ ${cluster_arr[servicestate_field]}  == *"FAULTED"* ]]; then
                log "non dbcluster SG group ${cluster_arr[group_field]} is Faulted"
                 sg_completed=false
                 break
            fi
            if [[ ${cluster_arr[servicestate_field]}  == "OFFLINE" || ${cluster_arr[servicestate_field]}  == "ONLINE" ]]; then
                sg_completed=true
            else
                sg_completed=false
                break
            fi
        done
        if [[ ${sg_completed}  == "true" ]]; then
            log "non dbcluster service groups startup completed; Check if some SGs are in faulted state"
            break
        fi
        sleep 180
         ((attempt++))
    done
    log "non dbcluster service groups startup monitor completed; Check if some SGs are in faulted state or still starting:"
    $vcs_cmd --groups | grep  Grp_CS | grep -v db_cluster
}

wait_neo4j_instance_online(){
    sg_name=$1
    node_name=$2
    ha_type=$3

    # Attempts number 30, every 3 mins query for status; So waiting time for Neo4j grp 90 mins
    attempts_number=30
    attempt=0
    while [ $attempt -le $attempts_number ]; do
        log "Waiting SG ${sg_name} is coming online....."
        state=$($vcs_cmd --groups -c db_cluster | grep -i $sg_name | grep -i $node_name | awk '{print $6}')
         if [[ ${state}  == *"FAULTED"* ]] && [[  ${state}   != *"STARTING"*  && ${state}  != *"STOPPING"* ]]
         then
            log "Neo4j $sg_name on $node_name is faulted; Exit and check the issue"
            exit 1
         fi
         if [[ ${state}  == "ONLINE" ]]; then
            log "Neo4j SG $sg_name is online on $node_name"
            break
         fi

          if [[ ${ha_type}  == "active-standby" ]]; then
            sleep 5
            state=$($vcs_cmd --groups -c db_cluster | grep -i $sg_name | grep -v -i $node_name | awk '{print $6}')
             if [[ ${state}  == *"FAULTED"* ]] && [[  ${state}   != *"STARTING"*  && ${state}  != *"STOPPING"* ]]
             then
                log "Neo4j $sg_name on $node_name is faulted; Exit and check the issue"
                exit 1
             fi
             if [[ ${state}  == "ONLINE" ]]; then
                log "Neo4j SG $sg_name is online"
                break
             fi
          fi

         sleep 180
         ((attempt++))
    done
    log "Neo4j SG $sg_name online done"
}

get_check_neo4j_on_db2(){
    echo 'checking neo4j is only service active on db-2, if any other db clusters found will move to db-1'
    ${PYTHON} ${ENMINST_LIB}/switch_db_groups_post_rollback.py 2>&1
}

# Main
log "Post_restore_post_reboot script to clear faulted non dbcluster groups"

case $1 in
   # used for the gossip router upgrade bounce healthcheck
   get_check_clear_non_dbcluster_groups)  "$@"; exit;;
esac

get_check_database_group

# Checks whether the neo4j is only AP service active on db-2
get_check_neo4j_on_db2

# First iteration to fix non dbcluster groups
get_check_clear_non_dbcluster_groups
if [ $? -eq 0 ]; then
    log  "No faulted non dbcluser groups at this stage, exit"
    exit 0
fi

log  "Pause for faulted non dbcluster groups get started"
# Pause for  10 mins
sleep 600

# Last iteration to fix non dbcluster groups
get_check_clear_non_dbcluster_groups

# Wait 60 mins (3600) until all non dbcluster groups complete online; param is waiting time in sec
monitor_non_db_cluster_groups 3600


