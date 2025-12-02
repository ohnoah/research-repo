"""
PDF Text Extraction Functions

This module contains all extraction functions for benchmarking:
- Single-threaded versions for each tool
- Parallel versions using ThreadPoolExecutor (for CLI tools and pypdf)
- Parallel versions using ProcessPoolExecutor (for PyMuPDF, pypdfium2, pdftext)
"""

import subprocess
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from pathlib import Path
from typing import Callable

# ============================================================================
# SINGLE-THREADED EXTRACTION FUNCTIONS
# ============================================================================

# -----------------------------------------------------------------------------
# PyMuPDF (fitz) - Single-threaded
# -----------------------------------------------------------------------------
def extract_text_pymupdf(path: str) -> str:
    """Extract text using PyMuPDF (MuPDF engine)."""
    import fitz

    text_chunks = []
    with fitz.open(path) as doc:
        for page in doc:
            text_chunks.append(page.get_text("text"))
    return "".join(text_chunks)


# -----------------------------------------------------------------------------
# pypdfium2 - Single-threaded
# -----------------------------------------------------------------------------
def extract_text_pypdfium2(path: str) -> str:
    """Extract text using pypdfium2 (PDFium engine)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(path)
    try:
        text_chunks = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            text_chunks.append(textpage.get_text_range())
            textpage.close()
        return "".join(text_chunks)
    finally:
        pdf.close()


# -----------------------------------------------------------------------------
# pypdf - Single-threaded
# -----------------------------------------------------------------------------
def extract_text_pypdf(path: str) -> str:
    """Extract text using pypdf (pure Python)."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "".join(page.extract_text() or "" for page in reader.pages)


# -----------------------------------------------------------------------------
# pdftext - Single-threaded
# -----------------------------------------------------------------------------
def extract_text_pdftext(path: str) -> str:
    """Extract text using pdftext (built on pypdfium2)."""
    from pdftext.extraction import plain_text_output

    return plain_text_output(path)


