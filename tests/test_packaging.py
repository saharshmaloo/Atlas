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
        assert {'atlas/static/index.html', 'atlas/static/style.css', 'atlas/static/app.js'} <= set(archive.namelist())
    target = tmp_path / 'installed'
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--target', str(target), str(wheel)],
                   check=True, capture_output=True)
    subprocess.run([sys.executable, '-c', '''
from fastapi.testclient import TestClient
from atlas.main import create_app
with TestClient(create_app()) as client:
    for path in ('/', '/assets/app.js', '/assets/style.css'):
        assert client.get(path).status_code == 200
'''], cwd=tmp_path, env={**os.environ, 'PYTHONPATH': str(target)}, check=True, capture_output=True)
