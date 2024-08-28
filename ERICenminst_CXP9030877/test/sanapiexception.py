class SanApiException(Exception):
    def __init__(self, message="", ReturnCode=1):
        """
        Constructor.
        """
        Exception.__init__(self, message)
        self.ReturnCode = ReturnCode


class SanApiEntityNotFoundException(SanApiException):
    pass

class SanApiOperationFailedException(SanApiException):
    pass
