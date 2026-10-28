"""Build and install a wheel outside the checkout to verify packaged assets."""
import os
from pathlib import Path
import subprocess
import sys
import zipfile


def test_wheel_serves_packaged_ui(tmp_path):
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps',
                    '-w', str(tmp_path), str(root)], check=True, capture_output=True)
    wheel = next(tmp_path.glob('*.whl'))
    with zipfile.ZipFile(wheel) as archive:
        expected = {f'atlas/static/{path.name}' for path in (root / 'src/atlas/static').iterdir() if path.is_file()}
        assert expected <= set(archive.namelist())
    target = tmp_path / 'installed'
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--target', str(target), str(wheel)],
                   check=True, capture_output=True)
    subprocess.run([sys.executable, '-c', '''
import re
from fastapi.testclient import TestClient
from atlas.main import create_app
with TestClient(create_app()) as client:
    html = client.get('/')
    assert html.status_code == 200
    for path in re.findall(r'(?:src|href)="(/assets/[^"]+)"', html.text):
        assert client.get(path).status_code == 200
'''], cwd=tmp_path, env={**os.environ, 'PYTHONPATH': str(target)}, check=True, capture_output=True)
