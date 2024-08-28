"""
Switch DB VCS groups from one system to another
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import ExitCodes, is_env_on_rack
from h_vcs.vcs_utils import VCS_AVAIL_ACTIVE_STANDBY, \
    VCS_GRP_SVS_STATE_ONLINE, VCS_GRP_SVS_STATE_OFFLINE, is_dps_using_neo4j
from h_vcs.vcs_cli import Vcs

_DB_CLUSTER = 'db_cluster'
_VERSANT_GROUP = 'versant_clustered_service'
_NEO4J_GROUP = 'sg_neo4j_clustered_service'


def _is_sg_failover_supported(vcs):
    """
    Check if the Service Group Failover is supported by the DB cluster.

    :param vcs: Vcs object reference
    :type vcs: Vcs
    :return: True if failover is supported by the cluster & False if not
    :rtype: bool
    """
    is_supported = False
    _, cluster_systems = vcs.get_cluster_system_status(_DB_CLUSTER)
    if len(cluster_systems) >= 2:
        is_supported = True
    return is_supported


def _get_dps_db_group_layout(vcs):
    """
    Obtain current distribution of DPS db (Versant or Neo4j) SG in DB cluster.
    Raise ValueError exception if database SG is OFFLINE on all systems.

    :param vcs: Vcs object reference
    :type vcs: Vcs
    :return dps_sg_name: dps database group name
    :rtype: str
    :return num_nodes: number of nodes dps group is registered with
    :return dps_db_group_layout: {active: VALUE1, standby: VALUE2}
    :rtype: dict
    """
    dps_db_group_layout = dict(active=None, standby=None)

    if is_dps_using_neo4j():
        dps_sg_name = _NEO4J_GROUP
    else:
        dps_sg_name = _VERSANT_GROUP

    dps_serv_groups, _ = vcs.get_cluster_group_status(
        cluster_filter=_DB_CLUSTER, group_filter=dps_sg_name, verbose=False)

    for group in dps_serv_groups:
        if group.get(Vcs.H_SERVICE_STATE) == VCS_GRP_SVS_STATE_ONLINE:
            dps_db_group_layout['active'] = group.get(Vcs.H_SYSTEM)
        if group.get(Vcs.H_SERVICE_STATE) == VCS_GRP_SVS_STATE_OFFLINE:
            dps_db_group_layout['standby'] = group.get(Vcs.H_SYSTEM)

    if not dps_db_group_layout['active']:
        raise ValueError('{0} is OFFLINE on all systems in '
                         'the DB cluster'.format(dps_sg_name))

    num_nodes = len(dps_serv_groups)

    return dps_sg_name, num_nodes, dps_db_group_layout


def _switch_from_neo4j_node(dps_sg_name, sorted_db_cluster_groups):
    """
    Switching HA database groups from db-2 to db-1 in 60k system scenario where
    Neo4j running in Causal Cluster mode with 3 active nodes.
    :param dps_sg_name: dps database group name to run in isolation
    :param sorted_db_cluster_groups: candidate groups to be switched
    :return: None
    """
    logger = init_enminst_logging()
    vcs = Vcs()

    system_db_1 = vcs.node_name_to_vcs_system('db-1')
    system_db_2 = vcs.node_name_to_vcs_system('db-2')

    for group in sorted_db_cluster_groups:

        group_name = group.get(Vcs.H_GROUP)

        if group.get(Vcs.H_SYSTEM) == system_db_2 and \
                group.get(Vcs.H_TYPE) == VCS_AVAIL_ACTIVE_STANDBY and \
                group.get(Vcs.H_SERVICE_STATE) == VCS_GRP_SVS_STATE_ONLINE \
                and dps_sg_name not in group_name:
            logger.info('Switching {0} from {1} to {2}.'.format(group_name,
                                                                system_db_1,
                                                                system_db_2))
            vcs.hagrp_switch(group_name, system_db_1, _DB_CLUSTER, timeout=-1)


def _switch_groups(dps_sg_name, sorted_db_cluster_groups,
                   dps_db_group_layout):
    """
    Switching groups between 2 nodes in 40k system scenario to run main dps
    database group in isolation, i.e., Versant or Neo4j
    :param dps_sg_name: dps database group name to run in isolation
    :param sorted_db_cluster_groups: candidate groups to be switched
    :param dps_db_group_layout: system info of dps db group
    :return: None
    """
    logger = init_enminst_logging()
    vcs = Vcs()

    for group in sorted_db_cluster_groups:

        group_name = group.get(Vcs.H_GROUP)
        group_h_sys = group.get(Vcs.H_SYSTEM)

        if group.get(Vcs.H_TYPE) != VCS_AVAIL_ACTIVE_STANDBY \
                or dps_sg_name in group_name:
            continue

        if group.get(Vcs.H_SERVICE_STATE) == VCS_GRP_SVS_STATE_ONLINE \
                and group_h_sys == dps_db_group_layout['active']:

            switch_to = dps_db_group_layout['standby']

            logger.info('Switching {0} from {1} to {2}.'.format(group_name,
                                                                group_h_sys,
                                                                switch_to))

            vcs.hagrp_switch(group_name, switch_to, _DB_CLUSTER, timeout=-1)


def switch_dbcluster_groups():
    """
    Switch all Active-Standby Groups except DPS db to the system with
    database (Versant or Neo4j) OFFLINE. Raise SystemExit if database  is
    OFFLINE on all systems.
    :return: None
    """
    logger = init_enminst_logging()
    logger.info('Distributing Active-Standby Service Groups among the systems '
                'in DB cluster')

    if is_env_on_rack():
        logger.info('ENM RACK Deployment')
        _switch_to_rack_layout()
        return

    vcs = Vcs()
    switch_sg = _is_sg_failover_supported(vcs)
    if not switch_sg:
        logger.warning('DB Cluster Service Group failover is not supported '
                       'on this environment')
        return

    try:
        dps_sg_name, num_nodes, dps_db_group_layout = \
            _get_dps_db_group_layout(vcs)
    except ValueError as error:
        logger.exception(error)
        raise SystemExit(ExitCodes.VCS_GROUP_OFFLINE)

    db_cluster_groups, _ = vcs.get_cluster_group_status(
        cluster_filter=_DB_CLUSTER, verbose=False)

    sorted_db_cluster_groups = []
    if db_cluster_groups:
        # TORF-159972: sorting the cluster groups (alphabetically by group)
        # will execute elastic* before postgr*.
        sorted_db_cluster_groups = sorted(
            db_cluster_groups,
            key=lambda k: k.get(Vcs.H_GROUP, None) if k else None
        )

    if num_nodes > 2:
        logger.info(
            'Neo4j SG causal cluster, check if failover SGs need to be '
            'switched from db-2.')
        _switch_from_neo4j_node(dps_sg_name, sorted_db_cluster_groups)
    elif num_nodes == 1:
        logger.info('SG has 1 node, no need to switch')
        return
    else:
        logger.info('SG cluster has 2 nodes, \
        going to check if switch required.')
        _switch_groups(dps_sg_name, sorted_db_cluster_groups,
                       dps_db_group_layout)


def _switch_to_rack_layout():
    """
    Switching HA database groups on RACK deployment
    """
    vcs = Vcs()

    system_db_1 = vcs.node_name_to_vcs_system('db-1')
    system_db_2 = vcs.node_name_to_vcs_system('db-2')
    system_db_3 = vcs.node_name_to_vcs_system('db-3')

    sg_switch_list = {
        'Grp_CS_db_cluster_elasticsearch_clustered_service': system_db_2,
        'Grp_CS_db_cluster_eshistory_clustered_service': system_db_3,
        'Grp_CS_db_cluster_jms_clustered_service': system_db_3,
        'Grp_CS_db_cluster_modeldeployment_cluster_service_1': system_db_1,
        'Grp_CS_db_cluster_postgres_clustered_service': system_db_3,
        'Grp_CS_db_cluster_sg_neo4jbur_clustered_service': system_db_1}

    for sg_name, db_node in sg_switch_list.items():
        vcs.hagrp_switch(sg_name, db_node, _DB_CLUSTER, timeout=-1)
