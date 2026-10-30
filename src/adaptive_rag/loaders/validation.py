"""Upload validation. The extension alone is never trusted."""

import zipfile
from pathlib import Path

MAX_DOCX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
ALLOWED_FORMATS = {".pdf": "pdf", ".docx": "docx", ".txt": "txt"}


class UploadRejected(Exception):
    """The upload failed validation. The message is user-facing."""


def _check_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise UploadRejected("This file is not a valid DOCX file.") from exc
    if not any(info.filename == "word/document.xml" for info in infos):
        raise UploadRejected("This file is not a valid DOCX file.")
    if sum(info.file_size for info in infos) > MAX_DOCX_UNCOMPRESSED_BYTES:
        raise UploadRejected("This DOCX file is too large when uncompressed.")


def validate_upload(path: Path, filename: str, max_bytes: int) -> str:
    """Return the file's format, or raise UploadRejected."""
    file_format = ALLOWED_FORMATS.get(Path(filename).suffix.lower())
    if file_format is None:
        raise UploadRejected("Unsupported file type. Upload a PDF, DOCX, or TXT file.")
    size = path.stat().st_size
    if size == 0:
        raise UploadRejected("This file is empty.")
    if size > max_bytes:
        raise UploadRejected(f"This file is larger than the {max_bytes // (1024 * 1024)} MB limit.")

    with path.open("rb") as file:
        head = file.read(8192)
    if file_format == "pdf" and b"%PDF-" not in head[:1024]:
        raise UploadRejected("This file is not a valid PDF.")
    if file_format == "docx":
        _check_docx(path)
    if file_format == "txt" and b"\x00" in head:
        raise UploadRejected("This file looks binary, not plain text.")
    return file_format
