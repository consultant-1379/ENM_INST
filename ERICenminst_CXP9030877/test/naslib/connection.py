from naslib.nasexceptions import NasConnectionException

class NasConnection(object):
    def __init__(self,
                 host,
                 username,
                 password=None,
                 port=22,
                 nas_type='veritas'):
        self.filesystem = self.fs()
        self.share = self.sh()
        self.cache = self.rbc()
        self.snapshot = self.rb()
        self.nasserver = self.ns()
        self.nas_type = nas_type

    class fs:
        def __init__(self):
            pass

        def list(self):
            return [self.fs_list_entry1, self.fs_list_entry2]

        def online(self, f_s, online=True):
            return online

        def _properties(self, fs_name):
            fs_details = {'name': 'ENM-FS1',
                          'layout': 'simple',
                          'pool': 'ENM_pool',
                          'size': '3221225472B'}
            return fs_details

        class fs_list_entry1:
            layout = 'simple'
            name = 'ENM-FS1'
            online = True
            pool = 'ENM_pool'
            display_size = '3.00G'

            def __init__(self):
                pass

            class size:
                megas = '3072M'

                def __init__(self):
                    pass

        class fs_list_entry2:
            layout = 'simple'
            name = 'NOTENM-FS1'
            online = True
            pool = 'ENM_pool'

            def __init__(self):
                pass

            class size:
                megas = '3072M'

                def __init__(self):
                    pass

    class rbc:
        def __init__(self):
            pass

        def list(self):
            return [self.rbc_list_entry1, self.rbc_list_entry2]

        class rbc_list_entry1:
            available = '1019M'
            used = '5M'
            name = 'enm-cache'
            snapshot_count = 0
            pool = None
            size = '1024M'

            def __init__(self):
                pass

        class rbc_list_entry2:
            available = '1019M'
            used = '5M'
            name = 'TORD1234-cache'
            snapshot_count = 0
            pool = None
            size = '1024M'

            def __init__(self):
                pass

    class rb:
        def __init__(self):
            pass

        def list(self):
            return [self.rb_list_entry1, self.rb_list_entry2, self.rb_list_entry3, self.rb_list_entry4]

        class rb_list_entry1:
            name = 'cirb-enm-batch'
            cache = None
            filesystem = 'enm-batch'
            date = '2022/01/11 08:31'
            snaptype = 'spaceopt'

            def __init__(self):
                pass

        class rb_list_entry2:
            name = 'cirb-test-batch'
            cache = None
            filesystem = 'test-batch'
            date = '2022/01/11 08:31'
            snaptype = 'spaceopt'

            def __init__(self):
                pass

        class rb_list_entry3:
            name = 'L_multi-data'
            cache = None
            filesystem = 'multi-data'
            date = '2022/01/11 08:31'
            snaptype = 'spaceopt'

            def __init__(self):
                pass

        class rb_list_entry4:
            name = 'Snapshot_multi-data'
            cache = None
            filesystem = 'multi-data'
            date = '2022/01/11 08:31'
            snaptype = 'spaceopt'

            def __init__(self):
                pass

    class sh:
        def __init__(self):
            pass

        def list(self):
            return [self.sh_list_entry1, self.sh_list_entry2, self.sh_list_entry3]

        def create(self, filesystem, client, options):
            return True

        class sh_list_entry1:
            faulted = False
            client = '172.16.30.0/24'
            name = '/vx/enm-batch'
            options = 'rw,sync,no_root_squash'

            def __init__(self):
                pass

        class sh_list_entry2:
            faulted = False
            client = '172.16.30.0/24'
            name = '/vx/pool-hcdumps'
            options = 'rw,sync,no_root_squash'

            def __init__(self):
                pass

        class sh_list_entry3:
            faulted = True
            client = '172.16.30.0/24'
            name = '/vx/FAULTED-FS'
            options = 'rw,sync,no_root_squash'

            def __init__(self):
                pass

    class ns:
        def __init__(self):
            pass

        def get_nasserver_details(self, nas_server):
            if nas_server == "dummy_nas_server_2":
                return {u'currentSP': {u'id': u'spb'},
                        u'homeSP': {u'id': u'spb'},
                        u'name': u'dummy_nas_server_2'}

            elif nas_server == "dummy_nas_server_1":
                return {u'currentSP': {u'id': u'spa'},
                        u'homeSP': {u'id': u'spa'},
                        u'name': u'dummy_nas_server_1'}

            elif nas_server == "dummy_nas_server_3":
                raise Exception("Not found")

            elif nas_server == "dummy_nas_server_4":
                return {u'currentSP': {u'id': u'spa'},
                        u'name': u'dummy_nas_server_4'}

            elif nas_server == "dummy_nas_server_5":
                return {u'homeSP': {u'id': u'spa'},
                        u'name': u'dummy_nas_server_5'}

            elif nas_server == "dummy_nas_server_6":
                return {u'homeSP': {u'id': u'spc'},
                        u'currentSP': {u'id': u'spc'},
                        u'name': u'dummy_nas_server_6'}

            else:
                raise NasConnectionException()

            def __init__(self):
                pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

