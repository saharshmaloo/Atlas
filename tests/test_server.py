"""Exercise the installed package through a real Uvicorn process and TCP socket."""

import json
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest


def test_installed_app_serves_health_over_http(tmp_path):
    # Pass a bound socket to Uvicorn to avoid a race when choosing a free port.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "atlas.main:app",
                "--fd", str(listener.fileno()),
            ],
            pass_fds=(listener.fileno(),),
            cwd=tmp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(f"Server exited early:\n{process.stdout.read()}")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                        assert response.status == 200
                        assert response.headers.get_content_type() == "application/json"
                        assert json.load(response) == {"status": "ok"}
                    break
                except (URLError, TimeoutError):
                    time.sleep(0.05)
            else:
                pytest.fail("Server did not become ready within 10 seconds")
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
