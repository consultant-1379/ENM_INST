from mock import MagicMock


class BasePluginApi(object):
    def __init__(self, model_manager):
        self.model_manager = model_manager

    def get_password(self, service_key, username):
        mock = MagicMock(service_key, username)
        return mock
