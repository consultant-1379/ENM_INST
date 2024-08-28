# pylint: disable=C0302
"""
Class to handle SFS filesystem snapshots
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************
import logging
from multiprocessing.pool import ThreadPool
from time import sleep

from h_litp.litp_rest_client import LitpRestClient
from h_snapshots.litp_snapshots import LitpSanSnapshots
from h_snapshots.snap_agent import SnapAgents
from h_snapshots.snapshots_utils import SAN_POOLNAME, SAN_PW, SAN_USER,\
    SAN_LOGIN_SCOPE, SAN_SPA_IP, SAN_TYPE, SAN_SPB_IP, NavisecCLI,\
    SAN_TYPE, read_ini, get_default_config, SanApiException

from h_util.h_utils import ExitCodes
from h_vcs.vcs_cli import Vcs
from h_vcs.vcs_utils import VcsException, is_dps_using_neo4j, \
    VCS_AVAIL_PARALLEL
from h_puppet.mco_agents import EnminstAgent


class InvalidStateForSnapshotCreation(Exception):
    """ This exception will be raised in an event of not a valid state during
    the creation of snapshot.
    """


def _or_filter_list(rlist):
    """
    Convert a list to an OR regex filter
    :param rlist: List of regex expressions to OR
    :returns: OR regex exp
    :rtype: str
    """
    return '({0})'.format('|'.join(rlist))


def filter_luns(luns, include_ids):
    """
    Remove LUNs from the ``luns`` dict that are not in the ``include_list``

    :param luns: LUN's to apply the filter on
    :type luns: dict
    :param include_ids: List of LUN ID's to leave in ``luns``, any other LUN's
    get removed.
    :type include_ids: list
    """
    ids = luns.keys()
    for found_id in ids:
        if found_id not in include_ids:
            del luns[found_id]


# TODO - RENAME THIS TO BE GENERIC  # pylint: disable=fixme
class VNXSnap(object):  # pylint: disable=R0902
    """
    Class to run SAN snapshot operations for a deployment
    """

    def __init__(self,  # pylint: disable=R0913
                 san_cred, snap_prefix, cfg_ini=None,
                 num_of_threads=10, log_silent=False):
        """
        Constructor
        :param snap_prefix:
        :param san_cred: san credentials
        :param cfg_ini: san config file ini instance
        :param num_of_threads: number of threads that can be used for
        thread pool
        :param log_silent: disable logging to enminst log
        :type log_silent: boolean
        :return:
        """

        self.san_cred = san_cred
        self._snap_prefix = snap_prefix
        self._cfg_ini = cfg_ini

        self.descr = 'ENM_Upgrade_Snapshot'
        self.num_of_threads = num_of_threads
        self.poolname = None
        self.db_lun_names = list()
        self.db_luns = dict()

        if log_silent:
            self.logger = logging.getLogger('enmsnapshots')
        else:
            self.logger = logging.getLogger('enminst')

        self.log_prefix = 'SAN SNAP'

        self.mysql_user = 'root'

        self.opendj_backup_cmd = '/opt/ericsson/com.ericsson.oss.security/' \
                                 'idenmgmt/opendj/bin/opendj_backup.sh'
        self.opendj_backup_dir = '/var/tmp/opendj_backup'
        self.opendj_log_dir = '/var/tmp/opendj_backup_log'

        self.versant_user = 'versant'
        self.neo4j_user = 'neo4j'

        self.snapper = SnapAgents()
        self.neo4j_snapper = SnapAgents(agent_name='neo4jsnapshots')
        self.enminst_agent = EnminstAgent()
        self.litp_lunlist = {}
        self.initialise()
        self.navi_cli = NavisecCLI(san_cred, self._cfg_ini)

    def get_snap_prefix(self):
        """
        Get the prefix for the LUN snapshot name
        :return:
        """
        return self._snap_prefix

    def initialise(self):
        """
        Set up the configuration related variable which will used when running
        navi command
        :param
        :return:
        """
        self.poolname = self.san_cred[SAN_POOLNAME]
        if not self._cfg_ini:
            self._cfg_ini = read_ini(get_default_config())

        # TODO NEED TO REFACTOR INI VNX NAME  # pylint: disable=fixme
        self.db_lun_names = self._cfg_ini.get('VNX', 'db_lun_names').split(',')
        self.litp_lunlist = LitpSanSnapshots().get_node_lundisks()

    def _get_luns_by_pool(self, storagepool):
        """
        Get a list of LUNs in a storage pool
        :param storagepool: The StoragePool to get the LUNs from
        :returns: A dictionary containing the LUNs in the storage pool,
        key is the LUN ID
        :rtype: dict
        """
        raw_lun_data = self.navi_cli.list_all_luns(storagepool)
        pool_luns = {}
        for lun in raw_lun_data:
            pool_luns[lun.id] = lun
        return pool_luns

    def get_snappable_luns(self, lunlist=None, for_snap_remove=False):
        """ Get a list of LUNs that are to be snapped, if lunlist is given
        then snappable LUNs are built based on the lunlist otherwise
        based on litp model.
        :param lunlist: List of lun ID to be used.
        :type lunlist: list
        :param for_snap_remove: Used only for snapshot removal
        :type for_snap_remove: bool
        :returns: Snappable LUNs
        :rtype: dict
        """
        self.logger.info('{0} : Building list of LUNs in the storagepool : '
                          '{1}'.format(self.log_prefix, self.poolname))
        pool_luns = self._get_luns_by_pool(self.poolname)
        for lunid, luninfo in pool_luns.items():
            if lunlist and lunid not in lunlist:
                del pool_luns[lunid]
            elif not lunlist and luninfo.name not in self.litp_lunlist:
                del pool_luns[lunid]

            if 'versant' in str(luninfo) and is_dps_using_neo4j()\
                    and not for_snap_remove:
                if lunid in pool_luns:
                    del pool_luns[lunid]
                    self.logger.info('Versant LUN not snappable '
                        'as not in use; LUN info: {0}'.format(str(luninfo)))
        return pool_luns

    def _get_lun_snapshots(self, luns, snap_prefix=None):
        """
        Get a list of snaps for each lun
        :param luns: The luns to get the snaps for
        :type luns: dict
        :param snap_prefix:
        :type snap_prefix: str
        :returns: Snapshots on each LUN (None if not snapped)
        :rtype: dict
        """
        raw_snap_data = self.navi_cli.list_all_snaps()
        snap_data = {}
        for snap in raw_snap_data:
            if snap_prefix and not snap.snap_name.startswith(snap_prefix):
                continue
            if snap.resource_id in luns:
                if snap.resource_id not in snap_data:
                    snap_data[snap.resource_id] = []
                snap_data[snap.resource_id].append(snap)

        for lunid in luns.keys():
            if lunid not in snap_data:
                snap_data[lunid] = []
        return snap_data

    def _get_lun_ids_for_dbs(self, lun_list):
        """
        Building a dictionary of all the db luns and their names
        :rtype: dict
        """
        self.logger.info("{0} : Building dictionary of DB LUNs "
                         "in the storagepool : {1}".
                         format(self.log_prefix, self.poolname))
        db_lun_ids = {}
        for lunid, luninfo in lun_list.items():
            for mname in self.db_lun_names:
                if mname in luninfo.name:
                    db_lun_ids[mname] = lunid
        return db_lun_ids

    def list_snapshots(self,  # pylint: disable=R0912,R0914
                       detailed, lun_ids=None, validating=False):
        """
        List the snapshots of the LUNs
        :param lun_ids : list of LUNs whose snapshots to be listed
        :type lun_ids: list
        :param validating: if True then validates existence / correct names
        of LUN snapshots
        :param detailed: Show more info on the LUN snap e.g. creation time
        :type detailed: bool
        :returns: list of LUN snapshots
        :rtype: list
        """
        lunlist = self.get_snappable_luns(lun_ids)

        if lun_ids:
            # Remove any not in the passed in list e.g. snaps were created
            # prior to adding a new lun i.e. expansion
            filter_luns(lunlist, lun_ids)

        lun_snapshots = self._get_lun_snapshots(
            lunlist, snap_prefix=self.get_snap_prefix())

        errors = False
        no_snaps_exists = True
        snapshots = []
        for snappable_lun_id in lunlist.keys():
            lunname = lunlist[snappable_lun_id].name
            exp_name = '{0}_{1}'.format(self.get_snap_prefix(),
                                        snappable_lun_id)
            lunsnaps = lun_snapshots[snappable_lun_id]
            if lunsnaps:
                for lsnap in lunsnaps:
                    act_name = lsnap.snap_name
                    if act_name == exp_name:
                        snapshots.append(lsnap)
                        no_snaps_exists = False
                        self.logger.info('{plog} : LUN {lunid}/{lunname} '
                                         'has snapshot "{snapname}"'
                                         ''.format(plog=self.log_prefix,
                                                   lunid=snappable_lun_id,
                                                   lunname=lunname,
                                                   snapname=act_name))
                        if detailed:
                            self.logger.info(
                                '{plog} :  Creation {ctime}'.format(
                                        plog=self.log_prefix,
                                        ctime=lsnap.creation_time))
                            self.logger.info(
                                '{plog} :  State    {state}'.format(
                                    plog=self.log_prefix, state=lsnap.state))
                    else:
                        msg = '{plog} : LUN {lunid}/{lunname} has a' \
                              ' snapshot "{act_snapname}" but expected one' \
                              ' called "{exp_snapname}"'. \
                            format(plog=self.log_prefix,
                                   act_snapname=act_name,
                                   exp_snapname=exp_name,
                                   lunid=snappable_lun_id,
                                   lunname=lunname)
                        if validating:
                            self.logger.error(msg)
                        else:
                            self.logger.info(msg)
                        errors = True
            else:
                msg = '{plog} : ' \
                      'LUN {lunid}/{lunname} has no snapshot with the prefix' \
                      ' "{prefix}".'.format(plog=self.log_prefix,
                                            snapname=exp_name,
                                            lunid=snappable_lun_id,
                                            lunname=lunname,
                                            prefix=self.get_snap_prefix())
                if not 'mysql' in lunname:
                    if validating:
                        self.logger.error(msg)
                    errors = True
                else:
                    mysql_sg_exists = \
                        VNXSnap._is_sg_exist('.*mysql_clustered_service')
                    if not mysql_sg_exists:
                        if validating:
                            self.logger.info(msg)
                    else:
                        if validating:
                            self.logger.error(msg)
                        errors = True
        if no_snaps_exists:
            self.logger.info('{0}: No LUN snapshots found on the system '
                             '(tag={1}).'.format(self.log_prefix,
                                                 self.get_snap_prefix()))
        if validating:
            if errors:
                raise SanApiException('Invalid LUN snapshots!', 1)

        return snapshots

    def _opendj_backup(self):
        """
        Takes a backup of opendj
        :return:
        """
        self.logger.info('Opendj backup : Getting Opendj node list')
        node_list = self._get_opendj_nodes()
        self.logger.info('Opendj backup : Running Opendj '
                         'backup on {0}'.format(node_list))
        self.logger.info('Opendj backup : Running command: {0} with '
                         'backup_dir={1} and '
                         'log_dir={2}'.format(self.opendj_backup_cmd,
                                              self.opendj_backup_dir,
                                              self.opendj_log_dir))
        self.snapper.backup_opendj(node_list, self.opendj_backup_cmd,
                                   self.opendj_backup_dir, self.opendj_log_dir)
        self.logger.info('Opendj backup : Opendj backup finished successfully'
                         ' on nodes {0}'.
                         format(node_list))

    def create_snapshots(self):   # pylint: disable=R0912,R0914,R0915
        """ Create the snapshots of the LUNs
        :return:
        """
        self._opendj_backup()

        luns_to_snap = self.get_snappable_luns()
        # Get the database luns
        db_id_name = self._get_lun_ids_for_dbs(luns_to_snap)

        active_versant_node = self._get_active_versant_node()
        online_neo4j_nodes, offline_neo4j_nodes, parallel = \
                                                        self._get_neo4j_nodes()

        dps_using_neo4j = is_dps_using_neo4j()
        self.logger.info('Is Neo4j in use: {0}:'.format(dps_using_neo4j))

        if not dps_using_neo4j and not active_versant_node:
            msg = "Versant is set as DPS provider but it is not active"
            self.logger.error(msg)
            raise InvalidStateForSnapshotCreation(msg)

        if dps_using_neo4j and not active_versant_node and \
                not Vcs.is_sg_persistently_frozen(
                    Vcs.ENM_DB_CLUSTER_NAME,
                    '.*versant_clustered_service'):
            msg = \
                "Neo4j is DPS provider, Versant offline but not ' \
                'persistently frozen"
            self.logger.error(msg)
            raise InvalidStateForSnapshotCreation(msg)

        if not dps_using_neo4j and not online_neo4j_nodes and \
                not Vcs.is_sg_persistently_frozen(
                    Vcs.ENM_DB_CLUSTER_NAME,
                    '.*neo4j_clustered_service'):
            msg = \
                "Versant is DPS provider, Neo4j offline but not ' \
                'persistently frozen"
            self.logger.error(msg)
            raise InvalidStateForSnapshotCreation(msg)

        if not dps_using_neo4j and online_neo4j_nodes:
            msg = "Snapshot cannot be taken as Versant in use and there" \
                  " is active Neo4j node(s)"
            self.logger.error(msg)
            raise InvalidStateForSnapshotCreation(msg)

        if dps_using_neo4j:
            if offline_neo4j_nodes:
                if parallel:
                    msg = "Neo4j is set as DPS provider but there are " \
                          "offline neo4j nodes: %s" % offline_neo4j_nodes
                    self.logger.error(msg)
                    raise InvalidStateForSnapshotCreation(msg)
                elif not online_neo4j_nodes:
                    msg = "Neo4j is set as DPS provider but there are no " \
                          "online neo4j nodes"
                    self.logger.error(msg)
                    raise InvalidStateForSnapshotCreation(msg)

        if dps_using_neo4j and active_versant_node:
            msg = "Snapshot cannot be taken as Neo4j in use and Versant" \
                  " is active "
            raise InvalidStateForSnapshotCreation(msg)

        # Remove db luns from snap list, these get snapped via the db
        for name, dblunid in db_id_name.items():
            if name == "versantdb" and not active_versant_node:
                continue
            if "neo4j" in name and not online_neo4j_nodes:
                continue
            del luns_to_snap[dblunid]

        if dps_using_neo4j:
            # make sure we run Neo4j check point before all snaps are taken
            # then we run another one later on just before Neo4j snaps
            self.logger.info("{0} : running Neo4j force checkpoint before all "
                             "snapshots are taken".format(self.log_prefix))
            self.neo4j_snapper.force_neo4j_checkpoint(online_neo4j_nodes)

        self.logger.info("{0} : Starting to create snapshot on LUNS in "
                         "pool {1} with tag : {2}"
                         "".format(self.log_prefix, self.poolname,
                                   self.get_snap_prefix()))

        vcs = Vcs()
        opendj_luns = VNXSnap._get_opendj_luns()

        # Snap all the non-db luns ...
        for lunid in sorted(luns_to_snap.keys()):
            snapname = self.get_snap_prefix() + "_" + lunid
            lunname = luns_to_snap[lunid].name

            opendj_vcs_action = False

            if lunname in opendj_luns.keys():
                opendj_node = opendj_luns[lunname]
                opendj_vcs_action = True

            if opendj_vcs_action:
                # Offline OpenDJ, see TORF-142036
                self.logger.info("Offlining OpenDJ on {node}/{sys}".format(
                                 node=opendj_node,
                                 sys=Vcs.node_name_to_vcs_system(opendj_node)))
                vcs.hagrp_offline(".*opendj_clustered_service",
                                  Vcs.node_name_to_vcs_system(opendj_node),
                                  Vcs.ENM_DB_CLUSTER_NAME,
                                  -1)
                sleep(60)

            try:
                self.navi_cli.snap_create(lunid, snapname)
            except SanApiException:
                self.logger.exception('{plog} : Failed to create the snapshot'
                                      ' "{snapname}" on LUN {lunid}/{lunname}'
                                      ''.format(plog=self.log_prefix,
                                                lunid=lunid,
                                                snapname=snapname,
                                                lunname=lunname))
                raise
            else:
                self.logger.info('{plog} : Snapped LUN {lunid}/{lunname} -> '
                                 '{snapname}'.format(plog=self.log_prefix,
                                                     snapname=snapname,
                                                     lunid=lunid,
                                                     lunname=lunname))
            finally:
                if opendj_vcs_action:
                    self.logger.info("Onlining OpenDJ on {node}/{sys}".format(
                                     node=opendj_node,
                                     sys=Vcs.node_name_to_vcs_system(
                                             opendj_node
                                     )))
                    vcs.hagrp_online(".*opendj_clustered_service",
                                     Vcs.node_name_to_vcs_system(opendj_node),
                                     Vcs.ENM_DB_CLUSTER_NAME,
                                     -1)

        self.logger.info('{0} : Snapping the DB '
                         'luns...'.format(self.log_prefix))

        ####### Neo4j snapshot

        if dps_using_neo4j:
            lun_ids = dict([(k, v)
                            for k, v in db_id_name.items() if "neo4j" in k])
            self.logger.debug('db_id_name: {0} '.format(str(db_id_name)))
            self.logger.debug('Neo4j lun_ids: {0} '.format(str(lun_ids)))
            self.neo4j_snapper.force_neo4j_checkpoint(online_neo4j_nodes)
            self.neo4j_snapper.freeze_neo4j_db_filesystems(online_neo4j_nodes)
            self.snapper.create_neo4j_snapshot(lun_ids,
                                               self.san_cred[SAN_TYPE],
                                               self.san_cred[SAN_SPA_IP],
                                               self.san_cred[SAN_SPB_IP],
                                               online_neo4j_nodes,
                                               self.san_cred[SAN_USER],
                                               self.san_cred[SAN_PW],
                                               self.san_cred[SAN_LOGIN_SCOPE],
                                               self.get_snap_prefix(),
                                               self.descr)
            self.neo4j_snapper.unfreeze_neo4j_db_filesystems(
                             online_neo4j_nodes)
            self.logger.info("{0} : Neo4j DB LUN : Neo4j snapshot finished"
                             " successfully".format(self.log_prefix))
        else:
            self.logger.debug("Neo4j snapshot skipped as it is not set as "
                              "DPS provider")
        ####### End of Neo4j snapshot

        ####### Postgres snapshot (it has to happen after neo4j snapshot)
        pg_lun_id = db_id_name['postgresdb']
        pg_snap_name = self.get_snap_prefix() + "_" + pg_lun_id
        try:
            self.navi_cli.snap_create(pg_lun_id, pg_snap_name)
        except SanApiException:
            self.logger.exception('{plog} : Failed to create the snapshot'
                                  ' "{snapname}" on LUN {lunid}/{lunname}'
                                  ''.format(plog=self.log_prefix,
                                            lunid=pg_lun_id,
                                            snapname=pg_snap_name,
                                            lunname='postgresdb'))
            raise
        else:
            self.logger.info('{plog} : Snapped LUN {lunid}/{lunname} -> '
                             '{snapname}'.format(plog=self.log_prefix,
                                                 snapname=pg_snap_name,
                                                 lunid=pg_lun_id,
                                                 lunname='postgresdb'))

        ##### End of Postgres snapshot

        if not dps_using_neo4j:
            self.logger.info("Versant in use and active!")
            self.snapper.create_versant_snapshot('versant',
                                             db_id_name['versantdb'],
                                             self.san_cred[SAN_TYPE],
                                             self.san_cred[SAN_SPA_IP],
                                             self.san_cred[SAN_SPB_IP],
                                             active_versant_node,
                                             self.san_cred[SAN_USER],
                                             self.san_cred[SAN_PW],
                                             self.san_cred[
                                                SAN_LOGIN_SCOPE],
                                             self.get_snap_prefix(),
                                             self.descr)
            self.logger.info("{0} : Versant DB LUN : {1} snapshot "
                         "finished successfully".format(self.log_prefix,
                                            db_id_name['versantdb']))

        active_mysql_node = self._get_active_mysql_node()
        if active_mysql_node:
            self.snapper.create_mysql_snapshot('mysql', db_id_name['mysql'],
                                               self.san_cred[SAN_TYPE],
                                               self.san_cred[SAN_SPA_IP],
                                               self.san_cred[SAN_SPB_IP],
                                               active_mysql_node,
                                               self.san_cred[SAN_USER],
                                               self.san_cred[SAN_PW],
                                               self.san_cred[SAN_LOGIN_SCOPE],
                                               self.get_snap_prefix(),
                                               self.descr,
                                               self.mysql_user)
            self.logger.info("{0} : Mysql DB LUN : {1} snapshot finished "
                             "successfully".format(self.log_prefix,
                                                   db_id_name['mysql']))

        self.logger.info("%s : SAN Snapshot create "
                         "finished successfully" % self.log_prefix)

    def _get_neo4j_nodes(self):
        """ Get the all neo4j nodes
        :return: Node names
        :type: str
        """
        info, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                               '.*neo4j_clustered_service',
                                               verbose=False)
        parallel = bool([e for e in info
                           if e[Vcs.H_TYPE] == VCS_AVAIL_PARALLEL])
        online = [e['System'] for e in info
                              if e[Vcs.H_SERVICE_STATE] == 'ONLINE']
        offline = [e['System'] for e in info
                               if 'OFFLINE' in e[Vcs.H_SERVICE_STATE]]
        self.logger.info('{0} : Online Neo4j nodes: {1}. Offline Neo4j nodes: '
                         '{2}'.format(self.log_prefix, ', '.join(online),
                                      ', '.join(offline)))
        return online, offline, parallel

    def _get_active_versant_node(self):
        """
        Get the node where versant DB is active
        :return: server name
        :type: string
        """
        info, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                               '.*versant_clustered_service',
                                               verbose=False)
        for entry in info:
            if entry[Vcs.H_SERVICE_STATE] == 'ONLINE':
                self.logger.info('{0} : Active versant node is {1}'.
                                 format(self.log_prefix, entry['System']))
                return entry['System']

    def _get_active_mysql_node(self):
        """
        Get the node where mysql DB is active
        :return: server name
        :type: string
        """
        info, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                               '.*mysql_clustered_service',
                                               verbose=False)
        for entry in info:
            if entry[Vcs.H_SERVICE_STATE] == 'ONLINE':
                self.logger.info('{0} : Active mysql node is {1}'.
                                 format(self.log_prefix, entry['System']))
                return entry['System']

    @staticmethod
    def _is_sg_exist(sg_name):
        """
        Checks if a SG is deployed or already removed
        :param sg_name: Name of SG to check
        :type sg_name: String
        :return: boolean
        :rtype: boolean
        """

        info, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                                       sg_name,
                                                       verbose=False)
        if not info:
            return False
        else:
            return True

    def _get_opendj_nodes(self):
        """
        Finds a list of all the nodes opendj is active on
        :return: list of nodes hostnames
        :rtype: list
        """
        info, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                               '.*opendj_clustered_service',
                                               verbose=False)
        node_list = []
        for entry in info:
            if entry[Vcs.H_SERVICE_STATE] == 'ONLINE':
                self.logger.info('{0} : Active opendj node is {1}'.
                                 format(self.log_prefix, entry['System']))
                node_list.append(entry['System'])
        if not node_list:
            raise VcsException('OpenDJ is not active on any nodes!')
        return node_list

    def remove_snapshots(self, luns=None, lunlist=None):
        """
        Deletes SAN snapshots on the LUNs in a storage pool
        :param luns: lun id to be used
        :type luns: list
        :param lunlist : list of all the luns
        :type lunlist: dict
        :return:
        """
        if not lunlist:
            lunlist = self.get_snappable_luns(luns, for_snap_remove=True)
        if luns:
            # Remove any not in the passed in list e.g. snaps were created
            # prior to adding a new lun i.e. expansion
            filter_luns(lunlist, luns)
        self._remove_snaps_by_prefix(self.get_snap_prefix(), luns=lunlist)

    def _remove_snaps_by_prefix(self, snapname_prefix, luns=None):
        """
        Remove snapshots with the name snapshot prefix
        :param snapname_prefix : name of snapshot prefix
        :type snapname_prefix: string
        :param luns : luns details
        :type luns: dict
        :return:
        """
        self.logger.info('{0} : Looking for snapshots to destroy.'.format
                         (self.log_prefix))
        if luns:
            snappable_luns = luns
        else:
            snappable_luns = self.get_snappable_luns()

        snapped_luns = self._get_lun_snapshots(snappable_luns,
                                               snap_prefix=snapname_prefix)
        snaps_destroyed = False
        # thread_pool = ThreadPool(processes=self.num_of_threads)
        # number of processes hardcoded to 1 as workaround until IS-3509
        # gets resolved
        thread_pool = ThreadPool(processes=1)

        thread_results = []

        try:
            self._remove_snaps_wrap(snappable_luns, snapped_luns,
                                    thread_pool,
                                    thread_results)
            thread_pool.close()
            thread_pool.join()
        except KeyboardInterrupt:
            thread_pool.terminate()
            raise

        all_ok = True
        for success, exception, destroyed in thread_results:
            if not success:
                all_ok = False
                if exception:
                    self.logger.error('{0}'.format(exception))
            if destroyed:
                snaps_destroyed = True
        if not all_ok:
            raise SanApiException('{0} : destroy snapshot failed'
                                  .format(self.log_prefix), 1)
        if snaps_destroyed:
            self.logger.info('{0} : destroy snapshots finished '
                             'successfully'.format(self.log_prefix))
        else:
            self.logger.info('{0} : No snapshots found to destroy.'
                             ''.format(self.log_prefix))

    def _remove_snaps_wrap(self, snappable_luns, snapped_luns, thread_pool,
                           thread_results):
        """
        Wrapper to call remove snapshot in threads.
        :param snappable_luns : luns which should have snapshots
        :type snappable_luns: dict
        :param snapped_luns : luns with snapshots
        :type snapped_luns: dict
        :param thread_pool : thread pool
        :type thread_pool: thread pool
        :param thread_results : execution result of thread
        :type thread_results: list
        :return:
        """

        def report(result):
            """
            Add result to list
            :param result: Thread result tuple
            :return:
            """
            thread_results.append(result)

        for lunid in sorted(snapped_luns.keys()):
            lun_snapshots = snapped_luns[lunid]
            lunname = snappable_luns[lunid].name
            for snapshot in lun_snapshots:
                thread_pool.apply_async(
                    self._remove_lun_snaps, args=(lunid, snapshot,
                                                  lunname),
                    callback=report)

    def _remove_lun_snaps(self, lunid, snapshot, lunname):
        """
        Function to remove the LUN snapshot
        :param lunid: lun id
        :type lunid: string
        :param snapshot : snapshots
        :type snapshot: named tuple
        :param lunname : name of the lun
        :type lunname: string
        :return: Thread result
        """
        snaps_destroyed = False
        try:
            self.logger.info('{plog} : Destroying snapshot "{snapname}" on'
                             ' LUN {lunid}/{lunname}'.format
                             (plog=self.log_prefix,
                              snapname=snapshot.snap_name,
                              lunid=lunid, lunname=lunname))
            self.navi_cli.snap_destroy(snapshot.snap_name)
            snaps_destroyed = True
        except Exception as error:  # pylint: disable=W0703
            self.logger.info('{plog} : Destroy snapshot for "{snapname}" '
                             'on LUN {lunid}/{lunname} failed with error {err}'
                             ''.format(plog=self.log_prefix,
                                       snapname=snapshot.snap_name,
                                       lunid=lunid,
                                       lunname=lunname, err=str(error)))
            return False, str(error), snaps_destroyed
        return True, None, snaps_destroyed

    def validate(self, luns=None):
        """
        Validates that all the luns have an associated snap
        :param luns: List of LUNs whose snapshot to be validated
        :type luns: List
        :return:
        """
        self.list_snapshots(False, luns, validating=True)
        self.logger.info('{plog} : All LUNs in storage pool {pool} have'
                         ' expected snapshots.'.format(plog=self.log_prefix,
                                                       pool=self.poolname))

    def restore_snapshots(self,  # pylint: disable=R0912
                          restore_lunids=None):
        """
        Restore snaps after some validation has been done.
        :param restore_lunids:List of LUNs to be restored
        :type restore_lunids: List
        :return:
        """
        lunlist = self.get_snappable_luns(restore_lunids)
        if restore_lunids:
            # Remove any not in the passed in list e.g. snaps were created
            # prior to adding a new lun i.e. expansion
            filter_luns(lunlist, restore_lunids)
        all_lun_snapshots = self._get_lun_snapshots(lunlist, self._snap_prefix)
        self.logger.info("{plog} : Starting restore snapshot on "
                         "LUNS in pool {pool}".format(plog=self.log_prefix,
                                                      pool=self.poolname))
        for lunid in sorted(all_lun_snapshots.keys()):
            lunsnaps = all_lun_snapshots[lunid]
            if len(lunsnaps) == 0:
                lunname = lunlist[lunid].name
                if not 'mysql' in lunname:
                    raise SanApiException('No snapshot found on '
                                        'LUN {0}'.format(lunlist[lunid].name),
                                        ExitCodes.LITP_SNAP_ERROR)
                else:
                    mysql_sg_exists = \
                        VNXSnap._is_sg_exist('.*mysql_clustered_service')
                    if mysql_sg_exists:
                        raise SanApiException('No snapshot found on '
                                        'LUN {0}'.format(lunlist[lunid].name),
                                        ExitCodes.LITP_SNAP_ERROR)
            elif len(lunsnaps) > 1:
                raise SanApiException('More than one snapshot found on '
                                      'LUN {0}'.format(lunlist[lunid].name),
                                      ExitCodes.LITP_SNAP_ERROR)

        # thread_pool = ThreadPool(processes=self.num_of_threads)
        #  number of processes hardcoded to 1 as workaround until IS-3509
        # gets resolved
        thread_pool = ThreadPool(processes=1)

        thread_results = []

        def report(result):
            """
            Add result to list
            :param result: Thread result tuple
            :return:
            """
            thread_results.append(result)

        try:
            for lunid in sorted(all_lun_snapshots.keys()):
                thread_pool.apply_async(self.restore_san_lun,
                                        args=(lunid, lunlist,
                                              all_lun_snapshots),
                                        callback=report)
            thread_pool.close()
            # Wait for pool to complete tasks.
            thread_pool.join()
        except KeyboardInterrupt:
            thread_pool.terminate()
            raise

        if not thread_results:
            raise SanApiException("{0} : Restore LUN threads did not return "
                                  "any result".format(self.log_prefix), 1)

        all_ok = True
        for success, lun in thread_results:
            if not success:
                all_ok = False
        if not all_ok:
            raise SanApiException('{0}: SAN snapshot restore failed'
                                  ''.format(self.log_prefix), 1)
        if len(thread_results) != len(lunlist):
            lunlist_result = dict(lunlist)
            for success, lun in thread_results:
                del lunlist_result[lun.id]
            for lunid in lunlist_result:
                self.logger.error("{plog} : Restore LUN {id}/{name} thread did"
                                  " not return any result".
                                  format(plog=self.log_prefix, id=lunid,
                                         name=lunlist_result[lunid].name))
            raise SanApiException("{0} : All the SAN snapshot restore threads"
                                  " did not return  result".format
                                  (self.log_prefix), 1)
        self.logger.info("%s : SAN Snapshot restore finished successfully"
                         % self.log_prefix)

    def remove_snaps_by_prefix(self, restore_lunids=None, lunlist=None):
        """
        Function to remove the snapshot with prefix name
        :param restore_lunids: restored luns
        :type restore_lunids: list
        :param lunlist : list of all the luns
        :type lunlist: dict
        :return:
        """
        # VNX snap creates one more snapshot just before the restore
        # so needs to remove that snap
        if not lunlist:
            lunlist = self.get_snappable_luns(restore_lunids)
        if restore_lunids:
            # Remove any not in the passed in list e.g. snaps were created
            # prior to adding a new lun i.e. expansion
            filter_luns(lunlist, restore_lunids)
        self.logger.info("%s : Calling destroy snapshot for the"
                         " snapshot created (if any) by VNX snap just before "
                         "the restore" % self.log_prefix)
        # pass on snapstr to  do_destroy_snapshot so that it will
        # not delete any of the snapshots which were there before
        # the restore
        self._remove_snaps_by_prefix('enm_upgrade_bkup', luns=lunlist)

    def restore_san_lun(self, lunid, lunlist, snapshots):
        """
        Function to restore the snapshot
        :param lunid: lun id
        :type lunid: string
        :param lunlist : list of all the luns
        :type lunlist: dict
        :param snapshots : name of the snapshots
        :type snapshots: dict
        :return:
        """
        try:
            snapshot = snapshots[lunid][0]
            snapname = snapshot.snap_name
            lunname = lunlist[lunid].name
            self.logger.info('{plog} : Restoring LUN {id}/{name} with '
                             'snapshot {snapname}'.format
                             (plog=self.log_prefix, id=lunid, name=lunname,
                              snapname=snapname))
            self.navi_cli.snap_restore(lunid, snapname)
        except Exception as error:  # pylint: disable=W0703
            lunname = lunlist[lunid].name
            if not 'mysql' in lunname:
                self.logger.error('{plog} : Restore LUN {id}/{name} failed '
                                  'with error - {err}'.format
                                  (plog=self.log_prefix, id=lunid,
                                   name=lunlist[lunid].name, err=str(error)))
                return False, lunlist[lunid]
            else:
                mysql_sg_exists = \
                    VNXSnap._is_sg_exist('.*mysql_clustered_service')
                if mysql_sg_exists:
                    self.logger.error('{plog} : Restore LUN {id}/{name} '
                                      'failed with error - {err}'.format
                                      (plog=self.log_prefix, id=lunid,
                                       name=lunlist[lunid].name,
                                       err=str(error)))
                    return False, lunlist[lunid]
        return True, lunlist[lunid]

    def opendj_backup_cleanup(self):
        """
        Function to clean opendj backup
        :param :
        :return:
        """
        opendj_node_list = self._get_opendj_nodes()
        self.logger.info('Cleaning up opendj backup files {0} {1}'.
                         format(self.opendj_backup_dir, self.opendj_log_dir))
        self.snapper.cleanup_opendj(opendj_node_list,
                                    self.opendj_backup_dir,
                                    self.opendj_log_dir)
        self.logger.info('Successfully deleted opendj backup files {0} {1}'.
                         format(self.opendj_backup_dir, self.opendj_log_dir))

    @staticmethod
    def _get_opendj_luns():
        """
        Function to get LUN names for OpenDJ
        :param :
        :returns: opendj_luns_nodes: dictionary with LUN names ad key
                    and node names as values
        :rtype dict
        """
        litp = LitpRestClient()
        opendj_luns_nodes = {}
        for node_path in VNXSnap._get_opendj_node_paths():
            device_name = VNXSnap._get_device(node_path, '/')
            lun_name = VNXSnap._get_lun_name(node_path, device_name)
            node_name = litp.get(node_path, log=False)['id']
            opendj_luns_nodes[lun_name] = node_name
        return opendj_luns_nodes

    @staticmethod
    def _get_opendj_node_paths():
        """
        Function to get paths for nodes on which OpenDJ is installed
        :param :
        :returns: list with node path in model
        :rtype list of string
        """
        litp = LitpRestClient()
        for deployment in litp.get_children('/deployments'):
            for cluster in litp.get_children(
                    '{0}/clusters'.format(deployment['path'])):
                for service in litp.get_children(
                        '{0}/services'.format(cluster['path'])):
                    applications_path = \
                        '{0}/applications'.format(service['path'])
                    if litp.exists(applications_path):
                        for app in litp.get_children(applications_path):
                            if app['data']['item-type-name'] == \
                                        'reference-to-opendj-service':
                                node_list = \
                                    service['data']['properties']['node_list']
                                node_names = node_list.split(',')
                                path = cluster['path'] + '/nodes/'
                                return [path + node for node in node_names]

    @staticmethod
    def _get_device(node_path, mount_point):
        """
        Function to find out what device corresponds to particular mount point
        on particular node
        :param node_path: node path in model
        :type node_path: string
        :param mount_point: mount point to find
        :type mount_point: string
        :returns: device name
        :rtype string
        """
        litp = LitpRestClient()
        for volume_group in litp.get_children(
                '{0}/storage_profile/volume_groups'.format(node_path)):
            for file_system in litp.get_children(
                    '{0}/file_systems'.format(volume_group['path'])):
                if mount_point == \
                  file_system['data']['properties']['mount_point']:
                    vg_props = litp.get(
                            '{0}/physical_devices/internal'.format(
                                    volume_group['path']),
                            log=False)['properties']
                    return vg_props['device_name']

    @staticmethod
    def _get_lun_name(node_path, device_name):
        """
        Function to get LUN name based on device name and node path in model
        :param node_path: node path in model
        :type node_path: string
        :param device_name: device name
        :type device_name: string
        :returns: LUN name
        :rtype string
        """
        litp = LitpRestClient()
        lun_disks = litp.get_items_by_type(node_path + '/system/disks',
                                           'reference-to-lun-disk', [])
        for lun_disk in lun_disks:
            if lun_disk['data']['properties']['name'] == device_name:
                return lun_disk['data']['properties']['lun_name']
