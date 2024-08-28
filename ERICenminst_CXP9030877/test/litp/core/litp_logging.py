from mock import MagicMock


class LitpLogger(object):
    def __init__(self):
        self.trace = MagicMock()
