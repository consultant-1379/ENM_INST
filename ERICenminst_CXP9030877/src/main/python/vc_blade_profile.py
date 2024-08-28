# -*- coding: utf-8 -*-
"""
Script to configure Virtual Connect server profiles
"""
####################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
####################################################################
# pylint: disable=R0902,R0904,R0912,R0914,R0915,W0703,W1201
import logging
import os
import re
import sys
import time

import argparse
import pexpect

SSH_PX = '/usr/bin/ssh'
SED_DATA = {}
LOG_FILE = '/var/log/vc_profile_configuration.log'


class HpVcProfile(object):
    """
    Class to handle HP VirtualConnect profile manipulation
    """
    def __init__(self, ip, username, password, log):
        self.vcip = ip
        self.vcuser = username
        self.vcpasswd = password
        self.last_loaded_profile = ''
        self.log = log
        self.spawned = None
        self.blades_info = {}
        self.current_vc_networks = {}
        self.current_vc_uplinks = []
        self.network_definitions = []
        self.profile_definitions = []  # prfile definition

    def vc_connect(self, timeout=80):
        """
        Connect the the VC via SSH
        :param timeout: timeout or password...........
        :return:
        """
        ssh_vc = '{2} -oStrictHostKeyChecking=no {0}@{1}'.format(
                self.vcuser, self.vcip, SSH_PX)
        self.spawned = pexpect.spawn(ssh_vc)
        self.spawned.expect('Password:', timeout)  # default value is 30s
        self.spawned.sendline(self.vcpasswd)
        i = self.spawned.expect(['Virtual Connect Manager not found', '->'],
                                timeout)
        if i == 0:  # connected to standby VC ethernet module
            self.vc_disconnect()
            return 5
        result = self.spawned.before
        result = re.search(r'No enclosures currently exist', result)
        if result:
            raise RuntimeError(
                    'No enclosures currently exist in the domain. Please use '
                    'the \'import enclosure\' command to import an enclosure.')

    def vc_connect_sim(self, timeout=80):
        """
        Connect to VC sim
        :param timeout: Timeout
        :return:
        """
        ssh_vc = '{0} -oStrictHostKeyChecking=no vcmcli@{1}'.format(
                SSH_PX, self.vcip)
        self.spawned = pexpect.spawn(ssh_vc)
        self.spawned.expect('password:', timeout)
        self.spawned.sendline('passw0rd')
        self.spawned.expect('VCM User Name:', timeout)
        self.spawned.sendline(self.vcuser)
        self.spawned.expect('Password:', timeout)  # default value is 30s
        self.spawned.sendline(self.vcpasswd)
        self.spawned.expect('->', timeout)
        result = self.spawned.before
        result = re.search(r'No enclosures currently exist', result)
        if result:
            raise RuntimeError(
                    'No enclosures currently exist in the domain. Please use '
                    'the \'import enclosure\' command to import an enclosure.')

    def vc_disconnect(self):
        """
        Disconnect from VC
        :return:
        """
        self.spawned.sendline('exit')
        self.spawned.close(force=True)

    def vc_exec(self, command, timeout=90):
        """
        Execute a VC command
        :param command: The command to run
        :param timeout: Max time to wait for a response
        :return:
        """
        self.log.info('exec: {0}'.format(command))
        self.spawned.sendline(command)
        self.spawned.expect('->', timeout)
        result = self.spawned.before
        result = re.search(r'\r\n(.+)', result, re.S).group(1)
        self.log.debug(result)
        return result

    def vc_blades_to_configure(self):
        """
        Get a list of blades to configure on VC
        :return:
        """
        self.blades_info = {}

        sed_nodes = [
            (key, value.upper()) for key, value in SED_DATA.items()
            if re.search(r'node\d+_serial$', key)]

        command = 'SHOW SERVER *'
        results = self.vc_exec(command)
        for blade in re.split(r'-+\r\n', results):
            b_snumber = (
                re.search(r'Serial Number\s*:(.*)', blade).group(1)).strip()
            for key, value in sed_nodes:
                if value == b_snumber:
                    node = re.sub(r'^(.*node\d+)_serial$', r'\1', key)
                    sed_p_name = SED_DATA['{0}_vcProfile'.format(node)]
                    sed_sname = SED_DATA['{0}_hostname'.format(node)]
                    sed_server_type = re.sub(r'^(.*node)\d+_serial$',
                                             r'\1', key)
                    b_id = (re.search(r'Server ID\s*:(.*)',
                                      blade).group(1)).strip()
                    b_status = (re.search(r'Status\s*:(.*)',
                                          blade).group(1)).strip()
                    b_power = (re.search(r'Power\s*:(.*)',
                                         blade).group(1)).strip()
                    b_p_name = (re.search(r'Server Profile\s*:(.*)',
                                          blade).group(1)).strip()
                    b_height = (re.search(r'Height\s*:(.*)',
                                          blade).group(1)).strip()
                    self.blades_info[node] = (
                        sed_p_name, b_id, b_status, b_power, b_p_name,
                        b_height, b_snumber, sed_sname, sed_server_type)

        msg = 'Blades to be configured on VC {0}'.format(self.vcip)
        self.log.info(msg)
        self.log.info(self.blades_info)

    def get_vc_networks(self):
        """
        Get existing networks defined on VC
        :return:
        """
        self.current_vc_networks = {}

        command = 'SHOW NETWORK *'
        results = self.vc_exec(command)
        _match = re.search(r'No networks exist', results)
        if _match:
            self.log.info('Currently there are no networks defined on VC')
            return
        else:
            rc_lines = re.split(r'-+\r\n', results)
            for net in rc_lines:
                _match = re.search(r'Shared Uplink Set\s*:.*', net)
                if _match:
                    vc_n_uplink = (re.search(
                            r'Shared Uplink Set\s*:(.*)', net).group(
                            1)).strip()
                    vc_n_vlanid = (re.search(
                            r'VLAN ID\s*:(.*)', net).group(1)).strip()
                else:
                    vc_n_uplink = 'none'
                    vc_n_vlanid = 'none'
                vc_n_name = (re.search(
                        r'Name\s*:(.*)', net).group(1)).strip()
                vc_n_status = (re.search(
                        r'Status\s*:(.*)', net).group(1)).strip()
                vc_n_slink = (re.search(
                        r'Smart Link\s*:(.*)', net).group(1)).strip()
                vc_n_mspeed = (re.search(
                        r'Max Speed\s*:(.*)', net).group(1)).strip()
                if vc_n_mspeed != 'Unrestricted':
                    if vc_n_mspeed.find('Mb') != -1:
                        vc_n_mspeed = vc_n_mspeed.split('Mb')[0]
                    else:
                        vc_n_mspeed = float(vc_n_mspeed.split('Gb')[0]) * 1000
                        vc_n_mspeed = int(vc_n_mspeed)
                        vc_n_mspeed = str(vc_n_mspeed)
                self.current_vc_networks[vc_n_name] = [
                    vc_n_uplink, vc_n_vlanid, vc_n_mspeed,
                    vc_n_slink, vc_n_status]

        msg = 'Currently defined networks on VC {0}'.format(self.vcip)
        self.log.info(msg)
        self.log.info(self.current_vc_networks)

    def is_hide_unused_flexnics_supported(self):  # pylint: disable=C0103
        """
        Gets and checks firmware version
        If firmware version is 4.10 or newer will return true
        """

        hide_unused_flexnics_version = 4.10
        bay_num = 0
        prev_fw = ""
        hide_unused_flexnics = True
        command = 'SHOW FIRMWARE *'
        results = self.vc_exec(command)
        check_fw = re.search(r'No firmware exist', results)
        if check_fw:
            err = 'Currently there are no firmware defined on VC'
            raise RuntimeError(err)
        rc_lines = re.split(r'-+\r\n', results)
        for net in rc_lines:
            n_type = (re.search(r'Type\s*:(.*)', net))
            n_firm = (re.search(r'Firmware Version\s*:(.\d+\.\d+)', net))
            n_status = (re.search(r'Status\s*:(.*)', net))

            if n_type:
                vc_type = n_type.group(1).strip()
                vc_status = n_status.group(1).strip()
            if vc_status != "OK":
                continue
            elif vc_type == "VC-ENET" and vc_status == "OK":
                if n_firm:
                    vc_firm = float(n_firm.group(1).strip())
                    if bay_num != 0 and vc_firm != prev_fw:
                        prev_fw = vc_firm
            else:
                if n_firm:
                    vc_firm = float(n_firm.group(1).strip())
            bay_num += 1
        if vc_firm >= hide_unused_flexnics_version:
            hide_unused_flexnics = False
        return hide_unused_flexnics

    def get_vc_uplinks(self):
        """
        Get VC Uplinks
        :return:
        """
        self.current_vc_uplinks = []

        command = 'SHOW UPLINKSET *'
        results = self.vc_exec(command)
        _match = re.search(r'No shared uplink', results)
        if _match:
            err = results.strip()
            raise RuntimeError(err)
        else:
            rc_lines = re.split(r'-+\r\n', results)
            for line in rc_lines:
                match = re.search(r'Name\s*:\s*.+', line)
                if match:
                    vc_n_uplink = re.search(r'Name\s*:\s*(.+)', line).group(1)
                    self.current_vc_uplinks.append(vc_n_uplink.strip())

        msg = 'Currently defined SharedUplinkSets on VC {0}'.format(self.vcip)
        self.log.info(msg)
        self.log.info(self.current_vc_uplinks)

    def network_commands(self, loaded_profile, sed_p_name):
        """
        Get commands needed to set up networks
        :param loaded_profile: The profile
        :param sed_p_name: Profile name
        :return:
        """
        self.network_definitions = []
        ports = loaded_profile.keys()

        for port in ports:
            nets = loaded_profile[port][4]
            for net in nets:
                net = net.split(':')

                # check network definition in blade_profiles
                if len(net) == 4:
                    n_name_key = net[0].strip()
                    n_name = SED_DATA[n_name_key]
                    if not n_name:
                        err = 'Empty value for key {0} in SED'.format(
                                n_name_key)
                        raise ValueError(err)
                    n_untag = net[1].strip()
                    n_uplink = net[2].strip()
                    n_mspeed = net[3].strip()
                else:
                    err = 'Invalid Network definition {0} in ' \
                          'blade_profiles'.format(net)
                    raise RuntimeError(err)

                if n_untag != 'true' and n_untag != 'false':
                    err = 'Invalid Untagged value {0} for network {1} in' \
                          ' blade_profiles'.format(n_untag, n_name)
                    raise RuntimeError(err)

                if n_uplink != 'true' and n_uplink != 'false':
                    err = 'Invalid UplinkSet value {0} for network {1} ' \
                          'in blade_profiles'.format(n_uplink, n_name)
                    raise RuntimeError(err)

                if n_mspeed != 'none':
                    try:
                        int(n_mspeed)
                    except ValueError:
                        err = 'Invalid NetworkMaxSpeed value [{0}] for ' \
                              'network {1} in blade_profiles'.format(
                                n_mspeed, n_name)
                        raise ValueError(err)
                    if int(n_mspeed) not in xrange(100, 10100, 100):
                        err = 'Incorrect NetworkMaxSpeed [{0}] for ' \
                              'network {1}. Allowed value is between 100-' \
                              '10000Mb in 100Mb increments'.format(
                                n_mspeed, n_name)
                        raise RuntimeError(err)

                # get vlanid from SED
                vlanid = ''
                s_net = n_name_key.split('_')
                if 'VLAN_ID_{0}' \
                        .format('_'.join(s_net[:-1])) in SED_DATA.keys():
                    vlanid = SED_DATA['VLAN_ID_{0}'.format(
                            '_'.join(s_net[:-1]))]

                # network name not found in current_vc_networks
                if n_name not in self.current_vc_networks.keys():
                    # uplink true in bldae_profile and vlanid set in sed
                    if n_uplink == 'true' and vlanid != '':
                        uplinkset_key = loaded_profile[port][3]
                        uplinkset = SED_DATA[uplinkset_key]
                        self.check_vlanid_not_in_uplink(vlanid, uplinkset)
                        self.network_definitions.append(
                                'add network {0} UplinkSet={1} '
                                'VlanID={2}'.format(n_name, uplinkset, vlanid))
                        self.network_definitions.append(
                                'set network {0} SmartLink=enabled'.format(
                                        n_name))
                        # update currently defined networks
                        self.current_vc_networks[n_name] = [
                            uplinkset, vlanid, 'Unrestricted', 'Enabled', 'OK']
                    # uplink true in blade profile but vlanid not set
                    # in sed, report error
                    elif n_uplink == 'true' and vlanid == '':
                        err = 'VLANID for the network {0} connected to ' \
                              'SharedUplinkSet is not found in SED'.format(
                                n_name)
                        raise RuntimeError(err)
                    else:
                        self.network_definitions.append(
                                'add network {0}'.format(n_name))
                        # update currently defined networks
                        self.current_vc_networks[n_name] = [
                            'none', 'none', 'Unrestricted', 'Disabled', 'OK']

                    # update network max speed
                    if n_mspeed != 'none':
                        self.network_definitions.append(
                                'set network {0} MaxSpeedType=Custom MaxSpeed='
                                '{1}'.format(n_name, n_mspeed))
                        self.current_vc_networks[n_name][2] = n_mspeed

                # network name found in current_vc_networks
                elif n_name in self.current_vc_networks.keys():
                    vc_n_uplink = self.current_vc_networks[n_name][0]
                    vc_n_vlanid = self.current_vc_networks[n_name][1]
                    vc_n_slink = self.current_vc_networks[n_name][3]
                    vc_n_mspeed = self.current_vc_networks[n_name][2]
                    # uplink true in bldae_profile and vlanid set in sed
                    # check if network already defined under different
                    # uplink or under the same uplink but with different
                    # vlanid
                    if n_uplink == 'true' and vlanid != '':
                        uplinkset_key = loaded_profile[port][3]
                        uplinkset = SED_DATA[uplinkset_key]
                        if uplinkset != vc_n_uplink or vlanid != vc_n_vlanid:
                            err = 'Network {0} already defined on VC with' \
                                  ' VLANID {1} and UplinkSet {2}'.format(
                                    n_name, vc_n_vlanid, vc_n_uplink)
                            raise RuntimeError(err)
                    # uplink true in blade profile but vlanid not set
                    # in sed, report error
                    elif n_uplink == 'true' and vlanid == '':
                        err = 'VLANID for the network {0} connected to ' \
                              'SharedUplinkSet is not found in SED'.format(
                                n_name)
                        raise RuntimeError(err)

                    # uplink set to false in blade_profiles
                    if n_uplink == 'false' and vc_n_uplink != 'none':
                        err = 'Network with the name {0} already defined' \
                              ' on VC and connected to UplinkSet {1}'.format(
                                n_name, vc_n_uplink)
                        raise RuntimeError(err)

                    # enable network smart link if not done yet
                    if n_uplink == 'true' and vc_n_slink == 'Disabled':
                        self.network_definitions.append(
                                'set network {0} SmartLink=enabled'.format(
                                        n_name))
                        self.current_vc_networks[n_name][3] = 'Enabled'
                        msg = 'Smartlink on existing network {0} will be ' \
                              'changed to enabled'.format(n_name)
                        self.log.warn(msg)

                    # set up network max speed
                    if n_mspeed != 'none' and n_mspeed != vc_n_mspeed:
                        self.network_definitions.append(
                                'set network {0} MaxSpeedType=Custom MaxSpeed='
                                '{1}'.format(n_name, n_mspeed))
                        self.current_vc_networks[n_name][2] = n_mspeed
                        msg = 'Max speed on existing network {0} will be ' \
                              'changed to {1}'.format(n_name, n_mspeed)
                        self.log.warn(msg)

        self.last_loaded_profile = sed_p_name

    def check_vlanid_not_in_uplink(self, vlanid, uplinkset):
        """
        Check if a VLAN ID is not in the Uplink
        :param vlanid: The VLAN id
        :param uplinkset: The Uplink set name
        """
        for net, net_info in self.current_vc_networks.items():
            if uplinkset == net_info[0] and vlanid == net_info[1]:
                err = 'VLANID {0} already used for {1} in {2}'.format(
                        vlanid, net, uplinkset)
                raise RuntimeError(err)

    def load_profile(self, block_type, profiles_path):
        """
        Load a profile
        :param block_type: The section name
        :param profiles_path: Path to profile config file
        :returns: The loaded profile
        """
        b_profile = {}
        p_start = 0
        p_found = False

        with open(profiles_path, 'r') as _reader:
            for line in _reader:
                line = line.strip()
                if '[{0}]'.format(block_type) == line and p_start == 0:
                    p_start = 1
                    p_found = True
                    continue
                if p_start == 1 and '[{0}_END]'.format(block_type) == line:
                    p_start = 0
                    break
                if p_start == 1:
                    parts = line.split(',')

                    port = parts[0].strip()

                    port_type = parts[1].strip()
                    if port_type != 'MN' and port_type != 'SN':
                        err = 'Incorrect PortType [{0}] in profile {1}. ' \
                              'Check profile configuration in {2}'.format(
                                port_type, block_type, profiles_path)
                        raise RuntimeError(err)

                    pxe = parts[2].strip()
                    if pxe != 'enabled' and pxe != 'disabled':
                        err = 'Incorrect PXE value [{0}] in profile {1}. ' \
                              'Check profile configuration in {2}'.format(
                                pxe, block_type, profiles_path)
                        raise RuntimeError(err)

                    speed = parts[3].strip()
                    speed_range = xrange(100, 10100, 100)
                    if speed != 'auto' and speed != 'preferred':
                        try:
                            int(speed)
                        except ValueError:
                            err = 'Invalid PortSpeed [{0}] in profile {1}. ' \
                                  'Check profile configuration in {2}'.format(
                                    speed, block_type, profiles_path)
                            raise ValueError(err)
                        if int(speed) not in speed_range:
                            err = 'Incorrect PortSpeed {0} for port {1} in ' \
                                  '{2}. Allowed value is between 100-10000Mb' \
                                  ' in 100Mb increments'.format(speed, port,
                                                                profiles_path)
                            raise RuntimeError(err)

                    uplink = parts[4].strip()
                    if uplink != 'none':
                        uplinkset = SED_DATA[uplink]
                        if not uplinkset:
                            err = 'Empty value for key {0} in SED'.format(
                                    uplink)
                            raise ValueError(err)
                        elif uplinkset not in self.current_vc_uplinks:
                            err = 'SharedUplinkSet {0} is not defined ' \
                                  'on VC'.format(uplinkset)
                            raise ValueError(err)

                    nets = parts[5:]

                    b_profile[port] = port_type, pxe, speed, uplink, nets

        if p_found is False:
            err = 'Profile type {0} specified in SED is not found in ' \
                  '{1}'.format(block_type, profiles_path)
            raise ValueError(err)

        msg = 'Profile [{0}] loaded from {1}'.format(block_type, profiles_path)
        self.log.info(msg)
        self.log.info(b_profile)
        return b_profile

    def profile_commands(self, loaded_profile, vc_p_name):
        """
        Run profile commands
        :param loaded_profile: The profile to load
        :param vc_p_name: The profile name
        """
        self.profile_definitions = []  # prfile definition

        # Check hide_unused_flexnics
        flex_flag = self.is_hide_unused_flexnics_supported()
        _cmd = 'ADD profile {0} -nodefaultenetconn '.format(vc_p_name)
        if not flex_flag:
            _cmd += 'HideUnusedFlexNICs=false'
        self.profile_definitions.append(_cmd)
        ports = loaded_profile.keys()
        ports.sort()

        for port in ports:
            port_type = loaded_profile[port][0]
            if port_type == 'MN':
                pxe = loaded_profile[port][1]
                self.profile_definitions.append(
                        'add enet-connection {0} pxe={1}'.format(vc_p_name,
                                                                 pxe))
                nets = loaded_profile[port][4]
                for net in nets:
                    net = net.split(':')
                    # split network name to get name defined in SED
                    n_name_key = net[0].strip()
                    n_name = SED_DATA[n_name_key]
                    s_net = n_name_key.split('_')
                    vlanid = SED_DATA['VLAN_ID_{0}'.format(
                            '_'.join(s_net[:-1]))]
                    n_untag = net[1].strip()
                    self.profile_definitions.append(
                            'add server-port-map {0}:{1} {2} VlanId={3} '
                            'UnTagged={4}'.format(vc_p_name, port, n_name,
                                                  vlanid, n_untag))

                speed_type = loaded_profile[port][2].strip()
                if speed_type == 'auto' or speed_type == 'preferred':
                    self.profile_definitions.append(
                            'set enet-connection {0} {1} SpeedType={2}'.format(
                                    vc_p_name, port, speed_type))
                else:
                    speed_type = 'custom'
                    speed = loaded_profile[port][2].strip()
                    self.profile_definitions.append(
                            'set enet-connection {0} {1} SpeedType={2} Speed='
                            '{3}'.format(vc_p_name, port, speed_type, speed))

            elif port_type == 'SN':
                pxe = loaded_profile[port][1]
                net = loaded_profile[port][4][0]
                net = net.split(':')
                n_name_key = net[0].strip()
                n_name = SED_DATA[n_name_key]
                self.profile_definitions.append(
                        'add enet-connection {0} pxe={1} network={2}'.format(
                                vc_p_name, pxe, n_name))

                speed_type = loaded_profile[port][2].strip()
                if speed_type == 'auto' or speed_type == 'preferred':
                    self.profile_definitions.append(
                            'set enet-connection {0} {1} SpeedType={2}'.format(
                                    vc_p_name, port, speed_type))
                else:
                    speed_type = 'custom'
                    speed = loaded_profile[port][2].strip()
                    self.profile_definitions.append(
                            'set enet-connection {0} {1} SpeedType={2} Speed='
                            '{3}'.format(vc_p_name, port, speed_type, speed))

    def add_profile(self, profiles_path, dry_run,
                    force_assign=True, vc_assign=True):
        """
        Add a profile
        :param profiles_path: Profile config path
        :param dry_run: Dont make the changes
        :param force_assign: Force changes
        :param vc_assign: Assign to VC
        """
        self.vc_blades_to_configure()

        for node in self.blades_info:
            call_exec_net_commands = 0
            sed_p_name = self.blades_info[node][0]
            b_id = self.blades_info[node][1]
            sed_sname = self.blades_info[node][7]
            server_type = self.blades_info[node][8]
            vc_p_name = '{0}_Bay_{1}_{2}'.format(
                    sed_p_name, b_id.split(':')[1], sed_sname)

            if vc_assign:
                block_type = '{0}_NON_MGMT'.format(sed_p_name)
            else:
                block_type = '{0}_{1}'.format(sed_p_name, server_type)

            if block_type != self.last_loaded_profile:
                loaded_profile = self.load_profile(block_type, profiles_path)
                self.network_commands(loaded_profile, block_type)
                call_exec_net_commands = 1

            self.profile_commands(loaded_profile, vc_p_name)

            if self.blades_info[node][4] != '<Unassigned>' \
                    and force_assign is False:
                err = 'Profile already assigned to blade {0} - {1}. ' \
                      'Execute script with -f, --force option to assign a ' \
                      'new profile'.format(b_id, sed_sname)
                raise RuntimeError(err)
            if self.blades_info[node][4] != '<Unassigned>' \
                    and force_assign is True:
                b_p_name = self.blades_info[node][4]
                self.poweroff_server(b_id, dry_run)
                self.unassign_server_profile(b_id, b_p_name, dry_run)
                self.remove_server_profile(b_p_name, dry_run)

            self.check_if_profile_name_exist(vc_p_name, dry_run)

            if call_exec_net_commands == 1:
                self.exec_net_commands(dry_run)
            self.exec_profile_commands(vc_p_name, dry_run)
            self.poweroff_server(b_id, dry_run)
            self.assign_server_profile(b_id, vc_p_name, dry_run)
            self.poweron_server(b_id, dry_run)

    def exec_net_commands(self, dry_run):
        """
        Execute a network command
        :param dry_run: Dont make the changes
        """
        for command in self.network_definitions:
            if dry_run:
                self.log.info(command)
                continue
            results = self.vc_exec(command)
            if 'SUCCESS' not in results:
                err = '{0}'.format(results.strip())
                raise RuntimeError(err)
        msg = 'Networks created / updated on VC successfully'
        self.log.info(msg)

    def exec_profile_commands(self, vc_p_name, dry_run):
        """
        :param vc_p_name:
        :param dry_run:
        :return:
        """
        for command in self.profile_definitions:
            if dry_run:
                self.log.info(command)
                continue
            results = self.vc_exec(command)
            if 'SUCCESS' not in results:
                err = '{0}'.format(results.strip())
                raise RuntimeError(err)
        msg = 'Profile {0} successfully created'.format(vc_p_name)
        self.log.info(msg)

    def check_if_profile_name_exist(self, vc_p_name, dry_run):
        """

        :param vc_p_name:
        :param dry_run:
        :return:
        """
        command = 'SHOW PROFILE {0}'.format(vc_p_name)
        results = self.vc_exec(command)
        _match = re.search(r'No profiles exist', results)
        if not _match and dry_run is False:
            err = 'Profile with name {0} already defined on VC'.format(
                    vc_p_name)
            raise RuntimeError(err)
        elif not _match and dry_run is True:
            msg = 'Profile with name {0} already defined on VC'.format(
                    vc_p_name)
            self.log.warn(msg)

    def unassign_server_profile(self, b_id, vc_p_name, dry_run):
        """

        :param b_id:
        :param vc_p_name:
        :param dry_run:
        :return:
        """
        command = 'unassign profile {0}'.format(vc_p_name)
        if dry_run:
            self.log.info(command)
            return
        results = self.vc_exec(command)
        if 'SUCCESS' in results:
            msg = 'Server profile {0} unassigned from device {1}'.format(
                    vc_p_name, b_id)
            self.log.info(msg)
        else:
            err = 'Failed to unassign profile {0} from device {1}'.format(
                    vc_p_name, b_id)
            raise RuntimeError(err)

    def assign_server_profile(self, b_id, vc_p_name, dry_run):
        """

        :param b_id:
        :param vc_p_name:
        :param dry_run:
        :return:
        """
        command = 'assign profile {0} {1}'.format(vc_p_name, b_id)
        if dry_run:
            self.log.info(command)
            return
        results = self.vc_exec(command)
        if 'SUCCESS' in results:
            msg = 'Server profile {0} assigned to device {1}'.format(
                    vc_p_name, b_id)
            self.log.info(msg)
        else:
            err = 'Failed to assign server profile {0} to device {1}'.format(
                    vc_p_name, b_id)
            raise RuntimeError(err)

    def remove_server_profile(self, vc_p_name, dry_run):
        """

        :param vc_p_name:
        :param dry_run:
        :return:
        """
        command = 'remove profile {0}'.format(vc_p_name)
        if dry_run:
            self.log.info(command)
            return
        results = self.vc_exec(command)
        if 'SUCCESS' in results:
            msg = 'Server profile {0} removed'.format(vc_p_name)
            self.log.info(msg)
        else:
            err = 'Failed to remove profile {0}'.format(vc_p_name)
            raise RuntimeError(err)

    def poweroff_server(self, b_id, dry_run):
        """

        :param b_id:
        :param dry_run:
        :return:
        """
        command = 'show server {0}'.format(b_id)
        results = self.vc_exec(command)
        _match = re.search(r'Power\s*:\s*Off', results)
        if _match:
            msg = 'Server {0} already powered off'.format(b_id)
            self.log.info(msg)
            return 0
        command = 'poweroff server {0} -timeout=30 -forceontimeout'.format(
                b_id)
        if dry_run:
            self.log.info(command)
            return
        results = self.vc_exec(command, timeout=180)
        if 'SUCCESS' in results:
            msg = 'Server {0} powered off'.format(b_id)
            self.log.info(msg)
        else:
            err = 'Failed to power off server {0}'.format(b_id)
            raise RuntimeError(err)

    def poweron_server(self, b_id, dry_run):
        """

        :param b_id:
        :param dry_run:
        :return:
        """
        command = 'poweron server {0} -timeout=180'.format(b_id)
        if dry_run:
            self.log.info(command)
            return
        results = self.vc_exec(command, timeout=220)
        if 'SUCCESS' in results:
            msg = 'Server {0} powered on'.format(b_id)
            self.log.info(msg)
        else:
            err = 'Failed to power on server {0}'.format(b_id)
            raise RuntimeError(err)


