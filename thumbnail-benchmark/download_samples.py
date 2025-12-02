#!/usr/bin/env python3
"""
Download sample PDF files for benchmarking.

This script downloads a variety of public domain and freely available PDFs
of different sizes and types for testing PDF thumbnail rendering performance.
"""

import os
import sys
import time
from pathlib import Path
from typing import NamedTuple

import requests
from tqdm import tqdm


class SamplePDF(NamedTuple):
    """Sample PDF metadata."""
    name: str
    url: str
    description: str
    expected_size_kb: int  # Approximate expected size in KB


# Collection of sample PDFs from various public sources
# Using a variety of document types and sizes
SAMPLE_PDFS = [
    # Small documents (< 500 KB)
    SamplePDF(
        name="w3c_dummy.pdf",
        url="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
        description="W3C dummy PDF - very small, simple text",
        expected_size_kb=13,
    ),
    SamplePDF(
        name="pdf_reference_1page.pdf",
        url="https://www.africau.edu/images/default/sample.pdf",
        description="Africa University sample - simple 1 page",
        expected_size_kb=4,
    ),

    # Medium documents (500 KB - 5 MB)
    SamplePDF(
        name="arxiv_attention_paper.pdf",
        url="https://arxiv.org/pdf/1706.03762",
        description="'Attention Is All You Need' - famous ML paper, ~15 pages",
        expected_size_kb=2200,
    ),
    SamplePDF(
        name="arxiv_bert_paper.pdf",
        url="https://arxiv.org/pdf/1810.04805",
        description="BERT paper - NLP research paper, ~16 pages",
        expected_size_kb=750,
    ),
    SamplePDF(
        name="arxiv_gpt2_paper.pdf",
        url="https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf",
        description="GPT-2 paper - OpenAI research, ~24 pages",
        expected_size_kb=400,
    ),
    SamplePDF(
        name="arxiv_resnet_paper.pdf",
        url="https://arxiv.org/pdf/1512.03385",
        description="ResNet paper - Deep Residual Learning, ~12 pages",
        expected_size_kb=850,
    ),
    SamplePDF(
        name="us_constitution.pdf",
        url="https://www.archives.gov/files/founding-docs/constitution_transcript.pdf",
        description="US Constitution transcript - government document",
        expected_size_kb=150,
    ),

    # Larger documents (5+ MB)
    SamplePDF(
        name="arxiv_gpt3_paper.pdf",
        url="https://arxiv.org/pdf/2005.14165",
        description="GPT-3 paper - 75 pages, larger document",
        expected_size_kb=2500,
    ),

    # Documents with various formatting (images, figures)
    SamplePDF(
        name="arxiv_vit_paper.pdf",
        url="https://arxiv.org/pdf/2010.11929",
        description="Vision Transformer paper - images and text",
        expected_size_kb=3500,
    ),
    SamplePDF(
        name="arxiv_clip_paper.pdf",
        url="https://arxiv.org/pdf/2103.00020",
        description="CLIP paper - OpenAI research with figures",
        expected_size_kb=6500,
    ),

    # Academic/research papers
    SamplePDF(
        name="arxiv_diffusion_paper.pdf",
        url="https://arxiv.org/pdf/2006.11239",
        description="DDPM paper - Denoising Diffusion Probabilistic Models",
        expected_size_kb=4000,
    ),
    SamplePDF(
        name="arxiv_llama_paper.pdf",
        url="https://arxiv.org/pdf/2302.13971",
        description="LLaMA paper - Meta's language model",
        expected_size_kb=1800,
    ),
]


def download_file(url: str, dest_path: Path, timeout: int = 60) -> bool:
    """Download a file from URL to destination path."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PDF-Benchmark/1.0)"
        }
        response = requests.get(url, stream=True, timeout=timeout, headers=headers)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        with open(dest_path, "wb") as f:
            if total_size == 0:
                f.write(response.content)
            else:
                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    desc=dest_path.name[:30],
                    ncols=80,
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
        return True
    except Exception as e:
        print(f"  Error downloading: {e}")
        return False


def download_samples(
    output_dir: Path,
    skip_existing: bool = True,
    rate_limit: float = 2.0,
) -> list[Path]:
    """
    Download all sample PDFs.

    Args:
        output_dir: Directory to save PDFs
        skip_existing: Skip files that already exist
        rate_limit: Seconds to wait between downloads (respect rate limits)

    Returns:
        List of paths to successfully downloaded PDFs
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []

    print(f"\nDownloading {len(SAMPLE_PDFS)} sample PDFs to {output_dir}")
    print("=" * 60)

    for i, sample in enumerate(SAMPLE_PDFS):
        dest_path = output_dir / sample.name

        print(f"\n[{i + 1}/{len(SAMPLE_PDFS)}] {sample.name}")
        print(f"  Description: {sample.description}")
        print(f"  Expected size: ~{sample.expected_size_kb} KB")

        # Handle zip file specially (Python docs)
        if sample.url.endswith(".zip"):
            print(f"  Skipping ZIP file: {sample.name} (requires manual extraction)")
            continue

        if skip_existing and dest_path.exists():
            actual_size = dest_path.stat().st_size / 1024
            print(f"  Already exists ({actual_size:.1f} KB), skipping")
            downloaded.append(dest_path)
            continue

        print(f"  Downloading from: {sample.url[:60]}...")

        if download_file(sample.url, dest_path):
            actual_size = dest_path.stat().st_size / 1024
            print(f"  Downloaded: {actual_size:.1f} KB")
            downloaded.append(dest_path)
        else:
            print("  Failed to download")

        # Rate limiting to be respectful to servers
        if i < len(SAMPLE_PDFS) - 1:
            time.sleep(rate_limit)

    print("\n" + "=" * 60)
    print(f"Successfully downloaded {len(downloaded)} PDFs")

    return downloaded


def verify_pdfs(pdf_dir: Path) -> list[tuple[Path, int, int]]:
    """
    Verify downloaded PDFs and return info about each.

    Returns:
        List of (path, size_bytes, page_count) tuples
    """
    from pypdf import PdfReader

    results = []
    pdf_files = sorted(pdf_dir.glob("*.pdf"))

    print(f"\nVerifying {len(pdf_files)} PDFs in {pdf_dir}")
    print("=" * 60)

    for pdf_path in pdf_files:
        try:
            size_bytes = pdf_path.stat().st_size
            reader = PdfReader(pdf_path)
            page_count = len(reader.pages)
            results.append((pdf_path, size_bytes, page_count))
            print(f"  {pdf_path.name}: {size_bytes / 1024:.1f} KB, {page_count} pages")
        except Exception as e:
            print(f"  {pdf_path.name}: ERROR - {e}")

    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Download sample PDFs for benchmarking")
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("sample_pdfs"),
        help="Output directory for PDFs (default: sample_pdfs)",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-download files even if they exist",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=2.0,
        help="Seconds between downloads (default: 2.0)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing PDFs, don't download",
    )

    args = parser.parse_args()

    if args.verify_only:
        verify_pdfs(args.output_dir)
    else:
        downloaded = download_samples(
            args.output_dir,
            skip_existing=not args.no_skip,
            rate_limit=args.rate_limit,
        )
        if downloaded:
            verify_pdfs(args.output_dir)


if __name__ == "__main__":
    main()
