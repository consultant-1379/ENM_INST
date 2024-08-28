"""
Module containing custom collections implementations
"""
##############################################################################
# COPYRIGHT Ericsson AB 2019
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


class ExceptHandlingDict(dict):
    """
    Specialised dictionary to handle KeyError exception and raise custom one.
    """
    def __init__(self, d, exc, msg=''):
        super(ExceptHandlingDict, self).__init__(d)
        self.exc = exc
        self.msg = msg

    def __getitem__(self, key):
        try:
            return super(ExceptHandlingDict, self).__getitem__(key)
        except KeyError as error:
            message = "%s %s" % (error, self.msg) if self.msg \
                else "%s key does not exist in %s" % (error, self)
            raise self.exc(message)

    @staticmethod
    def get_dict(dictionary, exc, msg=''):
        """
        Static method to wrap dictionary into customized KeyError exception
        handling dictionary. It also wraps nested dictionaries.
        :param dictionary: dict to wrap
        :param exc: custom exception to raise on KeyError
        :param msg: custom exception message.
        This will also contain key that generated exception
        in format "<<invalid_key>> <<custom message>>"
        :return: ExceptHandlingDict
        """
        if isinstance(dictionary, dict):
            dictionary = ExceptHandlingDict(dictionary, exc, msg)
            for key, value in dictionary.items():
                if isinstance(value, dict):
                    dictionary[key] = ExceptHandlingDict.get_dict(value, exc,
                                                                  msg)
                elif isinstance(value, list):
                    dictionary[key] = [ExceptHandlingDict.get_dict(item, exc,
                                                                   msg)
                                       for item in value]
        return dictionary