# -----------------------------------------------------------------------------
# mutool draw (MuPDF CLI) - Single-threaded
# -----------------------------------------------------------------------------
def extract_text_mutool(path: str) -> str:
    """Extract text using mutool draw (MuPDF CLI)."""
    result = subprocess.run(
        ["mutool", "draw", "-F", "txt", path],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8", errors="ignore")


# -----------------------------------------------------------------------------
# pdftotext (Poppler CLI) - Single-threaded
# -----------------------------------------------------------------------------
def extract_text_pdftotext(path: str) -> str:
    """Extract text using pdftotext (Poppler CLI)."""
    result = subprocess.run(
        ["pdftotext", path, "-"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8", errors="ignore")


# ============================================================================
# PARALLEL EXTRACTION FUNCTIONS
# ============================================================================

def _get_page_count(path: str) -> int:
    """Get page count using pypdf (cheap and pure Python)."""
    from pypdf import PdfReader
    return len(PdfReader(path).pages)


# -----------------------------------------------------------------------------
# pdftotext - Parallel (ThreadPoolExecutor + CLI)
# -----------------------------------------------------------------------------
def _extract_pdftotext_range(args: tuple) -> str:
    """Worker function for parallel pdftotext extraction."""
    path, first, last = args
    result = subprocess.run(
        ["pdftotext", "-f", str(first), "-l", str(last), path, "-"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8", errors="ignore")


def extract_text_pdftotext_parallel(path: str, chunk_size: int = 20, max_workers: int = None) -> str:
    """Extract text using pdftotext with ThreadPoolExecutor parallelization."""
    total_pages = _get_page_count(path)

    # Build page ranges (1-indexed for pdftotext)
    ranges = []
    start = 1
    while start <= total_pages:
        end = min(start + chunk_size - 1, total_pages)
        ranges.append((path, start, end))
        start = end + 1

    texts = [None] * len(ranges)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_extract_pdftotext_range, r): idx
            for idx, r in enumerate(ranges)
        }
        for fut in futures:
            idx = futures[fut]
            texts[idx] = fut.result()

    return "".join(texts)


# -----------------------------------------------------------------------------
# mutool draw - Parallel (ThreadPoolExecutor + CLI)
# -----------------------------------------------------------------------------
def _extract_mutool_range(args: tuple) -> str:
    """Worker function for parallel mutool extraction."""
    path, page_spec = args
    result = subprocess.run(
        ["mutool", "draw", "-F", "txt", path, page_spec],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8", errors="ignore")


def extract_text_mutool_parallel(path: str, chunk_size: int = 20, max_workers: int = None) -> str:
    """Extract text using mutool with ThreadPoolExecutor parallelization."""
    total_pages = _get_page_count(path)

    # Build page specs (1-indexed for mutool)
    specs = []
    start = 1
    while start <= total_pages:
        end = min(start + chunk_size - 1, total_pages)
        specs.append((path, f"{start}-{end}"))
        start = end + 1

    texts = [None] * len(specs)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_extract_mutool_range, s): idx
            for idx, s in enumerate(specs)
        }
        for fut in futures:
            idx = futures[fut]
            texts[idx] = fut.result()

    return "".join(texts)


# -----------------------------------------------------------------------------
# pypdf - Parallel (ThreadPoolExecutor)
# -----------------------------------------------------------------------------
def _extract_pypdf_range(args: tuple) -> str:
    """Worker function for parallel pypdf extraction."""
    path, start_idx, end_idx = args
    from pypdf import PdfReader

    reader = PdfReader(path)
    text_chunks = []
    for i in range(start_idx, end_idx):
        text_chunks.append(reader.pages[i].extract_text() or "")
    return "".join(text_chunks)


def extract_text_pypdf_parallel(path: str, chunk_size: int = 20, max_workers: int = None) -> str:
    """Extract text using pypdf with ThreadPoolExecutor parallelization."""
    total_pages = _get_page_count(path)

    # Build page ranges (0-indexed)
    ranges = []
    start = 0
    while start < total_pages:
        end = min(start + chunk_size, total_pages)
        ranges.append((path, start, end))
        start = end

    texts = [None] * len(ranges)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_extract_pypdf_range, r): idx
            for idx, r in enumerate(ranges)
        }
        for fut in futures:
            idx = futures[fut]
            texts[idx] = fut.result()

    return "".join(texts)


# -----------------------------------------------------------------------------
# PyMuPDF - Parallel (ProcessPoolExecutor)
# Note: PyMuPDF is NOT thread-safe, must use processes
# -----------------------------------------------------------------------------
def _pymupdf_worker(args: tuple) -> str:
    """Worker function for parallel PyMuPDF extraction (process-based)."""
    pdf_bytes, start_idx, end_idx = args
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        chunks = []
        for i in range(start_idx, end_idx):
            page = doc[i]
            chunks.append(page.get_text("text"))
        return "".join(chunks)
    finally:
        doc.close()


def extract_text_pymupdf_parallel(path: str, chunk_size: int = 20, max_workers: int = None) -> str:
    """Extract text using PyMuPDF with ProcessPoolExecutor parallelization."""
    import fitz

    pdf_bytes = Path(path).read_bytes()

    # Get page count
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        total_pages = len(doc)

    # Build page ranges (0-indexed)
    ranges = []
    start = 0
    while start < total_pages:
        end = min(start + chunk_size, total_pages)
        ranges.append((pdf_bytes, start, end))
        start = end

    texts = []
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        for chunk_text in ex.map(_pymupdf_worker, ranges):
            texts.append(chunk_text)

    return "".join(texts)


# -----------------------------------------------------------------------------
# pypdfium2 - Parallel (ProcessPoolExecutor)
# Note: pypdfium2 is NOT thread-safe, must use processes
# -----------------------------------------------------------------------------
def _pypdfium2_worker(args: tuple) -> str:
    """Worker function for parallel pypdfium2 extraction (process-based)."""
    pdf_bytes, start_idx, end_idx = args
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        chunks = []
        for i in range(start_idx, end_idx):
            page = pdf[i]
            textpage = page.get_textpage()
            chunks.append(textpage.get_text_range())
            textpage.close()
        return "".join(chunks)
    finally:
        pdf.close()


