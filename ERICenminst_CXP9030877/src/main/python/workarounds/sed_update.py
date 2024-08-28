#!/usr/bin/env python
""" Re-maps services IP addresses defined in a given SED based on 2 different
Deployment Descriptions containing different aliases definitions.
"""

import os
import re
import sys
import logging

from lxml import etree
from argparse import ArgumentParser
from collections import OrderedDict
from datetime import datetime

SED_IP_PROPERTY_REGEX = re.compile(r"^([\w-]+)_(\d+)_.*")
SED_SUB_REGEX = re.compile(r"(^[\w-]+_)\d+(_.*)")

EMPTY_LINE = "__EMPTY_LINE__"
COMMENT = "__COMMENT__"

DEFAULT_LOG_DIR = os.getcwd()
FAILSAFE_LOG_DIR = '/var/tmp'

LOG_DIR = DEFAULT_LOG_DIR
if not os.access(DEFAULT_LOG_DIR, os.W_OK):
    LOG_DIR = FAILSAFE_LOG_DIR
LOG_FILENAME_FORMAT = 'sed_aliases_remap_%s.log'

XML_NAMESPACES = {
    'litp': 'http://www.ericsson.com/litp'
}

log = None  # pylint: disable=C0103


class ExitCode(object):  # pylint: disable=R0903
    """ Exit code definitions
    """
    internal_error = 1
    validation_error = 2


class ValidationError(Exception):
    """ Validation Error exception base
    """


class FileDoesNotExist(ValidationError):
    """ Validation exception for a file that does not exit
    """

    def __init__(self, file_path):
        super(FileDoesNotExist, self).__init__("File %s does not exit" %
                                               file_path)


def setup_logger(log_level=logging.INFO):
    """ Creates a logger to log the script's execution
    """
    now = datetime.now()
    log_filename = os.path.join(LOG_DIR, LOG_FILENAME_FORMAT % now.isoformat())
    log_format_file = logging.Formatter('%(asctime)s %(levelname)s: '
                                        '%(message)s',
                                        datefmt='%Y-%m-%d %H:%M:%S')

    log_format_screen = logging.Formatter('%(asctime)s %(levelname)s: '
                                          '%(message)s', datefmt='%H:%M:%S')
    logger = logging.getLogger('app')

    # remove any existing handlers
    logger.handlers = []

    # log DEBUG messages to the log file
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format_file)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(log_format_screen)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.DEBUG)

    return logger


