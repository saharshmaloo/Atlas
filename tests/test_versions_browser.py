import pytest
from tests.test_browser import browser_page, create_workspace, open_source  # noqa: F401
pytestmark = [pytest.mark.database, pytest.mark.browser]


def test_browser_versions_preserve_original_source(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    create_workspace(page)
    original = open_source(page, 'Original evidence 😀\r\n')
    old_url = page.url
    page.locator('#version-file').set_input_files({'name': 'revision.txt', 'mimeType': 'text/plain', 'buffer': b'Revised evidence'})
    page.get_by_role('button', name='Upload new version', exact=True).click()
    expect(page.locator('#source-text')).to_have_text('Revised evidence')
    assert page.url != old_url
    page.get_by_role('link', name='Version 1: notes.txt', exact=True).click()
    expect(page.locator('#source-text')).to_have_text(original)
    assert page.locator('#source-text').text_content() == original
    expect(page.locator('#version-list a')).to_have_count(2)
