import struct
import tempfile
from pathlib import Path

import pytest

from .config import PrintSettings
from .printing import (
    PrintError,
    build_print_job_request,
    normalize_printer_uri,
    parse_ipp_status_code,
    print_paper,
)


class _Response:
    def __init__(self, status_code=200, content=None):
        self.status_code = status_code
        self.content = (
            content if content is not None else _ipp_response_bytes(0x0000)
        )


class _Session:
    def __init__(self, response=None):
        self.calls = []
        self._response = response or _Response()

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append((url, data, headers, timeout))
        return self._response


def _ipp_response_bytes(status_code: int) -> bytes:
    return struct.pack(">BBHI", 1, 1, status_code, 1) + b"\x03"


def _write_pdf(directory: Path) -> Path:
    path = directory / "Goosepaper.pdf"
    path.write_bytes(b"%PDF-1.4 honk")
    return path


def test_normalize_printer_uri_expands_bare_hosts():
    assert normalize_printer_uri("192.168.1.42") == "ipp://192.168.1.42:631/ipp/print"
    assert normalize_printer_uri("TS5350a.local") == "ipp://TS5350a.local:631/ipp/print"


def test_normalize_printer_uri_preserves_explicit_uris():
    assert (
        normalize_printer_uri("ipp://printer.local:1234/ipp/printers/goose")
        == "ipp://printer.local:1234/ipp/printers/goose"
    )
    assert (
        normalize_printer_uri("ipps://printer.local/") == "ipps://printer.local:631/ipp/print"
    )


def test_normalize_printer_uri_rejects_bad_input():
    with pytest.raises(PrintError):
        normalize_printer_uri("")
    with pytest.raises(PrintError):
        normalize_printer_uri("ftp://printer.local")


def test_build_print_job_request_contains_attributes_and_payload():
    request = build_print_job_request(
        printer_uri="ipp://printer.local:631/ipp/print",
        payload=b"%PDF-1.4 honk",
        job_name="Goosepaper",
        settings=PrintSettings(
            printer="printer.local",
            copies=2,
            media="iso_a4_210x297mm",
            sides="two-sided-long-edge",
            color_mode="monochrome",
        ),
    )

    version_major, version_minor, operation, request_id = struct.unpack(
        ">BBHI", request[:8]
    )
    assert (version_major, version_minor, operation, request_id) == (1, 1, 0x0002, 1)
    assert b"printer-uri" in request
    assert b"ipp://printer.local:631/ipp/print" in request
    assert b"job-name" in request
    assert b"application/pdf" in request
    assert b"iso_a4_210x297mm" in request
    assert b"two-sided-long-edge" in request
    assert request.endswith(b"%PDF-1.4 honk")
    assert struct.pack(">i", 2) in request


def test_build_print_job_request_omits_media_when_unset():
    request = build_print_job_request(
        printer_uri="ipp://printer.local:631/ipp/print",
        payload=b"payload",
        job_name="Goosepaper",
        settings=PrintSettings(printer="printer.local"),
    )
    assert b"media" not in request


def test_parse_ipp_status_code():
    assert parse_ipp_status_code(_ipp_response_bytes(0x0000)) == 0
    with pytest.raises(PrintError):
        parse_ipp_status_code(b"\x02\x00")


def test_print_paper_posts_ipp_request():
    session = _Session()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_pdf(Path(tmpdir))
        assert print_paper(
            path,
            PrintSettings(printer="192.168.1.42"),
            session=session,
        )

    url, data, headers, timeout = session.calls[0]
    assert url == "http://192.168.1.42:631/ipp/print"
    assert headers["Content-Type"] == "application/ipp"
    assert timeout is not None
    assert data.endswith(b"%PDF-1.4 honk")


def test_print_paper_requires_a_printer():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_pdf(Path(tmpdir))
        with pytest.raises(PrintError):
            print_paper(path, PrintSettings(), session=_Session())


def test_print_paper_requires_an_existing_file():
    with pytest.raises(PrintError):
        print_paper(
            "/tmp/definitely-not-a-goosepaper.pdf",
            PrintSettings(printer="printer.local"),
            session=_Session(),
        )


def test_print_paper_rejects_unprintable_formats():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "Goosepaper.epub"
        path.write_bytes(b"epub")
        with pytest.raises(PrintError):
            print_paper(
                path, PrintSettings(printer="printer.local"), session=_Session()
            )


def test_print_paper_raises_on_http_error():
    session = _Session(response=_Response(status_code=500))
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_pdf(Path(tmpdir))
        with pytest.raises(PrintError):
            print_paper(
                path, PrintSettings(printer="printer.local"), session=session
            )


def test_print_paper_raises_on_ipp_error_status():
    session = _Session(
        response=_Response(content=_ipp_response_bytes(0x0400))
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_pdf(Path(tmpdir))
        with pytest.raises(PrintError):
            print_paper(
                path, PrintSettings(printer="printer.local"), session=session
            )
