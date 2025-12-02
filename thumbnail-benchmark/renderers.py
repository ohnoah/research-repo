"""
PDF Thumbnail Rendering Functions

This module contains all thumbnail rendering functions for benchmarking:
- PyMuPDF (fitz) - MuPDF engine, one of the fastest rasterizers
- pypdfium2 - PDFium engine (Chrome's PDF renderer), comparable to MuPDF
- pdf2image - Poppler wrapper via pdftoppm CLI

Each renderer is tested in multiple modes:
- Single-threaded (runs in ThreadPoolExecutor via run_in_executor to simulate
  production async Django/FastAPI usage - NOT for parallelism)
- Multiprocessing (ProcessPoolExecutor - true parallelism by splitting pages
  across processes)

IMPORTANT Threading Notes:
- PyMuPDF and pypdfium2 are NOT thread-safe for rendering operations
- We do NOT use ThreadPoolExecutor for parallelism with these libraries
- The ThreadPoolExecutor is only used via run_in_executor to avoid blocking
  the async event loop (production pattern)
- For true parallelism, use ProcessPoolExecutor with separate Document instances

Performance Optimizations Included:
- Avoid JPEG encode/decode round-trip (use Image.frombytes directly)
- Dimension and pixel count capping to prevent memory explosions
"""

import io
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

# ============================================================================
# CONFIGURATION
# ============================================================================

# Defensive caps to avoid gigantic renders / memory issues
MAX_DIM_PX = 4096
MAX_PIXELS = 50_000_000  # Keep well below Pillow's decompression bomb threshold
DEFAULT_DPI = 200
DEFAULT_SHORTEST = None  # None = use DPI mode (200 DPI), int = shortest edge mode


def get_cpu_count() -> int:
    """Get CPU count from environment or system."""
    env_count = os.environ.get("BENCHMARK_CPU_COUNT")
    if env_count is not None:
        try:
            return max(1, int(env_count))
        except ValueError:
            pass
    return os.cpu_count() or 4


def get_default_workers() -> int:
    """Get default worker count from environment or default to 4."""
    env_workers = os.environ.get("BENCHMARK_WORKERS")
    if env_workers is not None:
        try:
            return max(1, int(env_workers))
        except ValueError:
            pass
    return min(4, get_cpu_count())


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _compute_scale(
    page_width: float,
    page_height: float,
    shortest_pixels: Optional[int] = None,
) -> float:
    """
    Compute rendering scale with dimension and pixel capping.

    Args:
        page_width: Page width in points (1 point = 1/72 inch)
        page_height: Page height in points
        shortest_pixels: Target shortest edge in pixels (None = 200 DPI mode)

    Returns:
        Scale factor to apply to page dimensions
    """
    # Base scale from caller intent
    if shortest_pixels is None:
        # DPI mode: 200 DPI = 200/72 scale factor
        target_scale = DEFAULT_DPI / 72.0
    else:
        # Shortest edge mode
        shortest = min(page_width, page_height) or 1.0
        target_scale = shortest_pixels / shortest

    # Clamp so neither dimension nor total pixels explode
    max_dim = max(page_width, page_height) or 1.0
    raw_pixels = (page_width or 1.0) * (page_height or 1.0)

    dim_cap_scale = MAX_DIM_PX / max_dim
    pixel_cap_scale = math.sqrt(MAX_PIXELS / raw_pixels)

    return min(target_scale, dim_cap_scale, pixel_cap_scale)


# ============================================================================
# PYMUPDF (fitz) RENDERERS
# ============================================================================

