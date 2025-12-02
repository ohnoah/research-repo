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

Each tool is tested in both single-threaded and parallel modes.
"""

import argparse
import gc
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from tabulate import tabulate
from tqdm import tqdm

from extractors import (
    SINGLE_THREADED_EXTRACTORS,
    PARALLEL_EXTRACTORS,
    ALL_EXTRACTORS,
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


def run_single_benchmark(
    extractor_name: str,
    extractor_func: Callable[[str], str],
    pdf_info: PDFInfo,
    is_parallel: bool = False,
) -> BenchmarkResult:
    """Run a single benchmark test."""
    gc.collect()

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
        )


def run_benchmarks(config: BenchmarkConfig) -> list[BenchmarkResult]:
    """Run all benchmarks according to configuration."""
    results = []

    # Discover PDFs
    pdf_files = sorted(config.pdf_dir.glob("*.pdf"))
    if config.pdfs:
        pdf_files = [p for p in pdf_files if p.name in config.pdfs]

    if not pdf_files:
        print(f"No PDF files found in {config.pdf_dir}")
        return results

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
        return results

    # Filter extractors
    extractors_to_run = {}
    for name in config.extractors:
        if name in ALL_EXTRACTORS:
            extractors_to_run[name] = ALL_EXTRACTORS[name]
        else:
            print(f"Warning: Unknown extractor '{name}', skipping")

    if not extractors_to_run:
        print("No valid extractors specified")
        return results

    total_tests = len(pdf_infos) * len(extractors_to_run) * (config.warmup_runs + config.benchmark_runs)
    print(f"\nRunning {total_tests} benchmark tests...")
    print(f"  PDFs: {len(pdf_infos)}")
    print(f"  Extractors: {len(extractors_to_run)}")
    print(f"  Warmup runs: {config.warmup_runs}")
    print(f"  Benchmark runs: {config.benchmark_runs}")
    print("=" * 60)

    # Run benchmarks
    with tqdm(total=total_tests, desc="Benchmarking", ncols=80) as pbar:
        for pdf_info in pdf_infos:
            for extractor_name, extractor_func in extractors_to_run.items():
                is_parallel = "_parallel" in extractor_name

                # Warmup runs (not recorded)
                for _ in range(config.warmup_runs):
                    run_single_benchmark(extractor_name, extractor_func, pdf_info, is_parallel)
                    pbar.update(1)

                # Benchmark runs (recorded)
                run_results = []
                for _ in range(config.benchmark_runs):
                    result = run_single_benchmark(extractor_name, extractor_func, pdf_info, is_parallel)
                    run_results.append(result)
                    pbar.update(1)

                # Use median result (by time)
                run_results.sort(key=lambda r: r.extraction_time_seconds)
                median_idx = len(run_results) // 2
                results.append(run_results[median_idx])

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
            tables.append("-" * 60)

            # Sort by time
            pdf_results.sort(key=lambda r: r.extraction_time_seconds)

            rows = []
            for r in pdf_results:
                status = "OK" if r.success else f"ERR: {r.error_message[:20]}"
                mode = "parallel" if r.is_parallel else "single"
                rows.append([
                    r.extractor_name,
                    mode,
                    f"{r.extraction_time_seconds*1000:.1f} ms",
                    f"{r.pages_per_second:.1f}",
                    f"{r.mb_per_second:.2f}",
                    f"{r.text_length:,}",
                    status,
                ])

            tables.append(tabulate(
                rows,
                headers=["Extractor", "Mode", "Time", "Pages/s", "MB/s", "Text Len", "Status"],
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

            mode = "parallel" if ext_results[0].is_parallel else "single"
            tables.append(f"\n{extractor_name} ({mode})")
            tables.append("-" * 60)

            # Sort by PDF size
            ext_results.sort(key=lambda r: r.pdf_size_bytes)

            rows = []
            for r in ext_results:
                status = "OK" if r.success else f"ERR"
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

    else:
        # Flat table
        rows = []
        for r in sorted(results, key=lambda r: (r.pdf_name, r.extraction_time_seconds)):
            status = "OK" if r.success else "ERR"
            mode = "P" if r.is_parallel else "S"
            rows.append([
                r.pdf_name[:20],
                r.extractor_name,
                mode,
                f"{r.extraction_time_seconds*1000:.1f}",
                f"{r.pages_per_second:.1f}",
                status,
            ])

        return tabulate(
            rows,
            headers=["PDF", "Extractor", "Mode", "Time (ms)", "Pages/s", "Status"],
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

    for name, avg_speed in avg_speeds:
        is_parallel = "_parallel" in name
        mode = "parallel" if is_parallel else "single"
        lines.append(f"  {name} ({mode}): {avg_speed:.1f} pages/s avg")

    # Single vs Parallel comparison
    lines.append("\n--- Single-threaded vs Parallel Comparison ---")

    base_extractors = set(r.extractor_name.replace("_parallel", "") for r in successful)

    for base_name in sorted(base_extractors):
        single_results = [r for r in successful if r.extractor_name == base_name]
        parallel_results = [r for r in successful if r.extractor_name == f"{base_name}_parallel"]

        if single_results and parallel_results:
            single_avg = sum(r.pages_per_second for r in single_results) / len(single_results)
            parallel_avg = sum(r.pages_per_second for r in parallel_results) / len(parallel_results)
            speedup = parallel_avg / single_avg if single_avg > 0 else 0

            lines.append(f"\n  {base_name}:")
            lines.append(f"    Single:   {single_avg:.1f} pages/s")
            lines.append(f"    Parallel: {parallel_avg:.1f} pages/s")
            lines.append(f"    Speedup:  {speedup:.2f}x")

    return "\n".join(lines)


def save_results(results: list[BenchmarkResult], output_dir: Path) -> Path:
    """Save results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"benchmark_results_{timestamp}.json"

    data = {
        "timestamp": timestamp,
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
  # Run all benchmarks
  python benchmark.py

  # Run only single-threaded extractors
  python benchmark.py --single-only

  # Run only parallel extractors
  python benchmark.py --parallel-only

  # Run specific extractors
  python benchmark.py -e pymupdf pypdfium2 pdftotext

  # Run on specific PDFs
  python benchmark.py -p sample.pdf other.pdf

  # More benchmark iterations for accuracy
  python benchmark.py --runs 5 --warmup 2
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
        "--single-only",
        action="store_true",
        help="Run only single-threaded extractors",
    )
    parser.add_argument(
        "--parallel-only",
        action="store_true",
        help="Run only parallel extractors",
    )
    parser.add_argument(
        "--group-by",
        choices=["pdf", "extractor", "flat"],
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
    elif args.single_only:
        extractors = list(SINGLE_THREADED_EXTRACTORS.keys())
    elif args.parallel_only:
        extractors = list(PARALLEL_EXTRACTORS.keys())
    else:
        extractors = list(ALL_EXTRACTORS.keys())

    config = BenchmarkConfig(
        pdf_dir=args.pdf_dir,
        results_dir=args.output_dir,
        warmup_runs=args.warmup,
        benchmark_runs=args.runs,
        extractors=extractors,
        pdfs=args.pdfs or [],
        verbose=args.verbose,
    )

    print("=" * 60)
    print("PDF TEXT EXTRACTION BENCHMARK")
    print("=" * 60)

    # Run benchmarks
    results = run_benchmarks(config)

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
        output_file = save_results(results, config.results_dir)
        print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
