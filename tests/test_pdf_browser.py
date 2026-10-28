import pytest
from tests.test_browser import browser_page, create_workspace, upload  # noqa: F401
from tests.test_pdf_extract import pdf_bytes
pytestmark = [pytest.mark.database, pytest.mark.browser]


def test_pdf_browser_upload_and_page_provenance(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    create_workspace(page)
    upload(page, pdf_bytes(), 'paper.pdf')
    page.locator('#source-list a').click()
    expect(page.locator('#research')).to_contain_text('page 2:')
    expect(page.locator('#source-text')).to_contain_text('Backups preserve evidence.')
    page.get_by_role('button', name='Generate passages', exact=True).click()
    expect(page.locator('#passages article')).to_have_count(1)
