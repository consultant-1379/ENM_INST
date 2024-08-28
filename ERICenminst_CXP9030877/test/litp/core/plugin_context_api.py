from mock import MagicMock


class PluginApiContext(object):
    def __init__(self, model_mngr):
        self.model_manager = model_mngr

    def query_by_vpath(self, vpath):
        mock = MagicMock(vpath=vpath)
        return mock