def extract_text_pypdfium2_parallel(path: str, chunk_size: int = 20, max_workers: int = None) -> str:
    """Extract text using pypdfium2 with ProcessPoolExecutor parallelization."""
    import pypdfium2 as pdfium

    pdf_bytes = Path(path).read_bytes()

    # Get page count
    pdf = pdfium.PdfDocument(pdf_bytes)
    total_pages = len(pdf)
    pdf.close()

    # Build page ranges (0-indexed)
    ranges = []
    start = 0
    while start < total_pages:
        end = min(start + chunk_size, total_pages)
        ranges.append((pdf_bytes, start, end))
        start = end

    texts = []
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        for chunk_text in ex.map(_pypdfium2_worker, ranges):
            texts.append(chunk_text)

    return "".join(texts)


# -----------------------------------------------------------------------------
# pdftext - Parallel (ProcessPoolExecutor)
# Note: pdftext is built on pypdfium2, so it's NOT thread-safe
# -----------------------------------------------------------------------------
def _pdftext_worker(args: tuple) -> str:
    """Worker function for parallel pdftext extraction (process-based)."""
    pdf_bytes, start_idx, end_idx = args
    import pypdfium2 as pdfium
    from pdftext.extraction import plain_text_output
    from pdftext.settings import settings
    import tempfile
    import os

    # pdftext doesn't support byte streams directly, so we use pypdfium2 directly
    # for page-range extraction
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        chunks = []
        for i in range(start_idx, end_idx):
            page = pdf[i]
            textpage = page.get_textpage()
            chunks.append(textpage.get_text_range())
            textpage.close()
        return "".join(chunks)
    finally:
        pdf.close()


def extract_text_pdftext_parallel(path: str, chunk_size: int = 20, max_workers: int = None) -> str:
    """Extract text using pdftext with ProcessPoolExecutor parallelization.

    Note: Since pdftext uses pypdfium2 under the hood, we use pypdfium2 directly
    for page-range parallel extraction.
    """
    import pypdfium2 as pdfium

    pdf_bytes = Path(path).read_bytes()

    # Get page count
    pdf = pdfium.PdfDocument(pdf_bytes)
    total_pages = len(pdf)
    pdf.close()

    # Build page ranges (0-indexed)
    ranges = []
    start = 0
    while start < total_pages:
        end = min(start + chunk_size, total_pages)
        ranges.append((pdf_bytes, start, end))
        start = end

    texts = []
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        for chunk_text in ex.map(_pdftext_worker, ranges):
            texts.append(chunk_text)

    return "".join(texts)


# ============================================================================
# REGISTRY OF ALL EXTRACTORS
# ============================================================================

SINGLE_THREADED_EXTRACTORS: dict[str, Callable[[str], str]] = {
    "pymupdf": extract_text_pymupdf,
    "pypdfium2": extract_text_pypdfium2,
    "pypdf": extract_text_pypdf,
    "pdftext": extract_text_pdftext,
    "mutool": extract_text_mutool,
    "pdftotext": extract_text_pdftotext,
}

PARALLEL_EXTRACTORS: dict[str, Callable[[str], str]] = {
    "pymupdf_parallel": extract_text_pymupdf_parallel,
    "pypdfium2_parallel": extract_text_pypdfium2_parallel,
    "pypdf_parallel": extract_text_pypdf_parallel,
    "pdftext_parallel": extract_text_pdftext_parallel,
    "mutool_parallel": extract_text_mutool_parallel,
    "pdftotext_parallel": extract_text_pdftotext_parallel,
}

ALL_EXTRACTORS: dict[str, Callable[[str], str]] = {
    **SINGLE_THREADED_EXTRACTORS,
    **PARALLEL_EXTRACTORS,
}
