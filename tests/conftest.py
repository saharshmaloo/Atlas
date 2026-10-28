import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from atlas.main import create_app


@pytest.fixture
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    # Never migrate or clear the supplied database: create and drop our own.
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    name = f"atlas_test_{uuid4().hex}"
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    test_url = make_url(url).set(database=name)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = test_url
    try:
        command.upgrade(config, "head")
        yield test_url, config
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def client(database):
    with TestClient(create_app(database[0])) as client:
        yield client


def pytest_sessionfinish(session, exitstatus):
    """CI must never report success by silently skipping integration checks."""
    if os.environ.get('STRICT_TESTS') == '1':
        reporter = session.config.pluginmanager.get_plugin('terminalreporter')
        if reporter and reporter.stats.get('skipped'):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
