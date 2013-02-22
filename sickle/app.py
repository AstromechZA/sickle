# coding: utf-8
"""
    Sickle
    ~~~~~~

    An OAI-PMH client.

    :copyright: Copright 2013 Mathias Loesch
"""


from .models import Set, Record, Header
import requests
try:
    from lxml import etree
except ImportError:
    from xml.etree import ElementTree as etree


OAI_NAMESPACE = '{http://www.openarchives.org/OAI/%s/}'


class Sickle(object):
    """Client for harvesting OAI interfaces.

    Use it like this::

        >>> sickle = Sickle('http://elis.da.ulcc.ac.uk/cgi/oai2')
        >>> response = sickle.ListRecords(metadataPrefix='oai_dc')


    :param endpoint: The endpoint of the OAI interface.
    :type endpoint: str
    :param http_method: Method used for requests (GET or POST).
    :type http_method: str
    :param protocol_version: The OAI protocol version.
    :type protocol_version: str
    """
    def __init__(self, endpoint, http_method='GET', protocol_version='2.0'):
        super(Sickle, self).__init__()
        self.endpoint = endpoint
        self.http_method = http_method
        self.protocol_version = protocol_version
        self.oai_namespace = OAI_NAMESPACE % self.protocol_version

    def harvest(self, **kwargs):
        """Make an HTTP request to the OAI server."""
        if self.http_method == 'GET':
            return requests.get(self.endpoint, params=kwargs)
        elif self.http_method == 'POST':
            return requests.post(self.endpoint, data=kwargs)

    def ListRecords(self, **kwargs):
        """Issue a ListRecords request.

        :rtype: :class:`~sickle.app.OAIResponse`
        """
        params = kwargs
        params.update({'verb': 'ListRecords'})
        response = self.harvest(**params)
        return OAIResponse(response, params, self)

    def ListIdentifiers(self, **kwargs):
        """Issue a ListIdentifiers request.

        :rtype: :class:`~sickle.app.OAIResponse`
        """
        params = kwargs
        params.update({'verb': 'ListIdentifiers'})
        response = self.harvest(**params)
        return OAIResponse(response, params, self)

    def ListSets(self, **kwargs):
        """Issue a ListSets request.

        :rtype: :class:`~sickle.app.OAIResponse`
        """
        params = kwargs
        params.update({'verb': 'ListSets'})
        response = self.harvest(**params)
        return OAIResponse(response, params, self)

    def Identify(self):
        """Issue a ListSets request.

        :rtype: :class:`~sickle.app.OAIResponse`
        """
        params = {'verb': 'Identify'}
        response = self.harvest(**params)
        return OAIResponse(response, params, self)

    def GetRecord(self, **kwargs):
        """Issue a ListSets request.

        :rtype: :class:`~sickle.app.OAIResponse`
        """
        params = kwargs
        params.update({'verb': 'GetRecord'})
        response = self.harvest(**params)
        return OAIResponse(response, params, self)

    def ListMetadataFormats(self, **kwargs):
        """Issue a ListMetadataFormats request.

        :rtype: :class:`~sickle.app.OAIResponse`
        """
        params = kwargs
        params.update({'verb': 'ListMetadataFormats'})
        response = self.harvest(**params)
        return OAIResponse(response, params, self)


