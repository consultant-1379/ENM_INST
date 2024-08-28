#!/bin/env python
# pylint: disable=F0401
"""
 DB Snapshot MCO agent implemtations.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# Purpose : Some of the action implementations are in this module, the ruby
# snap agent will forward the action to this module via the 'implemented_by'
# keyword
##############################################################################
import base64
import json
import os
import shutil
import tempfile
import re
from logging.handlers import SysLogHandler
from subprocess import Popen, PIPE, STDOUT
from time import sleep

import pwd
import syslog

from base_agent import RPCAgent

MCOLLECTIVE_REPLY_FILE = "MCOLLECTIVE_REPLY_FILE"
MCOLLECTIVE_REQUEST_FILE = "MCOLLECTIVE_REQUEST_FILE"
MYSQL_KFILE = "/ericsson/tor/data/idenmgmt/idmmysql_passkey"
MYSQL_PSW_KEY = "idm_mysql_admin_password"
GLOBAL_PROP_FILE = '/ericsson/tor/data/global.properties'


def open_log():
    """
    Open a syslog session.
    """
    syslog.openlog('dbsnapshots', syslog.LOG_PID)


def close_log():
    """
    Close a syslog session.
    """
    syslog.closelog()


def syslog_log(level, message):
    """
    Log a message to the system log at level `level`
    :param level: The log level to log the message at
    :param message: The message to log
    """
    syslog.syslog(level, message)


def syslog_info(message):
    """
    Log a message to the system log at level INFO
    :param message: The message to log
    """
    syslog_log(syslog.LOG_INFO, 'INFO: {0}'.format(message))


def syslog_error(message):
    """
    Log a message to the system log at level `error`
    :param message: The message to log
    """
    syslog_log(syslog.LOG_ERR, 'ERR: {0}'.format(message))


class Neo4jSnapshotCreationFailed(Exception):
    """ This exception will be raised when Neo4j snapshot fails
    """


class DbsnapshotsException(Exception):
    """
    General exception to handle DB snapshot errors.
    """

    def __init__(self, message='DB Snapshots Exception'):
        Exception.__init__(self, message)


class Dbsnapshots(RPCAgent):
    """
    Implementation of some mco action in python. The .rb acts a proxy
    and will call these action.
    """

    def __init__(self):
        """
         Constructor
       """
        super(Dbsnapshots, self).__init__()
        self.yum_retry_count = 3
        self.yum_retry_wait = 5

    @staticmethod
    def switch_user(username):
        """
        Elevates the script to the provided username uid and gid
        :param username: Username to change permissions to
        :type username: str
        :return: function
        """

        if username is None:
            return None

        def elevate():
            """
            Callback to switch to a user before executing a command
            """
            try:
                user = pwd.getpwnam(username)
            except KeyError:
                raise NameError('No such user %s' % username)

            os.setregid(user.pw_gid, user.pw_gid)
            os.setreuid(user.pw_uid, user.pw_uid)

        return elevate

    @staticmethod
    def exec_command(command, sudo=None, environ=None, use_shell=False):
        """
        Execute command on server
        :param command: command
        :param sudo: The use to execute the command under
        :param environ: Any environment variables to pass to the command
        :return: output of command
        """
        _cmd = command
        process = Popen(_cmd, stdout=PIPE, stderr=STDOUT,
                        env=environ, shell=use_shell,
                        preexec_fn=Dbsnapshots.switch_user(sudo))
        stdout = process.communicate()[0]
        if process.returncode != 0:
            raise IOError(process.returncode, stdout)
        return stdout

    @staticmethod
    def sanitize(raw_string):
        """
        Sanitizes a string by inserting escape characters to make it
        shell-safe.

        :param raw_string: The string to sanitise
        :type raw_string: string

        :returns: The escaped string
        :rtype: string
        """
        spec_chars = '''"`$'(\\)!~#<>&*;| '''
        escaped = ''.join([c if c not in spec_chars else '\\' + c
                           for c in raw_string])
        return escaped

    @staticmethod
    def get_sancli_snap_command(spa, spb,  # pylint: disable=too-many-arguments
                                username, password, scope, lunid,
                                name, descr, array="vnx2"):
        """
        Build up a sancli command string
        :param spa: The address of a Storage Processor
        :param username: The username to access the SAN with
        :param password: The password to the access user
        :param scope: The user login scope
        :param scope: The ID of the LUN to be snapped
        :param name: The name of the snapshot
        :param descr: The description of the snapshot
        :param array: The type of Storage Array (def: VNX2)
        :returns: sancli command to call to snap the LUN
        """
        spb_arg = ''

        if array.upper().startswith('VNX'):
            spb_arg = ' --ip_spb={0}'.format(spb)

        password = base64.b64encode(password, [':', '_'])

        cmd = ('/opt/ericsson/nms/litp/lib/sanapi/sancli.py create_snap'
               ' --ip_spa={0}{1} --user={2} '
               '--password={3} --scope={4} --lun_id={5} --snap_name={6} '
               '--array={7} --description="{8}" --enc=b64:_'.format(spa,
                                                        spb_arg,
                                                        username, password,
                                                        scope, lunid, name,
                                                        array, descr))
        return cmd

    @staticmethod
    def _set_neo4j_iops_limit(shell, limit):
        """ Sets Neo4j iops limit
        :param shell: ShellClientBase
        :param limit: int
        """
        instance = shell.instance
        try:
            instance.set_iops_limit(limit)
        except AttributeError:
            # if Neo4jInstance does not yet have the set_iops_limit method
            # implemented, we do it via cypher query directly
            query = "call dbms.setConfigValue(\"dbms.checkpoint.iops." \
                    "limit\", \"%s\");" % limit
            try:
                cred = shell.base_credentials.admin
            except AttributeError:
                # for very old versions of neo4jutilities
                from neo4jlib.neo4j.credentials import credentials
                cred = credentials.admin
            timeout = instance.transaction_timeout + 60
            instance.cypher(query, credential=cred, timeout=timeout)
        syslog_info('Neo4j IOPS limit set to %s' % limit)

    def force_neo4j_checkpoint(self, _):
        """ Force Neo4j checkpoint
        :param _:
        :return: dict of return code,output,err message
        """
        try:
            from neo4jlib.neo4j.drivers.base import Neo4jDriverCypherException
            from neo4jlib.neo4j.session import Neo4jSession
            from neo4jlib.error import get_traceback_str
            from neo4jlib.log import log
        except ImportError:
            from neo4jlib.client.drivers.base import Neo4jDriverCypherException
            from neo4jlib.client.session import Neo4jSession
            from pyu.error import get_traceback_str
            from pyu.log import log
        log.setup_log(SysLogHandler(address='/dev/log'),
                      "Neo4j Snapshot - force_checkpoint")
        try:
            try:
                from neo4jlib.neo4j.instance import ForceCheckpointTimeout
            except ImportError:
                from neo4jlib.client.instance import ForceCheckpointTimeout
            exceptions = (ForceCheckpointTimeout, Neo4jDriverCypherException)
        except ImportError:
            exceptions = (Neo4jDriverCypherException,)
        syslog_info('Starting Neo4j force_checkpoint')
        with Neo4jSession() as shell:
            self._set_neo4j_iops_limit(shell, 5000)
            try:
                shell.instance.force_checkpoint()
            except exceptions as err:
                syslog_error("Neo4j force_checkpoint failed: %s" % str(err))
                self._set_neo4j_iops_limit(shell, 5000)
                return self.get_return_struct(2, stderr=str(err))
            except Exception as err:  # pylint: disable=W0703
                traceback = get_traceback_str()
                syslog_error("Neo4j force_checkpoint error: %s\n%s" %
                             (str(err), str(traceback)))
                self._set_neo4j_iops_limit(shell, 5000)
                return self.get_return_struct(1, stderr=traceback)
        syslog_info('Neo4j force_checkpoint finished')
        return self.get_return_struct(0, stdout="")

    def freeze_neo4j_db_filesystem(self, _):  # pylint: disable=R0914,R0915
        """ Freeze Neo4j filesystem db
        :param _: list
        :return: dict of return code,output,err message
        """
        try:
            from neo4jlib.constants import NEO4J_DATA_DIR
            from neo4jlib.error import CommandFailed
            from neo4jlib.neo4j.session import Neo4jSession
            from neo4jlib.log import log
        except ImportError:
            NEO4J_DATA_DIR = None  # pylint: disable=C0103
            from neo4jlib.client.session import Neo4jSession
            from pyu.os.shell.errors import CommandFailed
            from pyu.log import log
        log.setup_log(SysLogHandler(address='/dev/log'),
                      "Neo4j Snapshot - fs freeze")
        with Neo4jSession() as shell:
            if shell.cluster.is_single():
                syslog_info('Neo4j is single, no need to freeze')
                return self.get_return_struct(0, stdout="")
            syslog_info('Freezing Neo4j DB filesystem')
            data_dir = NEO4J_DATA_DIR or shell.os.sg.neo4j.consts.data_dir
            try:
                shell.os.fs.freeze(data_dir)
            except CommandFailed as err:
                return self.get_return_struct(err.status_code, stderr=str(err))

        # We need to make sure that the fs will be unfrozen in a failure
        # scenario where the subsequent mco tasks are not properly executed.
        # We allow 60 seconds and then we unfreeze the fs anyway
        os.system("sleep 60 && /sbin/fsfreeze --unfreeze %s &" % data_dir)

        syslog_info('Neo4j DB filesystem freeze finished')
        return self.get_return_struct(0, stdout="")

    def unfreeze_neo4j_db_filesystem(self, _):  # pylint: disable=R0914,R0915
        """ Unfreeze Neo4j filesystem db
        :param _: list
        :return: dict of return code,output,err message
        """
        try:
            try:
                from neo4jlib.constants import NEO4J_DATA_DIR
                from neo4jlib.error import CommandFailed
                from neo4jlib.neo4j.session import Neo4jSession
                from neo4jlib.log import log
            except ImportError:
                NEO4J_DATA_DIR = None  # pylint: disable=C0103
                from neo4jlib.client.session import Neo4jSession
                from pyu.os.shell.errors import CommandFailed
                from pyu.log import log
            log.setup_log(SysLogHandler(address='/dev/log'),
                          "Neo4j Snapshot - fs unfreeze")
            with Neo4jSession() as shell:
                if shell.cluster.is_single():
                    syslog_info('Neo4j is single, no need to unfreeze')
                    return self.get_return_struct(0, stdout="")
                syslog_info('Unfreezing Neo4j DB filesystem')
                data_dir = NEO4J_DATA_DIR or shell.os.sg.neo4j.consts.data_dir
                try:
                    shell.os.fs.unfreeze(data_dir)
                except CommandFailed as err:
                    return self.get_return_struct(err.status_code,
                                                  stderr=str(err))
            syslog_info('Neo4j DB filesystem unfreeze finished')
            return self.get_return_struct(0, stdout="")
        finally:
            self._set_neo4j_iops_limit(shell, 5000)

    # pylint: disable=R0912,R0914,R0915
    def create_neo4j_db_snapshot(self, args):
        """ Neo4j snapshot database function
        :param args: command arguments
        :type args: dict
        :return: dict of return code,output,err message
        """
        try:
            from neo4jlib.constants import NEO4J_DATA_DIR
            from neo4jlib.error import CommandFailed
            from neo4jlib.eos.host import Host
            from neo4jlib.neo4j.session import Neo4jSession
            from neo4jlib.log import log
        except ImportError:
            NEO4J_DATA_DIR = None  # pylint: disable=C0103
            from neo4jlib.client.session import Neo4jSession
            from pyu.os.host import Host
            from pyu.os.shell.errors import CommandFailed
            from pyu.log import log
        log.setup_log(SysLogHandler(address='/dev/log'),
                      "Neo4j Snapshot - create snapshot")
        with Neo4jSession() as shell:
            try:
                lun_ids = json.loads(args['dblun_id'])
                if shell.cluster.is_single():
                    try:
                        lun_id = lun_ids["neo4jlun"]
                    except KeyError:
                        msg = "neo4jlun not in lun_ids: %s" % str(lun_ids)
                        raise Neo4jSnapshotCreationFailed(msg)
                else:
                    host = Host()
                    if not host.aliases:
                        msg = "Unable to get local host aliases from %s" % host
                        raise Neo4jSnapshotCreationFailed(msg)
                    db_alias_regex = re.compile(r"\w+\-(\d+)")
                    matches = [db_alias_regex.match(a)
                               for a in host.aliases
                               if db_alias_regex.match(a)]

                    if len(matches) != 1:
                        msg = "Unable to retrieve a unique local host " \
                              "db alias from %s" % host
                        raise Neo4jSnapshotCreationFailed(msg)
                    db_id = matches[0].groups()[0]
                    key = "neo4j_%s" % db_id
                    try:
                        lun_id = lun_ids[key]
                    except KeyError:
                        msg = "%s not in lun_ids: %s" % (key, str(lun_ids))
                        raise Neo4jSnapshotCreationFailed(msg)
                snap_name = "%s_%s" % (args['snap_name'], lun_id)
                user = args['spa_username']
                snap_command = self.get_sancli_snap_command(args['spa_ip'],
                                                            args['spb_ip'],
                                                            user,
                                                            args['Password'],
                                                            args['Scope'],
                                                            lun_id,
                                                            snap_name,
                                                            args['descr'],
                                                            args['array_type'])

                log_command = re.sub(r'--password=.*? ',
                                     '--password=****** ',
                                     snap_command)

                syslog_info('Executing {0}'.format(log_command))

                try:
                    _stdout = self.exec_command(snap_command, use_shell=True)
                except IOError as error:
                    syslog_error("Received Error Output: "
                                 "{0}".format(str(error)))
                    raise Neo4jSnapshotCreationFailed(str(error))
                _stdout_log = re.sub(r'--password=.*? ',
                                     '--password=****** ',
                                     _stdout)

                syslog_info("Received Output: {0}".format(_stdout_log))
                return self.get_return_struct(0, stdout=_stdout_log)

            except Neo4jSnapshotCreationFailed as err:
                # In case of any error, we make sure that the fs is unfrozen
                if shell.cluster.is_single():
                    syslog_info('Neo4j is single, no need to unfreeze')
                else:
                    data_dir = NEO4J_DATA_DIR or \
                               shell.os.sg.neo4j.consts.data_dir
                    try:
                        shell.os.fs.unfreeze(data_dir)
                    except CommandFailed as unfreeze_err:
                        syslog_error("Failed to unfreeze file system %s: %s" %
                                     (data_dir, unfreeze_err))
                    else:
                        syslog_info("File system %s is unfrozen" % data_dir)
                return self.get_return_struct(1, stderr=str(err))

    def create_versant_db_snapshot(self, args, db_name='dps_integration'):
        """
        Versant snapshot database function
        :param args: command arguments
        :type args: dict
        :param db_name: Name of the database to to execute the snap
        command from.
        :return: dict of return code,output,err message
        """

        snap_command = self.get_sancli_snap_command(args['spa_ip'],
                                                    args['spb_ip'],
                                                    args['spa_username'],
                                                    args['Password'],
                                                    args['Scope'],
                                                    args['dblun_id'],
                                                    args['snap_name'],
                                                    args['descr'],
                                                    args['array_type'])
        vjbackup_cmd = '/ericsson/versant/bin/vjbackup -cmd "{0}" ' \
                       '-split {1}'.format(snap_command, db_name)
        environ = os.environ.copy()
        environ['VERSANT_HOST_NAME'] = 'db1-service'

        log_command = re.sub(r'--password=.*? ',
                             '--password=****** ',
                             vjbackup_cmd)

        syslog_info('Executing {0}'.format(log_command))

        try:
            _stdout = self.exec_command(vjbackup_cmd, sudo='versant',
                                        environ=environ, use_shell=True)
        except IOError as error:
            syslog_error("Received Error Output: {0}".format(str(error)))
            return self.get_return_struct(1, stderr=str(error))
        _stdout_log = re.sub(r'--password=.*? ',
                             '--password=****** ',
                             _stdout)

        syslog_info("Received Output: {0}".format(_stdout_log))
        return self.get_return_struct(0, stdout=_stdout_log)

    def get_mysql_db_psw(self, psw_key, kfile, prop_file=GLOBAL_PROP_FILE):
        """
        Decrypt the MySQL password
        :param psw_key: key from global.properties file
        that stores the encrypted password
        :param kfile: key file
        :param prop_file: global.properties file
        :return:
        """

        with open(prop_file, 'r') as gpf:
            lines = gpf.readlines()

        for line in lines:
            key, value = line.strip().split('=', 1)
            if key == psw_key:
                mysql_pass = value
                break
        else:
            syslog_error('Did not find {0} value in {1} file'.
                         format(psw_key, prop_file))
            raise DbsnapshotsException

        tmp_file = tempfile.mktemp()
        with open(tmp_file, 'w') as _writer:
            _writer.write('{0}\n'.format(mysql_pass))

        command = 'openssl enc -a -d -aes-128-cbc -salt -kfile {0} -in {1}'. \
            format(kfile, tmp_file)

        try:
            decrypted = self.exec_command(command, use_shell=True)
        except Exception:
            raise DbsnapshotsException('Could not decrypt MySQL user password')
        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

        return decrypted.strip()

    @staticmethod
    def wrap_with_mysql_lock(db_user, db_password, command):
        """
        Get the mysql command that executes an SQL statement wrapped with
        lock/unlock statements.
        :param db_user: The user to execute the SQL statement as
        :param db_password: The user password
        :param command: The SQL statement to execute between the lock and
        unlock calls
        :returns: mysql cli command that will lock tables, execute a SQL
        statement, then unlock tables.
        """
        delim = "'"
        sql = [
            'FLUSH TABLES WITH READ LOCK',
            'system {0} || echo FAILED_SNAP_COMMAND\n'.format(command),
            'UNLOCK TABLES'
        ]
        mysql_pwflag = '--password={0}'.format(db_password)
        return ['/opt/mysql/bin/mysql',
                '--delimiter="{0}"'.format(delim),
                '--user={0}'.format(db_user),
                mysql_pwflag,
                '--execute="{0}"'.format(delim.join(sql))]

    def create_mysql_snapshot(self, args):
        """
        Mysql snapshot database functions

        :param args: command arguments
        :type args: dict
        :return: dict of return code,output,err message
        """
        mysql_user = args['mysql_user']
        dblun = args['dblun_id']
        snap_name = args['snap_name']
        mysql_psw = self.get_mysql_db_psw(MYSQL_PSW_KEY, MYSQL_KFILE)

        snap_command = self.get_sancli_snap_command(args['spa_ip'],
                                                    args['spb_ip'],
                                                    args['spa_username'],
                                                    args['Password'],
                                                    args['Scope'],
                                                    dblun,
                                                    snap_name,
                                                    args['descr'],
                                                    args['array_type'])
        try:
            lock_snap_cmd = self.wrap_with_mysql_lock(mysql_user, mysql_psw,
                                                      snap_command)
            lock_snap_cmd_str = ' '.join(lock_snap_cmd)
            logstring = ' '.join(lock_snap_cmd)

            logstring = logstring.replace('--password={0}'.format(mysql_psw),
                                          '--password=********')

            logstring = re.sub(r'--password=.*? ',
                                 '--password=****** ',
                                 logstring)

            syslog_info('Snapping MySQL LUN with: {0}'.format(logstring))
            stdout = self.exec_command(lock_snap_cmd_str, use_shell=True)
            syslog_info('MySQL Snap Output: {0}'.format(stdout))
            if 'FAILED_SNAP_COMMAND' in stdout:
                # If the system command fails then the mysql cli will still
                # exit zero so check the output for the failed shell command
                # tag i.e. FAILED_SNAP_COMMAND
                return self.get_return_struct(1, stderr=stdout)
            else:
                msg = 'Snapped LUN {0}/{1}'.format(dblun, snap_name)
                syslog_info(msg)
                return self.get_return_struct(0, stdout=msg)
        except IOError as error:
            return self.get_return_struct(1, stderr=str(error))

    def ensure_installed(self, args):
        """
        Check a package is installed, if not, install the package.

        :param args: command arguments
        :type args: dict

        """
        ensure_package = args['package']

        _stdout = None
        _stderr = None
        return_code = 1
        try:
            self.exec_command(['/bin/rpm', '-q', ensure_package])
            _stdout = 'Package {0} already installed.'.format(ensure_package)
            return_code = 0
            syslog_info(_stdout)
        except IOError:
            syslog_info('Need to install {0}'.format(ensure_package))
            _retry_count = 0
            while True:
                try:
                    _out = self.exec_command(['/usr/bin/yum', 'install', '-y',
                                              ensure_package])
                    syslog_info('{0}'.format(_out))
                    return_code = 0
                    _stdout = 'Installed {0}'.format(ensure_package)
                    break
                except IOError as error:
                    _msg = str(error)
                    if 'Another app is currently holding the yum lock' in _msg:
                        _retry_count += 1
                        if _retry_count > self.yum_retry_count:
                            _stderr = 'YUM is locked, retried {0} times to ' \
                                      'install {1} to no avail' \
                                      ''.format(self.yum_retry_count,
                                                ensure_package)
                            return_code = 1
                            break
                        sleep(self.yum_retry_wait)
                    else:
                        return_code = 1
                        _stderr = _msg
                        break

        return self.get_return_struct(return_code,
                                      stdout=_stdout,
                                      stderr=_stderr)

    def create_snapshot(self, args):
        """
        Wrapper on databases snapshot functions
        :param args: command arguments
        :type args: dict
        :return: dict of return code,output,err message
        """
        if args['dbtype'] == 'versant':
            return self.create_versant_db_snapshot(args)
        elif args['dbtype'] == 'mysql':
            return self.create_mysql_snapshot(args)
        elif args['dbtype'] == 'neo4j':
            return self.create_neo4j_db_snapshot(args)
        else:
            return self.get_return_struct(1,
                                          stderr='Unsupported db type '
                                                 '{0}'.format(args['dbtype']))

    def opendj_backup(self, args):
        """
        Take opendj backup
        :param args: backup command arguments
        :type args: dict
        :return: dict of return code,output,err message
        """
        command = "{0} {1} {2}".format(args['opendj_backup_cmd'],
                                       args['opendj_backup_dir'],
                                       args['opendj_log_dir'])
        syslog_info('Executing {0}'.format(command))
        try:
            _stdout = self.exec_command(command, sudo='opendj', use_shell=True)
        except IOError as error:
            syslog_error("OpenDJ backup failed: {0}".format(str(error)))
            return self.get_return_struct(1, stderr=str(error))
        return self.get_return_struct(0, stdout=_stdout)

    def opendj_cleanup(self, args):
        """
        Deletes the opendj dir structure when remove snapshots is called
        :param args: backup dir and log dir location
        :type args: dict
        :return: dict of return code, output, err message
        """
        try:

            if os.path.exists(args['opendj_backup_dir']):
                syslog_info('Deleting opendj backup directory {0}'.
                            format(args['opendj_backup_dir']))
                shutil.rmtree(args['opendj_backup_dir'])
            if os.path.exists(args['opendj_log_dir']):
                syslog_info('Deleting opendj backup log directory {0}'.
                            format(args['opendj_log_dir']))
                shutil.rmtree(args['opendj_log_dir'])
        except OSError as error:
            syslog_error("OpenDJ cleanup failed: {0}".format(str(error)))
            return self.get_return_struct(1, stderr=str(error))
        return self.get_return_struct(
                0, stdout='Opendj cleanup performed successfully')


if __name__ == '__main__':
    try:
        open_log()
        Dbsnapshots().action()
    finally:
        close_log()
