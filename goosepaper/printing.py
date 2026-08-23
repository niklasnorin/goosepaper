"""Send a rendered paper to a network printer with IPP (AirPrint).

Most modern home printers — including the Canon TS5350a — speak IPP over the
local network. They typically accept Apple Raster (`image/urf`) or PWG Raster,
not PDF, so Goosepaper rasterizes the rendered paper before sending it. No CUPS
or other print spooler is required.
"""

import struct
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import requests

from .config import PrintSettings
from .raster import RasterError, URF_CONTENT_TYPE, rasterize_pdf

DEFAULT_IPP_PORT = 631
DEFAULT_IPP_PATH = "/ipp/print"
IPP_CONTENT_TYPE = "application/ipp"
IPP_VERSION = (1, 1)
IPP_PRINT_JOB_OPERATION = 0x0002
IPP_REQUEST_TIMEOUT_SECONDS = 180

_OPERATION_ATTRIBUTES_TAG = 0x01
_JOB_ATTRIBUTES_TAG = 0x02
_END_OF_ATTRIBUTES_TAG = 0x03

_TAG_INTEGER = 0x21
_TAG_URI = 0x45
_TAG_KEYWORD = 0x44
_TAG_NAME = 0x42
_TAG_CHARSET = 0x47
_TAG_NATURAL_LANGUAGE = 0x48
_TAG_MIME_MEDIA_TYPE = 0x49

_DOCUMENT_FORMATS = {
    ".pdf": URF_CONTENT_TYPE,
    ".ps": "application/postscript",
    ".txt": "text/plain",
}

_IPP_STATUS_NAMES = {
    0x0000: "successful-ok",
    0x0400: "client-error-bad-request",
    0x0401: "client-error-forbidden",
    0x0406: "client-error-not-found",
    0x040A: "client-error-document-format-not-supported",
    0x040B: "client-error-attributes-or-values-not-supported",
    0x0410: "client-error-compression-error",
    0x0411: "client-error-document-format-error",
    0x0412: "client-error-document-access-error",
    0x0500: "server-error-internal-error",
    0x0501: "server-error-operation-not-supported",
    0x0502: "server-error-service-unavailable",
    0x0506: "server-error-not-accepting-jobs",
    0x0507: "server-error-busy",
}


class PrintError(RuntimeError):
    """Raised when a paper cannot be sent to the printer."""


def normalize_printer_uri(printer: str) -> str:
    """Expand a user-supplied printer address into a full IPP URI.

    Accepts bare hostnames or IPs (`192.168.1.42`, `TS5350a.local`) as well as
    complete `ipp://`, `ipps://`, `http://`, and `https://` URIs.
    """
    if not isinstance(printer, str) or not printer.strip():
        raise PrintError("The printer address must be a non-empty string.")

    candidate = printer.strip()
    if "://" not in candidate:
        candidate = f"ipp://{candidate}"

    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in {"ipp", "ipps", "http", "https"}:
        raise PrintError(
            f'Unsupported printer URI scheme "{parts.scheme}". '
            "Use ipp://, ipps://, http://, or https://."
        )
    if not parts.hostname:
        raise PrintError(f"Couldn't find a printer hostname in {printer!r}.")

    netloc = parts.netloc
    if parts.port is None:
        netloc = f"{netloc}:{DEFAULT_IPP_PORT}"

    path = parts.path or DEFAULT_IPP_PATH
    if path == "/":
        path = DEFAULT_IPP_PATH

    return urlunsplit((scheme, netloc, path, "", ""))


def _http_url_for(printer_uri: str) -> str:
    parts = urlsplit(printer_uri)
    scheme = {"ipp": "http", "ipps": "https"}.get(parts.scheme, parts.scheme)
    return urlunsplit((scheme, parts.netloc, parts.path, "", ""))


def _document_format_for(suffix: str) -> str:
    try:
        return _DOCUMENT_FORMATS[suffix.lower()]
    except KeyError:
        raise PrintError(
            f'Goosepaper can\'t print "{suffix}" files. '
            "Render a PDF (or another printer-friendly format) instead."
        ) from None


def prepare_print_document(filepath, settings: PrintSettings) -> Tuple[bytes, str]:
    """Return `(payload, document-format)` for an IPP Print-Job request.

    PDFs are rasterized to Apple Raster because most AirPrint printers reject
    `application/pdf` with IPP status 0x040a.
    """
    path = Path(filepath)
    suffix = path.suffix.lower()
    document_format = _document_format_for(suffix)
    if suffix == ".pdf":
        try:
            return rasterize_pdf(path, settings), document_format
        except RasterError as err:
            raise PrintError(str(err)) from err
    return path.read_bytes(), document_format