def render_thumbnail_pymupdf(
    pdf_bytes: bytes,
    shortest_pixels: Optional[int] = None,
    use_jpeg_roundtrip: bool = False,
) -> List[Image.Image]:
    """
    Render all pages of a PDF to Pillow Images using PyMuPDF.

    This is the optimized version that avoids JPEG encode/decode roundtrip
    by using Image.frombytes() directly from pixmap samples.

    Args:
        pdf_bytes: Raw PDF bytes
        shortest_pixels: Target shortest edge (None = 200 DPI mode)
        use_jpeg_roundtrip: If True, use JPEG intermediate (slower, for comparison)

    Returns:
        List of Pillow Image objects (RGB)
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: List[Image.Image] = []

    try:
        for page in doc:
            rect = page.rect
            scale = _compute_scale(rect.width, rect.height, shortest_pixels)
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)

            if use_jpeg_roundtrip:
                # Slower path: encode to JPEG then decode (your original code)
                jpeg_bytes = pix.tobytes("jpeg")
                img = Image.open(io.BytesIO(jpeg_bytes))
            else:
                # Fast path: direct bytes to Pillow (no codec roundtrip)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            images.append(img)
    finally:
        doc.close()

    return images


def _pymupdf_render_range_worker(
    args: Tuple[bytes, int, int, Optional[int]]
) -> List[Image.Image]:
    """
    Worker that renders a contiguous range of pages.

    Each worker opens its own Document instance (required since fitz
    Documents cannot be shared across processes).
    """
    import fitz

    pdf_bytes, start_idx, end_idx, shortest_pixels = args
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []

    try:
        for i in range(start_idx, end_idx):
            page = doc[i]
            rect = page.rect
            scale = _compute_scale(rect.width, rect.height, shortest_pixels)
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            images.append(img)
    finally:
        doc.close()

    return images


def render_thumbnail_pymupdf_multiprocess(
    pdf_bytes: bytes,
    shortest_pixels: Optional[int] = None,
    num_processes: int = 2,
) -> List[Image.Image]:
    """
    Split PDF pages across multiple processes for true parallelism.

    Divides pages between N processes where each process handles a
    contiguous range. This is the recommended approach for CPU-bound
    PDF rendering when you want parallelism.

    Args:
        pdf_bytes: Raw PDF bytes
        shortest_pixels: Target shortest edge (None = 200 DPI mode)
        num_processes: Number of processes to split work across (default: 2)

    Returns:
        List of Pillow Image objects (RGB)
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    doc.close()

    if page_count < num_processes:
        # Not enough pages to split, use single-threaded
        return render_thumbnail_pymupdf(pdf_bytes, shortest_pixels)

    # Calculate page ranges for each process
    pages_per_process = page_count // num_processes
    ranges = []
    for i in range(num_processes):
        start = i * pages_per_process
        end = start + pages_per_process if i < num_processes - 1 else page_count
        ranges.append((start, end))

    args_list = [
        (pdf_bytes, start, end, shortest_pixels)
        for start, end in ranges
    ]

    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        chunk_results = list(executor.map(_pymupdf_render_range_worker, args_list))

    # Flatten results maintaining order
    images = []
    for chunk in chunk_results:
        images.extend(chunk)

    return images


# ============================================================================
# PYPDFIUM2 RENDERERS
# ============================================================================

