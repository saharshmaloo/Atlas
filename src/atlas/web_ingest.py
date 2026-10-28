import base64
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import re
from typing import Annotated, Callable
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from atlas.sources import Source, SourceResponse, assign_version, find_source, require_workspace
from atlas.web_fetch import fetch_web
from atlas.workspaces import DatabaseSession


class WebText(HTMLParser):
    blocked = {'script', 'style', 'noscript', 'template', 'svg'}
    boundaries = {'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'article', 'section', 'tr', 'td'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.titles, self.ignored = [], [], []
        self.in_title = self.in_head = False

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.ignored.append(tag)
        if tag == 'head': self.in_head = True
        if tag == 'title': self.in_title = True
        if not self.ignored and tag in self.boundaries: self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self.ignored:
            self.ignored = self.ignored[:self.ignored.index(tag)]
        if tag == 'head': self.in_head = False
        if tag == 'title': self.in_title = False
        if not self.ignored and tag in self.boundaries: self.parts.append('\n')

    def handle_data(self, data):
        if self.ignored: return
        if self.in_title: self.titles.append(data)
        elif not self.in_head: self.parts.append(data)


def extract_web(data, mime):
    try:
        decoded = data.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError('Web documents must use UTF-8') from None
    title = ''
    if mime == 'text/html':
        parser = WebText(); parser.feed(decoded); parser.close()
        decoded, title = ''.join(parser.parts), ' '.join(''.join(parser.titles).split())
        decoded = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', decoded).strip()
    if not decoded.strip() or '\0' in decoded or '\0' in title:
        raise ValueError('Web document contains no supported text')
    return decoded, title[:200]


class WebRequest(BaseModel):
    previous_source_id: UUID | None = None
    url: str = Field(min_length=1, max_length=2048)


def get_web_fetcher():
    return fetch_web


router = APIRouter(prefix='/workspaces/{workspace_id}/sources', tags=['web'])


@router.post('/web', response_model=SourceResponse, status_code=201)
def ingest_web(workspace_id: UUID, body: WebRequest, session: DatabaseSession,
               fetcher: Annotated[Callable, Depends(get_web_fetcher)]):
    require_workspace(workspace_id, session)
    previous = find_source(workspace_id, body.previous_source_id, session) if body.previous_source_id else None
    if previous and previous.kind != 'web': raise HTTPException(409, 'Previous source must be a webpage')
    session.rollback()
    try:
        result = fetcher(body.url)
        data = base64.b64decode(result['data'], validate=True)
        content, title = extract_web(data, result['content_type'])
    except (ValueError, OSError):
        raise HTTPException(422, 'Cannot ingest this URL: use a public UTF-8 HTML/text document of at most 1 MiB') from None
    source = Source(workspace_id=workspace_id, title=title or urlsplit(result['url']).hostname,
                    content=content, content_hash=sha256(data).hexdigest(), kind='web',
                    original_uri=result['url'], retrieved_at=datetime.now(timezone.utc),
                    extractor='html-text-v1', original_data=data)
    if previous: assign_version(source, previous, session)
    session.add(source); session.commit(); session.refresh(source)
    return source
