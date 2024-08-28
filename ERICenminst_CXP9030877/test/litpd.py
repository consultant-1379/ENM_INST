"""
Classes to stub out a LITP MS
"""
import httplib
import re
from copy import deepcopy
from json import dumps

from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import LitpObject


class HttpResponse(object):
    def __init__(self, status, data=None, reason=None):
        super(HttpResponse, self).__init__()
        self.status = status
        self.rest_data = data
        self.reason = reason

    def read(self):
        return self.rest_data

    def getheader(self, name):
        return LitpRestClient.CONTENT_TYPE_JSON


class LitpIntegration(LitpRestClient):
    """
    LMS litpd stub.

    def test_something():
        litpd = LitpIntegration()
        litpd.create_empty_model()
        litpd.create_item(....)
        litpd.create_item(....)

        test_instance = SomeEnminstClass():
            def __init__():
                self._litp = LitpRestClient()

            def do_something(self):
                self._litp.get('some_path')

        test_instance._litp = litpd
        test_instance.do_something()


    """

    def __init__(self):
        super(LitpIntegration, self).__init__(
                'localhost', None, LitpRestClient.DEFAULT_REST_VERSION)
        self._model = {}
        self._request_response = None
        self.obj_template = {
            '_embedded': {
                'item': []
            },
            'item-type-name': None,
            'state': None,
            '_links': {
                'self': {
                    'href': '/'.join(['https://localhost:9999',
                                      self.base_rest_path])
                }
            },
            'id': None,
            'properties': {}
        }
        self._model['/'] = self.new_object('/', 'root')

    def setup_empty_model(self):
        self.create_item('/infrastructure')
        self.create_item('/infrastructure/service_providers')
        self.create_item('/infrastructure/networking')
        self.create_item('/infrastructure/networking/routes')
        self.create_item('/infrastructure/networking/networks')
        self.create_item('/infrastructure/items')
        self.create_item('/infrastructure/storage')
        self.create_item('/infrastructure/storage/storage_profiles')
        self.create_item('/infrastructure/storage/storage_providers')
        self.create_item('/infrastructure/storage/nfs_mounts')
        self.create_item('/infrastructure/system_providers')
        self.create_item('/infrastructure/systems')
        self.create_item('/ms', properties={'hostname': 'test-ms-1'})
        self.create_item('/ms/items')
        self.create_item('/ms/network_interfaces')
        self.create_item('/ms/services')
        self.create_item('/ms/routes')
        self.create_item('/ms/configs')
        self.create_item('/ms/file_systems')
        self.create_item('/software')
        self.create_item('/software/items')
        self.create_item('/software/profiles')
        self.create_item('/software/runtimes')
        self.create_item('/software/services')
        self.create_item('/software/deployables')
        self.create_item('/software/images')

        self.create_item('/deployments')
        self.create_item('/deployments/enm')
        self.create_item('/deployments/enm/clusters')

    def create_litp_system(self, system_name, ip='127.0.0.1',
                           state=LitpRestClient.ITEM_STATE_APPLIED):
        system_path = '/infrastructure/systems/{0}_system'.format(system_name)
        self.create_item(system_path, 'blade',
                         {'system_name': system_name}, state=state)
        self.create_item('{0}/controllers'.format(system_path), state=state)
        self.create_item('{0}/bmc'.format(system_path), state=state,
                         properties={'username': 'root',
                                     'password_key': 'password-key',
                                     'ipaddress': ip})
        self.create_item('{0}/disks'.format(system_path), state=state)
        return system_path

    def create_litp_vcscluster(self, deployment, cluster_name):
        cluster_path = '/deployments/{0}/clusters/{1}'.format(
                deployment, cluster_name)
        self.create_item(cluster_path, 'vcs-cluster')
        self.create_item('{0}/fencing_disks'.format(cluster_path))
        self.create_item('{0}/configs'.format(cluster_path))
        self.create_item('{0}/network_hosts'.format(cluster_path))
        self.create_item('{0}/nodes'.format(cluster_path))
        self.create_item('{0}/software'.format(cluster_path))
        self.create_item('{0}/services'.format(cluster_path))
        return cluster_path

    def create_litp_clusternode(self, cluster_path, node_name,
                                state=LitpRestClient.ITEM_STATE_APPLIED):
        node_path = '{0}/nodes/{1}'.format(cluster_path, node_name)
        self.create_item(node_path, 'node', {'hostname': node_name},
                         state=state)
        self.create_item('{0}/items'.format(node_path), state=state)
        self.create_item('{0}/network_interfaces'.format(node_path),
                         state=state)
        self.create_item('{0}/services'.format(node_path), state=state)
        self.create_item('{0}/routes'.format(node_path), state=state)
        self.create_item('{0}/configs'.format(node_path), state=state)
        self.create_item('{0}/file_systems'.format(node_path), state=state)
        return node_path

    def inherit_object(self, source_path, target):
        """

        :param source_path: Source path
        :param target: Target path
        :return:
        """
        source_obj = self._model[source_path]
        self.create_item(
                target, item_type='reference-to-' + source_obj.item_type,
                properties=source_obj.properties)

        self._copy_nodes(source_path, target)

    def _copy_nodes(self, from_path, to_path):
        for _item in self._model[from_path].as_struct()['_embedded']['item']:
            sitem = self._model[self.path_parser(
                    _item['_links']['self']['href'])]
            cpath = '{0}/{1}'.format(to_path, sitem.path.split('/')[-1])
            self.create_item(cpath, sitem.item_type, sitem.properties)
            self._copy_nodes(sitem.path, cpath)

    def new_object(self, path, item_type, properties=None,
                   state=LitpRestClient.ITEM_STATE_APPLIED):
        _new = deepcopy(self.obj_template)
        _new['id'] = path.split('/')[-1]
        _new['item-type-name'] = item_type
        _new['state'] = state
        '/'.join(_new['_links']['self']['href'])
        _new['_links']['self']['href'] += path
        if properties is None:
            properties = {}
        _new['properties'] = properties
        return LitpObject(None, _new, self.path_parser)

    def create_item(self, path, item_type=None, properties=None,
                    state=LitpRestClient.ITEM_STATE_APPLIED):
        if not item_type:
            item_type = path.split('/')[-1]
        _obj = self.new_object(path, item_type, properties=properties,
                               state=state)
        parent_path = re.sub('/+', '/',
                             '/{0}'.format(
                                     '/'.join(_obj.path.split('/')[:-1])))
        if parent_path not in self._model:
            raise IndexError('Parent {0} not found'.format(parent_path))
        if _obj.path in self._model:
            raise IndexError('Object {0} already defined'.format(path))
        self._model[_obj.path] = _obj
        self._model[parent_path].add_child(_obj)

    def get_https_connection(self):
        return self

    def _http_get(self, rest_path):
        _model_path = self.path_parser(rest_path)
        if _model_path[-1] == '/':
            _model_path = _model_path[:-1]
        if _model_path in self._model:
            _obj = self._model[_model_path]
            self._request_response = HttpResponse(
                    httplib.OK, _obj.as_json())
        else:
            _error = 'Path {0} not found!'.format(_model_path)
            self._request_response = HttpResponse(
                    httplib.NOT_FOUND,
                    data=dumps({'messages': _error}),
                    reason=_error)

    def request(self, request_type, rest_path, body=None, headers=None):
        if request_type.lower() == 'get':
            return self._http_get(rest_path)
        else:
            raise Exception('Request type {0} not implemented.'.format(
                    request_type))

    def getresponse(self):
        return self._request_response

    def setup_cluster_node(self, cluster_path, node_id,
                           state=LitpRestClient.ITEM_STATE_APPLIED,
                           storage_pool='pool'):
        nodepath = self.create_litp_clusternode(cluster_path, node_id,
                                                state=state)
        syspath = self.create_litp_system(node_id, ip='1.1.1.1')
        self.create_item('{0}/disks/lun_disk'.format(syspath),
                         item_type='lun-disk',
                         properties={
                             'lun_name': '600601600F103F005D37070811DCE611',
                             'size': '10G', 'snap_size': '100',
                             'shared': 'false',
                             'storage_container': storage_pool})
        self.inherit_object(syspath, '{0}/system'.format(nodepath))

    def setup_svc_cluster(self, storage_pool='pool'):
        if not self.exists('/deployments/enm/clusters'):
            self.setup_empty_model()
        cluster_path = self.create_litp_vcscluster('enm', 'svc_cluster')
        self.setup_cluster_node(cluster_path, 'svc-1',
                                storage_pool=storage_pool)
        return cluster_path

    def setup_db_cluster(self, node_count=1, storage_pool='pool'):
        if not self.exists('/deployments/enm/clusters'):
            self.setup_empty_model()
        cluster_path = self.create_litp_vcscluster('enm', 'db_cluster')
        self.create_item(cluster_path + '/fencing_disks/fen1')
        self.create_item(cluster_path + '/fencing_disks/fen2')

        for index in range(1, node_count + 1):
            self.setup_cluster_node(cluster_path, 'db-{0}'.format(index),
                                    storage_pool=storage_pool)

        return cluster_path

    def setup_str_cluster(self, node_name):
        if not self.exists('/deployments/enm/clusters'):
            self.setup_empty_model()
        cluster_path = self.create_litp_vcscluster('enm', 'str_cluster')
        nodepath = self.create_litp_clusternode(cluster_path, node_name)
        syspath = self.create_litp_system(node_name, ip='111')
        self.create_item('{0}/disks/local_disk'.format(syspath),
                         item_type='disk', properties={
                'name': 'sda'})
        self.inherit_object(syspath, '{0}/system'.format(nodepath))

        sprofile = '/infrastructure/storage/storage_profiles/profile'
        self.create_item(sprofile)
        self.create_item('{0}/volume_groups'.format(sprofile))
        vg_path = '{0}/volume_groups/vg_local'.format(sprofile)
        self.create_item(vg_path,
                         properties={'volume_group_name': 'vg_local'})
        self.create_item('{0}/physical_devices'.format(vg_path))
        self.create_item(
                '{0}/physical_devices/local_disk'.format(vg_path),
                properties={'device_name': 'sda'})

        self.create_item('{0}/file_systems'.format(vg_path))
        self.create_item(
                '{0}/file_systems/lv_local_snap'.format(vg_path),
                properties={'snap_size': 10})
        self.create_item(
                '{0}/file_systems/lv_local_nosnap'.format(vg_path),
                properties={'snap_size': 0})

        self.inherit_object(sprofile,
                            '{0}/storage_profile'.format(nodepath))
        return cluster_path

    def setup_str_cluster_multiple_nodes(
            self, nodes, state=LitpRestClient.ITEM_STATE_APPLIED):
        if not self.exists('/deployments/enm/clusters'):
            self.setup_empty_model()
        sprofile = '/infrastructure/storage/storage_profiles/profile'
        self.create_item(sprofile)
        self.create_item('{0}/volume_groups'.format(sprofile))
        vg_path = '{0}/volume_groups/vg_local'.format(sprofile)
        self.create_item(vg_path,
                         properties={'volume_group_name': 'vg_local'})
        self.create_item('{0}/physical_devices'.format(vg_path))
        self.create_item(
                '{0}/physical_devices/local_disk'.format(vg_path),
                properties={'device_name': 'sda'})

        self.create_item('{0}/file_systems'.format(vg_path))
        self.create_item(
                '{0}/file_systems/lv_local_snap'.format(vg_path),
                properties={'snap_size': 10})
        self.create_item(
                '{0}/file_systems/lv_local_nosnap'.format(vg_path),
                properties={'snap_size': 0})
        cluster_path = self.create_litp_vcscluster('enm', 'str_cluster')
        for node_name in nodes:
            nodepath = self.create_litp_clusternode(cluster_path, node_name)
            syspath = self.create_litp_system(node_name, ip='str_ip_address',
                                              state=state)
            self.create_item('{0}/disks/local_disk'.format(syspath),
                             item_type='disk', properties={
                    'name': 'sda'})
            self.inherit_object(syspath, '{0}/system'.format(nodepath))

            self.inherit_object(sprofile,
                                '{0}/storage_profile'.format(nodepath))

    def setup_storagepool(self, san_name, site_id, pool_name,
                          vnx_type='vnx2'):
        p_path = '/infrastructure/storage/storage_providers/' + san_name
        self.create_item(p_path, 'san-emc', properties={
            'username': 'admin',
            'name': 'ieatvnx-123',
            'storage_network': 'storage',
            'storage_site_id': site_id,
            'login_scope': 'global',
            'password_key': 'key-for-san-ieatvnx-123',
            'ip_b': '10.10.10.1',
            'san_type': vnx_type,
            'ip_a': '10.10.10.2'
        })
        p_path += '/storage_containers'
        self.create_item(p_path)

        self.create_item(p_path + '/' + pool_name, 'storage-container',
                         properties={
                             'type': 'POOL',
                             'name': pool_name
                         })
        self.create_item(p_path + '/rg', 'storage-container', properties={
            'type': 'RAID_GROUP',
            'name': '1'
        })

    def setup_shared_lun(self, pool_name, node_list):
        l_name = 'shared_lun'
        shared_props = {
            'lun_name': l_name,
            'storage_container': pool_name,
            'shared': 'true',
            'snap_size': '1',
            'size': '100M'
        }
        for system in node_list:
            self.create_item(
                    '/infrastructure/systems/{0}_system/'
                    'disks/{1}'.format(system, l_name),
                    'lun-disk', shared_props)
