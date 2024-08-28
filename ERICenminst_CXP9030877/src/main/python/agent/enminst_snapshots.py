#!/bin/env python
"""
 Enminst MCO agent implementation for remote snapshots.
"""

##############################################################################
# COPYRIGHT Ericsson AB 2017
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import logging
import logging.config
from json import loads
from os.path import dirname, abspath, join
from socket import gethostname

from base_agent import RPCAgent


class EnminstRemoteSnapshot(RPCAgent):
    """
    Agent implementation of LVM snapshot functions
    """
    LVCREATE = '/sbin/lvcreate'
    LVREMOVE = '/sbin/lvremove'
    LVCONVERT = '/sbin/lvconvert'
    SYNC = '/bin/sync'

    def __init__(self):
        _lcfg = join(dirname(abspath(__file__)), 'logging.cfg')
        logging.config.fileConfig(_lcfg)
        self.logger = logging.getLogger('enminst_snapshots')

    @staticmethod
    def enable_debug(args):
        """
        Enable debug logging of 'verbose' passed from client
        :param args: Arguements from the 'mco rpc ...' command issued on the
        LMS

        """
        if 'verbose' in args and args['verbose'].lower() == 'true':
            logging.getLogger().setLevel(logging.DEBUG)

    def create_lv_snapshots(self, args):
        """
        Create snapshots of local logical volumes.
        args['snap_info'] : dictionary of hosts->filesystems to be snapped.

        args['snap_info'] -> {
            '<hostname_1>': [
                {
                    'fs_snap_size': '<int>',
                    'snap_name': '<string>',
                    'lv_path': '<string>'
                },
                ...
                {
                    'fs_snap_size': '<int>',
                    'snap_name': '<string>',
                    'lv_path': '<string>'
                }
            ]
            ...
            '<hostname_N>': [...]
        }
        If the local hostname is not in args['snap_info'] then no LVM
        snapshots are taken.

        :param args: Arguements from the 'mco rpc ...' command issued on the
        LMS
        :type args: dict
        :returns: Results of each volume snapshot creation
        :rtype: dict
        """
        self.enable_debug(args)
        snap_vol_data = loads(args['snap_info'])
        this_hostname = gethostname()
        if this_hostname in snap_vol_data:
            snap_info = snap_vol_data[this_hostname]
            snap_tag = None
            if 'snap_tag' in snap_vol_data:
                snap_tag = snap_vol_data['snap_tag']
            _results = []
            for snap_fs in snap_info:
                _command = [EnminstRemoteSnapshot.LVCREATE,
                            '--snapshot']
                if snap_tag:
                    _command.append('--addtag')
                    _command.append(snap_tag)
                _command.append('--extents')
                _command.append('{0}%ORIGIN'.format(snap_fs['fs_snap_size']))
                _command.append('--name')
                _command.append(snap_fs['snap_name'])
                _command.append(snap_fs['lv_path'])

                self.logger.info(' '.join(_command))
                exitcode, _stdout, _stderr = self.execute(_command)
                if exitcode:
                    self.logger.info(_stderr)
                    return self.get_return_struct(
                        exitcode, stderr=_stderr)
                _results.append(_stdout)
                self.logger.info(_stdout)
            return self.get_return_struct(0,
                                          '\n'.join(_results))
        else:
            _msg = 'No local LVM filesystems to snap.'
            self.logger.info(_msg)
            return self.get_return_struct(0, stdout=_msg)

    def delete_lv_snapshots(self, args):
        """
        Delete LV snapshot with specific tag

        :param args: Client args: {'tag_name': '...'}
        :type args: dict
        :returns: Output of lvremove
        :rtype: dict
        """
        self.enable_debug(args)
        tag_name = args['tag_name']
        _command = [EnminstRemoteSnapshot.LVREMOVE,
                    '--force',
                    '@{0}'.format(tag_name)]
        self.logger.info(' '.join(_command))
        exitcode, _stdout, _stderr = self.execute(_command)
        if exitcode:
            self.logger.info(_stderr)
            return self.get_return_struct(
                    exitcode, stderr=_stderr)
        else:
            self.logger.info(_stdout)
            return self.get_return_struct(0, _stdout)

    def restore_lv_snapshots(self, args):
        """
        Restore LV snapshots with specific tag

        :param args: Client args: {'tag_name': '...'}
        :type args: dict
        :returns: Output of lvconvert
        :rtype: dict
        """
        self.enable_debug(args)
        tag_name = args['tag_name']
        _command = [EnminstRemoteSnapshot.LVCONVERT,
                    '--merge',
                    '@{0}'.format(tag_name)]
        self.logger.info(' '.join(_command))
        exitcode, _stdout, _stderr = self.execute(_command)
        if exitcode:
            self.logger.info(_stderr)
            return self.get_return_struct(
                    exitcode, stderr=_stderr)
        else:
            self.logger.info(_stdout)
            return self.get_return_struct(0, _stdout)

    def execute_sync_command(self, args):
        """
        Execute sync command to flush filesystem buffers
        to disk prior to hard reboot

        :param args: dict
        :returns: Output of /bin/sync
        :rtype: dict
        """
        self.enable_debug(args)
        _command = [EnminstRemoteSnapshot.SYNC]
        self.logger.info(' '.join(_command))
        exitcode, _stdout, _stderr = self.execute(_command)
        if exitcode:
            self.logger.info(_stderr)
            return self.get_return_struct(
                    exitcode, stderr=_stderr)
        else:
            self.logger.info(_stdout)
            return self.get_return_struct(0, _stdout)

if __name__ == '__main__':
    EnminstRemoteSnapshot().action()
