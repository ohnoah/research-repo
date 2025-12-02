"""
PDF Text Extraction Functions

This module contains all extraction functions for benchmarking:
- Single-threaded versions for each tool
- Parallel versions using ThreadPoolExecutor (for CLI tools and pypdf)
- Parallel versions using ProcessPoolExecutor (for PyMuPDF, pypdfium2, pdftext)
- Hybrid versions that switch between single/parallel based on page count
- Split-file versions that split PDFs before parallel processing
- Async wrappers for realistic runtime testing
"""

import asyncio
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from functools import partial
from pathlib import Path
from typing import Callable, Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

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


# Global thread pool for async execution (mimics real-world Django/FastAPI setup)
_CPU_POOL: Optional[ThreadPoolExecutor] = None


def get_cpu_pool() -> ThreadPoolExecutor:
    """Get or create the global CPU thread pool."""
    global _CPU_POOL
    if _CPU_POOL is None:
        _CPU_POOL = ThreadPoolExecutor(max_workers=get_default_workers())
    return _CPU_POOL


def shutdown_cpu_pool():
    """Shutdown the global CPU pool."""
    global _CPU_POOL
    if _CPU_POOL is not None:
        _CPU_POOL.shutdown(wait=True)
        _CPU_POOL = None


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _get_page_count(path: str) -> int:
    """Get page count using pypdf (cheap and pure Python)."""
    from pypdf import PdfReader
    return len(PdfReader(path).pages)


def _get_page_count_fitz(path: str) -> int:
    """Get page count using fitz."""
    import fitz
    with fitz.open(path) as doc:
        return len(doc)


def _split_pdf_to_temp_files(path: str, num_chunks: int) -> list[tuple[str, int, int]]:
    """
    Split a PDF into temporary files for parallel processing.

    Returns list of (temp_file_path, start_page, end_page) tuples.
    The caller is responsible for cleaning up temp files.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(path)
    total_pages = len(reader.pages)

    if total_pages <= num_chunks:
        # Don't split if fewer pages than chunks
        return [(path, 0, total_pages)]

    chunk_size = (total_pages + num_chunks - 1) // num_chunks
    temp_files = []

    for i in range(num_chunks):
        start_page = i * chunk_size
        end_page = min((i + 1) * chunk_size, total_pages)

        if start_page >= total_pages:
            break

        writer = PdfWriter()
        for page_num in range(start_page, end_page):
            writer.add_page(reader.pages[page_num])

        # Create temp file
        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        with open(temp_path, "wb") as f:
            writer.write(f)

        temp_files.append((temp_path, start_page, end_page))

    return temp_files


# ============================================================================
# SINGLE-THREADED EXTRACTION FUNCTIONS
# ============================================================================

def extract_text_pymupdf(path: str) -> str:
    """Extract text using PyMuPDF (MuPDF engine)."""
    import fitz

    text_chunks = []
    with fitz.open(path) as doc:
        for page in doc:
            text_chunks.append(page.get_text("text"))
    return "".join(text_chunks)


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


def extract_text_pypdf(path: str) -> str:
    """Extract text using pypdf (pure Python)."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "".join(page.extract_text() or "" for page in reader.pages)


def extract_text_pdftext(path: str) -> str:
    """Extract text using pdftext (built on pypdfium2)."""
    from pdftext.extraction import plain_text_output

    return plain_text_output(path)


