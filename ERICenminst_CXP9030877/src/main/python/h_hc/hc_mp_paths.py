"""
Healthcheck script for multipath paths
"""
# ********************************************************************
# Ericsson LMI SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2019 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : hc_mp_paths.py
# Purpose : The purpose of this script is to verify that each node in the
# deployment has 4 paths per each HBA controller, and also that no paths are
# disabled.
# ********************************************************************
from h_logging.enminst_logger import init_enminst_logging
import re
from collections import defaultdict

DMP_HDR_INFSCL = "NAME         STATE[A]   PATH-TYPE[M] DMPNODENAME  "\
                 "ENCLR-NAME   CTLR           ATTRS      PRIORITY"

DMP_HDR_VCS = "NAME         STATE[A]   PATH-TYPE[M] DMPNODENAME  "\
           "ENCLR-NAME   CTLR   ATTRS"

MP_REQUIREMENTS = {
    'vnx': {'paths_per_hba': 4,
            'number_of_hbas': 2
            },
    'unity': {'paths_per_hba': 3,
              'number_of_hbas': 2
              },
}


class MPpathsHealthCheck(object):  # pylint: disable=R0903
    """
    Class containing health check for model deployment
    """

    def __init__(self, verbose=False, deployment_type='vnx',
                 fc_switches='true'):
        self.logger = init_enminst_logging(logger_name='enmhealthcheck')
        self.verbose = verbose
        self.deployment_type = deployment_type
        self.fc_switches = fc_switches

    def process_dmp_paths_node_output(
        self, node, output, mp_config, mco_dsk_fct):
        """
        Get DMP command output and determine if all the nodes have the required
        number of paths on all disks for each controller
        :param node: node hostname
        :type node: str
        :param output: command output related to that node
        :type output: str
        :param mp_conf: mpath names from multipath binding config
        :type mp_conf: str
        :param mco_fct_dsk: disk list from mco facts.yaml and
                            dev_mapper list (ls -l /dev/mapper)
        :type mco_fct_dsk: str
        :return: bool
        """
        if not output:
            return
        hdl_line = output.split('\n')[0]
        is_db_node = any([hdl_line == hdr
                          for hdr in (DMP_HDR_INFSCL, DMP_HDR_VCS)])
        errors = False

        if is_db_node:
            # use Veritas MP
            node_metadata = self._create_dbnode_dmp_metadata(node, output)
            errors = self._process_node_mp_metadata(node, 'DB', node_metadata)
        else:
            # use Linux MP
            node_metadata = self._create_non_dbnode_mp_metadata(node, output)
            errors = self._process_node_mp_metadata(
                node, 'non-DB', node_metadata) or \
                self._check_mco_facts_mpath_disks(node, mp_config, mco_dsk_fct)
        return errors

    def _create_dbnode_dmp_metadata(self, node, lines):
        """
        Create multipath information for a DB node based on the command output.
        This is a sample Vcs output:
NAME  STATE[A]   PATH-TYPE[M] DMPNODENAME  ENCLR-NAME  CTLR  ATTRS
==========================================================================
sdaa  ENABLED    SECONDARY     emc_clariion0_11 emc_clariion0 c0  -
sdo   ENABLED(A) PRIMARY       emc_clariion0_11 emc_clariion0 c0  -
sdw   DISABLED(M) SECONDARY    emc_clariion0_93 emc_clariion0 c0  -
        This is a sample Infoscale output:
NAME  STATE[A]   PATH-TYPE[M] DMPNODENAME  ENCLR-NAME  CTLR  ATTRS   PRIORITY
==============================================================================
sdaj  ENABLED(A) Active/Optimized(P)  emc_clariion0_23 emc_clariion0 c0 -  -
sdax  ENABLED    Active/Non-Optimized emc_clariion0_23 emc_clariion0 c2 -  -
sdbi  ENABLED(A) Active/Optimized(P)  emc_clariion0_23 emc_clariion0 c0 -  -
sdbv  ENABLED(A) Active/Optimized(P)  emc_clariion0_23 emc_clariion0 c2 -  -
sdcl  ENABLED(A) Active/Optimized(P)  emc_clariion0_23 emc_clariion0 c2 -  -
        :param lines: list with the command output (one line per position)
        :type lines: list
        """
        if self.verbose:
            self.logger.info("Creating MP metadata from {0}\n{1}"
                             .format(node, lines))
        # something like d['emc_clariion0_93']['c0']['enabled'] = [sdai, sdau]
        data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        # remove two header lines
        for line in (l for l in lines.split('\n')[2:] if l):
            tokens = line.split()
            # vxdmpadm getsubpaths output varies between Vcs and Infoscale
            # 7 columns from Vcs
            # 8 columns (Priority added) from Infoscale
            if 5 <= len(tokens):
                dev_name = tokens[0]
                state = tokens[1]
                disk = tokens[3]
                ctlr = tokens[5]

                if state.lower().startswith('enabled'):
                    data[disk][ctlr]['enabled'].append(dev_name)
                else:
                    data[disk][ctlr]['disabled'].append(dev_name)
        return data

    def _create_non_dbnode_mp_metadata(self, node, lines):
        """
        Create multipath information for a non-DB node based on the
        command output. This is a sample output example:
mpathc (36006016007b038001502f409ed11e911) dm-0 DGC,VRAID
size=50G features='2 queue_if_no_path' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:1 sdh 8:112 active ready running
| `- 0:0:3:1 sdk 8:160 active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:0:1 sdb 8:16  failed ready running
  `- 0:0:1:1 sde 8:64  active ready running
        :param lines: list with the command output (one line per position)
        :type lines: list
        """
        # elements in data look like d[long_wwid]['0']['enabled'] = [sdai,sdau]
        if self.verbose:
            self.logger.info("Creating MP metadata from {0}\n{1}"
                             .format(node, lines))
        data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        current_wwid = ""
        for line in lines.split('\n'):
            line = (' '.join(line.split()))
            # does not start with | or `, then it is a header line
            if not re.search(r"^(\|)|(\`)", line):
                if line.strip().startswith("size="):
                    # this header line has no relevant info
                    continue
                # the other header line can have the following 3 formats
                # (1) action alias (wwid) more irrelevant things
                # (2) alias (wwid) more irrelevant things
                possible_header1 = r"^.+ \(([0-9a-fA-F]{16,33})\)"
                # (3) wwid more irrelevant things
                possible_header2 = r"^([0-9a-fA-F]{16,33})"
                for header in (possible_header1, possible_header2):
                    if re.search(header, line):
                        current_wwid = re.search(header, line).groups()[0]
            else:
                # if line starts with policy= there's nothing to count. It
                # identifies a path group, but we are only interested in actual
                # path count
                if 'policy=' in line:
                    continue
                # device_name will contain sdb in example below
                # the first digit indicates the controller
                # | `- 6:0:0:0 sdb 8:16  active ready  running
                device_match = re.search(r"(\d+)(?::\d+){3} (\S+)", line)
                device_name = ""
                ctlr = ""
                if device_match and len(device_match.groups()) == 2:
                    ctlr = device_match.groups()[0]
                    device_name = device_match.groups()[1]
                if not device_name:
                    self.logger.warning("Could not find device or controller "
                        "in {0}. This could affect the HC result".format(line))
                # split between active and failed paths
                if 'active ready' in line:
                    data[current_wwid][ctlr]['enabled'].append(device_name)
                else:
                    data[current_wwid][ctlr]['disabled'].append(device_name)
        return data

    def _process_node_mp_metadata(self, node, node_type, node_metadata):
        """
        Process node metadata and determine if all the paths in the node are
        correct. Return 'True' if errors exist.
        :param node: node hostname
        :type node: str
        :param node_type: usually, DB or non-DB
        :type node_type: str
        :param node_metadata: dictionary with the MP node metadata
        :type node_metadata: dict
        :return: bool
        """
        path_number_errors = False
        err_disabled = "ERROR: {0} node {1} has {2} disabled paths [{3}] on"\
                    " disk {4} and controller {5}{6}"
        err_enabled = "ERROR: {0} node {1} has {2} enabled paths "\
                    "({3} expected), [{4}], on disk {5} and controller {6}"
        if self.deployment_type == "unity" and self.fc_switches == "false":
            MP_REQUIREMENTS[self.deployment_type]['paths_per_hba'] = 1
        paths_per_hba = MP_REQUIREMENTS[self.deployment_type]['paths_per_hba']
        for dev in node_metadata:
            for ctlr in node_metadata[dev]:
                if node_metadata[dev][ctlr].get('disabled'):
                    unity_msg = ""
                    if self.deployment_type == "unity":
                        unity_msg = (". This can be OK for Unity "
                                        "deployments if a minimum of %d paths "
                                        "are enabled" % paths_per_hba)
                    self.logger.info(err_disabled.format(node_type, node,
                        len(node_metadata[dev][ctlr]['disabled']),
                        ','.join(node_metadata[dev][ctlr]['disabled']),
                        dev, ctlr, unity_msg))
                if node_metadata[dev][ctlr].get('enabled') and\
                    len(node_metadata[dev][ctlr]['enabled']) < paths_per_hba:
                    expected_msg = 4
                    if self.deployment_type == "unity":
                        expected_msg = "minimum of %d" % paths_per_hba
                    self.logger.error(err_enabled.format(node_type, node,
                        len(node_metadata[dev][ctlr]['enabled']), expected_msg,
                        ', '.join(node_metadata[dev][ctlr]['enabled']),
                        dev, ctlr))
                    path_number_errors = True
        controller_number_errors = self._check_all_controllers_used(
            node, node_type, node_metadata
        )
        return path_number_errors or controller_number_errors

    def _check_all_controllers_used(self, node, node_type, node_metadata):
        """
        Checks that the nodes have a number of HBAs used
        :param node: node hostname
        :type node: str
        :param node_type: usually, DB or non-DB
        :type node_type: str
        :param node_metadata: dictionary with the MP node metadata
        :type node_metadata: dict
        :return: bool
        """
        has_errors = False
        err_msg = "ERROR: {0} node {1} has paths to disk {2} "\
                  "on {3} of expected {4} controllers"
        hba_number = MP_REQUIREMENTS[self.deployment_type]['number_of_hbas']
        for dev in node_metadata:
            if len(node_metadata[dev]) < hba_number:
                self.logger.error(err_msg.format(node_type,
                                                 node,
                                                 dev,
                                                 len(node_metadata[dev]),
                                                 hba_number)
                                  )
                has_errors = True
        return has_errors

    def _check_mco_facts_mpath_disks(self, node, mp_conf, mco_fct_dsk):
        """
        Checks that the nodes have mco facts with the proper mpath name
        according to multipath friendly name config
        :param node: node hostname
        :type node: str
        :param mp_conf: mpath names from multipath binding config
        :type mp_conf: str
        :param mco_fct_dsk: disk list from mco facts.yaml and
                            dev_mapper list (ls -l /dev/mapper)
        :type mco_fct_dsk: str
        :return: bool
        """
        self.logger.info("Checking multipath map for mco facts on node {0}."
                            .format(node)
                        )
        mco_mp_ls = []
        has_errors = False
        err_msg = "ERROR: node {0} has mco facts missing"\
                     " multipath mapper to {1}.\n\n"\
                     "mco facts:\n{2}"
        for line in mco_fct_dsk.split('\n'):
            mco_mp_ls.extend(
                    (re.findall('^..disk_.*_dev.*mpath.$', line))
                    )
            if re.search('^dev_mapper_list', line):
                break

        for line in mp_conf.split('\n'):
            if any(line in mpath for mpath in mco_mp_ls):
                #mpath "mpath" found
                if self.verbose:
                    self.logger.info("MP friendly name {0} found"\
                        " on mco facts.".format(line))
            else:
                #mpath "mpath" not found
                self.logger.error(err_msg.format(node, line, mco_fct_dsk))
                has_errors = True
                break

        return has_errors
