"""
Helper functions.
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
import collections
import os
import re
import stat
import sys
import traceback
import glob
from ConfigParser import ConfigParser, MissingSectionHeaderError, \
    NoOptionError
from json import dumps
from os.path import expanduser, join, exists
from h_xml.xml_utils import xpath, load_xml
from h_util.h_utils import keyboard_interruptable, is_physical_environment,\
    exec_process_via_pipes


UNIX_SOCKET = '/var/run/litpd/litpd.sock'
TCP_CONNECTION = 'tcp'
UNIX_CONNECTION = 'unix'


class LitpException(Exception):
    """
    LITP operation failed.
    """

    def get_key_value(self, key='', value=''):
        """
        Check if messages dictionary inside this object contains
         given key and value
        :param key which is expected in messages structure
        :param value which is expected in messages structure
        :return: True if this exception contains
        given key and value in messages dictionary
        """
        message_value = self.get_message_from_messages(key)
        if message_value:
            return message_value == value
        else:
            return False

    def get_message_from_messages(self, key):
        """
        Retrieves message from messages dictionary for given key
        :param key which is expected in messages structure
        :type key: str
        :return: message if exists for given key or None otherwise
        :rtype str
        """
        if len(self.args) <= 1:
            return None
        if not isinstance(self.args[1], collections.Iterable):
            return None
        if 'messages' not in self.args[1]:
            return None
        for error in self.args[1]['messages']:
            if isinstance(error, dict):
                for item_key, item_value in error.items():
                    if item_key == key:
                        return item_value
        return None

    def get_default_message(self):
        """
        Retrieves default message from messages dictionary
        :return:  message if exists for default 'message' key, otherwise None
        :rtype str
        """
        return self.get_message_from_messages('message')

    def litp_in_maintenance_mode(self):
        """
        Determines if LITP is in maintenance mode
        :return: True if LITP in maintenance mode. False otherwise.
        :rtype boolean
        """
        msg = 'LITP is in maintenance mode'
        error_type = 'ServerUnavailableError'
        return self.get_key_value('message', msg) and \
               self.get_key_value('type', error_type)


class LitprcConfig(dict):
    """
    Object to encapsulate configuration data and information
    about configuration file itself.
    """
    def __init__(self, path):
        self.path = path
        self.file_missing = False
        self.file_broken = False
        super(LitprcConfig, self).__init__()


def get_connection_type(litprc_data):
    """
    Decide what is the type of connection.
    Choose Unix socket if available.

    :param litprc_data: instance of LitprcConfig
    :return: tuple of connection type and connection details
      - connection type is either TCP_CONNECTION or UNIX_CONNECTION
      - connection details is either None or path to unix socket
    """
    path = litprc_data.get('unix_socket_path', UNIX_SOCKET)
    if (path  # configuration provides path and allows socket
        and exists(path)  # socket exists in FS
        and stat.S_ISSOCK(os.stat(path).st_mode)  # socket is socket
        ):
        return UNIX_CONNECTION, path
    return TCP_CONNECTION, None


def read_litprc(litprc=None):
    """
    Reads the .litprc file so that litp-admin authentication is possible for
    REST calls
    :param litprc: Path to non-default litprc file
    :returns: dictionary litp-admin login credentials, path to file
    """
    if not litprc:
        if 'TEST_HOME' in os.environ:
            home = os.environ['TEST_HOME']
        else:
            home = expanduser("~")
        litprc = join(home, '.litprc')
    data = LitprcConfig(litprc)
    if not exists(litprc):
        # to distinguish missing file and file without credentials
        data.file_missing = True
        return data
    entries = ('username', 'password', 'unix_socket_path')
    reader = ConfigParser()
    try:
        reader.read(litprc)
    except MissingSectionHeaderError:
        data.file_broken = True
        return data
    option_counter = len(entries)
    for section in reader.sections():
        for option in entries:
            if option not in data:
                try:
                    data[option] = reader.get(section, option)
                except NoOptionError:
                    pass
                else:
                    option_counter -= 1
        if option_counter == 0:
            break
    return data


def get_cluster_types_from_dd_info():
    """
    Get the cluster names using the DST file
    :return: list containing cluster names
    """
    deploy_file = None
    cluster_lists = []
    for files in glob.glob("/ericsson/deploymentDescriptions/*/*.txt"):
        deploy_file = files
        break
    ref_file = open(deploy_file)
    lines = ref_file.readlines()
    for line in lines:
        if 'cluster' in line:
            cluster_string = (line.strip('\n')).split("=", 1)
            if "cluster" in cluster_string[0] and \
                    cluster_string[0] not in cluster_lists\
                    and str(cluster_string[1]).isdigit():
                cluster_lists.append(cluster_string[0])
    return cluster_lists


def get_dd_xml_file():  # pylint: disable=R0914, R0915, R0912, W0142
    """
    Using the LITP model retrieve the deployment Description
    XML file that was last used to deploy the system.
    :return: deployment Description file name.
    """
    cluster_nodes = []
    grep_commands = []

    cluster_lists = get_cluster_types_from_dd_info()
    for cluster in cluster_lists:
        node_name = cluster.split('_')[:-1]
        node_name = '{0}-'.format(node_name)
        path = '/deployments/enm/clusters/{0}/nodes/'.format(cluster)
        cmd = ['litp', 'show', '-p', path]
        grep_cmd = ['grep', '-c', node_name]
        try:
            result = exec_process_via_pipes(cmd, grep_cmd)
        except IOError:
            result = '0'
        node_number = '{0}={1}'.format(cluster, result.rstrip())
        cluster_nodes.append(node_number)

    for clusters in cluster_nodes:
        grep_cmd = ['xargs', 'grep', '-l', clusters]
        grep_commands.append(grep_cmd)

    find_cmd = ['find', '/ericsson/deploymentDescriptions/', '-type',
                'f', '-name', '*info.txt']

    grep_dualstack = ['grep', '-c', 'vipv6']
    grep_ipv6 = ['grep', '-c', 'ipv6']

    dualstack_cmd = ['litp', 'show', '-p', '/deployments/enm/clusters/'
                                           'svc_cluster/services/'
                                           'haproxy-ext/ipaddresses/']
    ipv6_cmd = ['litp', 'show', '-p', '/deployments/enm/clusters/'
                                      'svc_cluster/nodes/svc-1/'
                                      'network_interfaces/br3/']

    result2 = None
    try:
        result1 = exec_process_via_pipes(ipv6_cmd, grep_ipv6)
    except IOError:
        result1 = 0
    if result1 == 0:
        try:
            result2 = exec_process_via_pipes(dualstack_cmd, grep_dualstack)
        except IOError:
            result2 = 0

    if result1 != 0:
        dd_filter = ['xargs', 'grep', '-l', 'IPv6']
    elif result2 != 0:
        dd_filter = ['xargs', 'grep', '-l', 'dualStack']
    else:
        dd_filter = ['xargs', 'grep', '-l', 'IPv4']

    uniq = ['uniq']
    parameters = [find_cmd]
    for i in range(len(grep_commands)):
        parameters.append(grep_commands[i])
    parameters.extend([dd_filter, uniq])

    #  pylint: disable=W0142
    dd_info_file = exec_process_via_pipes(*parameters)

    dd_result = dd_info_file.rstrip()
    deployment_description = dd_result.replace("info.txt", "dd.xml")

    if not os.path.exists(deployment_description):
        return

    file_name = os.path.split(deployment_description)[-1]

    if os.path.exists('/tmp/{0}'.format(file_name)) and \
            is_physical_environment():
        deployment_description = ('/tmp/' + file_name)

    return deployment_description


def get_enm_version_deployed():
    """
    Gets the version on ENM ISO currently deployed.
    :return: iso_version
    """
    try:
        enm_version = open('/etc/enm-version')
        line = enm_version.readline()
        searching = re.search(r'\(([^)]+)', line).group(1)
        version = searching.split(' ')
        iso_version = version[-1]
        enm_version.close()
        return iso_version

    except IOError:
        raise IOError('Failed to get enm-version')


def get_xml_deployment_file():  # pylint: disable=R0912
    """
    Gets the deploymentDescription File currently
    deployed on the system
    :return:
    """
    path = ''
    iso_only_upgrade = False
    enm_version = get_enm_version_deployed()

    try:
        if not os.path.isfile('/opt/ericsson/enminst/log/cmd_arg.log'):
            raise IOError('cmd_arg.log file does not exist')

        files = open('/opt/ericsson/enminst/log/cmd_arg.log')
        lines = files.readlines()
        for line in reversed(lines):
            if line.startswith('./upgrade') or \
                    line.startswith('./deploy'):
                if (enm_version in line) or \
                        ('.iso' not in line) or iso_only_upgrade:
                    if '.xml' not in line:
                        iso_only_upgrade = True
                    args = (line.split(' '))
                    for arg in args:
                        arg = arg.rstrip()
                        if arg.startswith('/ericsson') or \
                                arg.startswith('/software'):
                            if arg.endswith('.xml'):
                                path = arg
                                break
                    if path:
                        break
                else:
                    continue

        files.close()

        if not path:
            raise IOError('Error getting path of the xml file '
                          'from cmd_arg.log')

        file_name = os.path.split(path)[-1]

        if os.path.exists('/tmp/{0}'.format(file_name)) and \
                is_physical_environment():
            path = ('/tmp/' + file_name)

        if not os.path.exists(path):
            raise IOError('DeploymentDescription XML file:{0} does not exist'
                          .format(path))

        return path
    except Exception:
        raise


def is_custom_service(vm_service, path):
    """
    Decides whether a service in the litp model is a customised service or not
    :param vm_service: Service element found under 'vm-service' in the
    litp model
    :param path: Path to dd xml for last deployed state.
    :returns: boolean of whether the service is a customised service or not
    :rtype bool
    """
    services = []
    try:

        vm_serv = vm_service.get('id')
        dd_xml = load_xml(path)

        for service in xpath(dd_xml, 'vm-service-inherit'):
            service_path = service.get('source_path')
            services.append(service_path)

        vm_serv_path = '/software/services/{0}'.format(vm_serv)

        if vm_serv_path not in services:
            print 'Custom Service: {0}'.format(vm_serv)
            return True
        return False

    except Exception:
        raise


@keyboard_interruptable()
def main_exceptions(main, prog_args=None):
    """
    Decorator function to handle errors from LITP
    :param main: The function being decorated
    :param prog_args: Arguements into the function
    :return: Return result from wrapped function
    """
    try:
        if prog_args is not None:
            main(prog_args)
        else:
            main()
    except LitpException as error:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, '{0}'.format(exc_value.args[1]),
                                  exc_traceback, file=sys.stderr)
        if 'messages' in error.args[1]:
            for error in error.args[1]['messages']:
                if isinstance(error, dict):
                    for key, value in error.items():
                        sys.stderr.write('\t{0} -> {1}\n'.format(key, value))
                else:
                    sys.stderr.write('{0}\n'.format(error))
        elif isinstance(error.args[1], dict):
            for _key, _value in error.args[1].items():
                sys.stderr.write('\t{0} -> {1}\n'.format(_key, _value))
        else:
            sys.stderr.write('{0}\n'.format(error.args[1]))
        raise SystemExit(exc_value.args[0])


class LitpObject(object):  # pylint: disable=R0902
    """
    Object to represent items in the LITP deployment model.
    """

    def __init__(self, parent, data, path_parser):
        self._parent = parent
        self._rel = None
        self._children = {}
        self._properties = {}
        self._state = None
        self._type = None
        self._desc = ''
        self._inheritted = False

        self.__referenceto = 'reference-to-'
        self._jsondata = data

        if self._jsondata:
            self._path = path_parser(self._jsondata['_links']['self']['href'])
            self._id = self._jsondata.get('id', 'N/A')
            self._type = self._jsondata.get('item-type-name', None)
            if self._type.startswith(self.__referenceto):
                self._inheritted = True
                self._type = self._type[len(self.__referenceto):]
            self._properties = self._jsondata.get('properties', None)
            self._state = self._jsondata.get('state', None)
            self._desc = self._jsondata.get('description', None)

        # State is generally a seperate attribute but certain item-types have
        # it in properties (plan root for example) ...
        p_state = self.get_property('state')
        if not self._state and p_state:
            self._state = p_state

        if '_embedded' in self._jsondata:
            for item in self._jsondata['_embedded']['item']:
                child = LitpObject(self, item, path_parser)
                self._children[child.item_id] = child
        else:
            self._jsondata['_embedded'] = {
                'item': []
            }

        if self.is_task:
            self._rel = path_parser(self._jsondata['_links']['rel']['href'])

    def as_json(self):
        """
        Get the data used to construct the object in json string format
        :returns: JSON string data used to populate the object
        :rtype: str
        """
        return dumps(self._jsondata)

    def as_struct(self):
        """
        Get a dict of the data used to populate the object
        :returns: dict of the data used to populate the object
        :rtype: dict
        """
        return self._jsondata

    def add_child(self, child):
        """
        Add a child to the object. This is a local only update i.e. it does
        not change anything in LITP (the LitpRestClient for that)

        :param child: The child to add
        :type child: LitpObject
        :return:
        """
        self._jsondata['_embedded']['item'].append(child.as_struct())

    @property
    def is_task(self):
        """
        Is the item as task item or not
        :return:
        """
        return self.item_type == 'task'

    @property
    def task_item(self):
        """
        Get the item in the model the task was generated from. If `self` is
        not a tasks then this will return `None`
        :return:
        """
        return self._rel

    @property
    def parent(self):
        """
        Get this items parent item (if set)
        :return:
        """
        return self._parent

    @property
    def state(self):
        """
        Get the state if the item when it was read from the model
        :return:
        """
        return self._state

    @property
    def item_id(self):
        """
        Get the item model ID
        :return:
        """
        return self._id

    @property
    def item_type(self):
        """
        Get the item type
        :return:
        """
        return self._type

    @property
    def path(self):
        """
        Get the items path in the model
        :return:
        """
        return self._path

    @property
    def children(self):
        """
        Get children of the item
        :return:
        """
        return self._children

    @property
    def properties(self):
        """
        Get all properties of the item
        :return:
        """
        return self._properties

    def get_property(self, property_name, default_value=None):
        """
        Get the value of an item property
        :param property_name: The property name
        :param default_value: Default value to return if property not set/found
        :return:
        """
        if self._properties:
            return self._properties.get(property_name, default_value)
        else:
            return default_value

    @property
    def is_inherrited(self):
        """
        Is the item inherrited from another item or not
        :return:
        """
        return self._inheritted

    def get_bool_property(self, property_name):
        """
        Returns bool value for given property name
        :param property_name: name of property
        :type property_name: str
        :return: True or False
        :rtype bool
        :raise ValueError: if conversion problem occurs or property is missing
        """
        value = self.get_property(property_name)
        if value is None:
            raise ValueError("No value defined for property {0}"
                             .format(property_name))
        if value == "true":
            return True
        elif value == "false":
            return False
        else:
            raise ValueError("No expected JSON boolean value "
                             "like 'true' or 'false' but {0}".format(value))

    def get_int_property(self, name, default_value=None):
        """
        Changing a property value from string into an integer.
        :param name: Property string value
        :param default_value: A default numeric value ie. `0`
        :return: The integer value of a string input.
        """
        _value = self.get_property(name)
        if _value is None:
            return default_value
        else:
            return int(_value)

    @property
    def description(self):
        """
        Get the item instance description
        :return:
        """
        return self._desc

    def __repr__(self):
        return '{path} [item-type:{type} state:{state}] ' \
               'properties{properties}'.format(path=self.path,
                                               type=self.item_type,
                                               state=self.state,
                                               properties=self._properties)
