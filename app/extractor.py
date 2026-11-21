import csv
import io
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

ALLOWED = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md"}


def extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if suffix == ".docx":
        doc = Document(path)
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
        return "\n".join(parts)
    if suffix == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        return "\n".join(" | ".join(str(v) for v in row if v is not None) for ws in workbook for row in ws.iter_rows(values_only=True))
    if suffix == ".csv":
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        return "\n".join(" | ".join(row) for row in csv.reader(io.StringIO(raw)))
    return path.read_text(encoding="utf-8-sig", errors="replace")


def chunk_text(text: str, size=900, overlap=120):
    clean = " ".join(text.split())
    if not clean:
        return []
    step = size - overlap
    return [clean[i:i + size] for i in range(0, len(clean), step)]
