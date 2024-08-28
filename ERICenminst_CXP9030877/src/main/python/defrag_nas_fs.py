"""
NAS filesystem defrag script
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

import logging

from h_litp.litp_rest_client import LitpRestClient
from h_logging.enminst_logger import init_enminst_logging
from h_logging.enminst_logger import set_logging_level
from litp.core.base_plugin_api import BasePluginApi
from litp.core.model_manager import ModelManager
from h_util.h_utils import create_ssh_client


def disconnect(ssh):
    """
    Disconnect from the SFS console
    :param ssh: An instance reference to paramiko.SSHClient
    :type ssh: SSHClient
    """
    ssh.close()


def nas_command(ssh, command):
    """
    Execute a command on remote system
    :param ssh: An instance reference to paramiko.SSHClient
    :type ssh: SSHClient
    :param command: A Command to be executed
    :type command: str
    :return: Return code, Command output
    :rtype: list
    """
    _, stdout, stderr = ssh.exec_command(command)
    retcode = stdout.channel.recv_exit_status()
    if retcode != 0:
        err = [line.strip() for line in stderr.readlines()]
        raise NasCommandException(err)
    output = [line.strip() for line in stdout.readlines()]
    return retcode, output


class NasCommandException(Exception):
    """ Operation failed """
    pass


class NasLitpModel(object):  # pylint: disable=R0903
    """
    Provide mechanism to obtain NAS information from the LITP model
    """
    SP_PATH = '/infrastructure/storage/storage_providers'

    def __init__(self):
        self.log = logging.getLogger('enminst')
        self.rest = LitpRestClient()

    def get_nas_info(self):
        """
        Obtain sfs service with a list of file system from the model
        :return: Information for all sfs services and their file systems
        :rtype: dict
        {sfs_id : [console_ipv4, user_name, password_key, fs_list]}
        """
        self.log.info('Obtaining NAS information from the LITP model')
        sfs_info = {}
        items = self.rest.get_items_by_type(NasLitpModel.SP_PATH,
                                            'sfs-service', [])
        if not items:
            self.log.info('Cannot find sfs-service in Applied state')
        for item in items:
            sfs_info[item['data']['id']] = [
                item['data']['properties']['management_ipv4'],
                item['data']['properties']['user_name'],
                item['data']['properties']['password_key'],
                item['path']]

        for sfs_id in sfs_info:
            fs_list = []
            items = self.rest.get_items_by_type(
                    sfs_info[sfs_id][-1], 'sfs-filesystem', [])
            if not items:
                self.log.info('Cannot find sfs-filesystem in Applied state')
            for item in items:
                fs_list.append(item['data']['properties']['path'])
            sfs_info[sfs_id][-1] = fs_list
        return sfs_info


class DefragNasFs(object):
    """
    Provide mechanism to perform file system defragmentation on NAS.
    The fsadm command executed with -d option reorganizes directories
    on a volume
    """

    def __init__(self):
        self.log = logging.getLogger('enminst')

    def connect_to_nas(self, nasip, username, sfs_key):
        """
        Initilise SSH connection to NAS console
        :param nasip: SFS management address
        :type nasip: str
        :param username: SFS management user name
        :type username: str
        :param sfs_key: SFS password key
        :type sfs_key: str
        :return: Instance reference to paramiko.SSClient
        :rtype: SSHClient
        """
        model_manager = ModelManager()
        base_api = BasePluginApi(model_manager)
        passw = base_api.get_password(sfs_key, username)
        if passw is None:
            self.log.error('Unable to obtain password for {0}'.format(
                    username))
            raise SystemExit()
        ssh = create_ssh_client(host=nasip, username=username, password=passw)
        self.log.info('Connected to NAS: {0}'.format(nasip))
        return ssh

    def get_nas_mounted_fs(self, ssh):
        """
        Obtain a list of mounted file systems on NAS
        :param ssh: An instance reference to paramiko.SSHClient
        :type ssh: SSHClient
        :return: A list of file systems defined and mounted on NAS
        :rtype: list
        """
        mounted_fs = []
        mount_col_index = 2
        try:
            mounts = nas_command(ssh, r'/bin/mount')[1]
            for mount in mounts:
                parts = mount.split()
                if len(parts) > mount_col_index and r'/vx/' in \
                        parts[mount_col_index]:
                    mounted_fs.append(parts[mount_col_index])
        except NasCommandException:
            self.log.exception('Could not get a list of mounted filesystems!')
            raise
        self.log.info('Mounted File systems: {0}'.format(
                ', '.join(mounted_fs)))
        return mounted_fs

    def defrag_fs(self):
        """
        Execute fsadm command for each file system defined in the LITP model
        and mounted on SFS
        """
        fsadm = '/opt/VRTS/bin/fsadm -t vxfs -T 3600 -d {0}'
        nlm = NasLitpModel()
        nas_info = nlm.get_nas_info()
        for nas in nas_info:
            ssh = self.connect_to_nas(nas_info[nas][0], nas_info[nas][1],
                                      nas_info[nas][2])
            mounted_fs = self.get_nas_mounted_fs(ssh)
            for filesystem in nas_info[nas][-1]:
                if filesystem in mounted_fs:
                    command = fsadm.format(filesystem)
                    self.log.info('Executing: {0}'.format(command))
                    try:
                        nas_command(ssh, command)
                    except NasCommandException as err:
                        self.log.exception(err)
                    else:
                        self.log.info('{0} defragmented successfully'.format(
                                filesystem))
                else:
                    self.log.info(
                            'File system {0} defined in the LITP model but '
                            'not mounted on the NAS. Skipping '
                            'defragmentation'.format(filesystem))
            disconnect(ssh)


def main():
    """
    Main function
    :return:
    """
    log = init_enminst_logging()
    set_logging_level(log, 'INFO')
    dnf = DefragNasFs()
    dnf.defrag_fs()


if __name__ == '__main__':
    main()
