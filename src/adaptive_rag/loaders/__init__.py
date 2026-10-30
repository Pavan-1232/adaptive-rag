"""Document loaders. To add a format, implement Loader and register it here."""

from .base import ExtractedDocument, ExtractionError, Loader, Section, Unit
from .docx import DocxLoader
from .pdf import PdfLoader
from .txt import TxtLoader
from .validation import UploadRejected, validate_upload

LOADERS: dict[str, Loader] = {"pdf": PdfLoader(), "docx": DocxLoader(), "txt": TxtLoader()}

__all__ = [
    "LOADERS",
    "ExtractedDocument",
    "ExtractionError",
    "Loader",
    "Section",
    "Unit",
    "UploadRejected",
    "validate_upload",
]
