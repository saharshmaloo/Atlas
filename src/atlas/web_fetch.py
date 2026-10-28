"""Public HTTP(S) only, with DNS pinning and a hard outer worker deadline."""
import base64
import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import sys
from time import monotonic
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

MAX_BYTES = 1048576
MAX_REDIRECTS = 3


def validate_url(url, resolver=socket.getaddrinfo):
    if not isinstance(url, str) or len(url) > 2048 or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError('Invalid URL')
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Only public HTTP(S) URLs without credentials are supported')
        host = parsed.hostname.rstrip('.').encode('idna').decode('ascii')
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if port not in (80, 443):
            raise ValueError('Only ports 80 and 443 are supported')
        addresses = {row[4][0] for row in resolver(host, port, type=socket.SOCK_STREAM)}
        if not addresses or any((not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast) for address in addresses):
            raise ValueError('URL must resolve exclusively to public addresses')
    except (UnicodeError, OSError) as error:
        raise ValueError('URL host could not be validated') from error
    return parsed, host, port, sorted(addresses)[0]


class PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, secure, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address, self.secure = address, secure

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)
        if self.secure:
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)


def fetch_public(url, resolver=socket.getaddrinfo, factory=PinnedConnection):
    deadline = monotonic() + 10
    for hop in range(MAX_REDIRECTS + 1):
        parsed, host, port, address = validate_url(url, resolver)
        target = quote(parsed.path or '/', safe='/%:@!$&\'()*+,;=-._~')
        if parsed.query:
            target += '?' + quote(parsed.query, safe='/%:@!$&\'()*+,;=?-._~')
        connection = factory(host, port, address, parsed.scheme == 'https', max(.01, min(5, deadline - monotonic())))
        try:
            connection.request('GET', target, headers={'Host': host, 'User-Agent': 'AtlasResearch/0.1',
                                'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location or hop == MAX_REDIRECTS:
                    raise ValueError('Too many or invalid redirects')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError('Web server did not return a document')
            mime = (response.getheader('Content-Type') or '').split(';')[0].lower().strip()
            if mime not in ('text/html', 'text/plain') or response.getheader('Content-Encoding', 'identity') != 'identity':
                raise ValueError('Only uncompressed HTML or plain text is supported')
            length = response.getheader('Content-Length')
            if length and (not length.isdigit() or int(length) > MAX_BYTES):
                raise ValueError('Web document exceeds 1 MiB')
            chunks, size = [], 0
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise ValueError('Fetch deadline exceeded')
                connection.sock.settimeout(min(5, remaining))
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('Web document exceeds 1 MiB')
                chunks.append(chunk)
            final_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
            return {'url': final_url, 'content_type': mime, 'data': base64.b64encode(b''.join(chunks)).decode('ascii')}
        finally:
            connection.close()
    raise ValueError('Fetch failed')


def fetch_web(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Invalid URL')
    try:
        result = subprocess.run([sys.executable, '-m', 'atlas.web_fetch'], input=url.encode(),
                                capture_output=True, timeout=15, check=True)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError):
        raise ValueError('Cannot fetch this public URL within limits') from None


if __name__ == '__main__':
    try:
        print(json.dumps(fetch_public(sys.stdin.buffer.read(8193).decode())))
    except Exception:
        sys.exit(1)
