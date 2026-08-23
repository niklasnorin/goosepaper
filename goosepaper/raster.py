"""Rasterize a PDF into Apple Raster (URF) for AirPrint printers.

Most home IPP printers — including the Canon TS5300/TS5350a — advertise
`image/urf` and `image/pwg-raster` but not `application/pdf`. AirPrint clients
convert the document before sending; Goosepaper does the same.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import List, Sequence, Tuple

from .config import PrintSettings

DEFAULT_PRINT_DPI = 300
URF_CONTENT_TYPE = "image/urf"
URF_MAGIC = b"UNIRAST\x00"
URF_PAGE_HEADER_SIZE = 32
URF_MAX_PACK = 128
URF_QUALITY = 4

# Apple Raster page-header color-space values (sGray=0, sRGB=1).
# W8 in a printer's urf-supported list is 8-bit sGray, not Device W (4).
_URF_COLORSPACE_SGRAY = 0
_URF_COLORSPACE_SRGB = 1
_URF_SIDES = {
    "one-sided": 1,
    "two-sided-short-edge": 2,
    "two-sided-long-edge": 3,
}

RasterPage = Tuple[int, int, bytes]


class RasterError(RuntimeError):
    """Raised when a PDF cannot be turned into printer raster data."""


def rasterize_pdf(filepath, settings: PrintSettings, dpi: int = DEFAULT_PRINT_DPI) -> bytes:
    """Render `filepath` and return an Apple Raster (URF) document."""
    pages = render_pdf_pages(filepath, settings, dpi=dpi)
    return encode_urf(pages, settings=settings, dpi=dpi)


def render_pdf_pages(
    filepath, settings: PrintSettings, dpi: int = DEFAULT_PRINT_DPI
) -> List[RasterPage]:
    """Render each PDF page to raw pixels."""
    try:
        import pypdfium2 as pdfium
    except ImportError as err:
        raise RasterError(
            "Printing a PDF requires the pypdfium2 package so Goosepaper can "
            "rasterize it for AirPrint printers."
        ) from err

    grayscale = settings.color_mode == "monochrome"
    path = Path(filepath)
    try:
        document = pdfium.PdfDocument(str(path))
    except Exception as err:
        raise RasterError(f"Couldn't open {path} as a PDF: {err}") from err

    try:
        if len(document) == 0:
            raise RasterError(f"{path} does not contain any pages.")
        pages: List[RasterPage] = []
        scale = dpi / 72.0
        for index in range(len(document)):
            page = document[index]
            try:
                bitmap = _render_page(page, scale=scale, grayscale=grayscale)
                image = bitmap.to_pil()
            finally:
                _close_if_possible(page)
            if grayscale:
                image = image.convert("L")
            else:
                image = image.convert("RGB")
            pages.append((image.width, image.height, image.tobytes()))
        return pages
    finally:
        _close_if_possible(document)


def encode_urf(
    pages: Sequence[RasterPage],
    settings: PrintSettings,
    dpi: int = DEFAULT_PRINT_DPI,
) -> bytes:
    """Encode raw page pixels as an `image/urf` (UNIRAST) document."""
    if not pages:
        raise RasterError("Cannot encode an empty URF document.")

    grayscale = settings.color_mode == "monochrome"
    components = 1 if grayscale else 3
    bits_per_pixel = 8 * components
    color_space = _URF_COLORSPACE_SGRAY if grayscale else _URF_COLORSPACE_SRGB
    duplex = _URF_SIDES.get(settings.sides, 1)

    document = bytearray()
    document += URF_MAGIC
    document += struct.pack(">I", len(pages))

    for width, height, pixels in pages:
        expected = width * height * components
        if width <= 0 or height <= 0:
            raise RasterError(f"Invalid URF page size {width}x{height}.")
        if len(pixels) != expected:
            raise RasterError(
                f"URF page pixel buffer is {len(pixels)} bytes, "
                f"expected {expected} for {width}x{height}."
            )
        header = bytearray(URF_PAGE_HEADER_SIZE)
        header[0] = bits_per_pixel
        header[1] = color_space
        header[2] = duplex
        header[3] = URF_QUALITY
        header[12:16] = struct.pack(">I", width)
        header[16:20] = struct.pack(">I", height)
        header[20:24] = struct.pack(">I", dpi)
        document += header
        document += _encode_urf_pixels(pixels, width, height, components)

    return bytes(document)


def decode_urf(data: bytes) -> List[RasterPage]:
    """Decode a URF document into raw pages. Used by tests."""
    if data[:8] != URF_MAGIC:
        raise RasterError("Not a URF document (bad magic).")
    if len(data) < 12:
        raise RasterError("Truncated URF header.")
    page_count = struct.unpack(">I", data[8:12])[0]
    pos = 12
    pages: List[RasterPage] = []
    for _ in range(page_count):
        if pos + URF_PAGE_HEADER_SIZE > len(data):
            raise RasterError("Truncated URF page header.")
        header = data[pos:pos + URF_PAGE_HEADER_SIZE]
        pos += URF_PAGE_HEADER_SIZE
        bits_per_pixel = header[0]
        width = struct.unpack(">I", header[12:16])[0]
        height = struct.unpack(">I", header[16:20])[0]
        components = bits_per_pixel // 8
        if components not in (1, 3):
            raise RasterError(f"Unsupported URF bits-per-pixel {bits_per_pixel}.")
        pixels, pos = _decode_urf_pixels(data, pos, width, height, components)
        pages.append((width, height, pixels))
    return pages


def _render_page(page, scale: float, grayscale: bool):
    try:
        return page.render(scale=scale, grayscale=grayscale)
    except TypeError:
        return page.render(scale=scale)


def _close_if_possible(resource) -> None:
    close = getattr(resource, "close", None)
    if close is not None:
        close()


def _encode_urf_pixels(
    pixels: bytes, width: int, height: int, components: int
) -> bytes:
    row_bytes = width * components
    encoded = bytearray()
    y = 0
    while y < height:
        row = pixels[y * row_bytes:(y + 1) * row_bytes]
        repeat = 1
        while y + repeat < height and repeat < 256:
            nxt = pixels[(y + repeat) * row_bytes:(y + repeat + 1) * row_bytes]
            if nxt != row:
                break
            repeat += 1
        encoded.append(repeat - 1)
        encoded += _encode_packbits_line(row, components)
        y += repeat
    return bytes(encoded)


def _encode_packbits_line(row: bytes, components: int) -> bytes:
    """Modified PackBits, matching libcups `cups_raster_write`."""
    encoded = bytearray()
    length = len(row)
    last = length - components
    i = 0
    while i < length:
        start = i
        i += components
        if i >= length:
            encoded.append(0)
            encoded += row[start:start + components]
            break
        if row[start:start + components] == row[i:i + components]:
            count = 2
            while count < URF_MAX_PACK and i < last:
                nxt = i + components
                if row[i:nxt] != row[nxt:nxt + components]:
                    break
                count += 1
                i = nxt
            encoded.append(count - 1)
            encoded += row[i:i + components]
            i += components
        else:
            count = 1
            while count < URF_MAX_PACK and i < last:
                nxt = i + components
                if row[i:nxt] == row[nxt:nxt + components]:
                    break
                count += 1
                i = nxt
            if i >= last and count < URF_MAX_PACK:
                count += 1
                i += components
            encoded.append((257 - count) & 0xFF)
            encoded += row[start:start + count * components]
    return bytes(encoded)


def _decode_urf_pixels(
    data: bytes, pos: int, width: int, height: int, components: int
) -> Tuple[bytes, int]:
    row_bytes = width * components
    out = bytearray(row_bytes * height)
    y = 0
    while y < height:
        if pos >= len(data):
            raise RasterError(f"EOF in URF pixel data at row {y}.")
        repeat = data[pos] + 1
        pos += 1
        row = bytearray(row_bytes)
        x = 0
        while x < width:
            if pos >= len(data):
                raise RasterError(f"EOF mid-row in URF pixel data at row {y}.")
            ctl = data[pos]
            pos += 1
            if ctl == 0x80:
                break
            if ctl <= 0x7F:
                run = ctl + 1
                pixel = data[pos:pos + components]
                pos += components
                row[x * components:(x + run) * components] = pixel * run
                x += run
            else:
                run = 257 - ctl
                nbytes = run * components
                row[x * components:(x + run) * components] = data[pos:pos + nbytes]
                pos += nbytes
                x += run
        copies = min(repeat, height - y)
        for offset in range(copies):
            start = (y + offset) * row_bytes
            out[start:start + row_bytes] = row
        y += copies
    return bytes(out), pos
