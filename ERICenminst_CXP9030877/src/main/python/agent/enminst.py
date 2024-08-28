#!/bin/env python
# pylint: disable=C0103
"""
 Enminst MCO agent implementations.
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
import logging.config
import os
import re
from os.path import dirname, abspath, join

from base_agent import RPCAgent

VCS_ENTRY_ALREADY_IN_KEYLIST = "V-16-1-10563"
VCS_ENTRY_NOT_IN_KEYLIST = "V-16-1-10566"
VCS_GROUP_NOT_EXIST_WARN = "VCS WARNING V-16-1-12130"


class VCSCommandException(Exception):
    """
    Exception to handle an VCS command errors.
    """
    pass


class Enminst(RPCAgent):
    """
    Implementation of some mco action in python. The .rb acts a proxy
    and will call these action.
    """
    def __init__(self):
        _lcfg = join(dirname(abspath(__file__)), 'logging.cfg')
        logging.config.fileConfig(_lcfg)
        self.logger = logging.getLogger('enminst_agent')

    @staticmethod
    def enable_debug(args):
        """
        Enable debug logging of 'verbose' passed from client
        :param args: Arguements from the 'mco rpc ...' command issued on the
        LMS

        """
        if 'verbose' in args and args['verbose'].lower() == 'true':
            logging.getLogger().setLevel(logging.DEBUG)

    def run_vcs_command(self, command, ignore_errors=False,
                        expected_errors=None,
                        rewrite_retcode=False):
        """
        Execute a VCS command handling I/O and errors
        and returning a tuple of ( exit_code, stdout, stderr )


        :param command: The VCS command to run e.g. hagrp or hasys
        :type command: list(str)
        :param ignore_errors: Should errors be ignored or not.
        :type ignore_errors: bool
        :return:
        """
        env = dict(os.environ)
        env['PATH'] = "/opt/VRTSvcs/bin:{0}".format(env['PATH'])
        self.logger.debug("executing {0}".format(command))
        returncode, stdout, stderr = self.execute(command, env=env)
        self.logger.debug("returncode:{0}\n stdout:{1}\n stderr:{2}\n".
                          format(returncode, stdout, stderr))

        if not ignore_errors and returncode:
            if expected_errors:
                for expected_error in expected_errors:
                    if expected_error in stderr:
                        if rewrite_retcode:
                            returncode = 0
                        return returncode, stdout, stderr
            raise VCSCommandException(
                "Error running '{0}': Out: '{1}' Err: '{2}'".format(
                        command, stdout, stderr))
        return returncode, stdout, stderr

    def hagrp_display(self, args):
        """
        Get attributes of a VCS group (or groups)
        args['groups'] : Comma separated list of VCS groups

        :param args: Input args from Puppet
        :type args: dict
        :return: hagrp -display results for requested groups
        """
        groups = args['groups']
        data = []
        for group_name in groups.split(','):
            cmd = ['hagrp', '-display', group_name]
            retcode, stdout, stderr = self.run_vcs_command(
                    cmd, ignore_errors=True)
            if retcode == 0:
                data.append(stdout)
            else:
                data.append('{0} {1} {2}'.format(group_name, stdout, stderr))
        return {"retcode": 0,
                "out": data,
                "err": ''}

    def hasys_display(self, args):
        """

        Get attributes of a VCS system (or system)
        args['groups'] : Comma separated list of VCS system(s)

        :param args: Input args from Puppet
        :type args: dict
        :return: hasys -display results for requested system(s)
        """
        if 'systems' in args:
            sysdata = {}
            for system_name in args['systems'].split(','):
                cmd = ['hasys', '-display', system_name]
                retcode, stdout, stderr = self.run_vcs_command(cmd)
                if retcode != 0:
                    return {"retcode": retcode,
                            "out": stdout,
                            "err": stderr}
                sysdata[system_name] = stdout
            return {"retcode": 0,
                    "out": sysdata,
                    "err": ''}
        else:
            cmd = ['hasys', '-display']
            retcode, stdout, stderr = self.run_vcs_command(cmd)
            return {"retcode": retcode,
                    "out": stdout,
                    "err": stderr}

    def get_engine_logs(self):
        """
        Get a list on VCS engine log files (engine_A engine_B etc)

        :return: List of engine_?? log files
        """
        retcode, stdout, stderr = self.run_vcs_command(['hamsg', '-list'])
        if retcode != 0:
            return retcode, {"retcode": retcode,
                             "out": stdout,
                             "err": stderr}
        engine_logs = []
        for line in stdout.split('\n'):
            line = line.strip()
            if len(line) == 0 or line.startswith('#'):
                continue
            if line.startswith('engine_'):
                engine_logs.append(line)
        return 0, engine_logs

    def hagrp_history(self, args):
        """
        Get a list of VCS events for VCS groups e.g. online, offline,
        switch etc.

        :param args: Action args from MCO, args['group'] will limit
        to one group
        :type args: dict
        :return: List of VCS events for groups
        """
        regex_split = re.compile(r'^(?P<date>.*?)\s+'
                                 r'VCS.*?(?P<msgid>V-16-1-[0-9]+)\s+'
                                 r'(?P<msgtxt>.*)')
        regex_groupname = re.compile(r'.*(?P<group>Grp_CS_.*?)\s+.*')
        history = {}

        cmd_prefix = ['hamsg', '-otype', 'GRP']
        if 'group' in args and args['group']:
            cmd_prefix.append('-oname')
            cmd_prefix.append(args['group'])
        retcode, engine_logs = self.get_engine_logs()
        if retcode != 0:
            return engine_logs
        for engine_l in engine_logs:
            retcode, stdout, stderr = self.run_vcs_command(cmd_prefix +
                                                           [engine_l])
            if retcode != 0:
                return {"retcode": retcode,
                        "out": stdout,
                        "err": stderr}
            for msg in stdout.split('\n'):
                _event = regex_split.search(msg)
                _gnmatch = regex_groupname.search(msg)
                if _event and _gnmatch:
                    _groupname = _gnmatch.group('group')
                    if _groupname not in history:
                        history[_groupname] = []
                    history[_groupname].append(
                            {'date': _event.group('date'),
                             'id': _event.group('msgid'),
                             'info': _event.group('msgtxt')}
                    )

        return {"retcode": 0,
                "out": history,
                "err": ''}

    def hagrp_switch(self, args):
        """
        Get attributes of a VCS group (or groups)
        args['groups'] : Comma separated list of VCS groups
        :param args: Input args from Puppet
        :return: hagrp -switch results for requested groups
        """
        data = []
        cmd = ['hagrp', '-switch', args]
        retcode, stdout, stderr = self.run_vcs_command(cmd)
        if retcode != 0:
            return {"retcode": retcode,
                    "out": stdout,
                    "err": stderr}
        data.append(stdout)

        return {"retcode": 0,
                "out": data,
                "err": ''}

    def check_service(self, args):
        """
        Checks the state of the service on each node
        args['service'] : service passed
        :param args: Input args from service_list
        :return: service <> status result from each node
        """
        service_status = {}
        if 'service' in args:
            for serv in args['service'].split(','):
                serv = serv.strip()
                cmd = ['service', serv, 'status']
                retcode, _, _ = self.execute(cmd)
                service_status[serv] = retcode
        return {"retcode": 0,
                "out": service_status,
                "err": ''}

    def hagrp_add_triggers_enabled(self, request):
        """
        Add in TriggersEnabled values get it from
        request['attribute_val'].
        """
        group = request['group_name']
        value = request['attribute_val']
        cmd = ['hagrp', '-modify', group, 'TriggersEnabled', '-add', value]
        expected_errors = [VCS_ENTRY_ALREADY_IN_KEYLIST]
        rewrite_retcode = True

        try:
            self.open_haconf()
            self.run_vcs_command(cmd,
                                 expected_errors=expected_errors,
                                 rewrite_retcode=rewrite_retcode)
            self.close_haconf()
            return {"retcode": 0, "out": "", "err": ""}
        except VCSCommandException as e:
            return {"retcode": 1, "out": "", "err": str(e)}

    def hagrp_delete_triggers_enabled(self, request):
        """
        Delete in TriggersEnabled values get it from
        request['attribute_val'].
        """
        group = request['group_name']
        value = request['attribute_val']
        cmd = ['hagrp', '-modify', group, 'TriggersEnabled', '-delete', value]
        expected_errors = [VCS_GROUP_NOT_EXIST_WARN,
                           VCS_ENTRY_NOT_IN_KEYLIST]
        rewrite_retcode = True

        try:
            self.open_haconf()
            self.run_vcs_command(cmd,
                                 expected_errors=expected_errors,
                                 rewrite_retcode=rewrite_retcode)
            self.close_haconf()
            return {"retcode": 0, "out": "", "err": ""}
        except VCSCommandException as e:
            return {"retcode": 1, "out": "", "err": str(e)}

    def hagrp_modify(self, request):
        """
        Modify parameter request['attribute'] in request['group_name']
        """
        group = request['group_name']

        attr = request['attribute']
        assert attr != "SystemList" and attr != "AutoStartList" and \
            attr != "TriggersEnabled"

        value = request['attribute_val']

        # Get the current value of the attribute and do not modify if
        # it currently has the same value. Needed for idempotency for
        # attributes (e.g. Parallel) which cannot be set if resources
        # exist under the service group

        cmd = ['hagrp', '-value', group, attr]
        try:
            _, result, e = self.run_vcs_command(cmd)
        except VCSCommandException as e:
            return {"retcode": 1, "out": "", "err": str(e)}

        if result.strip() == value:
            return {"retcode": 0, "out": '', "err": ''}
        cmd = ['hagrp', '-modify', group, attr, value]

        try:
            self.open_haconf()
            self.run_vcs_command(cmd)
            self.close_haconf()
            return {"retcode": 0, "out": "", "err": ""}
        except VCSCommandException as e:
            return {"retcode": 1, "out": "", "err": str(e)}

    def cluster_app_agent_num_threads(self, request):
        """
        Modify app_agent_num_threads
        """
        self.enable_debug(request)
        app_agent_num_threads = str(request["app_agent_num_threads"])
        cmd = ['hatype', '-modify', 'Application', 'NumThreads',
                app_agent_num_threads]

        try:
            self.open_haconf()
            self.run_vcs_command(cmd)
            self.close_haconf()
            return {"retcode": 0, "out": "", "err": ""}
        except VCSCommandException as e:
            return {"retcode": 1, "out": "", "err": str(e)}

    def _haconf(self, read_only=False):
        """
        Internal method to set haconf
        :param read_only: indicate whether to make rw or ro
        :return: tuple of ( exit_code, stdout, stderr )
        """
        if not read_only:
            cmd = ['haconf', '-makerw']

            try:
                return self.run_vcs_command(cmd)
                    #["VCS WARNING V-16-1-10364 Cluster already writable"])
            except VCSCommandException as e:
                return 1, '', str(e)
        else:
            cmd = ['haconf', '-dump', '-makero']
            try:
                c, o, e = self.run_vcs_command(cmd)
                # ["VCS WARNING V-16-1-10369 Cluster not writable"])
            except VCSCommandException as ex:
                c, o, e = 1, '', str(ex)

            if c == 0:
                # Wait for up to 60 seconds for the dump to finish
                cmd = ['haclus', '-wait', 'DumpingMembership', '0',
                        '-time', '60']
                wait_c, wait_o, wait_e = self.run_vcs_command(cmd)
                    #["VCS WARNING V-16-1-10805 Connection timed out"])
                if wait_c != 0:
                    wait_e = "\n".join([wait_e, "VCS took more than 60 "
                                        "seconds to dump its configuration "
                                        "to disk."])
                return wait_c, wait_o, wait_e
            return c, o, e

    def open_haconf(self):
        """
        Make haconf rw
        :return: tuple of ( exit_code, stdout, stderr )
        """
        return self._haconf(False)

    def close_haconf(self):
        """
        Make haconf ro
        :return: tuple of ( exit_code, stdout, stderr )
        """
        return self._haconf(True)

if __name__ == '__main__':
    Enminst().action()
