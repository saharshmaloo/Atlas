import base64
from types import SimpleNamespace

import pytest
from atlas.web_fetch import fetch_public, validate_url


def resolve(address):
    return lambda *args, **kwargs: [(None, None, None, None, (address, 443))]


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', 'fc00::1', '::ffff:127.0.0.1', '0.0.0.0', '224.0.0.1'])
def test_blocks_nonpublic_addresses(address):
    with pytest.raises(ValueError):
        validate_url('https://example.org/', resolve(address))


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://u:p@example.org', 'http://example.org:22', 'https://example.org/\n', 'http://[bad'])
def test_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_url(url, resolve('93.184.216.34'))


def test_rejects_mixed_dns_answers():
    def mixed(*args, **kwargs):
        return resolve('93.184.216.34')() + resolve('10.0.0.1')()
    with pytest.raises(ValueError):
        validate_url('https://example.org', mixed)


def test_pins_address_and_revalidates_redirects():
    connections = []
    class Connection:
        sock = SimpleNamespace(settimeout=lambda timeout: None)
        def __init__(self, host, port, address, secure, timeout):
            connections.append((host, address, secure))
        def request(self, method, path, headers):
            assert headers['Host'] == 'example.org'
        def getresponse(self):
            return SimpleNamespace(status=302, getheader=lambda key: 'http://private.local')
        def close(self): pass
    def resolver(host, *args, **kwargs):
        return resolve('10.0.0.1' if host == 'private.local' else '93.184.216.34')()
    with pytest.raises(ValueError, match='public'):
        fetch_public('https://example.org', resolver, Connection)
    assert connections == [('example.org', '93.184.216.34', True)]


def test_stream_size_and_response_type_limits():
    class Connection:
        sock = SimpleNamespace(settimeout=lambda timeout: None)
        def __init__(self, *args): pass
        def request(self, *args, **kwargs): pass
        def close(self): pass
        def getresponse(self):
            chunks = iter([b'hello', b''])
            return SimpleNamespace(status=200, getheader=lambda key, default=None: {'Content-Type': mime}.get(key, default),
                                   read1=lambda size: next(chunks))
    mime = 'text/html'
    result = fetch_public('https://example.org', resolve('93.184.216.34'), Connection)
    assert base64.b64decode(result['data']) == b'hello'
    mime = 'application/pdf'
    with pytest.raises(ValueError):
        fetch_public('https://example.org', resolve('93.184.216.34'), Connection)


def test_pinned_tls_uses_validated_ip_and_original_server_name(monkeypatch):
    from atlas.web_fetch import PinnedConnection
    calls = []
    sock = object()
    monkeypatch.setattr('atlas.web_fetch.socket.create_connection', lambda endpoint, timeout: calls.append(endpoint) or sock)
    monkeypatch.setattr('atlas.web_fetch.ssl.create_default_context', lambda: SimpleNamespace(
        wrap_socket=lambda raw, server_hostname: calls.append(server_hostname) or raw))
    connection = PinnedConnection('example.org', 443, '93.184.216.34', True, 5)
    connection.connect()
    assert calls == [('93.184.216.34', 443), 'example.org']


def test_redirect_loop_and_unbounded_stream_are_rejected():
    class Connection:
        sock = SimpleNamespace(settimeout=lambda timeout: None)
        def __init__(self, *args): pass
        def request(self, *args, **kwargs): pass
        def close(self): pass
        def getresponse(self):
            return response
    response = SimpleNamespace(status=302, getheader=lambda key, default=None: '/again')
    with pytest.raises(ValueError, match='redirects'):
        fetch_public('https://example.org', resolve('93.184.216.34'), Connection)
    response = SimpleNamespace(status=200, getheader=lambda key, default=None: {'Content-Type': 'text/plain'}.get(key, default),
                               read1=lambda size: b'x' * size)
    with pytest.raises(ValueError, match='1 MiB'):
        fetch_public('https://example.org', resolve('93.184.216.34'), Connection)
