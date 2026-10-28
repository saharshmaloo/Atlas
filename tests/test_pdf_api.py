import pytest
from tests.test_pdf_extract import pdf_bytes
pytestmark = pytest.mark.database


def test_pdf_upload_original_page_search_provenance_and_scoping(client):
    ws = client.post('/workspaces', json={'name': 'PDF'}).json()['id']
    base = f'/workspaces/{ws}/sources'
    data = pdf_bytes()
    response = client.post(f'{base}/pdf', files={'file': ('paper.pdf', data)})
    assert response.status_code == 201
    source = response.json()
    assert source['kind'] == 'pdf' and len(source['locations']) == 2
    url = f"{base}/{source['id']}"
    assert client.get(f'{url}/original').content == data
    assert client.post(f'{url}/passages').status_code == 200
    result = client.get(f'/workspaces/{ws}/search', params={'q': 'backups'}).json()[0]
    assert result['source_kind'] == 'pdf' and result['source_version'] == 1
    assert result['locations'][-1]['page'] == 2
    other = client.post('/workspaces', json={'name': 'Other'}).json()['id']
    assert client.get(f'{url}/original'.replace(ws, other)).status_code == 404
    assert client.post(f'{base}/pdf', files={'file': ('bad.pdf', b'%PDF-broken')}).status_code == 422
    assert len(client.get(base).json()) == 1


def test_pdf_versions_preserve_both_original_files(client):
    ws = client.post('/workspaces', json={'name': 'PDF versions'}).json()['id']
    base = f'/workspaces/{ws}/sources'
    first_data, second_data = pdf_bytes(('Original text.',)), pdf_bytes(('Revised text.',))
    first = client.post(f'{base}/pdf', files={'file': ('v1.pdf', first_data)}).json()
    second = client.post(f"{base}/pdf?previous_source_id={first['id']}", files={'file': ('v2.pdf', second_data)}).json()
    assert second['document_id'] == first['document_id'] and second['version'] == 2
    assert client.get(f"{base}/{first['id']}/original").content == first_data
    assert client.get(f"{base}/{second['id']}/original").content == second_data
    assert client.post(f"{base}/{first['id']}/versions", files={'file': ('wrong.txt', b'text')}).status_code == 409