def render_thumbnail_pypdfium2(
    pdf_bytes: bytes,
    shortest_pixels: Optional[int] = None,
) -> List[Image.Image]:
    """
    Render all pages using pypdfium2 (PDFium engine).

    PDFium is Chrome's PDF renderer, comparable in speed to MuPDF.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    images: List[Image.Image] = []

    try:
        for i in range(len(pdf)):
            page = pdf[i]
            width, height = page.get_size()
            scale = _compute_scale(width, height, shortest_pixels)

            # render() returns a PdfBitmap, to_pil() converts to Pillow Image
            bitmap = page.render(scale=scale)
            img = bitmap.to_pil()

            # Ensure RGB mode (PDFium may return RGBA)
            if img.mode == "RGBA":
                img = img.convert("RGB")

            images.append(img)
    finally:
        pdf.close()

    return images


def _pypdfium2_render_range_worker(
    args: Tuple[bytes, int, int, Optional[int]]
) -> List[Image.Image]:
    """Worker that renders a range of pages with pypdfium2."""
    import pypdfium2 as pdfium

    pdf_bytes, start_idx, end_idx, shortest_pixels = args
    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []

    try:
        for i in range(start_idx, end_idx):
            page = pdf[i]
            width, height = page.get_size()
            scale = _compute_scale(width, height, shortest_pixels)
            bitmap = page.render(scale=scale)
            img = bitmap.to_pil()
            if img.mode == "RGBA":
                img = img.convert("RGB")
            images.append(img)
    finally:
        pdf.close()

    return images


def render_thumbnail_pypdfium2_multiprocess(
    pdf_bytes: bytes,
    shortest_pixels: Optional[int] = None,
    num_processes: int = 2,
) -> List[Image.Image]:
    """Split PDF pages across multiple processes for true parallelism."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    page_count = len(pdf)
    pdf.close()

    if page_count < num_processes:
        return render_thumbnail_pypdfium2(pdf_bytes, shortest_pixels)

    pages_per_process = page_count // num_processes
    ranges = []
    for i in range(num_processes):
        start = i * pages_per_process
        end = start + pages_per_process if i < num_processes - 1 else page_count
        ranges.append((start, end))

    args_list = [
        (pdf_bytes, start, end, shortest_pixels)
        for start, end in ranges
    ]

    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        chunk_results = list(executor.map(_pypdfium2_render_range_worker, args_list))

    images = []
    for chunk in chunk_results:
        images.extend(chunk)

    return images


# ============================================================================
# PDF2IMAGE (POPPLER) RENDERERS
# ============================================================================

def render_thumbnail_pdf2image(
    pdf_bytes: bytes,
    shortest_pixels: Optional[int] = None,
) -> List[Image.Image]:
    """
    Render using pdf2image (Poppler's pdftoppm).

    pdf2image is a wrapper around Poppler CLI tools. It's generally
    slower than MuPDF/PDFium but very robust and widely available.

    Args:
        pdf_bytes: Raw PDF bytes
        shortest_pixels: Target shortest edge (used as 'size' parameter)

    Returns:
        List of Pillow Image objects
    """
    from pdf2image import convert_from_bytes

    # pdf2image uses DPI or size parameter
    if shortest_pixels is not None:
        # Use size parameter - pdf2image interprets this as max dimension
        # For shortest edge behavior, we approximate
        images = convert_from_bytes(
            pdf_bytes,
            fmt="jpeg",
            size=(shortest_pixels * 4, None),  # Approximate
        )
    else:
        # Use DPI mode
        images = convert_from_bytes(
            pdf_bytes,
            dpi=DEFAULT_DPI,
            fmt="jpeg",
        )

    return images


def _pdf2image_render_range_worker(
    args: Tuple[bytes, int, int, Optional[int]]
) -> List[Image.Image]:
    """Worker that renders a range of pages using pdf2image."""
    from pdf2image import convert_from_bytes

    pdf_bytes, start_page, end_page, shortest_pixels = args

    # pdf2image uses 1-indexed pages
    first_page = start_page + 1
    last_page = end_page  # end_page is exclusive, but pdf2image last_page is inclusive

    if shortest_pixels is not None:
        images = convert_from_bytes(
            pdf_bytes,
            fmt="jpeg",
            first_page=first_page,
            last_page=last_page,
            size=(shortest_pixels * 4, None),
        )
    else:
        images = convert_from_bytes(
            pdf_bytes,
            dpi=DEFAULT_DPI,
            fmt="jpeg",
            first_page=first_page,
            last_page=last_page,
        )

    return images


def render_thumbnail_pdf2image_multiprocess(
    pdf_bytes: bytes,
    shortest_pixels: Optional[int] = None,
    num_processes: int = 2,
) -> List[Image.Image]:
    """Split PDF and render each part using separate pdf2image processes."""
    from pypdf import PdfReader

    # Get page count
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_count = len(reader.pages)

    if page_count < num_processes:
        return render_thumbnail_pdf2image(pdf_bytes, shortest_pixels)

    pages_per_process = page_count // num_processes
    ranges = []
    for i in range(num_processes):
        start = i * pages_per_process
        end = start + pages_per_process if i < num_processes - 1 else page_count
        ranges.append((start, end))

    args_list = [
        (pdf_bytes, start, end, shortest_pixels)
        for start, end in ranges
    ]

    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        chunk_results = list(executor.map(_pdf2image_render_range_worker, args_list))

    images = []
    for chunk in chunk_results:
        images.extend(chunk)

    return images


