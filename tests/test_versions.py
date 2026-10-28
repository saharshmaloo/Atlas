from concurrent.futures import ThreadPoolExecutor
import pytest
pytestmark = pytest.mark.database


def test_versions_are_immutable_concurrent_and_scoped(client):
    ws = client.post('/workspaces', json={'name': 'Versions'}).json()['id']
    base = f'/workspaces/{ws}/sources'
    first = client.post(base, files={'file': ('v1.txt', '😀 original\r\n'.encode())}).json()
    assert first['kind'] == 'text' and first['version'] == 1
    url = f"{base}/{first['id']}/versions"
    def upload(i):
        return client.post(url, files={'file': ('next.txt', f'Version {i}'.encode())})
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(upload, range(2)))
    assert all(row.status_code == 201 for row in results)
    assert {row.json()['version'] for row in results} == {2, 3}
    assert {row.json()['document_id'] for row in results} == {first['document_id']}
    assert client.get(f"{base}/{first['id']}/content").text == '😀 original\r\n'
    assert [row['version'] for row in client.get(url).json()] == [1, 2, 3]
    other = client.post('/workspaces', json={'name': 'Other'}).json()['id']
    assert client.get(url.replace(ws, other)).status_code == 404
    assert client.post(url.replace(ws, other), files={'file': ('a.txt', b'foreign')}).status_code == 404
