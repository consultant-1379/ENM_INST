class SanApiInfo(object):
    def __init__(self, logger=None):
        self.logger = None
        self.cfg = None


class LunInfo(SanApiInfo):
    def __init__(self, lun_id, name, uid, container, size, container_type,
                 raid, controller=None, current_op="",
                 current_op_state="",
                 current_op_status="",
                 percent_complete="", consumed=None):
        super(LunInfo, self).__init__()

        self.id = lun_id
        self.name = name
        self.uid = uid
        self.container = container  # use setter
        self.size = size
        self.type = container_type  # use setter
        self.raid = str(raid)  # use setter
        self.controller = str(controller)
        self.current_op = current_op
        self.current_op_state = current_op_state
        self.current_op_status = current_op_status
        self.percent_complete = percent_complete
        self.consumed = consumed


class StoragePoolInfo(SanApiInfo):
    def __init__(self, name, ident, raid, size, available, perc_full=None, perc_sub=None):
        super(StoragePoolInfo, self).__init__()
        self.id = ident
        self.name = name
        self.raid = str(raid)
        self.size = size
        self.available = available
        self.full = perc_full
        self.subscribed = perc_sub


class HbaInitiatorInfo(SanApiInfo):
    def __init__(self, hbauid, spname, spport, hbaname=None,
                 hbaip=None):
        super(HbaInitiatorInfo, self).__init__()
        self.hbauid = hbauid
        self.spname = spname
        self.spport = spport
        self.hbaname = hbaname
        self.hbaip = hbaip


class HluAluPairInfo(SanApiInfo):
    def __init__(self, hlu, alu):
        self.hlu = hlu
        self.alu = alu


class StorageGroupInfo(SanApiInfo):
    def __init__(self, name, uid, shareable, hbasp_list, hlualu_list):
        super(StorageGroupInfo, self).__init__()
        self.hbasp_list = hbasp_list
        self.hlualu_list = hlualu_list
        self.name = name
        self.uid = uid
        self.shareable = shareable


class SnapshotInfo(SanApiInfo):
    def __init__(self, resource_lun_id, snapshot_name, created_time,
                 snap_state, resource_lun_name, description=None):
        super(SnapshotInfo, self).__init__()
        self.resource_id = resource_lun_id
        self.snap_name = snapshot_name
        self.creation_time = created_time
        self.state = snap_state
        self.resource_name = resource_lun_name
        self.description = description


class SanInfo(SanApiInfo):
    def __init__(self, oe_version, san_model):
        super(SanInfo, self).__init__()
        self.oe_version = oe_version
        self.san_model = san_model

