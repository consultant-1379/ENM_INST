#!/bin/env python
""" Module obtaining details about Neo4j filesystem """
import os
import json

from base_agent import RPCAgent


class Neo4jFilesystemStatus(RPCAgent):
    """ Class that obtains data about Neo4j filesystem and mount """
    NEO4J_DATA = "/ericsson/neo4j_data"
    NEO4J_DB_GRAPH = os.path.join(NEO4J_DATA, "databases/graph.db")
    NEO4J_LOGS = os.path.join(NEO4J_DATA, "logs")
    CLUSTER_STATE = os.path.join(NEO4J_DATA, "cluster-state")

    def _get_disk_usage(self, file_path):
        """ Fetching disk usage in bytes for a given file.
        If file not found, return 0 bytes
        :param file_path: can be single file, dir or a wildcard
        :return: int
        """
        _, out, err = self.execute("/usr/bin/du -scb %s | tail -1" % file_path,
                                   use_shell=True)
        if err:
            raise IOError("Failed to get '%s' directory size. "
                          "Error: %s" % (file_path, err))
        return int(out.split()[0])

    @property
    def _required_uplift_space(self):
        """ Returns required space for uplift in bytes.
        Excluded files and transactions are not copied during migration and
        subtracted from required uplift space.
        :return: int
        """
        excluded_files = [
            "neostore.relationshipgroupstore.db",
            "neostore.nodestore.db.labels",
            "neostore.nodestore.db",
            "neostore.relationshipstore.db",
            "neostore.labelscanstore.db"
        ]
        excluded_files = [os.path.join(self.NEO4J_DB_GRAPH, xfile)
                          for xfile in excluded_files]

        neostore_files = os.path.join(self.NEO4J_DB_GRAPH, "neostore*")
        neostore_files_size = self._get_disk_usage(neostore_files)

        excluded_files_size = [os.path.getsize(xfile) for xfile
                               in excluded_files if os.path.exists(xfile)]

        prunable_transactions_size = self._transactions_size - \
                                     self._retained_transactions_size
        return neostore_files_size - sum(excluded_files_size) \
                                   - prunable_transactions_size

    @property
    def _transactions_size(self):
        """ Size of all transaction files in bytes
        :return: int
        """
        return self._get_disk_usage(os.path.join(self.NEO4J_DB_GRAPH,
                                                 "neostore.transaction.*"))

    @property
    def _retained_transactions_size(self):
        """ Get a size of transactions that are retained
        :return: int
        """
        transactions = os.path.join(self.NEO4J_DB_GRAPH,
                                    "neostore.transaction.*")
        cmd = "du -scb $(ls -1t %s | tail -n +1  | head -6) | tail -1"

        _, out, err = self.execute(cmd % transactions, use_shell=True)
        if err:
            raise IOError("Failed to get retained transactions size. "
                          "Error: %s" % err)
        return int(out.split()[0])

    @property
    def _labelscanstore_size(self):
        """ Size of neostore.labelscanstore.db file in bytes
        :return: int
        """
        labelscanstore = os.path.join(self.NEO4J_DB_GRAPH,
                                      "neostore.labelscanstore.db")
        if not os.path.exists(labelscanstore):
            return 0
        return os.path.getsize(labelscanstore)

    @property
    def _logs_size(self):
        """ Size of all Neo4j logs in bytes
        :return: int
        """
        if not os.path.exists(self.NEO4J_LOGS):
            return 0
        return self._get_disk_usage(self.NEO4J_LOGS)

    @property
    def _cluster_state_size(self):
        """ Size of cluster state directory in bytes
        :return: int
        """
        if not os.path.exists(self.CLUSTER_STATE):
            return 0
        return self._get_disk_usage(self.CLUSTER_STATE)

    @property
    def _schema_size(self):
        """ Size of Neo4j schema directory in bytes
        :return: int
        """
        schema = os.path.join(self.NEO4J_DB_GRAPH, "schema")
        if not os.path.exists(schema):
            return 0
        return self._get_disk_usage(schema)

    @property
    def _mount_data(self):
        """ Fetch information about /ericsson/neo4j_data mount
        with usage in bytes
        :return: dict
        """
        header = ['fs_path', 'size', 'used', 'available',
                  'used_perc', 'mount_path']

        retcode, out, stderr = self.execute("/bin/df -B1 %s" % self.NEO4J_DATA,
                                            use_shell=True)
        if retcode:
            raise IOError("Failed to get '%s' mount data. "
                          "Error: %s" % (self.NEO4J_DATA, stderr))
        non_empty_lines = [i.lstrip() for i in out.splitlines() if i.strip()]

        data = []
        fs_path = None
        for line in non_empty_lines[1:]:
            cols = line.split()
            if len(cols) == 1:
                fs_path = cols[0]
                continue
            if fs_path:
                cols = [fs_path] + cols
                fs_path = None
            data.append(dict(zip(header, cols)))
        return data[0]

    def pre_uplift_space_check(self, args):  # pylint: disable=R0914
        """ Determines if Neo4j store migration has enough disk space on
        /ericsson/neo4j_data mount and returns detailed status.
        Formula for determining space sufficiency.
        free + can_free + extension - reserved > required
        where:
            free -> current free space
            can_free -> space that can be potentially be reclaimed
                        during store migration by removing non required files.
                        transactions, logs, schema and labelscanstore
            extension -> size of possible LUN extension in case store migration
                        still require more space
            reserved -> 5% of the total allocated mount space is reserved
                        to not fill file system to 100%
            required -> space required for store migration, i.e., files that
                        are copied from old store to new store during migration
        :return: dict
        """
        expansion_error = ""
        try:
            # required space for uplift
            required = self._required_uplift_space

            # Obtain space possible to free up in bytes and sum it.
            labelscanstore_size = self._labelscanstore_size
            logs_size = self._logs_size
            schema_size = self._schema_size
            # this value can be 0 if number of transactions on the filesystem
            # is same as retention(6) number
            prunable_transactions_size = self._transactions_size - \
                                         self._retained_transactions_size
            cluster_state = self._cluster_state_size
            space_can_free = sum([labelscanstore_size, logs_size,
                                  prunable_transactions_size, schema_size,
                                  cluster_state])

            # Obtain Neo4j mount details with usage in bytes
            mount_data = self._mount_data

            is_cluster = self.execute("/bin/grep 'db-3' /etc/hosts",
                                      use_shell=True)[0] == 0
            has_neo4jbur = self.execute("/opt/VRTSvcs/bin/hagrp -list | "
                                        "/bin/grep neo4jbur",
                                        use_shell=True)[0] == 0
            if is_cluster or has_neo4jbur:
                # Obtain possible extension size of Neo4j Lun in bytes
                # 5% is reserved for the pool
                extension_size = int(args['lun_size']) * 0.95 \
                                 - int(mount_data["size"])
            else:
                extension_size = 0
                expansion_error = "A filesystem expansion is only supported " \
                                  "on 15k/40k systems when neo4jbur volume " \
                                  "is available"

        except Exception as error:  # pylint: disable=W0703
            return self.get_return_struct(1, stderr=str(error))

        # Calculate total possible free space
        total_avail_space = int(mount_data["available"]) + space_can_free \
                                                         + extension_size

        # 5% of total Neo4j mount allocated space is reserved to avoid
        # mount filling up to 100%
        reserved_space = int(int(mount_data["size"]) * 0.05)

        # Calculate if Neo4j mount space is sufficient to run store migration
        enough_space = total_avail_space - reserved_space > required

        resp = {
            "enough_space": enough_space,
            "avail_space": int(mount_data["available"]),
            "can_free": {
                "labels_scan": labelscanstore_size,
                "transactions": prunable_transactions_size,
                "logs": logs_size,
                "schema": schema_size,
                "cluster_state": cluster_state,
                "total": space_can_free
            },
            "expansion_error": expansion_error,
            "extension": extension_size,
            "required": required,
            "reserved": reserved_space,
        }
        json.dumps(resp)
        return self.get_return_struct(0, stdout=resp)

    def has_file(self, args):
        """ Check whether a file exist or not
        :param args: dict
        :return: str
        """
        file_path = args['file_path']
        resp = str(os.path.exists(file_path)).lower()
        return self.get_return_struct(0, stdout=resp)

    def check_ssh_connectivity(self, args):
        """ Check SSH connectivity given credentials
        :param args: dict
        :return: str
        """
        host = args['host']
        user = args['user']
        password = args.get('password')
        key_filename = args.get('key_filename')
        sudo = args.get('sudo', False)
        # pylint: disable=F0401
        from pyu.os.shell.session import ShellSession, SshConnectionFailed
        session = ShellSession(host, user, password=password,
                               key_filename=key_filename, sudo=sudo)
        try:
            session.check_connectivity(True)
        except SshConnectionFailed as err:
            return self.get_return_struct(1, stderr=str(err))
        return self.get_return_struct(0, stdout='ok')


if __name__ == '__main__':
    Neo4jFilesystemStatus().action()
