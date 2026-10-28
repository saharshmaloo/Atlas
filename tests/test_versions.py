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


def test_duplicate_detection_preserves_distinct_versions_and_workspace_privacy(client):
    ws = client.post('/workspaces', json={'name': 'Duplicates'}).json()['id']
    base = f'/workspaces/{ws}/sources'
    def upload(url, content=b'same'):
        return client.post(url, files={'file': ('same.txt', content)}).json()
    first, second = upload(base), upload(base)
    third = upload(f"{base}/{first['id']}/versions")
    different = upload(base, b'different')
    other = client.post('/workspaces', json={'name': 'Other'}).json()['id']
    foreign = upload(base.replace(ws, other))
    duplicates = client.get(f"{base}/{first['id']}/duplicates").json()
    assert {row['id'] for row in duplicates} == {second['id'], third['id']}
    assert len({first['id'], second['id'], third['id']}) == 3
    assert different['id'] not in {row['id'] for row in duplicates}
    assert client.get(f"{base.replace(ws, other)}/{foreign['id']}/duplicates").json() == []
    assert client.get(f"{base.replace(ws, other)}/{first['id']}/duplicates").status_code == 404
