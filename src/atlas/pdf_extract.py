"""PDF extraction in a short-lived worker; offsets refer to extracted Unicode text."""
import io
import json
import subprocess
import sys

from pypdf import PdfReader

MAX_BYTES = 1048576
MAX_PAGES = 200
MAX_TEXT = 1048576


def extract_pages(data):
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or not 0 < len(reader.pages) <= MAX_PAGES:
        raise ValueError('Encrypted PDF or unsupported page count')
    content, locations = '', []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ''
        if '\0' in text or len(content) + len(text) + 3 > MAX_TEXT:
            raise ValueError('Unsupported extracted text')
        if number > 1:
            content += '\n\f\n'
        start = len(content)
        content += text
        locations.append({'page': number, 'start_char': start, 'end_char': len(content)})
    if not content.replace('\f', '').strip():
        raise ValueError('No extractable text; OCR is not supported')
    return {'text': content, 'locations': locations, 'extractor': 'pypdf-v1'}


def extract_pdf(data, timeout=10):
    if len(data) > MAX_BYTES or not data.startswith(b'%PDF-'):
        raise ValueError('PDF must be valid and at most 1 MiB')
    try:
        result = subprocess.run([sys.executable, '-m', 'atlas.pdf_extract'], input=data,
                                capture_output=True, timeout=timeout, check=True)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError):
        raise ValueError('PDF could not be extracted within limits; encrypted or image-only PDFs are unsupported') from None


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    try:
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('PDF too large')
        print(json.dumps(extract_pages(data)))
    except Exception:
        sys.exit(1)
