import pytest
from tests.test_browser import browser_page, create_workspace, open_source, ask  # noqa: F401
from tests.test_vector_search import SemanticFake
from atlas.embeddings import get_embedding_provider
from atlas.hybrid import get_embedding_factory
pytestmark = [pytest.mark.database, pytest.mark.browser]


def test_optional_hybrid_browser_flow(browser_page):
    from playwright.sync_api import expect
    page, app = browser_page
    app.dependency_overrides[get_embedding_provider] = SemanticFake
    app.dependency_overrides[get_embedding_factory] = lambda: SemanticFake
    create_workspace(page)
    open_source(page, 'Cats rest.')
    page.get_by_role('button', name='Generate passages', exact=True).click()
    expect(page.locator('#passages article')).to_have_count(1)
    page.get_by_role('link', name='Workspace sources').click()
    page.get_by_role('button', name='Generate embeddings', exact=True).click()
    expect(page.locator('#embedding-controls')).to_contain_text('Complete')
    page.locator('#search-query').fill('feline')
    page.locator('#search-retrieval').select_option('hybrid')
    page.locator('#search-query').press('Enter')
    expect(page.locator('#search-results article')).to_have_count(1)
    page.locator('#search-results a').click()
    page.get_by_role('link', name='Workspace sources').click()
    expect(page.locator('#search-retrieval')).to_have_value('hybrid')
    page.locator('#question-retrieval').select_option('hybrid')
    ask(page, 'feline')
    expect(page.locator('#answer .claim')).to_have_count(1)
    expect(page.locator('#answer')).to_contain_text('hybrid-rrf60-v1')