# ============================================================================
# WRAPPER FUNCTIONS FOR BENCHMARK INTERFACE
#
# These are file-path based wrappers that read the PDF and call the
# bytes-based renderers. The benchmark runs these via run_in_executor
# to simulate production async usage.
# ============================================================================

def pymupdf_single(path: str) -> List[Image.Image]:
    """PyMuPDF single-threaded renderer (optimized, no JPEG roundtrip)."""
    return render_thumbnail_pymupdf(Path(path).read_bytes())


def pymupdf_single_jpeg(path: str) -> List[Image.Image]:
    """PyMuPDF with JPEG roundtrip (your original code path, for comparison)."""
    return render_thumbnail_pymupdf(Path(path).read_bytes(), use_jpeg_roundtrip=True)


def pymupdf_multiprocess_2(path: str) -> List[Image.Image]:
    """PyMuPDF with 2 processes (split in half)."""
    return render_thumbnail_pymupdf_multiprocess(Path(path).read_bytes(), num_processes=2)


def pymupdf_multiprocess_4(path: str) -> List[Image.Image]:
    """PyMuPDF with 4 processes."""
    return render_thumbnail_pymupdf_multiprocess(Path(path).read_bytes(), num_processes=4)


def pypdfium2_single(path: str) -> List[Image.Image]:
    """pypdfium2 single-threaded renderer."""
    return render_thumbnail_pypdfium2(Path(path).read_bytes())


def pypdfium2_multiprocess_2(path: str) -> List[Image.Image]:
    """pypdfium2 with 2 processes (split in half)."""
    return render_thumbnail_pypdfium2_multiprocess(Path(path).read_bytes(), num_processes=2)


def pypdfium2_multiprocess_4(path: str) -> List[Image.Image]:
    """pypdfium2 with 4 processes."""
    return render_thumbnail_pypdfium2_multiprocess(Path(path).read_bytes(), num_processes=4)


def pdf2image_single(path: str) -> List[Image.Image]:
    """pdf2image (Poppler) single-threaded."""
    return render_thumbnail_pdf2image(Path(path).read_bytes())


def pdf2image_multiprocess_2(path: str) -> List[Image.Image]:
    """pdf2image with 2 processes (split in half)."""
    return render_thumbnail_pdf2image_multiprocess(Path(path).read_bytes(), num_processes=2)


def pdf2image_multiprocess_4(path: str) -> List[Image.Image]:
    """pdf2image with 4 processes."""
    return render_thumbnail_pdf2image_multiprocess(Path(path).read_bytes(), num_processes=4)


# ============================================================================
# REGISTRY OF ALL RENDERERS
# ============================================================================

SINGLE_THREADED_RENDERERS = {
    "pymupdf": pymupdf_single,
    "pymupdf_jpeg": pymupdf_single_jpeg,
    "pypdfium2": pypdfium2_single,
    "pdf2image": pdf2image_single,
}

MULTIPROCESS_RENDERERS = {
    "pymupdf_mp2": pymupdf_multiprocess_2,
    "pymupdf_mp4": pymupdf_multiprocess_4,
    "pypdfium2_mp2": pypdfium2_multiprocess_2,
    "pypdfium2_mp4": pypdfium2_multiprocess_4,
    "pdf2image_mp2": pdf2image_multiprocess_2,
    "pdf2image_mp4": pdf2image_multiprocess_4,
}

ALL_RENDERERS = {
    **SINGLE_THREADED_RENDERERS,
    **MULTIPROCESS_RENDERERS,
}

RENDERER_CATEGORIES = {
    "single": list(SINGLE_THREADED_RENDERERS.keys()),
    "multiprocess": list(MULTIPROCESS_RENDERERS.keys()),
}
