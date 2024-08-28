# pylint: disable=E1103
"""
Class comparing LVs in grub.cfg with LVs in model
"""
##############################################################################
# COPYRIGHT Ericsson LMI 2023
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only with written
# permission from Ericsson LMI. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from h_litp.litp_rest_client import LitpRestClient
from h_puppet.mco_agents import EnminstAgent


class GrubConfCheck(object):
    """
    Class to handle grub.conf LVs check
    """

    def __init__(self):
        """
        Main grub.cfg LVs Health Checker constructor.
        """
        self.rest = LitpRestClient()
        self.enminst_agent = EnminstAgent()
        self.nodes = self.rest.get_cluster_nodes()
        self.lvs_report = []
        self.cluster_lv_enable_dict = self.cluster_lv_enable()
        self.grub_lvs_check_failed = False

    def cluster_lv_enable(self):
        """
        Function Description:
        Creates a dictionary contains all clusters and
        grub_lv_enable property status
        :return: dict
        """
        clusters_path = '/deployments/enm/clusters/'
        clusters = self.rest.get_children(clusters_path, verbose=False)
        cluster_lv_enable_dict = {}
        for cluster in clusters:
            _cluster_name = str(cluster['data']['id'])
            try:
                grub_lv_enable = str(cluster['data']['properties'][
                    'grub_lv_enable'])
            except KeyError:
                grub_lv_enable = 'false'
            cluster_lv_enable_dict[_cluster_name] = grub_lv_enable
        return cluster_lv_enable_dict

    def report_lvs(self):
        """
        Function Description:
        Creates a report for LVs in grub.cfg and LVs in the model
        :return: list of VG reports
        """
        for cluster, cluster_nodes in self.nodes.items():
            if self.cluster_lv_enable_dict[cluster] == 'true':
                for node in cluster_nodes.items():
                    node_hostname = str(node[1].get_property('hostname'))
                    node_name = str(node[0])
                    vgs_path = '/deployments/enm/clusters/{0}/nodes/{1}/' \
                        'storage_profile/volume_groups'.format(
                            cluster, node_name)
                    vgs = self.rest.get_children(vgs_path, verbose=False)
                    for _vg in vgs:
                        vg_report = self.handle_vg(node_hostname, str(cluster),
                                                   node_name, _vg)
                        self.lvs_report.append(vg_report)
            else:
                self.lvs_report.append({'Cluster': str(cluster), 'Node': '-',
                                        'VG': '-', 'Grub State': 'OK',
                                        'Missing LV': '-', 'Extra LV': '-'})
        return self.lvs_report

    def handle_vg(self, node_hostname, cluster, node_name, _vg):
        """
        Function Description:
        Handle each VG and produce a report
        :return:
        """
        vg_name = str(_vg.get('data').get('id'))
        vg_report = {'Cluster': cluster, 'Node': node_name,
                        'VG': vg_name}
        grub_conf_lvs = []
        for grub_lv in self.enminst_agent.get_grub_conf_lvs(
            node_hostname).split('\n'):
            if str(grub_lv).startswith(vg_name + '_'):
                grub_conf_lvs.append(str(grub_lv).replace(
                    vg_name + '_', ''))
        lvs_path = '/deployments/enm/clusters/{0}/nodes/{1}/' \
            'storage_profile/volume_groups/{2}/file_systems' \
            ''.format(cluster, node_name, vg_name)
        lvs = self.rest.get_children(lvs_path, verbose=False)
        lvs_from_model = get_model_lvs(lvs)
        missing_lvs, extra_lvs, check_fails = compare_lvs(
            lvs_from_model, grub_conf_lvs)
        if check_fails:
            vg_report.update({'Grub State': 'NOT OK'})
            self.grub_lvs_check_failed = True
        else:
            vg_report.update({'Grub State': 'OK'})
        if missing_lvs:
            vg_report.update({'Missing LV': missing_lvs})
        else:
            vg_report.update({'Missing LV': '-'})
        if extra_lvs:
            vg_report.update({'Extra LV': extra_lvs})
        else:
            vg_report.update({'Extra LV': '-'})
        return vg_report


def get_model_lvs(lvs):
    """
    Function Description:
    Gets LVs in model
    :return: list of lvs in model
    """
    lvs_from_model = []
    for _lv in lvs:
        lv_name = str(_lv.get('data').get('id'))
        lvs_from_model.append(lv_name)
    return lvs_from_model


def compare_lvs(model_lvs, grub_cfg_lvs):
    """
    Function Description:
    Compares LVs in grub.cfg with LVs in the model
    :return: tuple
    """
    missing_in_grub = set()
    missing_in_model = set()
    check_fails = False
    for model_lv in model_lvs:
        if model_lv not in grub_cfg_lvs:
            missing_in_grub.add(model_lv)
    for grub_cfg_lv in grub_cfg_lvs:
        if grub_cfg_lv not in model_lvs:
            missing_in_model.add(grub_cfg_lv)
    if missing_in_grub or missing_in_model:
        check_fails = True
    missing_in_grub = ", ".join(missing_in_grub)
    missing_in_model = ", ".join(missing_in_model)
    return missing_in_grub, missing_in_model, check_fails