class SedAliasesRemapper(object):
    """ Main class to be used to fix SED entries based on 2 DDs.
    """

    def __init__(self, sed_path, old_dd_path, new_dd_path):
        """ SedAliasesRemapper constructor.
        :param sed_path str: SED file path
        :param old_dd_path: old Deployment Description file path
        :param new_dd_path: new Deployment Description file path
        """
        if not os.path.isfile(sed_path):
            raise FileDoesNotExist(sed_path)
        if not os.path.isfile(old_dd_path):
            raise FileDoesNotExist(old_dd_path)
        if not os.path.isfile(new_dd_path):
            raise FileDoesNotExist(new_dd_path)
        self.sed_path = sed_path
        self.old_dd_path = old_dd_path
        self.new_dd_path = new_dd_path

    @property
    def sed(self):
        """ Parses the current SED file transforming it into a dictionary.

        NOTE: potential empty lines are also kept using a special key
        EMPTY_LINE_#. Similar occurs for possible comments starting with #.

        :return OrderedDict: a dictionary containing all SED properties as keys
        and its corresponding values.
        """
        data = OrderedDict()
        empty_line_count = 0
        comment_count = 0
        with open(self.sed_path) as sed_file:
            for line in sed_file:
                line = line.strip()
                if not line:
                    key = "%s_%s" % (EMPTY_LINE, empty_line_count)
                    empty_line_count += 1
                    data[key] = ""
                    continue
                if line.startswith("#"):  # ignore comments
                    key = "%s_%s" % (COMMENT, comment_count)
                    comment_count += 1
                    data[key] = line
                    continue
                split = line.split("=", 1)
                if len(split) < 2:
                    prop, value = split[0], ""
                else:
                    prop, value = split
                prop = prop.strip()
                data[prop] = value
        return data

    @property
    def categorized_sed(self):
        """ Returns a similar structure as self.sed, however, for properties
        matching the regular expression SED_IP_PROPERTY_REGEX (e.g. cmserv_1_*)
        it re-structures in a specific format to categorize it based on the
        service name.

        For example, for a SED file parsed as:
        {
            'VLAN_ID_services': '169',
            'VLAN_ID_backup': '999',
            'cmserv_1_ip_internal': '192.168.20.25',
            'cmserv_1_ip_jgroups': '192.168.10.10'
            'cmserv_2_ip_internal': '192.168.20.18',
            'cmserv_2_ip_jgroups': '192.168.10.11'
            'netext_1_ip_internal': '192.168.20.25',
            'netext_1_ip_jgroups': '192.168.10.18'
            'netext_2_ip_internal': '192.168.20.26',
            'netext_2_ip_jgroups': '192.168.10.19'
        }

        it will be transformed into the following structure:
        {
            'VLAN_ID_services': 169,
            'VLAN_ID_backup': 999,
            'cmserv': {
                1: [
                    ('cmserv_1_ip_internal', '192.168.20.17'),
                    ('cmserv_1_ip_jgroups', '192.168.10.10')
                ],
                2: [
                    ('cmserv_2_ip_internal', '192.168.20.18'),
                    ('cmserv_2_ip_jgroups', '192.168.10.11')
                ]
            },
            'netext': {
                1: [
                    ('netext_1_ip_internal', '192.168.20.25'),
                    ('netext_1_ip_jgroups', '192.168.10.18')
                ],
                2: [
                    ('netext_2_ip_internal', '192.168.20.26'),
                    ('netext_2_ip_jgroups', '192.168.10.19')
                ]
            }
        }
        :return OrderedDict: a categorized sed
        """
        data = OrderedDict()
        previous_index = None
        previous_service_name = None
        previous_prop = None
        for prop, value in self.sed.items():
            match = SED_IP_PROPERTY_REGEX.search(prop)
            if match:
                service_name, index = match.groups()
                if previous_service_name != service_name:
                    previous_index = None
                previous_service_name = service_name
                if previous_index is not None and previous_index != index:
                    # this check is just to make sure we maintain the empty
                    # lines in the order as they were previously
                    if data.keys()[-1].startswith(EMPTY_LINE):
                        empty_entry = (previous_prop, data.pop(previous_prop))
                        data.setdefault(service_name, OrderedDict()) \
                            .setdefault(int(previous_index),
                                        []).append(empty_entry)
                previous_index = index
                data.setdefault(service_name, OrderedDict())\
                    .setdefault(int(index), []).append((prop, value))
            else:
                data[prop] = value
            previous_prop = prop
        return data

    @staticmethod
    def _parse_internal_aliases(dd_path):
        """ Parses a Deployment Description xml looking for all tags named
        <litp:vcs-clustered-service> and build a dictionary with the service
        names as keys and as value another dictionary holding a map of aliases
        and position in the list.

        Return example:
        {
            'kpicalcserv':
                {'svc-9': 1,
                 'svc-10': 2},
            ...
        }

        :param dd_path str: a deployment description file path
        :return dict: a dictionary as described above
        """
        # pylint: disable=W1201
        data = {}
        root = etree.parse(dd_path)
        vcs_clustered_services = root.xpath(".//litp:vcs-clustered-service",
                                            namespaces=XML_NAMESPACES)
        for vcs_clustered_service in vcs_clustered_services:
            name = vcs_clustered_service.get('id')
            active_el = vcs_clustered_service.find('active')
            if active_el is None:
                log.debug("Could not parse <active> tag from "
                          "vcs-clustered-service %s" % name)
                continue
            active = bool(int(active_el.text))
            if not active:
                log.debug("Ignoring non active vcs-clustered-service %s" %
                          name)
                continue
            node_list_el = vcs_clustered_service.find('node_list')
            if node_list_el is None:
                log.debug("Ignoring vcs-clustered-service %s as it has an "
                          "empty node_list" % name)
                continue
            node_list = node_list_el.text.split(',')
            for i, alias in enumerate(node_list):
                data.setdefault(name, {})[alias] = i + 1
        return data

    @property
    def _old_internal_aliases_index_map(self):
        """ Returns a map of internal aliases and its corresponding index from
        the old Deployment Description.
        :return dict: a dictionary as described in self._parse_internal_aliases
        """
        return self._parse_internal_aliases(self.old_dd_path)

    @property
    def _new_internal_aliases_index_map(self):
        """ Returns a map of internal aliases and its corresponding index from
        the new Deployment Description.
        :return dict: a dictionary as described in self._parse_internal_aliases
        """
        return self._parse_internal_aliases(self.new_dd_path)

    def _generate_aliases_position_map(self):
        """ Generates a map by service containing the IP position index in the
        list from both provided Deployment Description files (old and new one),
        if they are common encountered in each other's list.

        Example for a service "mscmapg" with aliases defined as following:
        Old DD: 10svc_4scp_enm_physical_production_dd.xml
        New DD: 10svc_4scp_8str_rack_3ebs_6asr_enm_physical_production_dd.xml

        Position  1       2       3       4       5       6
        Old DD    svc-2   svc-3   svc-7   svc-8	  svc-9	  svc-10
        New DD    svc-1   svc-2   svc-3   svc-5   svc-6   svc-8

        This method will return a dict mapping all services with all aliases
        positions that are common in both. For this specific service "mscmapg",
        the return value will be:
        {
            ...
            'mscmapg': [(1, 2), (2, 3), (4, 6)]
            ...
        }

        :return dict: a map of service names and its aliases position indexes.
        """
        all_old_aliases = self._old_internal_aliases_index_map
        all_new_aliases = self._new_internal_aliases_index_map
        data = {}
        for name, old_aliases in all_old_aliases.items():
            for old_alias, old_index in old_aliases.items():
                new_aliases = all_new_aliases.get(name)
                if not new_aliases:
                    continue
                new_index = new_aliases.get(old_alias)
                if new_index:
                    data.setdefault(name, []).append((old_index, new_index))
        return data

    def _remap(self):
        """ Remaps the SED fixing the order of IPs defined by renaming the
        properties aliases.
        Basically, we get the index position from both old and new DDs and use
        it to be able to identify which property in the SED should be renamed.

        self._generate_aliases_position_map() will return
        a dict mapping all services with all aliases positions that are common
        in both. Refer to this method docstring. Illustration below:

        Old DD: 10svc_4scp_enm_physical_production_dd.xml
        New DD: 10svc_4scp_8str_rack_3ebs_6asr_enm_physical_production_dd.xml

         * For a service "mscmapg" with aliases defined as following:
        Position  1       2       3       4       5       6
        Old DD    svc-2   svc-3   svc-7   svc-8	  svc-9	  svc-10
        New DD    svc-1   svc-2   svc-3   svc-5   svc-6   svc-8

        {
            ...
            'mscmapg': [(1, 2), (2, 3), (4, 6)]
            ...
        }

        With this information, we know that every "mscmapg_<INDEX>_*"
        property in the SED should be renamed accordingly. From above:
            mscmapg_1_*  will be renamed to  mscmapg_2_*
            mscmapg_2_*  will be renamed to  mscmapg_3_*
            mscmapg_4_*  will be renamed to  mscmapg_6_*

        As a second step, we need to make sure that the remaining aliases in
        from the old SED with indexes (3, 5, 6) are assigned in order to the
        remaining aliases from the new SED (1, 4, 5):
            mscmapg_3_*  will be renamed to  mscmapg_1_*
            mscmapg_5_*  will be renamed to  mscmapg_4_*
            mscmapg_6_*  will be renamed to  mscmapg_5_*

        Real example below with entries in the SED:

@=mscmapg
ORIGINAL SED                                      MODIFIED SED

@_1_ip_internal=192.168.20.208 }------+   { @_1_ip_internal=192.168.20.210
@_1_ip_jgroups=192.168.10.182  }      |   { @_1_ip_jgroups=192.168.10.184
@_1_ipv6address=               }    +-|-->{ @_1_ipv6address=
                                    | |
@_2_ip_internal=192.168.20.209 }    | |   { @_2_ip_internal=192.168.20.208
@_2_ip_jgroups=192.168.10.183  }--+ | +-->{ @_2_ip_jgroups=192.168.10.182
@_2_ipv6address=               }  | |     { @_2_ipv6address=
                                  | |
@_3_ip_internal=192.168.20.210 }--|-+     { @_3_ip_internal=192.168.20.209
@_3_ip_jgroups=192.168.10.184  }  |       { @_3_ip_jgroups=192.168.10.183
@_3_ipv6address=               }  +------>{ @_3_ipv6address=

@_4_ip_internal=192.168.20.211 }--+       { @_4_ip_internal=192.168.20.212
@_4_ip_jgroups=192.168.10.185  }  |       { @_4_ip_jgroups=192.168.10.186
@_4_ipv6address=               }  | +---->{ @_4_ipv6address=
                                  | |
@_5_ip_internal=192.168.20.212 }  | |     { @_5_ip_internal=192.168.20.213
@_5_ip_jgroups=192.168.10.186  }--|-+     { @_5_ip_jgroups=192.168.10.187
@_5_ipv6address=               }  |   +-->{ @_5_ipv6address=
                                  |   |
@_6_ip_internal=192.168.20.213 }--|---+   { @_6_ip_internal=192.168.20.211
@_6_ip_jgroups=192.168.10.187  }  |       { @_6_ip_jgroups=192.168.10.185
@_6_ipv6address=               }  +------>{ @_6_ipv6address=

        """
        # pylint: disable=R0914,R0912
        aliases_pos = self._generate_aliases_position_map()
        new_sed = []
        for prop, value in self.categorized_sed.items():
            if isinstance(value, basestring):
                # for a non categorized attribute, we just append the property
                # and value and continue
                new_sed.append((prop, value))
                continue

            # if reaches here, it means that the value is a categorized groups,
            # refer to "self.categorized_sed". The variable prop, is now a
            # service name, e.g: "kpicalcserv".
            categorized_group = value
            service_name = prop
            # getting the aliases position indexes from both old and new DD
            # based on the given service name "prop".
            alias_pos = aliases_pos.get(service_name)
            if alias_pos is None:
                # if None, we just append the categorized properties/values
                # and continue
                for sub_props in categorized_group.values():
                    for sub_prop, sub_value in sub_props:
                        new_sed.append((sub_prop, sub_value))
                continue

            # this dict will contain potential modified aliases position
            modified_service = {}
            # populate diffs
            for old_index, new_index in sorted(alias_pos):
                # get the properties group given the old index
                sub_props = categorized_group.get(old_index)
                if old_index != new_index:
                    msg = "Moving %s %s -> %s" % (service_name, old_index,
                                                  new_index)
                    log.info(msg)
                modified_properties = []
                for sub_prop, sub_value in sub_props:
                    # for each property in the categorized dict, we make sure
                    # we assign the correct new index
                    renamed_prop = SED_SUB_REGEX.sub(r"\g<1>%s\2" % new_index,
                                                     sub_prop)
                    modified_properties.append((renamed_prop, sub_value))
                modified_service[new_index] = modified_properties

            # get the indexes of the remaining properties
            remaining = [i for i in xrange(1, len(categorized_group) + 1)
                         if i not in modified_service]

            # populate the remaining ones accordingly in order
            for old_index, sub_props in sorted(categorized_group.items()):
                modified_properties = []
                # gets the new_index number based on the old_index
                new_index = dict(alias_pos).get(old_index)
                if new_index in modified_service:
                    # it's already in the dictionary, just continue
                    continue
                # defining a list to hold potential modified properties if the
                # remaining index is different than the old one

                ind = remaining.pop(0)  # getting a remaining index in order
                if old_index != ind:
                    msg = "Moving %s %s -> %s" % (prop, old_index, ind)
                    log.info(msg)
                for sub_prop, sub_value in sub_props:
                    # same as before we make sure we assign the correct new
                    # index for this remaining property
                    renamed_prop = SED_SUB_REGEX.sub(r"\g<1>%s\2" % ind,
                                                     sub_prop)
                    modified_properties.append((renamed_prop, sub_value))
                modified_service[ind] = modified_properties

            # make sure we sort the modified_service list of tuples before
            # we append to the new_sed list
            for _, mvalue in sorted(modified_service.items()):
                for mprop, val in mvalue:
                    new_sed.append((mprop, val))
        return new_sed

    def start(self):
        """ The main method that will fix the order of IPs defined in the SED
        and save the new SED file generated.
        """
        print
        print "Remapping..."
        print
        new_sed = self._remap()
        # finally we use the new_sed list of tuples to write the SED fixed
        new_sed_file_path = "%s.updated" % self.sed_path
        with open(new_sed_file_path, 'w') as new_sed_file:
            # below we consider including empty lines and potential original
            # comments to keep the file as closer as possible to the original
            new_sed_file.write('\n'.join("" if p.startswith(EMPTY_LINE)
                                            else v if p.startswith(COMMENT)
                                                 else "%s=%s" % (p, v)
                                         for p, v in new_sed))
        msg = "New SED file generated: %s" % new_sed_file_path
        log.info(msg)
        print
        print "#" * 100
        print msg
        print "-" * 100
        print


def parse_args():
    """ Parse CLI arguments
    :return Namespace: argparse Namespace
    """
    parser = ArgumentParser(description="Re-maps services IP addresses "
                                        "defined in a given SED based on 2 "
                                        "different Deployment Descriptions "
                                        "containing different aliases "
                                        "definitions.")
    parser.add_argument("-s", "--sed", help="SED file path", required=True)
    parser.add_argument("-o", "--old-dd", help="From state DD file path",
                        required=True)
    parser.add_argument("-n", "--new-dd", help="To state DD file path",
                        required=True)
    return parser.parse_args()


def main():
    """ Main function which will parse arguments from CLI and start the SED
    Aliases re-mapper.
    """
    global log  # pylint: disable=W0603,C0103
    log = setup_logger()
    args = parse_args()
    try:
        sed_remapper = SedAliasesRemapper(args.sed, args.old_dd, args.new_dd)
    except ValidationError as err:
        print "Validation failed: %s" % err
        return ExitCode.validation_error

    sed_remapper.start()


if __name__ == '__main__':
    sys.exit(main())
