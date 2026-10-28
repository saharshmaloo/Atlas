from hashlib import sha256
from pathlib import PurePosixPath
from uuid import UUID
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from atlas.pdf_extract import extract_pdf
from atlas.sources import MAX_SOURCE_BYTES, Source, SourceResponse, find_source, require_workspace
from atlas.workspaces import DatabaseSession

router = APIRouter(prefix='/workspaces/{workspace_id}/sources', tags=['PDF'])


@router.post('/pdf', response_model=SourceResponse, status_code=201)
def upload_pdf(workspace_id: UUID, file: UploadFile, session: DatabaseSession):
    require_workspace(workspace_id, session)
    title = PurePosixPath((file.filename or '').replace('\\', '/')).name.strip()
    if not title.lower().endswith('.pdf') or len(title) > 200 or '\0' in title:
        raise HTTPException(422, 'Choose a PDF filename of at most 200 characters')
    data = file.file.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(413, 'PDF exceeds 1 MiB')
    session.rollback()  # Extraction runs without holding a database connection.
    try:
        result = extract_pdf(data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    source = Source(workspace_id=workspace_id, title=title, kind='pdf', content=result['text'],
                    content_hash=sha256(data).hexdigest(), original_data=data,
                    locations=result['locations'], extractor=result['extractor'])
    session.add(source); session.commit(); session.refresh(source)
    return source


@router.get('/{source_id}/original')
def download_original(workspace_id: UUID, source_id: UUID, session: DatabaseSession):
    source = find_source(workspace_id, source_id, session)
    data = source.original_data if source.kind == 'pdf' else source.content.encode('utf-8')
    return Response(data, media_type='application/pdf' if source.kind == 'pdf' else 'text/plain',
                    headers={'Content-Disposition': 'attachment; filename="source.pdf"' if source.kind == 'pdf' else 'attachment; filename="source.txt"'})