def extract_text_mutool(path: str) -> str:
    """Extract text using mutool draw (MuPDF CLI)."""
    result = subprocess.run(
        ["mutool", "draw", "-F", "txt", path],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8", errors="ignore")


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
# PARALLEL EXTRACTION FUNCTIONS (Page-range based)
# ============================================================================

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
    if max_workers is None:
        max_workers = get_default_workers()

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
    if max_workers is None:
        max_workers = get_default_workers()

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
    if max_workers is None:
        max_workers = get_default_workers()

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
    if max_workers is None:
        max_workers = get_default_workers()

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
    if max_workers is None:
        max_workers = get_default_workers()

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
    """Extract text using pdftext with ProcessPoolExecutor parallelization."""
    if max_workers is None:
        max_workers = get_default_workers()

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
# HYBRID EXTRACTION FUNCTIONS
# Single-threaded below cutoff, parallel above
# ============================================================================

def _make_hybrid_extractor(
    single_func: Callable[[str], str],
    parallel_func: Callable[[str], str],
    cutoff: int,
) -> Callable[[str], str]:
    """Create a hybrid extractor that switches based on page count."""
    def hybrid_extractor(path: str) -> str:
        page_count = _get_page_count(path)
        if page_count < cutoff:
            return single_func(path)
        else:
            return parallel_func(path)
    return hybrid_extractor


# Hybrid with 50 page cutoff
extract_text_pymupdf_hybrid_50 = _make_hybrid_extractor(
    extract_text_pymupdf, extract_text_pymupdf_parallel, 50
)
extract_text_pypdfium2_hybrid_50 = _make_hybrid_extractor(
    extract_text_pypdfium2, extract_text_pypdfium2_parallel, 50
)
extract_text_pypdf_hybrid_50 = _make_hybrid_extractor(
    extract_text_pypdf, extract_text_pypdf_parallel, 50
)
extract_text_pdftext_hybrid_50 = _make_hybrid_extractor(
    extract_text_pdftext, extract_text_pdftext_parallel, 50
)
extract_text_mutool_hybrid_50 = _make_hybrid_extractor(
    extract_text_mutool, extract_text_mutool_parallel, 50
)
extract_text_pdftotext_hybrid_50 = _make_hybrid_extractor(
    extract_text_pdftotext, extract_text_pdftotext_parallel, 50
)

# Hybrid with 100 page cutoff
extract_text_pymupdf_hybrid_100 = _make_hybrid_extractor(
    extract_text_pymupdf, extract_text_pymupdf_parallel, 100
)
extract_text_pypdfium2_hybrid_100 = _make_hybrid_extractor(
    extract_text_pypdfium2, extract_text_pypdfium2_parallel, 100
)
extract_text_pypdf_hybrid_100 = _make_hybrid_extractor(
    extract_text_pypdf, extract_text_pypdf_parallel, 100
)
extract_text_pdftext_hybrid_100 = _make_hybrid_extractor(
    extract_text_pdftext, extract_text_pdftext_parallel, 100
)
extract_text_mutool_hybrid_100 = _make_hybrid_extractor(
    extract_text_mutool, extract_text_mutool_parallel, 100
)
extract_text_pdftotext_hybrid_100 = _make_hybrid_extractor(
    extract_text_pdftotext, extract_text_pdftotext_parallel, 100
)


# ============================================================================
# SPLIT-FILE EXTRACTION FUNCTIONS
# Split PDF into N files, run single-threaded extraction in parallel, combine
# ============================================================================

def _extract_single_on_split_file(args: tuple) -> tuple[int, str]:
    """Worker to extract text from a split PDF file."""
    temp_path, chunk_idx, extractor_name = args

    # Get the appropriate single-threaded extractor
    extractor = SINGLE_THREADED_EXTRACTORS[extractor_name]
    text = extractor(temp_path)

    return (chunk_idx, text)


def _make_split_extractor(
    extractor_name: str,
    num_chunks: int,
) -> Callable[[str], str]:
    """Create an extractor that splits PDF and processes chunks in parallel."""
    def split_extractor(path: str, max_workers: int = None) -> str:
        if max_workers is None:
            max_workers = get_default_workers()

        # Split PDF into temp files
        temp_files = _split_pdf_to_temp_files(path, num_chunks)

        try:
            if len(temp_files) == 1 and temp_files[0][0] == path:
                # No split happened (too few pages), just run single-threaded
                return SINGLE_THREADED_EXTRACTORS[extractor_name](path)

            # Process each chunk in parallel using threads
            args_list = [
                (temp_path, idx, extractor_name)
                for idx, (temp_path, start, end) in enumerate(temp_files)
            ]

            results = [None] * len(args_list)
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {
                    ex.submit(_extract_single_on_split_file, args): args[1]
                    for args in args_list
                }
                for fut in futures:
                    chunk_idx, text = fut.result()
                    results[chunk_idx] = text

            return "".join(results)
        finally:
            # Clean up temp files
            for temp_path, _, _ in temp_files:
                if temp_path != path:  # Don't delete original
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

    return split_extractor


# Split into 2 chunks
extract_text_pymupdf_split_2 = _make_split_extractor("pymupdf", 2)
extract_text_pypdfium2_split_2 = _make_split_extractor("pypdfium2", 2)
extract_text_pypdf_split_2 = _make_split_extractor("pypdf", 2)
extract_text_pdftext_split_2 = _make_split_extractor("pdftext", 2)
extract_text_mutool_split_2 = _make_split_extractor("mutool", 2)
extract_text_pdftotext_split_2 = _make_split_extractor("pdftotext", 2)

# Split into 4 chunks
extract_text_pymupdf_split_4 = _make_split_extractor("pymupdf", 4)
extract_text_pypdfium2_split_4 = _make_split_extractor("pypdfium2", 4)
extract_text_pypdf_split_4 = _make_split_extractor("pypdf", 4)
extract_text_pdftext_split_4 = _make_split_extractor("pdftext", 4)
extract_text_mutool_split_4 = _make_split_extractor("mutool", 4)
extract_text_pdftotext_split_4 = _make_split_extractor("pdftotext", 4)

# Split into 8 chunks
extract_text_pymupdf_split_8 = _make_split_extractor("pymupdf", 8)
extract_text_pypdfium2_split_8 = _make_split_extractor("pypdfium2", 8)
extract_text_pypdf_split_8 = _make_split_extractor("pypdf", 8)
extract_text_pdftext_split_8 = _make_split_extractor("pdftext", 8)
extract_text_mutool_split_8 = _make_split_extractor("mutool", 8)
extract_text_pdftotext_split_8 = _make_split_extractor("pdftotext", 8)


# ============================================================================
# ASYNC WRAPPERS
# Run extractors in async context using ThreadPoolExecutor (realistic runtime)
# ============================================================================

async def run_extractor_async(
    extractor: Callable[[str], str],
    path: str,
    executor: Optional[ThreadPoolExecutor] = None,
) -> str:
    """
    Run an extractor in an async context using run_in_executor.

    This mimics real-world usage in Django/FastAPI where PDF extraction
    is offloaded to a thread pool from an async context.
    """
    loop = asyncio.get_running_loop()
    pool = executor or get_cpu_pool()
    return await loop.run_in_executor(pool, extractor, path)


def make_async_extractor(
    sync_extractor: Callable[[str], str],
) -> Callable[[str], str]:
    """
    Create a sync wrapper that runs the extractor in an async context.

    This is used for benchmarking to simulate real-world async usage.
    The benchmark will call this sync function which internally uses asyncio.
    """
    def async_wrapped_extractor(path: str) -> str:
        async def _run():
            return await run_extractor_async(sync_extractor, path)

        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, create a task
            import concurrent.futures
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result()
        except RuntimeError:
            # No running loop, we can use asyncio.run
            return asyncio.run(_run())

    return async_wrapped_extractor


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

HYBRID_50_EXTRACTORS: dict[str, Callable[[str], str]] = {
    "pymupdf_hybrid_50": extract_text_pymupdf_hybrid_50,
    "pypdfium2_hybrid_50": extract_text_pypdfium2_hybrid_50,
    "pypdf_hybrid_50": extract_text_pypdf_hybrid_50,
    "pdftext_hybrid_50": extract_text_pdftext_hybrid_50,
    "mutool_hybrid_50": extract_text_mutool_hybrid_50,
    "pdftotext_hybrid_50": extract_text_pdftotext_hybrid_50,
}

HYBRID_100_EXTRACTORS: dict[str, Callable[[str], str]] = {
    "pymupdf_hybrid_100": extract_text_pymupdf_hybrid_100,
    "pypdfium2_hybrid_100": extract_text_pypdfium2_hybrid_100,
    "pypdf_hybrid_100": extract_text_pypdf_hybrid_100,
    "pdftext_hybrid_100": extract_text_pdftext_hybrid_100,
    "mutool_hybrid_100": extract_text_mutool_hybrid_100,
    "pdftotext_hybrid_100": extract_text_pdftotext_hybrid_100,
}

SPLIT_2_EXTRACTORS: dict[str, Callable[[str], str]] = {
    "pymupdf_split_2": extract_text_pymupdf_split_2,
    "pypdfium2_split_2": extract_text_pypdfium2_split_2,
    "pypdf_split_2": extract_text_pypdf_split_2,
    "pdftext_split_2": extract_text_pdftext_split_2,
    "mutool_split_2": extract_text_mutool_split_2,
    "pdftotext_split_2": extract_text_pdftotext_split_2,
}

SPLIT_4_EXTRACTORS: dict[str, Callable[[str], str]] = {
    "pymupdf_split_4": extract_text_pymupdf_split_4,
    "pypdfium2_split_4": extract_text_pypdfium2_split_4,
    "pypdf_split_4": extract_text_pypdf_split_4,
    "pdftext_split_4": extract_text_pdftext_split_4,
    "mutool_split_4": extract_text_mutool_split_4,
    "pdftotext_split_4": extract_text_pdftotext_split_4,
}

SPLIT_8_EXTRACTORS: dict[str, Callable[[str], str]] = {
    "pymupdf_split_8": extract_text_pymupdf_split_8,
    "pypdfium2_split_8": extract_text_pypdfium2_split_8,
    "pypdf_split_8": extract_text_pypdf_split_8,
    "pdftext_split_8": extract_text_pdftext_split_8,
    "mutool_split_8": extract_text_mutool_split_8,
    "pdftotext_split_8": extract_text_pdftotext_split_8,
}

ALL_EXTRACTORS: dict[str, Callable[[str], str]] = {
    **SINGLE_THREADED_EXTRACTORS,
    **PARALLEL_EXTRACTORS,
    **HYBRID_50_EXTRACTORS,
    **HYBRID_100_EXTRACTORS,
    **SPLIT_2_EXTRACTORS,
    **SPLIT_4_EXTRACTORS,
    **SPLIT_8_EXTRACTORS,
}

# Extractor categories for easier selection
EXTRACTOR_CATEGORIES = {
    "single": list(SINGLE_THREADED_EXTRACTORS.keys()),
    "parallel": list(PARALLEL_EXTRACTORS.keys()),
    "hybrid_50": list(HYBRID_50_EXTRACTORS.keys()),
    "hybrid_100": list(HYBRID_100_EXTRACTORS.keys()),
    "split_2": list(SPLIT_2_EXTRACTORS.keys()),
    "split_4": list(SPLIT_4_EXTRACTORS.keys()),
    "split_8": list(SPLIT_8_EXTRACTORS.keys()),
}
