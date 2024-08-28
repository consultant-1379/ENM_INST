"""
XML SAX Parser implementation
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from xml.dom.minidom import getDOMImplementation
from xml.sax import handler


class SAXParser(handler.ContentHandler):
    """
    Basic SAX parser
    """
    def __init__(self):
        """
        Default Constructor
        """
        handler.ContentHandler.__init__(self)
        self.dommer = getDOMImplementation()
        self.doc = None
        self.parent_node = None
        self.cw_element = None
        self.parent_node = None
        self.extracted_nodes = None

    def get_parent_node(self):
        """
        Get the parent node the xml snippet should be inserted into

        @return: the parent node
        @rtype: Element
        """
        return self.parent_node

    def get_extracted_nodes(self):
        """
        Get the list of nodes to insert into the TORINST definition xml

        @return: the nodes the insert
        @rtype: Element[]
        """
        return self.extracted_nodes

    def startDocument(self):
        """
        Reset the parser for a new parse run
        """
        self.doc = self.dommer.createDocument(None, 'ROOT', None)
        self.parent_node = self.doc.documentElement
        self.cw_element = None

    def endDocument(self):
        """
        Finised parsing, setup return values
        """
        self.parent_node = self.doc.documentElement.firstChild
        self.extracted_nodes = self.doc.documentElement.firstChild.childNodes

    def startElement(self, name, attrs):
        """
        Parse an element
        :param name: The element name
        :param attrs: Element attributes
        """
        if self.cw_element:
            self.parent_node = self.cw_element
        self.cw_element = self.doc.createElement(name)
        self.parent_node.appendChild(self.cw_element)
        for a_name, a_value in attrs.items():
            self.cw_element.setAttribute(a_name, a_value)

    def endElement(self, name):
        """
        Finish parsing an element
        :param name: The element name
        """
        if self.cw_element:
            self.cw_element = self.parent_node
            if self.cw_element:
                self.parent_node = self.cw_element.parentNode

    def characters(self, data):
        """
        Parse text elements, if no text then nothing is added
        :param data: CDATA
        """
        data = data.strip()
        if len(data) > 0:
            text_node = self.doc.createTextNode(data)
            self.cw_element.appendChild(text_node)
