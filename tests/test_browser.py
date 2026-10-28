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


def upload(page, content=b'Transactions preserve evidence.', name='notes.txt'):
    page.locator('#source-file').set_input_files({'name': name, 'mimeType': 'text/plain', 'buffer': content})
    page.get_by_role('button', name='Upload source', exact=True).click()


def test_upload_validation_and_persistence(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    create_workspace(page)
    expect(page.locator('#source-list')).to_contain_text('No sources yet')
    for content, message in [(b'', 'nonempty'), (b'x' * 1048577, 'at most 1 MiB'),
                             (b'\xff', 'UTF-8'), (b'   ', 'must contain text')]:
        upload(page, content)
        expect(page.locator('#research form')).to_contain_text(message)
    upload(page, name='<img>.txt')
    expect(page.locator('#source-list')).to_contain_text('<img>.txt')
    page.reload()
    expect(page.locator('#source-list')).to_contain_text('<img>.txt')
    assert page.locator('#source-list b').count() == 0


def test_upload_pending_navigation(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    create_workspace(page)
    page.route('**/sources', lambda route: None if route.request.method == 'POST' else route.continue_())
    upload(page)
    expect(page.get_by_role('button', name='Upload source', exact=True)).to_be_disabled()
    page.get_by_role('link', name='All workspaces').click()
    expect(page.locator('#library')).to_be_visible()
    create_workspace(page, 'Other workspace')
    expect(page.locator('#source-list')).to_contain_text('No sources yet')
    expect(page.get_by_role('button', name='Upload source', exact=True)).to_be_enabled()


def open_source(page, content='😀 Transactions\r\n\r\n  evidence <script>alert(1)</script>'):
    upload(page, content.encode())
    page.locator('#source-list a').first.click()
    page.locator('#source-text').wait_for()
    return content


def test_source_text_passages_and_refresh(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    create_workspace(page)
    content = open_source(page, '😀 Transactions\r\n\r\n  evidence <script>alert(1)</script>' + 'x' * 12000)
    assert page.locator('#source-text').text_content() == content
    expect(page.locator('#passages')).to_contain_text('No passages yet')
    page.get_by_role('button', name='Generate passages', exact=True).click()
    expect(page.locator('#passages article')).to_have_count(10)
    ids = page.locator('#passages article').evaluate_all('(items) => items.map(x => x.id)')
    page.get_by_role('button', name='Generate passages', exact=True).click()
    expect(page.locator('#research [role=status]')).to_contain_text('passages available')
    assert page.locator('#passages article').evaluate_all('(items) => items.map(x => x.id)') == ids
    page.get_by_role('button', name='Next passages', exact=True).click()
    expect(page.locator('#passages')).to_contain_text('Passage 11')
    page.reload()
    assert page.locator('#source-text').text_content() == content
    page.go_back()
    expect(page.locator('#source-list a')).to_have_count(1)
    page.go_forward()
    expect(page.locator('#source-text')).to_be_visible()
    page.goto(page.url.rsplit('/', 1)[0] + '/00000000-0000-0000-0000-000000000000')
    expect(page.locator('#notice')).to_contain_text('could not be found')


def test_source_stale_response(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    create_workspace(page)
    upload(page)
    page.route('**/content', lambda route: None)
    page.locator('#source-list a').click()
    expect(page.locator('#research')).to_contain_text('Loading source')
    page.get_by_role('link', name='All workspaces').click()
    expect(page.locator('#library')).to_be_visible()
