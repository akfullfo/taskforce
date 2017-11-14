# ________________________________________________________________________
#
#  Copyright (C) 2014 Andrew Fullford
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ________________________________________________________________________
#

import os, sys, socket, ssl, json, re, logging
from . import httpd
try:
    from http.client import HTTPConnection, HTTPSConnection, BadStatusLine
except:
    from httplib import HTTPConnection, HTTPSConnection, BadStatusLine
try:
    from urllib.parse import parse_qs, urlparse, urlencode
except:
    from urlparse import parse_qs, urlparse
    from urllib import urlencode

class udomHTTPConnection(HTTPConnection, object):
    def __init__(self, path, timeout):
        self.path = path
        self.timeout = timeout
        super(udomHTTPConnection, self).__init__('localhost', port=None, timeout=timeout)

        # We don't actually want the IP-based socket.
        try: self.sock.close()
        except: pass

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.path)
        self.sock = sock
        if self.timeout:
            self.sock.settimeout(self.timeout)

class udomHTTPSConnection(HTTPConnection, object):
    def __init__(self, path, **params):
        self.path = path
        self.timeout = params.get('timeout')
        self.context = params.get('context')
        self.log = params.get('log')
        super(udomHTTPSConnection, self).__init__('localhost', port=None, timeout=self.timeout)

        # We don't actually want the IP-based socket.
        try: self.sock.close()
        except: pass

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.path)
        ctx = None
        if self.context:
            ctx = self.context
        else:                                                                                   # pragma: no cover
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            except AttributeError:
                pass
        if ctx:
            sslsock = ctx.wrap_socket(sock, server_side=False)
        else:
            if self.log: self.log.warning("No ssl.SSLContext(), less secure connections may be allowed")
            sslsock = ssl.wrap_socket(sock, server_side=False)
        self.sock = sslsock
        if self.timeout:
            self.sock.settimeout(self.timeout)

class HttpError(Exception):
    def __init__(self, code=400, content_type='text/plain', content='Generic error\n'):
        self.code = code
        self.content_type = content_type
        self.content = content

    def __str__(self):
        message = ''
        if self.content_type == 'text/plain':
            for line in self.content.splitlines():
                text = line.strip()
                if len(text) > 0:
                    message = text
                    break
        else:                                                                                   # pragma: no cover
            message = 'Error content %s, length %d' % (self.content_type, len(self.content))
        return ("%d %s" % (self.code, message))

