#!/usr/bin/env python3
"""
PDF Thumbnail Rendering Benchmark

This script benchmarks various PDF thumbnail rendering tools:
- PyMuPDF (fitz) - MuPDF engine
- pypdfium2 - PDFium engine (Chrome's renderer)
- pdf2image - Poppler wrapper

Each tool is tested in two modes:
- Single-threaded: Sequential page rendering, but run via run_in_executor
  in an async context to simulate production Django/FastAPI usage
- Multiprocessing: True parallelism by splitting pages across processes

The benchmark runs inside an async event loop with a ThreadPoolExecutor
(4 workers by default) to simulate production deployment patterns.

Usage:
    # Run all benchmarks
    python benchmark.py

    # Run only single-threaded renderers
    python benchmark.py --category single

    # Run multiprocessing renderers
    python benchmark.py --category multiprocess

    # Run specific renderers
    python benchmark.py -r pymupdf pypdfium2

    # More benchmark iterations for accuracy
    python benchmark.py --runs 5 --warmup 2
"""

import argparse
import asyncio
import gc
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from PIL import Image
from tabulate import tabulate
from tqdm import tqdm

from renderers import (
    SINGLE_THREADED_RENDERERS,
    MULTIPROCESS_RENDERERS,
    ALL_RENDERERS,
    RENDERER_CATEGORIES,
    get_default_workers,
    get_cpu_count,
)


# Default thread pool size (matches user's production config)
DEFAULT_THREADPOOL_WORKERS = 4


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    renderer_name: str
    pdf_name: str
    pdf_size_bytes: int
    pdf_pages: int
    render_time_seconds: float
    images_count: int
    total_pixels: int
    success: bool
    error_message: Optional[str] = None
    category: str = "single"

    @property
    def pages_per_second(self) -> float:
        """Calculate pages rendered per second."""
        if self.render_time_seconds > 0:
            return self.pdf_pages / self.render_time_seconds
        return 0.0

    @property
    def mb_per_second(self) -> float:
        """Calculate input MB processed per second."""
        if self.render_time_seconds > 0:
            return (self.pdf_size_bytes / 1024 / 1024) / self.render_time_seconds
        return 0.0

    @property
    def megapixels_per_second(self) -> float:
        """Calculate output megapixels rendered per second."""
        if self.render_time_seconds > 0:
            return (self.total_pixels / 1_000_000) / self.render_time_seconds
        return 0.0


@dataclass
class PDFInfo:
    """Information about a PDF file for benchmarking."""

    path: Path
    size_bytes: int
    page_count: int


@dataclass
class BenchmarkConfig:
    """Configuration for the benchmark run."""

    pdf_dir: Path = field(default_factory=lambda: Path("sample_pdfs"))
    results_dir: Path = field(default_factory=lambda: Path("results"))
    warmup_runs: int = 1
    benchmark_runs: int = 3
    renderers: List[str] = field(default_factory=lambda: list(ALL_RENDERERS.keys()))
    pdfs: List[str] = field(default_factory=list)  # empty = all PDFs
    verbose: bool = False
    threadpool_workers: int = DEFAULT_THREADPOOL_WORKERS


def get_pdf_info(pdf_path: Path) -> PDFInfo:
    """Get information about a PDF file."""
    from pypdf import PdfReader

    size_bytes = pdf_path.stat().st_size
    try:
        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
    except Exception:
        page_count = 0

    return PDFInfo(
        path=pdf_path,
        size_bytes=size_bytes,
        page_count=page_count,
    )


def get_renderer_category(name: str) -> str:
    """Determine the category of a renderer by its name."""
    if "_mp" in name:
        return "multiprocess"
    else:
        return "single"


def calculate_total_pixels(images: List[Image.Image]) -> int:
    """Calculate total pixels across all images."""
    return sum(img.width * img.height for img in images)


