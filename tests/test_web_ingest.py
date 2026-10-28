import base64
from uuid import uuid4
import pytest
from atlas.web_ingest import extract_web, get_web_fetcher


def test_html_extraction_excludes_active_content_and_retains_unicode():
    text, title = extract_web(b'<head><title>A &amp; B</title><style>hidden</style></head><p>Caf\xc3\xa9</p><script>secret()</script><p>Evidence &lt;img&gt;</p>', 'text/html')
    assert title == 'A & B'
    assert 'Café' in text and 'Evidence <img>' in text
    assert 'hidden' not in text and 'secret' not in text
    with pytest.raises(ValueError): extract_web(b'<script>secret</script>', 'text/html')
    with pytest.raises(ValueError): extract_web(b'\xff', 'text/plain')


@pytest.mark.database
def test_ingest_persists_original_and_provenance_without_network(client):
    ws = client.post('/workspaces', json={'name': 'Web'}).json()['id']
    base = f'/workspaces/{ws}/sources'
    data = '<title>Page</title><p>Transactions Café 😀</p>'.encode()
    calls = []
    def fetch(url):
        calls.append(url)
        return {'url': 'https://example.org/final', 'content_type': 'text/html', 'data': base64.b64encode(data).decode()}
    client.app.dependency_overrides[get_web_fetcher] = lambda: fetch
    response = client.post(f'{base}/web', json={'url': 'https://example.org/start'})
    assert response.status_code == 201
    source = response.json()
    assert source['original_uri'] == 'https://example.org/final' and source['retrieved_at']
    assert source['kind'] == 'web' and source['extractor'] == 'html-text-v1'
    assert client.get(f"{base}/{source['id']}/original").content == data
    assert client.post(f"{base}/{source['id']}/passages").status_code == 200
    assert client.get(f'/workspaces/{ws}/search', params={'q': 'transactions'}).json()[0]['source_kind'] == 'web'
    assert client.post(f'/workspaces/{uuid4()}/sources/web', json={'url': 'https://example.org'}).status_code == 404
    assert len(calls) == 1
    def failure(url): raise ValueError('secret internal host')
    client.app.dependency_overrides[get_web_fetcher] = lambda: failure
    response = client.post(f'{base}/web', json={'url': 'http://localhost'})
    assert response.status_code == 422 and 'secret' not in response.text
    assert len(client.get(base).json()) == 1
