"""
MCO client for the dbsnapshots RPC agent
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************
#
# ********************************************************************
# Name    : snap_agent.py
# Purpose : The purpose of this module is to perform SAN level snapshots
# operations on the db nodes
##############################################################################
import json

from h_puppet.mco_agents import BaseAgent


class SnapAgents(BaseAgent):
    """
    Wrapper for Snap mco agent.
    """

    def __init__(self, agent_name='dbsnapshots'):
        """ Constructor
        """
        super(SnapAgents, self).__init__(agent_name)

    def force_neo4j_checkpoint(self, target_hosts):
        """ Force a checkpoint on the specified Neo4j instances
        :param target_hosts: target hosts
        :type target_hosts: list
        :return: None
        """
        self.mco_exec('force_neo4j_checkpoint', [], target_hosts,
                      rpc_command_timeout=5400)

    def freeze_neo4j_db_filesystems(self, target_hosts):
        """ Freezes Neo4j database filesystems of the specified hosts
        :param target_hosts: target hosts
        :type target_hosts: list
        :return: None
        """
        self.mco_exec('freeze_neo4j_db_filesystem', [], target_hosts)

    def unfreeze_neo4j_db_filesystems(self, target_hosts):
        """ Unfreezes Neo4j database filesystems of the specified hosts
        :param target_hosts: target hosts
        :type target_hosts: list
        :return: None
        """
        self.mco_exec('unfreeze_neo4j_db_filesystem', [], target_hosts)

    def create_neo4j_snapshot(self,  # pylint: disable=R0913
                              lun_ids, array_type, spa_ip, spb_ip,
                              target_hosts, san_user, san_pw, san_login_scope,
                              snap_prefix, descr):
        """ Run create neo4j snapshot function on all the specified hosts

        :param lun_ids: lun ids
        :type lun_ids: dict
        :param array_type: array type
        :type array_type: str
        :param spa_ip: spa ip of SAN
        :type spa_ip: str
        :param spb_ip: spb ip of SAN
        :type spb_ip: str
        :param target_hosts: target hosts
        :type target_hosts: list
        :param san_user: san user name
        :type san_user: str
        :param san_pw: san psw
        :type san_pw: str
        :param snap_prefix: snap prefix
        :type snap_prefix: str
        :param descr: snap description
        :type descr: str
        :param san_login_scope: SAN login scope
        :return:
        """
        args = [
            'dbtype=neo4j',
            'array_type={0}'.format(array_type),
            'spa_ip={0}'.format(spa_ip),
            'spb_ip={0}'.format(spb_ip),
            'spa_username={0}'.format(san_user),
            'Password={0}'.format(san_pw),
            'Scope={0}'.format(san_login_scope),
            'dblun_id={0}'.format(json.dumps(lun_ids)),
            'snap_name={0}'.format(snap_prefix),
            'descr={0}'.format(descr)
        ]
        self.mco_exec('create_snapshot', args, target_hosts)

    def create_versant_snapshot(self,  # pylint: disable=R0913
                                db_name, dblun_id,
                                array_type, spa_ip, spb_ip,
                                active_db_host,
                                san_user, san_pw, san_login_scope,
                                snap_prefix, descr):
        """
        Run create versant snapshot function on active db node

        :param db_name: name of db to be snapped
        :type db_name: str
        :param dblun_id: lun id of DB
        :type dblun_id: str
        :param array_type: array type
        :type array_type: str
        :param spa_ip: spa ip of SAN
        :type spa_ip: str
        :param spb_ip: spa ip of SAN
        :type spb_ip: str
        :param active_db_host: hostname where db is active
        :type active_db_host: str
        :param san_user: san user name
        :type san_user: str
        :param san_pw: san psw
        :type san_pw: str
        :param snap_prefix: snap prefix
        :type snap_prefix: str
        :param descr: snap description
        :type descr: str
        :param san_login_scope: SAN login scope
        :return:
        """
        args = [
            'dbtype={0}'.format(db_name),
            'array_type={0}'.format(array_type),
            'spa_ip={0}'.format(spa_ip),
            'spb_ip={0}'.format(spb_ip),
            'spa_username={0}'.format(san_user),
            'Password={0}'.format(san_pw),
            'Scope={0}'.format(san_login_scope),
            'dblun_id={0}'.format(dblun_id),
            'snap_name={0}_{1}'.format(snap_prefix, dblun_id),
            'descr={0}'.format(descr)

        ]
        self.mco_exec('create_snapshot', args, active_db_host)

    def create_mysql_snapshot(self,  # pylint: disable=R0913,R0914
                              db_name, dblun_id, array_type,
                              spa_ip, spb_ip,
                              active_db_host, san_user, san_pw,
                              san_login_scope, snap_prefix,
                              descr, mysql_user):
        """
        Run create versant snapshot function on active db node

        :param db_name: name of db to be snapped
        :type db_name: str
        :param dblun_id: lun id of DB
        :type dblun_id: str
        :param array_type: array type
        :type array_type: str
        :param spa_ip: spa ip of SAN
        :type spa_ip: str
        :param spb_ip: spb ip of SAN
        :type spb_ip: str
        :param active_db_host: hostname where db is active
        :type active_db_host: str
        :param san_user: san user name
        :type san_user: str
        :param san_pw: san psw
        :type san_pw: str
        :param snap_prefix: snap prefix
        :type snap_prefix: str
        :param descr: snap description
        :type descr: str
        :param mysql_user: mysql user name
        :type mysql_user: str
        :param san_login_scope: SAN login scope
        :return:
        """
        args = [
            'dbtype={0}'.format(db_name),
            'array_type={0}'.format(array_type),
            'spa_ip={0}'.format(spa_ip),
            'spb_ip={0}'.format(spb_ip),
            'spa_username={0}'.format(san_user),
            'Password={0}'.format(san_pw),
            'Scope={0}'.format(san_login_scope),
            'dblun_id={0}'.format(dblun_id),
            'snap_name={0}_{1}'.format(snap_prefix, dblun_id),
            'descr={0}'.format(descr),
            'mysql_user={0}'.format(mysql_user)
        ]
        self.mco_exec('create_snapshot', args, active_db_host)

    def backup_opendj(self, node_list, opendj_backup_cmd, opendj_backup_dir,
                      opendj_log_dir):
        """
        Backup OpenDJ on both of the db nodes
        :param node_list: db nodes
        :type node_list: list
        :param opendj_backup_cmd: opendj backup command
        :type opendj_backup_cmd: str
        :param opendj_backup_dir: opendj backup dir
        :type opendj_backup_dir: str
        :param opendj_log_dir: opendj backup log dir
        :type opendj_log_dir: str
        :return: list(str)
        """
        args = [
            'opendj_backup_cmd={0}'.format(opendj_backup_cmd),
            'opendj_backup_dir={0}'.format(opendj_backup_dir),
            'opendj_log_dir={0}'.format(opendj_log_dir)
        ]
        for node in node_list:
            self.mco_exec('opendj_backup', args, node, rpc_command_timeout=210)

    def ensure_installed(self, package_name, node):
        """
        Ensure a package is installed on a node

        :param package_name: The package to check
        :type package_name: str
        :param node: The node to check
        :type node: str
        :returns:
        """
        return self.mco_exec('ensure_installed',
                             ['package={0}'.format(package_name)],
                             node)

    def cleanup_opendj(self, opendj_node_list, opendj_backup_dir,
                       opendj_log_dir):
        """
        Cleanup opendj backup dirs

        :param opendj_node_list: Nodes OPenDJ can be running on
        :param opendj_backup_dir: OpenDJ backup dir to clean
        :param opendj_log_dir: OpenDJ logs dir to clean
        :return:
        """
        args = [
            'opendj_backup_dir={0}'.format(opendj_backup_dir),
            'opendj_log_dir={0}'.format(opendj_log_dir)
        ]
        for node in opendj_node_list:
            self.mco_exec('opendj_cleanup', args, node)