async def run_single_benchmark(
    renderer_name: str,
    renderer_func: Callable[[str], List[Image.Image]],
    pdf_info: PDFInfo,
    executor: ThreadPoolExecutor,
) -> BenchmarkResult:
    """
    Run a single benchmark test via run_in_executor.

    This simulates production usage where the sync renderer runs in a
    ThreadPoolExecutor to avoid blocking the async event loop.
    """
    gc.collect()

    category = get_renderer_category(renderer_name)
    loop = asyncio.get_running_loop()

    start_time = time.perf_counter()
    try:
        # Run the renderer in the thread pool (simulates production pattern)
        images = await loop.run_in_executor(
            executor, renderer_func, str(pdf_info.path)
        )
        elapsed = time.perf_counter() - start_time

        total_pixels = calculate_total_pixels(images)

        return BenchmarkResult(
            renderer_name=renderer_name,
            pdf_name=pdf_info.path.name,
            pdf_size_bytes=pdf_info.size_bytes,
            pdf_pages=pdf_info.page_count,
            render_time_seconds=elapsed,
            images_count=len(images),
            total_pixels=total_pixels,
            success=True,
            category=category,
        )
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        return BenchmarkResult(
            renderer_name=renderer_name,
            pdf_name=pdf_info.path.name,
            pdf_size_bytes=pdf_info.size_bytes,
            pdf_pages=pdf_info.page_count,
            render_time_seconds=elapsed,
            images_count=0,
            total_pixels=0,
            success=False,
            error_message=str(e),
            category=category,
        )


async def run_benchmarks_async(
    config: BenchmarkConfig,
    pdf_infos: List[PDFInfo],
    renderers_to_run: dict,
) -> List[BenchmarkResult]:
    """
    Run all benchmarks in async context with ThreadPoolExecutor.

    This simulates production Django/FastAPI usage where PDF rendering
    is offloaded to a thread pool via run_in_executor.
    """
    results = []

    total_tests = (
        len(pdf_infos) * len(renderers_to_run) * (config.warmup_runs + config.benchmark_runs)
    )

    # Create thread pool with configured workers (default: 4)
    # This mimics the production CPU_POOL pattern
    with ThreadPoolExecutor(max_workers=config.threadpool_workers) as executor:
        with tqdm(total=total_tests, desc="Benchmarking", ncols=100) as pbar:
            for pdf_info in pdf_infos:
                for renderer_name, renderer_func in renderers_to_run.items():
                    # Warmup runs (not recorded)
                    for _ in range(config.warmup_runs):
                        await run_single_benchmark(
                            renderer_name, renderer_func, pdf_info, executor
                        )
                        pbar.update(1)

                    # Benchmark runs (recorded)
                    run_results = []
                    for _ in range(config.benchmark_runs):
                        result = await run_single_benchmark(
                            renderer_name, renderer_func, pdf_info, executor
                        )
                        run_results.append(result)
                        pbar.update(1)

                    # Use median result (by time)
                    run_results.sort(key=lambda r: r.render_time_seconds)
                    median_idx = len(run_results) // 2
                    results.append(run_results[median_idx])

    return results


def run_benchmarks(config: BenchmarkConfig) -> List[BenchmarkResult]:
    """Run all benchmarks according to configuration."""
    # Discover PDFs
    pdf_files = sorted(config.pdf_dir.glob("*.pdf"))
    if config.pdfs:
        pdf_files = [p for p in pdf_files if p.name in config.pdfs]

    if not pdf_files:
        print(f"No PDF files found in {config.pdf_dir}")
        return []

    # Get PDF info
    print(f"\nDiscovering PDFs in {config.pdf_dir}...")
    pdf_infos = []
    for pdf_path in pdf_files:
        info = get_pdf_info(pdf_path)
        if info.page_count > 0:
            pdf_infos.append(info)
            print(f"  {info.path.name}: {info.size_bytes / 1024:.1f} KB, {info.page_count} pages")
        else:
            print(f"  {info.path.name}: SKIPPED (unable to read)")

    if not pdf_infos:
        print("No valid PDFs found")
        return []

    # Filter renderers
    renderers_to_run = {}
    for name in config.renderers:
        if name in ALL_RENDERERS:
            renderers_to_run[name] = ALL_RENDERERS[name]
        else:
            print(f"Warning: Unknown renderer '{name}', skipping")

    if not renderers_to_run:
        print("No valid renderers specified")
        return []

    total_tests = (
        len(pdf_infos) * len(renderers_to_run) * (config.warmup_runs + config.benchmark_runs)
    )
    print(f"\nRunning {total_tests} benchmark tests...")
    print(f"  PDFs: {len(pdf_infos)}")
    print(f"  Renderers: {len(renderers_to_run)}")
    print(f"  Warmup runs: {config.warmup_runs}")
    print(f"  Benchmark runs: {config.benchmark_runs}")
    print(f"  ThreadPool workers: {config.threadpool_workers}")
    print(f"  CPU count: {get_cpu_count()}")
    print("=" * 80)

    # Run benchmarks in async context
    results = asyncio.run(run_benchmarks_async(config, pdf_infos, renderers_to_run))

    return results


