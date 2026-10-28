import pytest
from tests.test_browser import browser_page, prepare_evidence, ask  # noqa: F401
pytestmark = [pytest.mark.database, pytest.mark.browser]


def test_memory_and_open_question_history(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    prepare_evidence(page)
    ask(page)
    page.get_by_role('button', name='Save claims to memory', exact=True).click()
    expect(page.locator('#answer')).to_contain_text('1 interpretations saved')
    page.get_by_role('link', name='Workspace history').click()
    expect(page.locator('#memory-list')).to_contain_text('Generated interpretation · active')
    page.locator('#memory-list button').first.click()
    expect(page.locator('#evidence-dialog pre')).to_contain_text('evidence <script>')
    page.keyboard.press('Escape')
    page.locator('#open-question').fill('Unknown <img> question')
    page.get_by_role('button', name='Save open question', exact=True).click()
    expect(page.locator('#open-questions article')).to_have_count(1)
    page.locator('#open-questions article input').fill('Resolved <script> note')
    page.get_by_role('button', name='Resolve question', exact=True).click()
    expect(page.locator('#open-questions')).to_contain_text('resolved: Resolved <script> note')
    page.reload()
    expect(page.locator('#memory-list')).to_contain_text('Generated interpretation')
    expect(page.locator('#open-questions')).to_contain_text('Resolved <script> note')
    assert page.locator('#memory img, #open-questions img, #open-questions script').count() == 0