class OAIResponse(object):
    """A response from an OAI server.

    Provides access to the returned data on different abstraction
    levels::

        >>> response = sickle.ListRecords(metadataPrefix='oai_dc')
        >>> response.xml
        <Element {http://www.openarchives.org/OAI/2.0/}OAI-PMH at 0x10469a8c0>
        >>> response.raw
        u'<?xml version=\'1.0\' encoding ...'

    :param response: The original HTTP response.
    :param params: The OAI parameters for the request.
    :type params: dict
    :param sickle: The Sickle object that issued the original request.
    :type sickle: :class:`~sickle.app.Sickle`
    """
    def __init__(self, response, params, sickle):
        self.params = params
        self.response = response
        self.sickle = sickle

    @property
    def raw(self):
        """The server's response as unicode."""
        return self.response.text

    @property
    def xml(self):
        """The server's response as parsed XML."""
        return etree.XML(self.response.text.encode("utf8"))

    def iter(self, ignore_deleted=False):
        """Iterate through the resulting records of the request.

        Iterable OAI verbs are:
            - ListRecords
            - ListIdentifiers
            - ListSets


         Raises NotImplementedError if called on a response for a non-eligible OAI request
         (e.g., Identify).

        :param ignore_deleted: Flag for whether to ignore deleted records.
        :type ignore_deleted: bool
        :rtype: :class:`sickle.app.OAIIterator`
        """
        if self.params.get("verb") not in ['ListRecords', 'ListSets', 'ListIdentifiers']:
            raise NotImplementedError(
                '%s can not be iterated' % self.params.get("verb"))
        else:
            return OAIIterator(self, self.sickle, ignore_deleted=ignore_deleted)

    def __repr__(self):
        return '<OAIResponse %s>' % self.params.get('verb')


class OAIIterator(object):
    """Iterator over OAI records/identifiers/sets transparently aggregated via
    OAI-PMH.

    Can be used to conveniently iterate through the records of a repository::

        >>> oai_response = sickle.ListRecords(metadataPrefix='oai_dc')
        >>> records = oai_response.iter()
        >>> records.next()
        <Element {http://www.openarchives.org/OAI/2.0/}record at 0x1051b3b90>

    :param oai_response: The first OAI response.
    :type oai_response: :class:`~sickle.app.OAIResponse`
    :param sickle: The Sickle object that issued the first request.
    :type sickle: :class:`~sickle.app.Sickle`
    :param ignore_deleted: Flag for whether to ignore deleted records.
    :type ignore_deleted: bool
    """
    def __init__(self, oai_response, sickle, ignore_deleted=False):
        self.sickle = sickle
        self.oai_response = oai_response
        self.verb = self.oai_response.params.get("verb")
        # Determine on what element to iterate (records, headers, or sets)
        if self.verb == 'ListRecords':
            self.element = 'record'
            self.mapper = Record
        elif self.verb == 'ListIdentifiers':
            self.element = 'header'
            self.mapper = Header
        elif self.verb == 'ListSets':
            self.element = 'set'
            self.mapper = Set
        self._items = self.oai_response.xml.iterfind(
            './/' + self.sickle.oai_namespace + self.element)
        self.resumption_token = self._get_resumption_token()
        self.ignore_deleted = ignore_deleted
        self.request = getattr(self.sickle, self.verb)

    def __iter__(self):
        return self

    def __repr__(self):
        return '<OAIIterator %s>' % self.verb

    def _get_resumption_token(self):
        """Extract and store the resumptionToken from the last response."""
        resumption_token = self.oai_response.xml.find(
            './/' + self.sickle.oai_namespace + 'resumptionToken')
        if resumption_token is None:
            return None
        else:
            return resumption_token.text

    def _next_response(self):
        """Get the next response from the OAI server."""
        print "DEBUG: fetching %s" % self.resumption_token
        self.oai_response = self.request(resumptionToken=self.resumption_token)
        self.resumption_token = self._get_resumption_token()
        self._items = self.oai_response.xml.iterfind(
            './/' + self.sickle.oai_namespace + self.element)

    def next(self):
        """Return the next record/header/set."""
        try:
            while True:
                mapped = self.mapper(self._items.next())
                if self.ignore_deleted and mapped.deleted:
                    continue
                return mapped
        except StopIteration:
            if self.resumption_token is None:
                raise StopIteration
            else:
                self._next_response()
                while True:
                    mapped = self.mapper(self._items.next())
                    if self.ignore_deleted and mapped.deleted:
                        continue
                    return mapped