def format_results_table(results: List[BenchmarkResult], group_by: str = "pdf") -> str:
    """Format results as a table."""
    if not results:
        return "No results"

    if group_by == "pdf":
        # Group by PDF, compare renderers
        tables = []
        pdf_names = sorted(set(r.pdf_name for r in results))

        for pdf_name in pdf_names:
            pdf_results = [r for r in results if r.pdf_name == pdf_name]
            if not pdf_results:
                continue

            # Get PDF info from first result
            pdf_size = pdf_results[0].pdf_size_bytes
            pdf_pages = pdf_results[0].pdf_pages

            tables.append(f"\n{pdf_name} ({pdf_size / 1024:.1f} KB, {pdf_pages} pages)")
            tables.append("-" * 100)

            # Sort by time
            pdf_results.sort(key=lambda r: r.render_time_seconds)

            rows = []
            for r in pdf_results:
                status = "OK" if r.success else f"ERR: {r.error_message[:20] if r.error_message else 'unknown'}"
                rows.append([
                    r.renderer_name[:25],
                    r.category[:10],
                    f"{r.render_time_seconds * 1000:.1f} ms",
                    f"{r.pages_per_second:.1f}",
                    f"{r.megapixels_per_second:.2f}",
                    f"{r.images_count}",
                    f"{r.total_pixels / 1_000_000:.1f} MP",
                    status[:12],
                ])

            tables.append(
                tabulate(
                    rows,
                    headers=["Renderer", "Category", "Time", "Pages/s", "MP/s", "Images", "Total MP", "Status"],
                    tablefmt="simple",
                )
            )

        return "\n".join(tables)

    elif group_by == "renderer":
        # Group by renderer, compare PDFs
        tables = []
        renderer_names = sorted(set(r.renderer_name for r in results))

        for renderer_name in renderer_names:
            rend_results = [r for r in results if r.renderer_name == renderer_name]
            if not rend_results:
                continue

            category = rend_results[0].category
            tables.append(f"\n{renderer_name} ({category})")
            tables.append("-" * 80)

            # Sort by PDF size
            rend_results.sort(key=lambda r: r.pdf_size_bytes)

            rows = []
            for r in rend_results:
                status = "OK" if r.success else "ERR"
                rows.append([
                    r.pdf_name[:30],
                    f"{r.pdf_size_bytes / 1024:.1f} KB",
                    f"{r.pdf_pages}",
                    f"{r.render_time_seconds * 1000:.1f} ms",
                    f"{r.pages_per_second:.1f}",
                    f"{r.megapixels_per_second:.2f}",
                    status,
                ])

            tables.append(
                tabulate(
                    rows,
                    headers=["PDF", "Size", "Pages", "Time", "Pages/s", "MP/s", "Status"],
                    tablefmt="simple",
                )
            )

        return "\n".join(tables)

    elif group_by == "category":
        # Group by category
        tables = []
        categories = sorted(set(r.category for r in results))

        for category in categories:
            cat_results = [r for r in results if r.category == category]
            if not cat_results:
                continue

            tables.append(f"\n=== Category: {category} ===")

            # Group by renderer base name
            base_names = sorted(set(r.renderer_name.split("_")[0] for r in cat_results))

            for base_name in base_names:
                base_results = [
                    r for r in cat_results if r.renderer_name.startswith(base_name)
                ]
                if base_results:
                    successful = [r for r in base_results if r.success]
                    if successful:
                        avg_speed = sum(r.pages_per_second for r in successful) / len(successful)
                        tables.append(f"  {base_results[0].renderer_name}: {avg_speed:.1f} pages/s avg")

        return "\n".join(tables)

    else:
        # Flat table
        rows = []
        for r in sorted(results, key=lambda r: (r.pdf_name, r.render_time_seconds)):
            status = "OK" if r.success else "ERR"
            rows.append([
                r.pdf_name[:20],
                r.renderer_name[:20],
                r.category[:8],
                f"{r.render_time_seconds * 1000:.1f}",
                f"{r.pages_per_second:.1f}",
                status,
            ])

        return tabulate(
            rows,
            headers=["PDF", "Renderer", "Category", "Time (ms)", "Pages/s", "Status"],
            tablefmt="simple",
        )


