import base64
import pytest
from tests.test_browser import browser_page, create_workspace  # noqa: F401
from atlas.web_ingest import get_web_fetcher
pytestmark = [pytest.mark.database, pytest.mark.browser]


def test_web_upload_error_recovery_and_provenance(browser_page):
    from playwright.sync_api import expect
    page, app = browser_page
    create_workspace(page)
    def bad(url): raise ValueError('private')
    app.dependency_overrides[get_web_fetcher] = lambda: bad
    page.locator('#web-url').fill('https://example.org')
    page.locator('#web-url').press('Enter')
    expect(page.locator('#web-upload')).to_contain_text('Cannot ingest')
    app.dependency_overrides[get_web_fetcher] = lambda: lambda url: {
        'url': 'https://example.org/final', 'content_type': 'text/html',
        'data': base64.b64encode(b'<title>Web evidence</title><p>Transactions</p>').decode()}
    page.get_by_role('button', name='Save webpage', exact=True).click()
    page.locator('#source-list a').click()
    expect(page.locator('#research')).to_contain_text('https://example.org/final')
    expect(page.locator('#source-text')).to_have_text('Transactions')
