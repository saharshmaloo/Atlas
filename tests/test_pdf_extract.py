import io
import subprocess

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas
from atlas.pdf_extract import extract_pdf


def pdf_bytes(texts=('Transactions use logs.', 'Backups preserve evidence.')):
    stream = io.BytesIO()
    canvas = Canvas(stream)
    for text in texts:
        if text:
            canvas.drawString(72, 720, text)
        canvas.showPage()
    canvas.save()
    return stream.getvalue()


def test_pdf_extraction_retains_page_spans():
    result = extract_pdf(pdf_bytes())
    assert len(result['locations']) == 2
    for location, expected in zip(result['locations'], ['Transactions use logs.', 'Backups preserve evidence.']):
        assert result['text'][location['start_char']:location['end_char']].strip() == expected
    assert result['extractor'] == 'pypdf-v1'


@pytest.mark.parametrize('data', [b'not a PDF', b'%PDF-broken', b'%PDF-' + b'x' * 1048576])
def test_malformed_and_oversized_pdf(data):
    with pytest.raises(ValueError):
        extract_pdf(data)


def test_image_only_and_encrypted_pdf():
    with pytest.raises(ValueError):
        extract_pdf(pdf_bytes(('',)))
    writer = PdfWriter(); writer.add_blank_page(612, 792); writer.encrypt('password')
    stream = io.BytesIO(); writer.write(stream)
    with pytest.raises(ValueError):
        extract_pdf(stream.getvalue())


def test_timeout_is_bounded_and_sanitized(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('secret', 10)
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(ValueError, match='within limits'):
        extract_pdf(pdf_bytes())
