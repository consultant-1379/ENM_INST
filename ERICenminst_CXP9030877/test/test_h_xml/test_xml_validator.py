from h_xml.xml_validator import XMLValidator
from h_util.h_utils import touch
from lxml.etree import DocumentInvalid, XMLSyntaxError
from os.path import join
from os import path, remove
from tempfile import gettempdir
import unittest2 as unittest



SCHEMA_XML = """\
<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'>
 <xs:element name="addresses">
 <xs:complexType>
 <xs:sequence>
 <xs:element ref="address" minOccurs='1' maxOccurs='unbounded'/>
 </xs:sequence>
 </xs:complexType>
</xs:element>

 <xs:element name="address">
 <xs:complexType>
 <xs:sequence>
 <xs:element ref="name" minOccurs='0' maxOccurs='1'/>
 <xs:element ref="street" minOccurs='0' maxOccurs='1'/>
 </xs:sequence>
 </xs:complexType>
 </xs:element>

 <xs:element name="name" type='xs:string'/>
 <xs:element name="street" type='xs:string'/>
</xs:schema>
"""

SCHEMA_XML_INVALID = """\
.
"""

DEPLOYMENT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<addresses xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
	   xsi:noNamespaceSchemaLocation='test.xsd'>

  <address>
    <name>Test</name>
    <street>Test</street>
  </address>
</addresses>
"""


DEPLOYMENT_XML_INVALID = """\
.
"""

DEPLOYMENT_XML_MISSING_ELEMENT = """\
<?xml version="1.0" encoding="UTF-8"?>
<addresses xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
	   xsi:noNamespaceSchemaLocation='test.xsd'>

  <address>
    <name>Test</name>
    <name>Test2</name>
  </address>
</addresses>
"""



class TestXMLValidator(unittest.TestCase):
    """
    Test XMLValidator
    """

    def setUp(self):
        self.xml_path = path.join(gettempdir(), 'enm_deployment.xml')
        self.schema_path = path.join(gettempdir(), 'litp.xsd')
        self.make_file(self.xml_path)
        self.make_file(self.schema_path)

    def tearDown(self):
        try:
            remove(self.xml_path)
            remove(self.schema_path)
        except OSError:
            pass

    def write_content_to_file(self, content, filename):
        with open(filename, 'w') as ofile:
            ofile.write(content)

    def make_file(self, filename, filepath=None):
        if filepath:
            filename = join(filepath, filename)
        touch(filename)
        return filename

    def test_validate_parse_xml_deployment_invalid(self):
        xml_validator = XMLValidator()
        self.write_content_to_file(DEPLOYMENT_XML_INVALID, self.xml_path)
        self.write_content_to_file(SCHEMA_XML, self.schema_path)
        self.assertRaises(XMLSyntaxError, xml_validator.validate, self.xml_path, self.schema_path)

    def test_validate_parse_xml_schema_invalid(self):
        xml_validator = XMLValidator()
        self.write_content_to_file(DEPLOYMENT_XML, self.xml_path)
        self.write_content_to_file(SCHEMA_XML_INVALID, self.schema_path)
        self.assertRaises(XMLSyntaxError, xml_validator.validate, self.xml_path, self.schema_path)

    def test_validate_xml_validation_valid_schema_valid_xml(self):
        xml_validator = XMLValidator()
        self.write_content_to_file(DEPLOYMENT_XML, self.xml_path)
        self.write_content_to_file(SCHEMA_XML, self.schema_path)
        xml_validator.validate(self.xml_path, self.schema_path)

    def test_validate_xml_validation_valid_schema_valid_xml_additional_element(self):
        xml_validator = XMLValidator()
        self.write_content_to_file(DEPLOYMENT_XML_MISSING_ELEMENT, self.xml_path)
        self.write_content_to_file(SCHEMA_XML, self.schema_path)
        self.assertRaises(DocumentInvalid, xml_validator.validate, self.xml_path, self.schema_path)

