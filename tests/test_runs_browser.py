import pytest
from tests.test_browser import browser_page, create_workspace  # noqa: F401
pytestmark = [pytest.mark.database, pytest.mark.browser]


def test_planned_run_progress_reopen_and_controls(browser_page):
    from playwright.sync_api import expect
    page, app = browser_page
    create_workspace(page)
    page.locator('#run-objective').fill('unknown evidence <img>')
    page.locator('#run-objective').press('Enter')
    expect(page.locator('#run-detail')).to_contain_text('Run status: queued')
    page.get_by_role('button', name='Plan saved-evidence steps', exact=True).click()
    expect(page.locator('#run-detail article')).to_have_count(3)
    for position, kind in enumerate(['search', 'answer', 'verify'], 1):
        page.get_by_role('button', name='Run next task', exact=True).click()
        expect(page.locator('#run-detail')).to_contain_text(f'{position}. {kind}: completed')
    expect(page.locator('#run-detail')).to_contain_text('Run status: completed')
    expect(page.locator('#run-events')).to_contain_text('task_completed')
    page.reload()
    expect(page.locator('#run-detail')).to_contain_text('Run status: completed')
    page.locator('#run-detail a').first.click()
    expect(page.locator('#answer')).to_contain_text('Insufficient evidence')
    assert app.state.test_provider.calls == 0
    assert page.locator('#view-title img').count() == 0


def test_resumed_run_reconnects_progress_stream(browser_page):
    from playwright.sync_api import expect
    page, _ = browser_page
    create_workspace(page)
    page.locator('#run-use-memory').check()
    page.locator('#run-objective').fill('unmatched')
    page.locator('#run-objective').press('Enter')
    page.get_by_role('button', name='Cancel run', exact=True).click()
    expect(page.locator('#run-detail')).to_contain_text('Run status: cancelled')
    expect(page.locator('#run-detail')).to_contain_text('Research memory: enabled')
    page.get_by_role('button', name='Resume run', exact=True).click()
    expect(page.locator('#run-detail')).to_contain_text('Run status: queued')
    page.get_by_role('button', name='Run next task', exact=True).click()
    expect(page.locator('#run-detail')).to_contain_text('Run status: completed')
    expect(page.locator('#run-events')).to_contain_text('task_completed')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
