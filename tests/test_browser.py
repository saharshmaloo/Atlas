"""Real Chromium + HTTP + disposable PostgreSQL; no live model calls."""
import os
import socket
import threading
import time

import pytest
import uvicorn

from atlas.main import create_app

pytestmark = pytest.mark.database


@pytest.fixture
def browser_page(database):
    if os.environ.get('RUN_BROWSER_TESTS') != '1':
        pytest.skip('Set RUN_BROWSER_TESTS=1 and install .[browser] plus Chromium')
    from playwright.sync_api import sync_playwright

    app = create_app(database[0])
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(128)
        base = f'http://127.0.0.1:{listener.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', ws='none'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline
                time.sleep(.01)
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(base_url=base, viewport={'width': 390, 'height': 844})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                try:
                    yield page, app
                    assert not errors
                finally:
                    browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


def create_workspace(page, name='Browser research'):
    page.goto('/')
    page.locator('#new-workspace').click()
    page.locator('#workspace-name').fill(name)
    page.locator('#workspace-name').press('Enter')
    page.locator('#detail').wait_for(state='visible')


def test_workspace_mobile_navigation(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    create_workspace(page, '<b>Research</b>')
    expect(page.locator('#view-title')).to_have_text('<b>Research</b>')
    page.reload()
    expect(page.locator('#view-title')).to_have_text('<b>Research</b>')
    page.get_by_role('link', name='All workspaces').click()
    page.get_by_role('link', name='<b>Research</b>').click()
    expect(page.locator('#detail')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#new-workspace').click()
    page.keyboard.press('Escape')
    expect(page.locator('#create-dialog')).not_to_be_visible()
    page.locator('#skip').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#main')).to_be_focused()
