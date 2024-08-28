#pylint: disable=R0903
"""
XML Validator
"""
##############################################################################
# COPYRIGHT Ericsson AB 2018
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from lxml.etree import parse, XMLSchema, \
    DocumentInvalid, XMLSyntaxError
import logging


class XMLValidator(object):
    """
    Basic XML Validator
    """

    def __init__(self):
        self.log = logging.getLogger('enminst')

    def validate(self, xml_path, schema_path):
        """
        Validates XML against Schema
        :xml_path: Path to xml file
        :schema_path: Path to xml schema file
        """
        try:
            self.log.debug("Parsing schema: {0}".format(schema_path))
            schema_doc = parse(schema_path)

            schema = XMLSchema(schema_doc)

            self.log.debug("Parsing XML: {0}".format(xml_path))
            doc = parse(xml_path)

            self.log.debug("Validating XML: {0} against {1}"
                           .format(xml_path, schema_path))
            schema.assertValid(doc)

        except XMLSyntaxError:
            raise

        except DocumentInvalid:
            raise

        except Exception:
            raise
