#!/usr/bin/env python3
"""
PDF Text Extraction Benchmark

This script benchmarks various PDF text extraction tools:
- PyMuPDF (fitz)
- pypdfium2
- pypdf
- pdftext
- mutool (CLI)
- pdftotext (CLI)

Each tool is tested in multiple modes:
- Single-threaded
- Parallel (page-range based)
- Hybrid (single below cutoff, parallel above)
- Split (split PDF into chunks, process in parallel)

All tests run inside an async runtime with ThreadPoolExecutor
to simulate real-world Django/FastAPI usage.
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
from typing import Callable, Optional

from tabulate import tabulate
from tqdm import tqdm

from extractors import (
    SINGLE_THREADED_EXTRACTORS,
    PARALLEL_EXTRACTORS,
    HYBRID_50_EXTRACTORS,
    HYBRID_100_EXTRACTORS,
    SPLIT_50_EXTRACTORS,
    SPLIT_100_EXTRACTORS,
    ALL_EXTRACTORS,
    EXTRACTOR_CATEGORIES,
    get_cpu_pool,
    get_default_workers,
    get_cpu_count,
    shutdown_cpu_pool,
    run_extractor_async,
)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    extractor_name: str
    pdf_name: str
    pdf_size_bytes: int
    pdf_pages: int
    extraction_time_seconds: float
    text_length: int
    success: bool
    error_message: Optional[str] = None
    is_parallel: bool = False
    category: str = "single"

    @property
    def pages_per_second(self) -> float:
        if self.extraction_time_seconds > 0:
            return self.pdf_pages / self.extraction_time_seconds
        return 0.0

    @property
    def mb_per_second(self) -> float:
        if self.extraction_time_seconds > 0:
            return (self.pdf_size_bytes / 1024 / 1024) / self.extraction_time_seconds
        return 0.0


@dataclass
class PDFInfo:
    """Information about a PDF file."""
    path: Path
    size_bytes: int
    page_count: int


@dataclass
class BenchmarkConfig:
    """Configuration for the benchmark."""
    pdf_dir: Path = Path("sample_pdfs")
    results_dir: Path = Path("results")
    warmup_runs: int = 1
    benchmark_runs: int = 3
    extractors: list[str] = field(default_factory=lambda: list(ALL_EXTRACTORS.keys()))
    pdfs: list[str] = field(default_factory=list)  # empty = all PDFs
    verbose: bool = False
    use_async: bool = True  # Run in async context (realistic)
    workers: int = 4


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


def get_extractor_category(name: str) -> str:
    """Determine the category of an extractor by its name."""
    if "_split_100" in name:
        return "split_100"
    elif "_split_50" in name:
        return "split_50"
    elif "_hybrid_100" in name:
        return "hybrid_100"
    elif "_hybrid_50" in name:
        return "hybrid_50"
    elif "_parallel" in name:
        return "parallel"
    else:
        return "single"


async def run_single_benchmark_async(
    extractor_name: str,
    extractor_func: Callable[[str], str],
    pdf_info: PDFInfo,
    executor: ThreadPoolExecutor,
) -> BenchmarkResult:
    """Run a single benchmark test in async context."""
    gc.collect()

    category = get_extractor_category(extractor_name)
    is_parallel = category != "single"

    start_time = time.perf_counter()
    try:
        text = await run_extractor_async(extractor_func, str(pdf_info.path), executor)
        elapsed = time.perf_counter() - start_time
        return BenchmarkResult(
            extractor_name=extractor_name,
            pdf_name=pdf_info.path.name,
            pdf_size_bytes=pdf_info.size_bytes,
            pdf_pages=pdf_info.page_count,
            extraction_time_seconds=elapsed,
            text_length=len(text),
            success=True,
            is_parallel=is_parallel,
            category=category,
        )
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        return BenchmarkResult(
            extractor_name=extractor_name,
            pdf_name=pdf_info.path.name,
            pdf_size_bytes=pdf_info.size_bytes,
            pdf_pages=pdf_info.page_count,
            extraction_time_seconds=elapsed,
            text_length=0,
            success=False,
            error_message=str(e),
            is_parallel=is_parallel,
            category=category,
        )


def run_single_benchmark_sync(
    extractor_name: str,
    extractor_func: Callable[[str], str],
    pdf_info: PDFInfo,
) -> BenchmarkResult:
    """Run a single benchmark test synchronously."""
    gc.collect()

    category = get_extractor_category(extractor_name)
    is_parallel = category != "single"

    start_time = time.perf_counter()
    try:
        text = extractor_func(str(pdf_info.path))
        elapsed = time.perf_counter() - start_time
        return BenchmarkResult(
            extractor_name=extractor_name,
            pdf_name=pdf_info.path.name,
            pdf_size_bytes=pdf_info.size_bytes,
            pdf_pages=pdf_info.page_count,
            extraction_time_seconds=elapsed,
            text_length=len(text),
            success=True,
            is_parallel=is_parallel,
            category=category,
        )
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        return BenchmarkResult(
            extractor_name=extractor_name,
            pdf_name=pdf_info.path.name,
            pdf_size_bytes=pdf_info.size_bytes,
            pdf_pages=pdf_info.page_count,
            extraction_time_seconds=elapsed,
            text_length=0,
            success=False,
            error_message=str(e),
            is_parallel=is_parallel,
            category=category,
        )


async def run_benchmarks_async(
    config: BenchmarkConfig,
    pdf_infos: list[PDFInfo],
    extractors_to_run: dict[str, Callable],
) -> list[BenchmarkResult]:
    """Run all benchmarks in async context."""
    results = []

    total_tests = len(pdf_infos) * len(extractors_to_run) * (config.warmup_runs + config.benchmark_runs)

    # Create thread pool for async execution
    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        with tqdm(total=total_tests, desc="Benchmarking (async)", ncols=80) as pbar:
            for pdf_info in pdf_infos:
                for extractor_name, extractor_func in extractors_to_run.items():
                    # Warmup runs (not recorded)
                    for _ in range(config.warmup_runs):
                        await run_single_benchmark_async(
                            extractor_name, extractor_func, pdf_info, executor
                        )
                        pbar.update(1)

                    # Benchmark runs (recorded)
                    run_results = []
                    for _ in range(config.benchmark_runs):
                        result = await run_single_benchmark_async(
                            extractor_name, extractor_func, pdf_info, executor
                        )
                        run_results.append(result)
                        pbar.update(1)

                    # Use median result (by time)
                    run_results.sort(key=lambda r: r.extraction_time_seconds)
                    median_idx = len(run_results) // 2
                    results.append(run_results[median_idx])

    return results


def run_benchmarks_sync(
    config: BenchmarkConfig,
    pdf_infos: list[PDFInfo],
    extractors_to_run: dict[str, Callable],
) -> list[BenchmarkResult]:
    """Run all benchmarks synchronously."""
    results = []

    total_tests = len(pdf_infos) * len(extractors_to_run) * (config.warmup_runs + config.benchmark_runs)

    with tqdm(total=total_tests, desc="Benchmarking (sync)", ncols=80) as pbar:
        for pdf_info in pdf_infos:
            for extractor_name, extractor_func in extractors_to_run.items():
                # Warmup runs (not recorded)
                for _ in range(config.warmup_runs):
                    run_single_benchmark_sync(extractor_name, extractor_func, pdf_info)
                    pbar.update(1)

                # Benchmark runs (recorded)
                run_results = []
                for _ in range(config.benchmark_runs):
                    result = run_single_benchmark_sync(
                        extractor_name, extractor_func, pdf_info
                    )
                    run_results.append(result)
                    pbar.update(1)

                # Use median result (by time)
                run_results.sort(key=lambda r: r.extraction_time_seconds)
                median_idx = len(run_results) // 2
                results.append(run_results[median_idx])

    return results


def run_benchmarks(config: BenchmarkConfig) -> list[BenchmarkResult]:
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
            print(f"  {info.path.name}: {info.size_bytes/1024:.1f} KB, {info.page_count} pages")
        else:
            print(f"  {info.path.name}: SKIPPED (unable to read)")

    if not pdf_infos:
        print("No valid PDFs found")
        return []

    # Filter extractors
    extractors_to_run = {}
    for name in config.extractors:
        if name in ALL_EXTRACTORS:
            extractors_to_run[name] = ALL_EXTRACTORS[name]
        else:
            print(f"Warning: Unknown extractor '{name}', skipping")

    if not extractors_to_run:
        print("No valid extractors specified")
        return []

    total_tests = len(pdf_infos) * len(extractors_to_run) * (config.warmup_runs + config.benchmark_runs)
    print(f"\nRunning {total_tests} benchmark tests...")
    print(f"  PDFs: {len(pdf_infos)}")
    print(f"  Extractors: {len(extractors_to_run)}")
    print(f"  Warmup runs: {config.warmup_runs}")
    print(f"  Benchmark runs: {config.benchmark_runs}")
    print(f"  Workers: {config.workers}")
    print(f"  Async mode: {config.use_async}")
    print("=" * 60)

    # Run benchmarks
    if config.use_async:
        results = asyncio.run(run_benchmarks_async(config, pdf_infos, extractors_to_run))
    else:
        results = run_benchmarks_sync(config, pdf_infos, extractors_to_run)

    return results


def format_results_table(results: list[BenchmarkResult], group_by: str = "pdf") -> str:
    """Format results as a table."""
    if not results:
        return "No results"

    if group_by == "pdf":
        # Group by PDF, compare extractors
        tables = []
        pdf_names = sorted(set(r.pdf_name for r in results))

        for pdf_name in pdf_names:
            pdf_results = [r for r in results if r.pdf_name == pdf_name]
            if not pdf_results:
                continue

            # Get PDF info from first result
            pdf_size = pdf_results[0].pdf_size_bytes
            pdf_pages = pdf_results[0].pdf_pages

            tables.append(f"\n{pdf_name} ({pdf_size/1024:.1f} KB, {pdf_pages} pages)")
            tables.append("-" * 80)

            # Sort by time
            pdf_results.sort(key=lambda r: r.extraction_time_seconds)

            rows = []
            for r in pdf_results:
                status = "OK" if r.success else f"ERR: {r.error_message[:15] if r.error_message else 'unknown'}"
                rows.append([
                    r.extractor_name[:25],
                    r.category[:10],
                    f"{r.extraction_time_seconds*1000:.1f} ms",
                    f"{r.pages_per_second:.1f}",
                    f"{r.mb_per_second:.2f}",
                    f"{r.text_length:,}",
                    status[:10],
                ])

            tables.append(tabulate(
                rows,
                headers=["Extractor", "Category", "Time", "Pages/s", "MB/s", "Text Len", "Status"],
                tablefmt="simple",
            ))

        return "\n".join(tables)

    elif group_by == "extractor":
        # Group by extractor, compare PDFs
        tables = []
        extractor_names = sorted(set(r.extractor_name for r in results))

        for extractor_name in extractor_names:
            ext_results = [r for r in results if r.extractor_name == extractor_name]
            if not ext_results:
                continue

            category = ext_results[0].category
            tables.append(f"\n{extractor_name} ({category})")
            tables.append("-" * 60)

            # Sort by PDF size
            ext_results.sort(key=lambda r: r.pdf_size_bytes)

            rows = []
            for r in ext_results:
                status = "OK" if r.success else "ERR"
                rows.append([
                    r.pdf_name[:30],
                    f"{r.pdf_size_bytes/1024:.1f} KB",
                    f"{r.pdf_pages}",
                    f"{r.extraction_time_seconds*1000:.1f} ms",
                    f"{r.pages_per_second:.1f}",
                    status,
                ])

            tables.append(tabulate(
                rows,
                headers=["PDF", "Size", "Pages", "Time", "Pages/s", "Status"],
                tablefmt="simple",
            ))

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

            # Group by extractor base name
            base_names = sorted(set(r.extractor_name.split("_")[0] for r in cat_results))

            for base_name in base_names:
                base_results = [r for r in cat_results if r.extractor_name.startswith(base_name)]
                if base_results:
                    avg_speed = sum(r.pages_per_second for r in base_results if r.success) / len([r for r in base_results if r.success]) if any(r.success for r in base_results) else 0
                    tables.append(f"  {base_results[0].extractor_name}: {avg_speed:.1f} pages/s avg")

        return "\n".join(tables)

    else:
        # Flat table
        rows = []
        for r in sorted(results, key=lambda r: (r.pdf_name, r.extraction_time_seconds)):
            status = "OK" if r.success else "ERR"
            rows.append([
                r.pdf_name[:20],
                r.extractor_name[:20],
                r.category[:8],
                f"{r.extraction_time_seconds*1000:.1f}",
                f"{r.pages_per_second:.1f}",
                status,
            ])

        return tabulate(
            rows,
            headers=["PDF", "Extractor", "Category", "Time (ms)", "Pages/s", "Status"],
            tablefmt="simple",
        )


def generate_summary(results: list[BenchmarkResult]) -> str:
    """Generate a summary of benchmark results."""
    if not results:
        return "No results to summarize"

    lines = [
        "\n" + "=" * 60,
        "BENCHMARK SUMMARY",
        "=" * 60,
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
        lines.append(f"  {category}: {avg_speed:.1f} pages/s avg")

    # Best performers by extractor
    lines.append("\n--- Fastest by Extractor (averaged across all PDFs) ---")

    extractor_times = {}
    for r in successful:
        if r.extractor_name not in extractor_times:
            extractor_times[r.extractor_name] = []
        extractor_times[r.extractor_name].append(r.pages_per_second)

    avg_speeds = [
        (name, sum(speeds) / len(speeds))
        for name, speeds in extractor_times.items()
    ]
    avg_speeds.sort(key=lambda x: -x[1])

    # Show top 10
    for name, avg_speed in avg_speeds[:10]:
        category = get_extractor_category(name)
        lines.append(f"  {name} ({category}): {avg_speed:.1f} pages/s avg")

    if len(avg_speeds) > 10:
        lines.append(f"  ... and {len(avg_speeds) - 10} more")

    # Comparison between modes for each base extractor
    lines.append("\n--- Mode Comparison by Base Extractor ---")

    base_extractors = set()
    for r in successful:
        base = r.extractor_name.split("_")[0]
        base_extractors.add(base)

    for base_name in sorted(base_extractors):
        base_results = [r for r in successful if r.extractor_name.startswith(base_name + "_") or r.extractor_name == base_name]
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

        for cat in ["single", "parallel", "hybrid_50", "hybrid_100", "split_50", "split_100"]:
            if cat in cat_speeds:
                avg = sum(cat_speeds[cat]) / len(cat_speeds[cat])
                lines.append(f"    {cat:12}: {avg:8.1f} pages/s")

    return "\n".join(lines)


def save_results(results: list[BenchmarkResult], output_dir: Path, config: BenchmarkConfig) -> Path:
    """Save results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"benchmark_results_{timestamp}.json"

    data = {
        "timestamp": timestamp,
        "config": {
            "workers": config.workers,
            "warmup_runs": config.warmup_runs,
            "benchmark_runs": config.benchmark_runs,
            "use_async": config.use_async,
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
        description="Benchmark PDF text extraction tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all benchmarks (async mode, default)
  python benchmark.py

  # Run only single-threaded extractors
  python benchmark.py --category single

  # Run only parallel extractors
  python benchmark.py --category parallel

  # Run hybrid extractors (50 and 100 page cutoffs)
  python benchmark.py --category hybrid_50 hybrid_100

  # Run split extractors (only split large PDFs)
  python benchmark.py --category split_50 split_100

  # Run specific extractors
  python benchmark.py -e pymupdf pypdfium2 pdftotext

  # Run on specific PDFs
  python benchmark.py -p sample.pdf other.pdf

  # More benchmark iterations for accuracy
  python benchmark.py --runs 5 --warmup 2

  # Control worker count
  python benchmark.py --workers 8

  # Run in sync mode (not async)
  python benchmark.py --sync

Environment Variables:
  BENCHMARK_WORKERS     Default worker count (default: 4)
  BENCHMARK_CPU_COUNT   Override detected CPU count

Categories:
  single      Single-threaded extractors
  parallel    Parallel extractors (page-range based)
  hybrid_50   Hybrid: single < 50 pages, parallel >= 50 pages
  hybrid_100  Hybrid: single < 100 pages, parallel >= 100 pages
  split_50    Split into 4 chunks only if >= 50 pages
  split_100   Split into 4 chunks only if >= 100 pages
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
        "-e", "--extractors",
        nargs="+",
        default=None,
        help="Specific extractors to run (default: all)",
    )
    parser.add_argument(
        "-c", "--category",
        nargs="+",
        choices=list(EXTRACTOR_CATEGORIES.keys()),
        default=None,
        help="Run extractors from specific categories",
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
        default=None,
        help=f"Number of workers for thread pool (default: {get_default_workers()})",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run in synchronous mode (not async)",
    )
    parser.add_argument(
        "--group-by",
        choices=["pdf", "extractor", "category", "flat"],
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

    # Determine which extractors to run
    if args.extractors:
        extractors = args.extractors
    elif args.category:
        extractors = []
        for cat in args.category:
            extractors.extend(EXTRACTOR_CATEGORIES.get(cat, []))
    else:
        # Default: run single, parallel, hybrid_50, and split_50
        extractors = (
            EXTRACTOR_CATEGORIES["single"] +
            EXTRACTOR_CATEGORIES["parallel"] +
            EXTRACTOR_CATEGORIES["hybrid_50"] +
            EXTRACTOR_CATEGORIES["split_50"]
        )

    workers = args.workers if args.workers else get_default_workers()

    config = BenchmarkConfig(
        pdf_dir=args.pdf_dir,
        results_dir=args.output_dir,
        warmup_runs=args.warmup,
        benchmark_runs=args.runs,
        extractors=extractors,
        pdfs=args.pdfs or [],
        verbose=args.verbose,
        use_async=not args.sync,
        workers=workers,
    )

    print("=" * 60)
    print("PDF TEXT EXTRACTION BENCHMARK")
    print("=" * 60)
    print(f"CPU Count: {get_cpu_count()}")
    print(f"Workers: {workers}")
    print(f"Async Mode: {config.use_async}")

    # Run benchmarks
    try:
        results = run_benchmarks(config)
    finally:
        shutdown_cpu_pool()

    if not results:
        print("No results generated")
        sys.exit(1)

    # Display results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(format_results_table(results, group_by=args.group_by))

    # Summary
    print(generate_summary(results))

    # Save results
    if not args.no_save:
        output_file = save_results(results, config.results_dir, config)
        print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
