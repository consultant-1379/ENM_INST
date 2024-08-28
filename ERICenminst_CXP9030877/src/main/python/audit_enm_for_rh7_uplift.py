# pylint: disable=C0302
#!/usr/bin/python
"""
ENM model auditor for RHEL 7.x uplift.
"""
# CXP 9042174
######################################################################
# COPYRIGHT Ericsson AB 2021
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
######################################################################

import os
import sys
import time
import hashlib
import platform
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from argparse import ArgumentParser, RawTextHelpFormatter
from ConfigParser import ConfigParser, Error


class EnmAuditForUplift(object):
    """
    ENM model auditor for RHEL 7.x uplift.
    """

    this_script = 'audit_enm_for_rh7_uplift.py'

    COLOR_RED = '\033[91m'
    COLOR_GREEN = '\033[92m'
    COLOR_YELLOW = '\033[93m'
    COLOR_BLUE = '\033[94m'
    END_COLOR = '\033[0m'

    CMD_TIMEOUT = 600

    RHEL_SANTIAGO = '6.10'

    namespace = '{http://www.ericsson.com/litp}'

    itemtypes = ['firewall-rule', 'package', 'alias',
                 'user', 'group',
                 'ntp-service', 'ntp-server',
                 'sysparam', 'logrotate-rule',
                 'dns-client', 'nameserver',
                 'eth', 'bond', 'bridge', 'vlan']

    removable_itypes = ['model-package']

    model_file1 = os.path.join(os.sep, 'opt', 'ericsson', 'enminst',
                               'runtime', 'enm_deployment.xml')
    model_file2 = os.path.join(os.sep, 'tmp', 'exported_model.xml')

    risk_categories = ['High', 'Medium', 'Low']
    unknown_category = 'Unknown'

    arguments = ['--help', '--verbose']

    log_msg_preamble = 'Custom items of ItemType'

    reportfile = 'rh7_uplift_audit.log'

    remove_scriptlet = 'audit_enm_for_rh7_uplift.remove_items'

    class Timeout(object):
        """
        Class to manage a timer/timeout
        """
        def __init__(self, seconds):
            """
            Initialise a new Timeout
            :param seconds: Seconds for which this Timeout should run
            :type seconds: int
            """
            self._wait_for = seconds
            self._start_time = EnmAuditForUplift.Timeout.get_cur_time()

        @staticmethod
        def get_cur_time():
            """
            Get the current (integer) time
            :return: Current time
            :rtype: int
            """
            return time.time()

        @staticmethod
        def take_a_nap(secs):
            """
            Nap/sleep for a fixed time
            :param secs: nap interval
            :type secs: int
            :return: None
            """
            time.sleep(secs)

        def has_time_elapsed(self):
            """
            Check if the maximum Timeout time has elapsed
            :return: Boolean True if Timeout seconds have elapsed
            """
            return self.get_time_elapsed() >= self._wait_for

        def get_time_elapsed(self):
            """
            Get the time difference between now and start of Timeout
            :return: Time difference
            :rtype: int
            """
            return int(EnmAuditForUplift.Timeout.get_cur_time() -
                       self._start_time)

        def get_remaining_time(self):
            """
            Get the time remaining in this Timeout
            :return: Time remaining
            :rtype: int
            """
            return int(self._wait_for - self.get_time_elapsed())

    def __init__(self):
        self.cleanup_required = True
        self.gen_reportfile = True
        self.all_inherit_types = []
        self.srcs_ref_counts = {}
        self.models_yum_repo_rpmnames = None
        self.removable_items = None

        self.do_cleanup()
        EnmAuditForUplift._export_model(EnmAuditForUplift.model_file2)

    @staticmethod
    def _run_command(cmd, timeout_secs=CMD_TIMEOUT):
        """
        Thin wrapper to call subprocess.Popen
        :param cmd: Command string to execute
        :type cmd: string
        :param timeout_secs: seconds to wait before timing out cmd
        :type timeout_secs: integer
        :return: returncode, STDOUT text
        :rtype: 2-tuple: int, string
        """

        stdout = ''
        proc = None

        timeout = EnmAuditForUplift.Timeout(timeout_secs)

        try:
            proc = subprocess.Popen(cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    shell=True)
        except OSError as oe_err:
            msg = ('Error processing command {0}, {1}, {2}\n'
                   .format(cmd, oe_err.errno, oe_err.strerror))
            sys.stderr.write(msg)
            sys.exit(1)

        while proc.poll() is None and not timeout.has_time_elapsed():
            timeout.take_a_nap(0.5)

        if proc.poll() is None and timeout.has_time_elapsed():
            msg = 'Command timed out, {0}\n'.format(cmd)
            sys.stderr.write(msg)
            sys.exit(1)

        stdout, _ = proc.communicate()
        cleaned_stdout = stdout.strip()

        return proc.returncode, cleaned_stdout

    @staticmethod
    def print_help_text():
        """
        Print help text
        :return: None
        """

        logs = [EnmAuditForUplift.reportfile + '.' + category.lower()
                for category in (EnmAuditForUplift.risk_categories +
                                 [EnmAuditForUplift.unknown_category])]
        cats = ','.join([cat.lower()
                         for cat in (EnmAuditForUplift.risk_categories +
                                     [EnmAuditForUplift.unknown_category])])

        cmd_tmplt = ("for vpath in $(grep '{lm_preamble}' {{filename}} | "
                     "awk -F':' '{{{{print $2}}}}'); "
                     "do litp show -p ${{{{vpath}}}}; done").format(
                                lm_preamble=EnmAuditForUplift.log_msg_preamble)
        cmd_eg = cmd_tmplt.format(filename='<log-filename>')
        cmd_hi = cmd_tmplt.format(filename=logs[0])
        cmd_all = ('for file in {reportfile}.{{{cats}}}; ' +
                   'do if [ -f ${{file}} ]; then ' +
                   cmd_tmplt + '; fi; done').format(
                       reportfile=EnmAuditForUplift.reportfile,
                       cats=cats, filename='${file}')

        txt = \
