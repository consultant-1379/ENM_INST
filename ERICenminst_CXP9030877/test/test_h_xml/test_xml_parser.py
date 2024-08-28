import tempfile
from os import remove
from os.path import join
from xml.sax import make_parser

import unittest2

from h_xml.xml_parser import SAXParser

document = """\
<litp:attr id="abc">
  <first/>
  <second/>
  <third/>
</litp:attr>
"""


class TestXMLParser(unittest2.TestCase):
    def setUp(self):
        self.make_parser = make_parser()
        self.content_handler = SAXParser()
        self.snippet_basedir = tempfile.gettempdir()
        self.make_parser.setContentHandler(self.content_handler)
        self.input_file = join(self.snippet_basedir, 'test.xml')
        f = open(self.input_file, 'w+')
        f.write(document)
        f.close()

    def test_getParentNode(self):
        self.make_parser.parse(self.input_file)
        self.assertEqual('abc', self.content_handler.get_parent_node()
                         .getAttribute('id'))

    def test_getExtractedNodes(self):
        self.make_parser.parse(self.input_file)
        nodelist = self.content_handler.get_extracted_nodes()
        self.assertEqual(3, nodelist.length)

    def tearDown(self):
        try:
            remove(self.input_file)
        except OSError:
            pass


if __name__ == '__main__':
    unittest2.main()
