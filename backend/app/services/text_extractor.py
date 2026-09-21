"""
AI Workspace Platform - Text Extractor
Extracts readable text from uploaded project files so it can be injected
into AI completion context.

Supported formats:
  - Plain text  (.txt, .md, .py, .js, .ts, etc.) — read as UTF-8
  - JSON        (.json)                           — pretty-printed
  - PDF         (application/pdf)                 — pdfplumber > pypdf, if installed
  - DOCX        (.docx/.doc)                      — python-docx if installed
  - Binary      (everything else)                 — returns informational placeholder
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)

# Hard cap to keep context windows sane (chars, not tokens)
MAX_CHARS = 8_000


def extract_text(file_path: Path, mime_type: str) -> str:
    """
    Return up to MAX_CHARS of readable text from *file_path*.
    Never raises — on any error it returns a short description instead.
    """
    try:
        return _extract(file_path, mime_type)[:MAX_CHARS]
    except Exception as exc:
        _log.warning("text_extractor failed for %s: %s", file_path, exc)
        return f"[Could not extract text from {file_path.name}: {exc}]"


def _extract(path: Path, mime: str) -> str:
    mime = (mime or "").lower()

    # --- JSON (pretty-print) ---
    if path.suffix.lower() == ".json" or mime == "application/json":
        return _read_json(path)

    # --- Plain text ---
    if mime.startswith("text/") or path.suffix.lower() in {
        ".txt", ".md", ".csv", ".log", ".yaml", ".yml",
        ".xml", ".html", ".htm", ".py", ".js", ".ts", ".css",
        ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php",
        ".sh", ".bat", ".ini", ".toml", ".conf",
    }:
        return _read_text(path)

    # --- PDF ---
    if mime == "application/pdf" or path.suffix.lower() == ".pdf":
        return _read_pdf(path)

    # --- DOCX ---
    if "wordprocessingml" in mime or "openxmlformats" in mime or path.suffix.lower() in {".docx", ".doc"}:
        return _read_docx(path)

    # --- Binary / unknown ---
    return "[binary file, no text extracted]"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _read_json(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _read_text(path)


def _read_pdf(path: Path) -> str:
    # Try pdfplumber first (best quality)
    try:
        import pdfplumber  # type: ignore[import]
        with pdfplumber.open(path) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            return "\n".join(parts) or "[PDF: no extractable text found]"
    except ImportError:
        pass
    except Exception as exc:
        _log.debug("pdfplumber failed: %s", exc)

    # Fallback: pypdf (formerly PyPDF2)
    try:
        from pypdf import PdfReader  # type: ignore[import]
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n".join(parts) or "[PDF: no extractable text found]"
    except ImportError:
        pass
    except Exception as exc:
        _log.debug("pypdf failed: %s", exc)

    return f"[PDF: {path.name} — install pdfplumber or pypdf to extract text]"


def _read_docx(path: Path) -> str:
    try:
        from docx import Document  # type: ignore[import]
        doc = Document(str(path))
        return "\n".join(para.text for para in doc.paragraphs if para.text)
    except ImportError:
        return f"[DOCX: {path.name} — install python-docx to extract text]"
    except Exception as exc:
        return f"[DOCX: could not read {path.name}: {exc}]"