"""
{script} [{arg_verbose}] [{arg_help}]

Audit script = {script}
Intermediate XML file = {exported_xml}
Log file = {default_log}
Generated scriptlet = {remove_script}

Steps:

 1. Copy the audit script to the {lms} to a location of your
    choice, preferably /tmp/. Take note of the {cwd}.
 2. Run the script using the python interpreter or directly as an executable.
    If running the script as an executable, ensure that the script has the
    correct execute permissions. Run the following command if the permissions
    are not correct:
      chmod +x {script}
 3. Run the audit script, preferably as "root" user or else using a suitable
    "sudo" equivalent with one of the following:
      python {script}  or
      ./{script}
 4. The script begins by exporting the current "live" ENM model (including
    customizations) to the intermediate XML file.
 5. The script loads and parses that exported ENM model available in the
    intermediate XML file.
 6. The script loads and parses the default ENM deployment description
    (without customizations) located at
      <{lms}>:{default_xml}
 7. The script determines the differences between the two XML files. By
    default, the script filters the differences by ~15 ItemTypes. If the
    '{arg_verbose}' parameter is passed to the script, no filtering is applied,
    but differences are categorized as {red}high{no_color}, \
{yellow}medium{no_color} or {green}low{no_color} risk.
 8. The script output is printed to the screen. In default mode, output is also
    written to the log file in the {cwd}. In verbose
    mode, each category of output is written to a dedicated file, such as
      {log0},
      {log1},
      {log2}, and
      {log3} (unknown risk category for these items)
 9. At the end of the execution, the script deletes the intermediate XML file.
10. The output identifies ItemTypes on the left-hand side, and a
    space-separated list of item vpaths on the right-hand side.
11. To view the full detail of each item, use this command for each or \
any vpath:
      litp show -p <vpath>
12. Use the following helpful command to show all items in the \
{cwd}:
      {cmd_eg}
    Example 1. "show" each high risk item:
      {cmd_hi}
    Example 2. "show" all items:
      {cmd_all}
13. Certain {red}high risk{no_color} legacy items, known to be safe to \
remove, will be added to
    a scriptlet {remove_script} in the {cwd}
    to cleanup the ENM model. Where the scriptlet {remove_script}
    was created, it must be run using:
      sh {remove_script}
14. After running the scriptlet {remove_script}, re-run the audit script,
    as before, to assess any remaining {red}high risk{no_color} items.

Suggestions:

   I: Read this entire help text. Use the "litp show" command examples to fully
      view and understand the custom items.
  II: All custom items are site-specific and their exact content and makeup
      is known to site personnel only.
 III: Items listed as {green}low in risk{no_color} are shown here for \
completeness and do not require
      any action. They will be automatically reapplied on the target \
RHEL {os_ver} uplifted deployment.
  IV: Items listed as {yellow}medium risk{no_color} do not pose a problem for \
the uplift procedure,
      but should be reviewed nonetheless. Remove any item no longer required.
   V: Items listed as {red}high in risk{no_color} require most attention as \
their presence in
      the ENM model jeopardize the RHEL {os_ver} uplift and could cause the \
uplift to fail.
  VI: Items listed as {blue}unknown in risk{no_color} may be legacy items no \
longer known to
      ENM and cannot be categorized.
 VII: Assess each {red}high risk{no_color} item as follows:
     i. Does the item remain relevant or can it be removed?
    ii. Is the item safe to be applied on a RHEL {os_ver} platform?
   iii. Where the item references a software artifact, is a RHEL {os_ver} \
artifact
        available and has it been verified?
    iv. Where a RHEL {os_ver} test or lab environment is available, apply \
the item
        there to confirm no risk to the ENM uplift procedure.
VIII: Where a {red}high risk{no_color} item has been evaluated as safe for
      inclusion in the RHEL {os_ver} uplift procedure, then keep the item in
      the ENM model and it will be automatically reapplied on the target
      RHEL {os_ver} uplifted deployment.
  IX: Where the scriptlet {remove_script} was created in the
      {cwd}, the scriptlet must be run to remove unwanted
      {red}high risk{no_color} known items, using:
          sh {remove_script}

For more information, contact your local Ericsson support team.
""".format(script=EnmAuditForUplift.this_script,
           lms='LITP Management Server',
           cwd='current working directory',
           default_xml=EnmAuditForUplift.model_file1,
           exported_xml=EnmAuditForUplift.model_file2,
           default_log=EnmAuditForUplift.reportfile,
           log0=logs[0], log1=logs[1], log2=logs[2], log3=logs[3],
           arg_help=EnmAuditForUplift.arguments[0],
           arg_verbose=EnmAuditForUplift.arguments[1],
           cmd_eg=cmd_eg, cmd_hi=cmd_hi, cmd_all=cmd_all, os_ver='7.9',
           red=EnmAuditForUplift.COLOR_RED,
           yellow=EnmAuditForUplift.COLOR_YELLOW,
           green=EnmAuditForUplift.COLOR_GREEN,
           blue=EnmAuditForUplift.COLOR_BLUE,
           no_color=EnmAuditForUplift.END_COLOR,
           remove_script=EnmAuditForUplift.remove_scriptlet)
        return txt

    @staticmethod
    def _export_model(model_filename):
        """
        Export current LITP model to file.
        :param model_filename: Output model filename.
        :type model_filename: string
        :return: None
        """
        cmd = 'litp export -p / -f {0}'.format(model_filename)
        msg = "Running command: {0}\n".format(cmd)
        sys.stdout.write(msg)
        EnmAuditForUplift._run_command(cmd)

    @staticmethod
    def _get_rtd_13032_ndm_rpm_names():
        """
        Get the RTD-13032 Non-Deployed Model RPM names.
        :return: list of RPM names
        :rtype: list
        """
        shortnames = ['sbgmodel16a_CXP9032973',
                      'rnnodenodemodel_CXP9034439',
                      'mediationvbgfnodemodel16a_CXP9033470',
                      'mediationsapcnodemodel17a_CXP9033758',
                      'mediationsapcnodemodel16b_CXP9033230',
                      'mediationmgwnodemodel17a_CXP9033711',
                      'mediationmgwnodemodel16b_CXP9032435',
                      'mediationmgwnodemodel16a_CXP9032454',
                      'mediationmgwnodemodel15b_CXP9032455',
                      'mediationmgwnodemodel14b_CXP9032714',
                      'cscfnodemodel16a_CXP9032940',
                      'radiotnodenodemodel17a_CXP9032894',
                      'radiotnodenodemodel16b_CXP9032892',
                      'radiotnodenodemodel16a_CXP9032891',
                      'radionodenodemodel17b_CXP9033720',
                      'radionodenodemodel17a_CXP9032950',
                      'radionodenodemodel16b_CXP9032534',
                      'pmicservicesubepgvepglegacymodel_CXP9033287',
                      'mtasnodemodel16a_CXP9032938',
                      'mediationsapcnodemodel16a_CXP9032890',
                      'identitymgmtsecuritymodel_CXP9034655',
                      'hpenfvdirmediationconfig_CXP9035659',
                      'cppinventoryflow_CXP9030621',
                      'vrsmnodemodelcommon_CXP9036242',
                      'vrsmnodemodel_CXP9036241',
                      'vrmnodemodelcommon_CXP9035588',
                      'mediationvrcnodemodel17b_CXP9033870',
                      'mediationvrcnodemodel17a_CXP9033064',
                      'mediationvppnodemodel17b_CXP9033868',
                      'mediationvppnodemodel17a_CXP9033067',
                      'vrmnodemodel_CXP9035583',
                      'mediationrnnodenodemodelcommon_CXP9033259',
                      'mediationrnnodenodemodel17b_CXP9033869',
                      'mediationrnnodenodemodel17a_CXP9033294',
                      'mediationvepgnodemodel16b_CXP9032866',
                      'mediationvepgnodemodel16a_CXP9032867',
                      'mediationepgnodemodel16b_CXP9032868',
                      'mediationepgnodemodel16a_CXP9032869',
                      'mediationbscnodemodel17b_CXP9033541',
                      'bscpmmediationhandlermodels_CXP9034198',
                      'bscpmmediationflowmodel_CXP9034199',
                      'bscfmmediationhandlers_CXP9034203',
                      'mgwtransportcimmedflowmodel_CXP9037253',
                      'bscpocned_CXP9033388',
                      'bscpocmodels_CXP9033387',
                      'mediationbscnodemodel17b_CXP9033541',
                      'mediationbscnodemodel17b_CXP9033541',
                      'bscpocned_CXP9033388',
                      'mediationrnnodenodemodel17a_CXP9033294',
                      'mediationrnnodenodemodel17b_CXP9033869',
                      'mediationvppnodemodel17a_CXP9033067',
                      'mediationvppnodemodel17b_CXP9033868',
                      'mediationvrcnodemodel17a_CXP9033064',
                      'mediationvrcnodemodel17b_CXP9033870']
        return ['ERIC{0}'.format(sname) for sname in shortnames]

    @staticmethod
    def _get_ext_classpaths():
        """
        Get model-extension classpaths
        :return: list of model-extension class paths
        :rtype: list
        """
        classpaths = []
        conf_dir = os.path.join(os.sep, 'opt', 'ericsson', 'nms',
                                'litp', 'etc', 'extensions')
        for conf_file in os.listdir(conf_dir):
            if conf_file.endswith(".conf"):
                conf = ConfigParser()
                conf.read(os.path.join(conf_dir, conf_file))
                try:
                    classpaths.append(conf.get('extension', 'class'))
                except Error as err:
                    msg = "Error while parsing config file {0}\n".format(err)
                    sys.stderr.write(msg)
                    raise

        return classpaths

    @staticmethod
    def _get_ext_itemtypes(classpaths):
        """
        Get model-extension ItemType definitions
        :param classpaths: model-extension classpaths
        :type classpaths: list
        :return: list of model-extension ItemTypes
        :rtype: list
        """
        itemtypes = []
        for classpath in classpaths:
            parts = classpath.split('.')
            klassname = parts[-1]
            modules = '.'.join(parts[:-1])
            module = __import__(modules, fromlist=[klassname])
            klass = getattr(module, klassname)

            itemtypes.extend(klass().define_item_types())

        return itemtypes

    # pylint: disable=C0103,W0703
    def get_all_inherit_itemtypes(self):
        """
        Get all ItemTypes that may be used for inheritance,
        including their extensions.
        :rtype: list of strings
        :return: list of inheritable ItemTypes
        """

        def _flatten_extends_tree(long_list, etype1, etypes):
            """
            Flatten a hierarchy tree of extension
            :param long_list: flattened extends list
            :type long_list: list
            :param etype1: extend type
            :type etype1: string
            :param etypes: dict of extends
            :type etypes: dict
            :return: None
            """
            long_list.append(etype1)
            if etype1 in etypes.keys():
                long_list.extend(etypes[etype1])
                for etype2 in etypes[etype1]:
                    _flatten_extends_tree(long_list, etype2, etypes)

        try:
            itemtypes = EnmAuditForUplift._get_ext_itemtypes(
                                       EnmAuditForUplift._get_ext_classpaths())

            inherit_types = set()
            extends = defaultdict(list)
            for itype in itemtypes:
                if itype.extend_item:
                    extends[itype.extend_item].append(itype.item_type_id)

                itype_inherit_types = \
                    set([ftype.item_type_id
                         for ftype in itype.structure.itervalues()
                         if ftype.__class__.__name__ in
                                               ('Reference', 'RefCollection')])
                inherit_types = set.union(inherit_types, itype_inherit_types)

            all_inherit_types = []
            for rtype in inherit_types:
                _flatten_extends_tree(all_inherit_types, rtype, extends)

            self.all_inherit_types = list(set(all_inherit_types))
        except Exception as err:
            print ("Failed to discover model-extensions " +
                    "and inheritable ItemTypes: {0}".format(err))
            # If all above type discovery goes wrong,
            # use these as backstop ItemTypes
            bt = ['blade', 'blade-rack', 'cobbler-service', 'config-manager',
                  'consulserver', 'dhcp-service', 'dhcp6-service',
                  'elasticsearch', 'file-system', 'file-system-base',
                  'hyperic-agent', 'hyperic-server', 'libvirt-provider',
                  'libvirt-system', 'managed-file', 'managed-file-base',
                  'managed-file-list', 'model-deployment-tool-package',
                  'model-deployment-tool-plugin-package', 'model-package',
                  'ms-service', 'mysql-server', 'neo4j-service', 'nfs-mount',
                  'ntp-service', 'opendj-service', 'os-profile', 'package',
                  'package-list', 'postgresql-service', 'route', 'route-base',
                  'route6', 'service', 'service-base', 'sfs-filesystem',
                  'software-item', 'storage-profile', 'storage-profile-base',
                  'system', 'system-provider', 'versant-database-service',
                  'versant-service', 'vm-service', 'yum-repository']
            self.all_inherit_types = bt

    @staticmethod
    def _gen_itype_name(itemtype):
        """
        Generate an ItemType name, complete with namespace.
        :param itemtype: ItemType base name.
        :type itemtype: string
        :return: Fully qualified ItemType name.
        :rtype: string
        """
        return '{0}{1}'.format(EnmAuditForUplift.namespace, itemtype)

    @staticmethod
    def _encode_item(element_tag, vpath):
        """
        Encode XML element tag and item vpath
        :param element_tag: XML element tag ie ItemType
        :type element_tag: string
        :param vpath: item LITP vpath
        :type vpath: string
        :return: encoded representation of tag and vpath
        :rtype: string
        """
        itype = element_tag[len(EnmAuditForUplift.namespace):]
        return '{0}::{1}'.format(itype, vpath)

    @staticmethod
    def _decode_item(entry):
        """
        Decode representation of XML tag and vpath
        :param entry: encoded representation
        :type entry: string
        :return 2-tuple ItemType and vpath
        :rtype: 2-tuple (string, string)
        """
        (itype, vpath) = entry.split('::', 2)
        return itype, vpath

    # pylint: disable=R0913
    def _iter_by_itype(self, element, itype, vpath, it_items, ref_counts):
        """
        Iterate by recursing over XML elements,
        identifying items by ItemType.
        :param element: Current XML element
        :type element: ``xml.etree.ElementTree.Element``
        :param itype: ItemType
        :type itype: string
        :param vpath: LITP vpath [suffix]
        :type vpath: string
        :param it_items: Cumulative set of items
        :type it_items: set
        :param ref_counts: reference counts by vpath
        :type ref_counts: dict
        :return: None
        """
        if (not element.tag or
            not element.tag.startswith(EnmAuditForUplift.namespace)):
            return

        full_path = vpath
        element_id = element.get('id')
        if element_id:
            full_path = vpath + '/' + element_id

        if ref_counts != None:
            element_src = element.get('source_path')
            if element_src:
                if element_src not in ref_counts.keys():
                    ref_counts[element_src] = 0
                ref_counts[element_src] += 1

        if itype:
            if element.tag == EnmAuditForUplift._gen_itype_name(itype):
                it_items.add(full_path)
        else:
            it_items.add(EnmAuditForUplift._encode_item(element.tag,
                                                        full_path))

        for child in element.getchildren():
            self._iter_by_itype(child, itype, full_path, it_items, ref_counts)

    @staticmethod
    def _get_xml_root(xml_file):
        """
        Get root element for XML document
        :param xml_file: XML file absolute path
        :type xml_file: string
        :return: Root XML element
        :rtype: ``xml.etree.ElementTree.Element``
        """
        if not os.path.exists(xml_file):
            msg = 'File "{0}" does not exist\n'.format(xml_file)
            sys.stderr.write(msg)
            sys.exit(1)

        msg = "Processing {0} ...\n".format(xml_file)
        sys.stdout.write(msg)

        tree = ET.parse(xml_file)
        return tree.getroot()

    def _process_xml_file(self, xml_file):
        """
        Process an XML [model] file, by parsing and extracting item vpaths.
        :param xml_file: XML file absolute path
        :type xml_file: string
        :return: dictionary keyed on ItemType, values are sets of item vpaths.
        :rtype: dict
        """
        root = EnmAuditForUplift._get_xml_root(xml_file)

        model_data = {}

        for itype in EnmAuditForUplift.itemtypes:
            it_items = set()
            for child in root.getchildren():
                self._iter_by_itype(child, itype, '', it_items, None)
            if it_items:
                model_data[itype] = it_items

        return model_data

    def do_cleanup(self):
        """
        Perform [file] cleanup; delete model_file2
        :return: None
        """
        fname = EnmAuditForUplift.model_file2

        if self.cleanup_required:
            if os.path.exists(fname):
                try:
                    os.remove(fname)
                except (OSError, IOError) as ex:
                    if 2 != ex.errno:
                        msg = "Failed to remove file: {0}\n".format(fname)
                        sys.stderr.write(msg)

    def _get_all_custom_items(self):
        """
        Get all custom items (ie no filtering)
        :return: set of custom items
        :rtype: set
        """
        all_items = []

        for (mfile, ref_counts) in \
                       ((EnmAuditForUplift.model_file2, self.srcs_ref_counts),
                        (EnmAuditForUplift.model_file1, None)):
            root = self._get_xml_root(mfile)
            all_items.append(self._get_all_items(root, ref_counts))

        return all_items[0] - all_items[1]

    def _get_all_items(self, root_element, ref_counts):
        """
        Get all children XML elements / item from a given XML root
        :param root_element: XML doc root element
        :type root_element: ``xml.etree.ElementTree.Element``
        :param ref_counts: reference counts by vpath
        :type ref_counts: dict
        :return: complete set of items in XML "tree"
        :rtype: set
        """
        items = set()
        for child in root_element.getchildren():
            self._iter_by_itype(child, None, '', items, ref_counts)
        return items

    def _hndl_removable_item(self, itype, vpath):
        """
        Handle removable item
        :param itype: ItemType
        :type itype: string
        :param vpath: Item vpath
        :type vpath: string
        :return: None
        """

        if not self.removable_items:
            self.removable_items = set()

        if EnmAuditForUplift.removable_itypes[0] == itype:
            self._hndl_model_pkg(vpath)

    def _hndl_model_pkg(self, vpath):
        """
        Handle removal of a model-package item
        :param vpath: Item vpath
        :type vpath: string
        :return: None
        """

        cmd = 'litp show -p {0} -o name'.format(vpath)
        _, rpmname = self._run_command(cmd)

        # Category 1: vpath RPM is a RTD-13032 NDM
        # Category 2: vpath RPM is in ENM_models yum repo
        if rpmname and \
           (rpmname in EnmAuditForUplift._get_rtd_13032_ndm_rpm_names() or \
            rpmname in self._get_models_yum_repo()):
            self.removable_items.add(vpath)

        # Categories 3+ not handled here.

    def _get_models_yum_repo(self):
        """
        Get the RPM names from the /var/www/html/ENM_models
        yum repository
        :return: list of RPM names (strings)
        :rtype: list

        """
        if not self.models_yum_repo_rpmnames:
            repo_path = os.path.join(os.sep, 'var', 'www',
                                     'html', 'ENM_models')
            if not os.path.exists(repo_path):
                msg = 'Folder "{0}" does not exist\n'.format(repo_path)
                sys.stderr.write(msg)
                sys.exit(1)

            for _, _, files in os.walk(repo_path):
                self.models_yum_repo_rpmnames = [filename.split('-')[0]
                                             for filename in files
                                             if filename.startswith('ERIC') and
                                             filename.endswith('.rpm')]
                break

        return self.models_yum_repo_rpmnames

    def process_removable_items(self):
        """
        Process removable items
        Iterate removable items and write scriptlet
        :return None
        """
        filename = EnmAuditForUplift.remove_scriptlet

        monitor = os.path.join(os.sep, 'opt', 'ericsson',
                               'enminst', 'bin', 'monitor_plan.sh')

        tmplt = ('#!/bin/bash\n' +
                 'set -x\n' +
                 '{removes}\n' +
                 'litp create_plan\n' +
                 'litp run_plan\n' +
                 monitor + '\n')

        remove_cmds = '\n'.join(['litp remove -p {0}'.format(vpath)
                                 for vpath in self.removable_items])
        txt = tmplt.format(removes=remove_cmds)

        try:
            with open(filename, 'w') as ofile:
                ofile.write(txt)
        except IOError:
            msg = 'Could not write to file {0}\n'.format(filename)
            sys.stderr.write(msg)
            sys.exit(1)

        cmd = 'chmod +x {0}'.format(filename)
        EnmAuditForUplift._run_command(cmd)

        msg = 'Created scriptlet to remove items: {0}\n'.format(filename)
        sys.stdout.write(msg)

    # pylint: disable=C0103
    @staticmethod
    def _get_itype_risk_categories():
        """
        Get risk categories for LITP ItemTypes
        :return: dict of categorized ItemTypes
        :rtype: dict
        """
        h = ['blade', 'blade-rack', 'bmc', 'cluster', 'consulserver', 'disk',
             'file-system', 'group', 'group-cluster-config',
             'group-node-config', 'hba', 'libvirt-provider', 'libvirt-system',
             'lun-disk', 'managed-file', 'managed-file-list',
             'model-deployment-tool-package',
             'model-deployment-tool-plugin-package',
             'model-package', 'ms-service', 'nfs-service', 'node', 'package',
             'package-list', 'physical-device', 'runtime-entity', 'san',
             'san-emc', 'sata-block-device', 'scsi-block-device', 'service',
             'sysparam', 'sysparam-node-config', 'system',
             'user', 'user-cluster-config', 'user-node-config', 'vcs-cluster',
             'vcs-clustered-service', 'vcs-network-host', 'vcs-trigger',
             'volume-group', 'yum-repository']

        m = ['clustered-service', 'deployable-entity', 'elasticsearch',
             'elasticsearch-option', 'elasticsearch-sysconfig-option',
             'jee-deployable-entity', 'lsb-runtime', 'mysql-database',
             'mysql-grant', 'mysql-override-option', 'mysql-server',
             'mysql-user', 'neo4j-config_entry', 'neo4j-server',
             'neo4j-service', 'network', 'opendj-service', 'os-profile',
             'postgresql-client', 'postgresql-config_entry',
             'postgresql-contrib', 'postgresql-database', 'postgresql-server',
             'postgresql-server-pg-hba-rule',
             'postgresql-server-pg-ident-rule', 'postgresql-server-role',
             'postgresql-server-schema', 'postgresql-server-table-grant',
             'postgresql-server-tablespace', 'postgresql-service',
             'postgresql-validate-db-connection', 'route', 'route6',
             'sfs-cache', 'sfs-export', 'sfs-filesystem', 'sfs-pool',
             'sfs-service', 'sfs-virtual-server', 'storage-container',
             'storage-profile']

        l = ['alias', 'alias-cluster-config', 'alias-node-config', 'bond',
             'bridge', 'cluster-config', 'cobbler-service', 'config-manager',
             'config-manager-property', 'dhcp-range', 'dhcp-service',
             'dhcp-subnet', 'dhcp6-range', 'dhcp6-service', 'dhcp6-subnet',
             'dns-client', 'eth', 'firewall-cluster-config',
             'firewall-node-config', 'firewall-rule', 'ha-config',
             'ha-service-config', 'hyperic-agent', 'hyperic-server',
             'logrotate-rule', 'logrotate-rule-config', 'nameserver',
             'nfs-mount', 'node-config', 'ntp-server', 'ntp-service',
             'profile', 'service-provider', 'software-item',
             'system-provider', 'vip', 'vlan', 'vm-alias',
             'vm-custom-script', 'vm-disk', 'vm-firewall-rule', 'vm-image',
             'vm-network-interface', 'vm-nfs-mount', 'vm-package',
             'vm-ram-mount', 'vm-service', 'vm-ssh-key', 'vm-yum-repo',
             'vm-zypper-repo']

        return {EnmAuditForUplift.risk_categories[0]: h,
                EnmAuditForUplift.risk_categories[1]: m,
                EnmAuditForUplift.risk_categories[2]: l}

    def categorize_custom_items(self):
        """
        Assign custom items into risk categories
        :return: Categorized custom items
        :rtype: dict
        """

        custom_items = self._get_all_custom_items()
        itype_risks = EnmAuditForUplift._get_itype_risk_categories()

        risk_categorized_items = {}
        for kategory in (EnmAuditForUplift.risk_categories +
                         [EnmAuditForUplift.unknown_category]):
            risk_categorized_items[kategory] = {}

        for citem in custom_items:

            (itype, vpath) = EnmAuditForUplift._decode_item(citem)

            if 'sshd-config' == itype or \
               'collection' in itype or \
               itype.endswith('-inherit'):
                continue

            if itype in EnmAuditForUplift.removable_itypes:
                self._hndl_removable_item(itype, vpath)

            if itype in self.all_inherit_types:
                rcount = 0
                if vpath in self.srcs_ref_counts.keys():
                    rcount = self.srcs_ref_counts[vpath]

                if rcount == 0:
                    continue

            categories = [rc for rc in EnmAuditForUplift.risk_categories
                          if itype in itype_risks[rc]]

            category = (categories[0] if 1 == len(categories)
                                      else EnmAuditForUplift.unknown_category)

            if not itype in risk_categorized_items[category].keys():
                risk_categorized_items[category][itype] = set()

            risk_categorized_items[category][itype].add(vpath)

        return risk_categorized_items

    def get_custom_items(self):
        """
        Get custom items, by processing two XML files,
        and set subtracting the item vpaths by ItemType.
        :return: dictionary keyed on ItemType, values are sets of item vpaths.
        :rtype: dict
        """
        model2_data = self._process_xml_file(EnmAuditForUplift.model_file2)
        model1_data = self._process_xml_file(EnmAuditForUplift.model_file1)

        custom_items = {}
        for itype in EnmAuditForUplift.itemtypes:
            if itype in model2_data.keys():
                if not itype in model1_data.keys():
                    citems = model2_data[itype]
                else:
                    citems = model2_data[itype] - model1_data[itype]
                if citems:
                    custom_items[itype] = citems

        return custom_items

    def _write_to_log_file(self, filename, text):
        """
        Write content to a log file
        :param filename: Log file absolute path
        :type filename: string
        :param text: Content for file
        :type text: string
        :return: None
        """
        if self.gen_reportfile and text:
            with open(filename, 'w') as report_fd:
                report_fd.write(text)

    @staticmethod
    def assert_rhel_version(expected_ver):
        """
        Assert the Platform is a specific version
        :param expected_ver: Expected RHEL OS version
        :type expected_ver: string
        :return: None
        """

        ver_names = {EnmAuditForUplift.RHEL_SANTIAGO: 'Santiago'}
                   # '7.9': 'Maipo'
                   # '8.0': 'Ootpa'

        if expected_ver not in ver_names.keys():
            msg = 'Unsupported Platform: {0}\n'.format(expected_ver)
            sys.stderr.write(msg)
            sys.exit(1)

        version = platform.dist()
        for idx, expected_val in enumerate(['redhat',
                                            expected_ver,
                                            ver_names[expected_ver]]):
            try:
                assert expected_val == version[idx]
            except AssertionError:
                msg = 'Unexpected Platform info: {0}\n'.format(version[idx])
                sys.stderr.write(msg)
                sys.exit(1)

    # pylint: disable=R0912
    def render_custom_items(self, custom_items, categorized=False):
        """
        Presentation: print/log the custom items.
        :param custom_items: dictionary keyed on ItemType,
                             values are sets of item vpaths.
        :type custom_items: dict
        :param categorized: boolean indicating if custom items are categorized
        :type categorized: bool
        :return: None
        """

        def _get_category_color(category):
            """
            Get visualization color for a risk category.
            :param category: risk category name
            :type category: string
            :return: color code
            :rtype: string
            """
            return dict(zip((EnmAuditForUplift.risk_categories +
                              [EnmAuditForUplift.unknown_category]),
                            [EnmAuditForUplift.COLOR_RED,
                             EnmAuditForUplift.COLOR_YELLOW,
                             EnmAuditForUplift.COLOR_GREEN,
                             EnmAuditForUplift.COLOR_BLUE]))[category]

        def _get_formatted_txt(itype, items):
            """
            Get formatted text for logging
            :param itype: ItemType
            :type itype: string
            :param items: LITP item vpaths
            :type items: list
            :return: formatted text for logging
            :rtype: string
            """
            return '{0} "{1}": {2}\n'.format(
                EnmAuditForUplift.log_msg_preamble, itype, ' '.join(items))

        no_citems_found_msg = 'No custom items found\n'
        text = ''

        if not categorized:
            for itype, items in custom_items.iteritems():
                if items:
                    text += _get_formatted_txt(itype, items)

            if not text:
                sys.stderr.write(no_citems_found_msg)
            else:
                sys.stdout.write(text)
                self._write_to_log_file(EnmAuditForUplift.reportfile, text)
        else:
            citems_found = False
            for category in (EnmAuditForUplift.risk_categories +
                             [EnmAuditForUplift.unknown_category]):
                if not custom_items[category]:
                    continue

                color = _get_category_color(category)
                text += '{0}{1}{2} risk items\n'.format(color, category,
                                                   EnmAuditForUplift.END_COLOR)

                ctext = ''
                for itype in sorted(custom_items[category].keys()):
                    citems_found = True
                    ctext += _get_formatted_txt(itype,
                                                custom_items[category][itype])

                text += ctext
                fname = EnmAuditForUplift.reportfile + '.' + category.lower()
                self._write_to_log_file(fname, ctext)

            if not citems_found:
                sys.stderr.write(no_citems_found_msg)
            else:
                sys.stdout.write(text)


def run_main(args):
    """
    Main auditing function.
    :return: None
    """

    abspath = os.path.abspath(__file__)
    digest = hashlib.md5(open(abspath, 'rb').read()).hexdigest()
    print "Signature: {0}".format(digest)

    parser = ArgumentParser(prog=EnmAuditForUplift.this_script,
                            epilog=EnmAuditForUplift.print_help_text(),
                            formatter_class=RawTextHelpFormatter)

    parser.add_argument('-v', '--verbose',
                        dest='verbose',
                        default=False,
                        action='store_true',
                        help='enable verbose auditing')

    processed_args = parser.parse_args(args[1:])

    EnmAuditForUplift.assert_rhel_version(EnmAuditForUplift.RHEL_SANTIAGO)

    auditor = EnmAuditForUplift()
    if getattr(processed_args, 'verbose', False):
        auditor.get_all_inherit_itemtypes()
        auditor.render_custom_items(auditor.categorize_custom_items(),
                                    categorized=True)
        if auditor.removable_items:
            auditor.process_removable_items()
    else:
        auditor.render_custom_items(auditor.get_custom_items())

    auditor.do_cleanup()


if __name__ == '__main__':
    run_main(sys.argv)