class Client(object):
    """
    Provides methods to access the taskforce http service.  These are basically
    for convenience in clients, and are particularly useful when using
    Unix domain sockets (thanks to Erik van Zijst for the nice approach --
    https://pypi.python.org/pypi/uhttplib).

    Parameters:

      address   - The address to listen on, defaults to "httpd.def_address".
              This may be specified as "[host][:port]" for TCP, or
              as "path" to select a Udom service (path must contain
              at least one "/" character).
      use_ssl   - If None (default) the connection will not use SSL.
              If False, SSL will be used but the certificate will
              not be verified.
              If True, SSL will be used and the server must have a
              valid certificate (assumes python >= 2.7.9)
      timeout   - The timeout in seconds (float) for query I/O.
      log       - A 'logging' object to log errors and activity.
"""

    def __init__(self, address=None, use_ssl=None, timeout=5, log=None):
        if log:
            self.log = log
        else:
            self.log = logging.getLogger(__name__)
            self.log.addHandler(logging.NullHandler())

        if address:
            self.address = address
        else:
            self.address = httpd.def_address

        if self.address.find('/') >=0 :
            if use_ssl is None:
                self.http = udomHTTPConnection(self.address, timeout)
            else:
                ssl_params = self._build_params(use_ssl, timeout)
                self.http = udomHTTPSConnection(self.address, **ssl_params)
        else:
            port = None
            m = re.match(r'^(.*):(.*)$', self.address)
            if m:
                self.log.debug("Matched host '%s', port '%s'", m.group(1), m.group(2))
                host = m.group(1)
                try:
                    port = int(m.group(2))
                except:
                    raise HttpError(code=500, content_type='text/plain',
                                content="TCP listen port must be an integer")
            else:
                host = self.address
                self.log.debug("No match, proceding with host '%s'", host)
            if use_ssl is None:
                if not port:
                    port = httpd.def_port
                self.log.debug("Connecting to host '%s', port '%s'", host, port)
                self.http = HTTPConnection(host, port, timeout=timeout)
            else:
                if not port:
                    port = httpd.def_sslport
                ssl_params = self._build_params(use_ssl, timeout)
                self.http = HTTPSConnection(host, port, **ssl_params)
                self.log.debug("Connecting via ssl to host '%s', port '%s'", host, port)
            self.address = "%s:%d" % (host, port)
        self.http.connect()
        self.sock = self.http.sock
        self.lastpath = None
        self.log.info("HTTP connected via %s", self.http.sock)
        if use_ssl and hasattr(self.http.sock, 'cipher'):                                       # pragma: no cover
            self.log.debug("Cipher: %s", self.http.sock.cipher())

    def _build_params(self, use_ssl, timeout):
        ssl_params = {'timeout': timeout}
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        except AttributeError:                                                                  # pragma: no cover
            self.log.info("No ssl.SSLContext(), assuming older python")
            return ssl_params
        if use_ssl is False:
            ctx.verify_mode = ssl.CERT_NONE
        else:                                                                                   # pragma: no cover
            ctx.verify_mode = ssl.CERT_REQUIRED
        if 'OP_NO_SSLv2' in ssl.__dict__:
            ctx.options |= ssl.OP_NO_SSLv2
        else:                                                                                   # pragma: no cover
            self.log.info("Implementation does not offer ssl.OP_NO_SSLv2 which may allow less secure connections")
        if 'OP_NO_SSLv3' in ssl.__dict__:
            ctx.options |= ssl.OP_NO_SSLv3
        else:                                                                                   # pragma: no cover
            self.log.info("Implementation does not offer ssl.OP_NO_SSLv3 which may allow less secure connections")
        ssl_params['context'] = ctx
        return ssl_params

    def get(self, path, query=None):
        """
        Issue a GET request.  If specfied, "query" should be a dict of name/value
        pairs.  Names should be normal identifiers which start with an alpha
        followed by alnums or underscores.  The values are url-encoded and
        become the "query" part of the request header (ie, the part after
        the '?' in the URI).

        The result is the tuple:
            (code, content, content_type)

        If the request is unsuccessful returning code 400 or higher, the
        http.HttpError exception is raised.
    """
        self.lastpath = path
        if query is not None:
            self.lastpath += '?' + urlencode(query)
        self.http.request('GET', self.lastpath)
        resp = self.http.getresponse()
        ctype = resp.getheader('Content-Type')
        data = resp.read().decode('utf-8')
        self.log.debug("Request '%s' status %d, %s length %d", self.lastpath, resp.status, ctype, len(data))
        if resp.status < 400:
            return (resp.status, data, ctype)
        else:
            raise HttpError(code=resp.status, content_type=ctype, content=data)

    def getmap(self, path, query=None):
        """
        Performs a GET request where the response content type is required to be
        "application/json" and the content is a JSON-encoded data structure.
        The decoded structure is returned.
    """
        code, data, ctype = self.get(path, query)
        if ctype != 'application/json':
            self.log.error("Expecting JSON from GET of '%s', got '%s'", self.lastpath, ctype)
            raise HttpError(code=400, content_type='text/plain', content='Remote returned invalid content type: '+ctype)
        try:
            result = json.loads(data)
        except Exception as e:                                                                  # pragma: no cover
            self.log.error("Could not load JSON content from GET %r -- %s", self.lastpath, e)
            raise HttpError(code=400, content_type='text/plain', content='Could not load JSON content')
        return result

    def post(self, path, valuemap=None, query=None):
        """
        Performs a POST request.  "valuemap" is a dict sent as "application/x-www-form-urlencoded".
        "query" is as for get().  Return is same as get().
    """
        self.lastpath = path
        if query is not None:
            self.lastpath += '?' + urlencode(query)
        if valuemap:
            self.http.request('POST', self.lastpath, urlencode(valuemap),
                                {"Content-type": "application/x-www-form-urlencoded"})
        else:
            self.http.request('POST', self.lastpath, '')
        resp = self.http.getresponse()
        ctype = resp.getheader('Content-Type')
        data = resp.read().decode('utf-8')
        self.log.debug("Request '%s' status %d, %s length %d", self.lastpath, resp.status, ctype, len(data))
        if resp.status < 400:
            return (resp.status, data, ctype)
        else:
            raise HttpError(code=resp.status, content_type=ctype, content=data)

    def postmap(self, path, valuemap=None, query=None):
        """
        Performs a POST request as per post() but the response content type
        is required to be "application/json" and is processed as with getmap().
    """
        code, data, ctype = self.post(path, valuemap, query)
        if ctype != 'application/json':
            self.log.error("Expecting JSON from POST of '%s', got '%s'", self.lastpath, ctype)
            raise HttpError(code=400, content_type='text/plain', content='Remote returned invalid content type: '+ctype)
        try:
            result = json.loads(data)
        except Exception as e:                                                                  # pragma: no cover
            self.log.error("Could not load JSON content from POST %r -- %s", self.lastpath, e)
            raise HttpError(code=400, content_type='text/plain', content='Could not load JSON content')
        return result

    def request(self, method, url, *args):
        """
        Pass-thru method to make this class behave a little like HTTPConnection
    """
        return self.http.request(method, url, *args)

    def getresponse(self):
        """
        Pass-thru method to make this class behave a little like HTTPConnection
    """
        resp = self.http.getresponse()
        self.log.info("resp is %s", str(resp))
        if resp.status < 400:
            return resp
        else:
            errtext = resp.read()
            content_type = resp.getheader('Content-Type', 'text/plain')
            raise HttpError(code=resp.status, content_type=content_type, content=errtext)
