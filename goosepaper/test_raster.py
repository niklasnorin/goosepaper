import tempfile
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from .config import PrintSettings
from .raster import RasterError, decode_urf, encode_urf, rasterize_pdf


def _solid_page(width, height, pixel: bytes):
    return (width, height, pixel * (width * height))


def test_urf_roundtrip_grayscale_with_repeats():
    # Two identical white rows, then a row with a black run and a mixed tail.
    width = 8
    white = b"\xff" * width
    mixed = b"\x00\x00\x00\x00\x11\x22\x33\x44"
    pages = [(width, 3, white + white + mixed)]

    encoded = encode_urf(
        pages, settings=PrintSettings(printer="printer.local"), dpi=300
    )
    assert encoded.startswith(b"UNIRAST\x00")
    # Page header: 8-bit sGray (W8), not Device W / Gray32.
    assert encoded[12] == 8
    assert encoded[13] == 0
    decoded = decode_urf(encoded)
    assert decoded == pages


def test_urf_roundtrip_color():
    pixel = b"\x10\x20\x30"
    pages = [_solid_page(4, 2, pixel)]
    encoded = encode_urf(
        pages,
        settings=PrintSettings(printer="printer.local", color_mode="color"),
        dpi=600,
    )
    assert decode_urf(encoded) == pages


def test_encode_urf_rejects_empty_and_mismatched_buffers():
    settings = PrintSettings(printer="printer.local")
    with pytest.raises(RasterError):
        encode_urf([], settings=settings)
    with pytest.raises(RasterError):
        encode_urf([(2, 2, b"\x00")], settings=settings)


def test_rasterize_pdf_renders_a_page():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tiny.pdf"
        pdf = pdfium.PdfDocument.new()
        pdf.new_page(36, 36)
        pdf.save(path)
        urf = rasterize_pdf(
            path, PrintSettings(printer="printer.local"), dpi=72
        )

    pages = decode_urf(urf)
    assert len(pages) == 1
    width, height, pixels = pages[0]
    assert width == 36
    assert height == 36
    assert len(pixels) == 36 * 36
    # Empty page should be paper-white (or very close after rasterization).
    assert pixels.count(255) > (36 * 36) * 0.9