def generate_summary(results: List[BenchmarkResult]) -> str:
    """Generate a summary of benchmark results."""
    if not results:
        return "No results to summarize"

    lines = [
        "\n" + "=" * 80,
        "BENCHMARK SUMMARY",
        "=" * 80,
    ]

    # Overall stats
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    lines.append(f"\nTotal tests: {len(results)}")
    lines.append(f"Successful: {len(successful)}")
    lines.append(f"Failed: {len(failed)}")

    if not successful:
        return "\n".join(lines)

    # Best performers by category
    lines.append("\n--- Average Speed by Category ---")

    categories = sorted(set(r.category for r in successful))
    for category in categories:
        cat_results = [r for r in successful if r.category == category]
        avg_speed = sum(r.pages_per_second for r in cat_results) / len(cat_results)
        avg_mpps = sum(r.megapixels_per_second for r in cat_results) / len(cat_results)
        lines.append(f"  {category}: {avg_speed:.1f} pages/s, {avg_mpps:.2f} MP/s avg")

    # Best performers by renderer
    lines.append("\n--- Fastest Renderers (averaged across all PDFs) ---")

    renderer_times = {}
    for r in successful:
        if r.renderer_name not in renderer_times:
            renderer_times[r.renderer_name] = []
        renderer_times[r.renderer_name].append(r.pages_per_second)

    avg_speeds = [
        (name, sum(speeds) / len(speeds))
        for name, speeds in renderer_times.items()
    ]
    avg_speeds.sort(key=lambda x: -x[1])

    # Show all
    for name, avg_speed in avg_speeds:
        category = get_renderer_category(name)
        lines.append(f"  {name:25} ({category:12}): {avg_speed:8.1f} pages/s avg")

    # Comparison between modes for each base library
    lines.append("\n--- Mode Comparison by Library ---")

    base_libs = {"pymupdf", "pypdfium2", "pdf2image"}

    for base_name in sorted(base_libs):
        base_results = [
            r for r in successful
            if r.renderer_name.startswith(base_name)
        ]
        if not base_results:
            continue

        lines.append(f"\n  {base_name}:")

        # Group by category
        cat_speeds = {}
        for r in base_results:
            cat = r.category
            if cat not in cat_speeds:
                cat_speeds[cat] = []
            cat_speeds[cat].append(r.pages_per_second)

        for cat in ["single", "multiprocess"]:
            if cat in cat_speeds:
                avg = sum(cat_speeds[cat]) / len(cat_speeds[cat])
                lines.append(f"    {cat:15}: {avg:8.1f} pages/s")

    # Speedup analysis
    lines.append("\n--- Speedup Analysis (multiprocess vs single) ---")

    for base_name in sorted(base_libs):
        single_results = [
            r for r in successful
            if r.renderer_name == base_name and r.category == "single"
        ]
        mp_results = [
            r for r in successful
            if r.renderer_name.startswith(base_name) and r.category == "multiprocess"
        ]

        if single_results and mp_results:
            single_avg = sum(r.pages_per_second for r in single_results) / len(single_results)

            # Group multiprocess results by renderer name
            mp_by_name = {}
            for r in mp_results:
                if r.renderer_name not in mp_by_name:
                    mp_by_name[r.renderer_name] = []
                mp_by_name[r.renderer_name].append(r.pages_per_second)

            for mp_name, speeds in sorted(mp_by_name.items()):
                mp_avg = sum(speeds) / len(speeds)
                speedup = mp_avg / single_avg if single_avg > 0 else 0
                lines.append(f"  {mp_name:25}: {speedup:.2f}x speedup over {base_name}")

    return "\n".join(lines)