def describe_ipp_status(status_code: int) -> str:
    name = _IPP_STATUS_NAMES.get(status_code)
    if name:
        return f"0x{status_code:04x} {name}"
    return f"0x{status_code:04x}"


def _encode_attribute(tag: int, name: str, value: bytes) -> bytes:
    name_bytes = name.encode("utf-8")
    return (
        struct.pack(">B", tag)
        + struct.pack(">H", len(name_bytes))
        + name_bytes
        + struct.pack(">H", len(value))
        + value
    )


def _encode_text_attribute(tag: int, name: str, value: str) -> bytes:
    return _encode_attribute(tag, name, value.encode("utf-8"))


def _encode_integer_attribute(name: str, value: int) -> bytes:
    return _encode_attribute(_TAG_INTEGER, name, struct.pack(">i", value))


def build_print_job_request(
    printer_uri: str,
    payload: bytes,
    job_name: str,
    settings: PrintSettings,
    requesting_user: str = "goosepaper",
    document_format: str = "application/pdf",
    request_id: int = 1,
) -> bytes:
    """Build the raw bytes of an IPP Print-Job request."""
    message = struct.pack(">BBHI", IPP_VERSION[0], IPP_VERSION[1], IPP_PRINT_JOB_OPERATION, request_id)

    message += struct.pack(">B", _OPERATION_ATTRIBUTES_TAG)
    message += _encode_text_attribute(_TAG_CHARSET, "attributes-charset", "utf-8")
    message += _encode_text_attribute(
        _TAG_NATURAL_LANGUAGE, "attributes-natural-language", "en-us"
    )
    message += _encode_text_attribute(_TAG_URI, "printer-uri", printer_uri)
    message += _encode_text_attribute(
        _TAG_NAME, "requesting-user-name", requesting_user
    )
    message += _encode_text_attribute(_TAG_NAME, "job-name", job_name)
    message += _encode_text_attribute(
        _TAG_MIME_MEDIA_TYPE, "document-format", document_format
    )

    message += struct.pack(">B", _JOB_ATTRIBUTES_TAG)
    message += _encode_integer_attribute("copies", settings.copies)
    message += _encode_text_attribute(_TAG_KEYWORD, "sides", settings.sides)
    message += _encode_text_attribute(
        _TAG_KEYWORD, "print-color-mode", settings.color_mode
    )
    if settings.media:
        message += _encode_text_attribute(_TAG_KEYWORD, "media", settings.media)

    message += struct.pack(">B", _END_OF_ATTRIBUTES_TAG)
    return message + payload


def parse_ipp_status_code(response_body: bytes) -> int:
    """Pull the status code out of an IPP response."""
    if len(response_body) < 8:
        raise PrintError("The printer sent back a response Goosepaper couldn't read.")
    return struct.unpack(">H", response_body[2:4])[0]


def print_paper(
    filepath,
    print_settings: PrintSettings,
    showconfig: bool = False,
    session: Optional[object] = None,
) -> bool:
    """Send `filepath` to the configured printer.

    Returns True when the printer accepted the job.
    """
    if print_settings is None or not print_settings.printer:
        raise PrintError(
            "No printer configured. Set printing.printer in your paper config, "
            "print_defaults.printer in your user config, or pass '--printer'."
        )

    filepath = Path(filepath)
    resolved = filepath.resolve()
    if not resolved.is_file():
        raise PrintError(f"Error locating or opening {filepath} for printing.")

    printer_uri = normalize_printer_uri(print_settings.printer)
    payload, document_format = prepare_print_document(resolved, print_settings)

    if showconfig:
        print(f"Printing to {printer_uri} as {document_format}.")

    request_body = build_print_job_request(
        printer_uri=printer_uri,
        payload=payload,
        job_name=filepath.stem,
        settings=print_settings,
        document_format=document_format,
    )

    http = session if session is not None else requests
    try:
        response = http.post(
            _http_url_for(printer_uri),
            data=request_body,
            headers={"Content-Type": IPP_CONTENT_TYPE},
            timeout=IPP_REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as err:
        raise PrintError(f"Couldn't reach the printer at {printer_uri}: {err}") from err

    if response.status_code != 200:
        raise PrintError(
            f"The printer at {printer_uri} responded with HTTP {response.status_code}."
        )

    status_code = parse_ipp_status_code(response.content)
    if status_code >= 0x0100:
        raise PrintError(
            f"The printer rejected the job (IPP status {describe_ipp_status(status_code)})."
        )

    print("Honk! Sent to the printer!")
    return True