def function_logger(log_level=logging.INFO):
    """

    :param log_level:
    :return:
    """
    log_format = logging.Formatter('%(asctime)s %(levelname)s: %(message)s',
                                   datefmt='%Y-%m-%d %H:%M:%S')

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(log_format)

    if os.path.isfile(LOG_FILE):
        os.rename(LOG_FILE, '{0}_{1}'.format(
                LOG_FILE, time.strftime('%Y%m%d_%H%M%S')))

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)

    logger = logging.getLogger('app')
    logger.setLevel(log_level)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


def main():
    """
    :return:
    """
    parser = argparse.ArgumentParser(
            description='Script to configure Virtual Connect server profiles')
    parser.add_argument('sed', help='path to Site Engineering Document')
    parser.add_argument('profile', help='path to blade_profiles file')
    parser.add_argument('-f', '--force', action='store_true',
                        help='force to assign a new profile to blade')
    parser.add_argument('-d', '--debug', action="store_true")
    parser.add_argument('-dr', '--dry_run', action='store_true',
                        help='do not change VC configuration')
    parser.add_argument('-s', '--sim', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('-e', '--exist_config', action='store_true',
                        help='Deployments that cannot support '
                             'LITP Management via Internal Vlan')

    args = parser.parse_args()
    sed_file = args.sed
    blade_profiles = args.profile
    dry_run = args.dry_run
    run_on_vcsim = args.sim

    if args.force:
        force_assign = True
    else:
        force_assign = False

    if args.exist_config:
        update_vc_assign = True
    else:
        update_vc_assign = False

    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    log = function_logger(log_level)
    try:
        log.info('*** Start script execution ***')
        if dry_run:
            log.info('This is dry-run. The VC configuration is not changed')

        with open(sed_file, 'r') as _reader:
            for line in _reader:
                _match = re.search(r'^\s*(\w+)\s*=(.*)', line)
                if _match:
                    SED_DATA[_match.group(1)] = (_match.group(2)).strip()

        sed_enc_vc_list = [
            (key, value) for key, value in SED_DATA.items()
            if re.search(r'^enclosure\d+_VC_IP(1|2)$', key) and value != '']

        if len(sed_enc_vc_list) == 0:
            msg = 'Virtual Connect IP address not found in SED'
            log.info(msg)

        for key, value in sed_enc_vc_list:
            key = re.search(r'(enclosure\d+_VC)_IP', key).group(1)
            username_key = key + '_username'
            password_key = key + '_password'
            enc_vc_ip = value
            enc_vc_uname = SED_DATA[username_key]
            enc_vc_pass = SED_DATA[password_key]
            if enc_vc_uname != '' and enc_vc_pass != '':
                vc_profile = HpVcProfile(enc_vc_ip, enc_vc_uname,
                                         enc_vc_pass, log)
                msg = 'Connecting to VC {0}'.format(enc_vc_ip)
                log.info(msg)
                if run_on_vcsim:
                    vc_profile.vc_connect_sim()
                else:
                    result = vc_profile.vc_connect()
                    if result == 5:
                        msg = 'Standby VC ethernet module - disconnecting'
                        log.info(msg)
                        continue
                msg = 'Connected to VC {0}'.format(enc_vc_ip)
                log.info(msg)
                vc_profile.get_vc_networks()
                vc_profile.get_vc_uplinks()
                vc_profile.add_profile(blade_profiles, dry_run, force_assign,
                                       update_vc_assign)
                vc_profile.vc_disconnect()
                msg = 'Connection closed to VC {0}'.format(enc_vc_ip)
                log.info(msg)
            else:
                msg = 'User or Password not found in SED for VC - {0}'.format(
                        enc_vc_ip)
                log.info(msg)

        if dry_run:
            log.info('The dry-run execution finished')
        log.info('*** Script executed successfully ***')
    except Exception as err:
        log.error('%s\n' % err, exc_info=True)


if __name__ == '__main__':
    main()