def save_results(
    results: List[BenchmarkResult],
    output_dir: Path,
    config: BenchmarkConfig,
) -> Path:
    """Save results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"thumbnail_benchmark_{timestamp}.json"

    data = {
        "timestamp": timestamp,
        "config": {
            "threadpool_workers": config.threadpool_workers,
            "warmup_runs": config.warmup_runs,
            "benchmark_runs": config.benchmark_runs,
            "cpu_count": get_cpu_count(),
        },
        "results": [asdict(r) for r in results],
    }

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return output_file


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark PDF thumbnail rendering tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all benchmarks
  python benchmark.py

  # Run only single-threaded renderers
  python benchmark.py --category single

  # Run multiprocessing renderers
  python benchmark.py --category multiprocess

  # Run specific renderers
  python benchmark.py -r pymupdf pypdfium2 pdf2image

  # Run on specific PDFs
  python benchmark.py -p arxiv_gpt3_paper.pdf

  # More benchmark iterations for accuracy
  python benchmark.py --runs 5 --warmup 2

  # Control thread pool size
  python benchmark.py --workers 8

Environment Variables:
  BENCHMARK_WORKERS     Default worker count for multiprocess
  BENCHMARK_CPU_COUNT   Override detected CPU count

Categories:
  single        Single-threaded renderers (run via run_in_executor)
  multiprocess  ProcessPoolExecutor renderers (true parallelism)

Renderers:
  Single-threaded (run in ThreadPoolExecutor via run_in_executor):
    pymupdf           PyMuPDF (MuPDF engine), optimized (no JPEG roundtrip)
    pymupdf_jpeg      PyMuPDF with JPEG encode/decode (your current code)
    pymupdf_grayscale PyMuPDF grayscale mode (faster, less memory)
    pypdfium2         pypdfium2 (PDFium/Chrome engine)
    pdf2image         pdf2image (Poppler/pdftoppm)

  Multiprocess (true parallelism):
    pymupdf_mp2       PyMuPDF split across 2 processes
    pymupdf_mp4       PyMuPDF split across 4 processes
    pypdfium2_mp2     pypdfium2 split across 2 processes
    pypdfium2_mp4     pypdfium2 split across 4 processes
    pdf2image_mp2     pdf2image split across 2 processes
    pdf2image_mp4     pdf2image split across 4 processes
        """,
    )

    parser.add_argument(
        "-d", "--pdf-dir",
        type=Path,
        default=Path("sample_pdfs"),
        help="Directory containing PDF files (default: sample_pdfs)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("results"),
        help="Directory for results (default: results)",
    )
    parser.add_argument(
        "-r", "--renderers",
        nargs="+",
        default=None,
        help="Specific renderers to run (default: all)",
    )
    parser.add_argument(
        "-c", "--category",
        nargs="+",
        choices=list(RENDERER_CATEGORIES.keys()),
        default=None,
        help="Run renderers from specific categories",
    )
    parser.add_argument(
        "-p", "--pdfs",
        nargs="+",
        default=None,
        help="Specific PDF files to test (default: all in pdf-dir)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of benchmark runs per test (default: 3)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Number of warmup runs per test (default: 1)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_THREADPOOL_WORKERS,
        help=f"Number of workers for thread pool (default: {DEFAULT_THREADPOOL_WORKERS})",
    )
    parser.add_argument(
        "--group-by",
        choices=["pdf", "renderer", "category", "flat"],
        default="pdf",
        help="How to group results in output (default: pdf)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to JSON",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Determine which renderers to run
    if args.renderers:
        renderers = args.renderers
    elif args.category:
        renderers = []
        for cat in args.category:
            renderers.extend(RENDERER_CATEGORIES.get(cat, []))
    else:
        # Default: run all categories
        renderers = list(ALL_RENDERERS.keys())

    config = BenchmarkConfig(
        pdf_dir=args.pdf_dir,
        results_dir=args.output_dir,
        warmup_runs=args.warmup,
        benchmark_runs=args.runs,
        renderers=renderers,
        pdfs=args.pdfs or [],
        verbose=args.verbose,
        threadpool_workers=args.workers,
    )

    print("=" * 80)
    print("PDF THUMBNAIL RENDERING BENCHMARK")
    print("=" * 80)
    print(f"CPU Count: {get_cpu_count()}")
    print(f"ThreadPool Workers: {config.threadpool_workers}")
    print(f"Mode: Async (run_in_executor pattern)")

    # Run benchmarks
    results = run_benchmarks(config)

    if not results:
        print("No results generated")
        sys.exit(1)

    # Display results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(format_results_table(results, group_by=args.group_by))

    # Summary
    print(generate_summary(results))

    # Save results
    if not args.no_save:
        output_file = save_results(results, config.results_dir, config)
        print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
