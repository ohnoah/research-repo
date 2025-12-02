# PDF Text Extraction Benchmark

A Dockerized benchmark suite for comparing PDF text extraction performance across various Python libraries and CLI tools.

## Features

- **6 extraction tools**: PyMuPDF, pypdfium2, pypdf, pdftext, mutool, pdftotext
- **7 extraction modes**: single, parallel, hybrid (50/100), split (2/4/8)
- **Async runtime**: Tests run inside asyncio with ThreadPoolExecutor (realistic Django/FastAPI usage)
- **Configurable workers**: Control parallelism via environment variables
- **Comprehensive results**: JSON output with detailed metrics

## Tools Benchmarked

### Python Libraries
| Tool | Engine | Thread Safety | Parallelization |
|------|--------|---------------|-----------------|
| **PyMuPDF** (`fitz`) | MuPDF | Not thread-safe | ProcessPoolExecutor |
| **pypdfium2** | PDFium | Not thread-safe | ProcessPoolExecutor |
| **pypdf** | Pure Python | Thread-safe | ThreadPoolExecutor |
| **pdftext** | pypdfium2 | Not thread-safe | ProcessPoolExecutor |

### CLI Tools
| Tool | Engine | Parallelization |
|------|--------|-----------------|
| **mutool draw** | MuPDF | ThreadPoolExecutor (subprocess) |
| **pdftotext** | Poppler | ThreadPoolExecutor (subprocess) |

## Extraction Modes

| Mode | Description | Best For |
|------|-------------|----------|
| **single** | Single-threaded extraction | Small PDFs, baseline |
| **parallel** | Page-range chunking with process/thread pool | Large PDFs (50+ pages) |
| **hybrid_50** | Single if <50 pages, parallel otherwise | Mixed workloads |
| **hybrid_100** | Single if <100 pages, parallel otherwise | Mixed workloads |
| **split_2** | Split PDF into 2 files, extract in parallel | Alternative parallelism |
| **split_4** | Split PDF into 4 files, extract in parallel | 4-core systems |
| **split_8** | Split PDF into 8 files, extract in parallel | 8-core systems |

## Quick Start

```bash
# 1. Download sample PDFs
./run.sh download

# 2. Run default benchmark (single, parallel, hybrid_50, split_4)
./run.sh benchmark

# Or do both in one step (auto-downloads if no PDFs found)
./run.sh
```

## Usage

```bash
# Run default benchmarks
./run.sh benchmark

# Run only single-threaded benchmarks
./run.sh single

# Run only parallel benchmarks
./run.sh parallel

# Run hybrid benchmarks (test cutoff points)
./run.sh hybrid

# Run split benchmarks (test split strategies)
./run.sh split

# Run ALL extractors (comprehensive - 42 total)
./run.sh all

# Run with more iterations for accuracy
./run.sh benchmark --runs 5 --warmup 2

# Control worker count
./run.sh benchmark --workers 8

# Run in sync mode (not async)
./run.sh benchmark --sync

# Test specific extractors
./run.sh benchmark -e pymupdf pypdfium2 pdftotext

# Test specific categories
./run.sh benchmark --category single hybrid_50
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BENCHMARK_WORKERS` | Number of workers in thread pool | 4 |
| `BENCHMARK_CPU_COUNT` | Override detected CPU count | auto |

## Project Structure

```
pdf-benchmark/
├── Dockerfile           # Container definition
├── docker-compose.yml   # Docker services
├── requirements.txt     # Python dependencies
├── run.sh              # Runner script
├── benchmark.py        # Main benchmark script (async)
├── extractors.py       # All extraction functions
├── download_samples.py # Sample PDF downloader
├── sample_pdfs/        # Test PDFs (downloaded)
└── results/            # Benchmark results (JSON)
```

## Available Extractors (42 total)

### Single-threaded (6)
`pymupdf`, `pypdfium2`, `pypdf`, `pdftext`, `mutool`, `pdftotext`

### Parallel (6)
`pymupdf_parallel`, `pypdfium2_parallel`, `pypdf_parallel`, `pdftext_parallel`, `mutool_parallel`, `pdftotext_parallel`

### Hybrid 50-page cutoff (6)
`pymupdf_hybrid_50`, `pypdfium2_hybrid_50`, `pypdf_hybrid_50`, `pdftext_hybrid_50`, `mutool_hybrid_50`, `pdftotext_hybrid_50`

### Hybrid 100-page cutoff (6)
`pymupdf_hybrid_100`, `pypdfium2_hybrid_100`, `pypdf_hybrid_100`, `pdftext_hybrid_100`, `mutool_hybrid_100`, `pdftotext_hybrid_100`

### Split into 2 chunks (6)
`pymupdf_split_2`, `pypdfium2_split_2`, `pypdf_split_2`, `pdftext_split_2`, `mutool_split_2`, `pdftotext_split_2`

### Split into 4 chunks (6)
`pymupdf_split_4`, `pypdfium2_split_4`, `pypdf_split_4`, `pdftext_split_4`, `mutool_split_4`, `pdftotext_split_4`

### Split into 8 chunks (6)
`pymupdf_split_8`, `pypdfium2_split_8`, `pypdf_split_8`, `pdftext_split_8`, `mutool_split_8`, `pdftotext_split_8`

## Sample PDFs

Downloads from public sources including:
- arXiv papers (Attention, BERT, GPT-2/3, ResNet, ViT, CLIP, LLaMA, Diffusion)
- W3C dummy PDF
- Varying sizes from ~4KB to ~10MB

## Results

Results are saved as JSON files in `results/` with:
- Extraction time (seconds)
- Pages per second
- MB per second
- Text length extracted
- Success/failure status
- Extractor category
- Configuration (workers, async mode, etc.)

Example output:
```
arxiv_gpt3_paper.pdf (6609.4 KB, 75 pages)
--------------------------------------------------------------------------------
Extractor                 Category    Time       Pages/s  MB/s   Text Len  Status
------------------------  ----------  -------  ---------  -----  --------  ------
pypdfium2                 single      157ms        478.3  43.3   225,891   OK
pymupdf                   single      168ms        446.4  40.4   223,456   OK
pypdfium2_hybrid_50       hybrid_50   395ms        189.8  17.2   225,891   OK
pymupdf_split_4           split_4     312ms        240.4  21.7   223,456   OK
```

## Async Runtime

All benchmarks run inside an async context to simulate real-world usage:

```python
# Similar to Django/FastAPI usage pattern
loop = asyncio.get_running_loop()
cpu_pool = ThreadPoolExecutor(max_workers=4)
result = await loop.run_in_executor(cpu_pool, extractor_func, pdf_path)
```

This ensures benchmark results reflect actual production performance.

## Thread Safety Notes

- **PyMuPDF**, **pypdfium2**, **pdftext**: NOT thread-safe
  - Use ProcessPoolExecutor for parallelization
  - Split mode uses file splitting to enable ThreadPoolExecutor

- **pypdf**: Thread-safe for reading
  - Can use ThreadPoolExecutor
  - Limited speedup due to GIL

- **CLI tools** (`mutool`, `pdftotext`): Safe with ThreadPoolExecutor
  - Each call spawns a separate process
  - Native page range support

## Building Manually

```bash
# Build image
docker compose build

# Run benchmark
docker compose run --rm benchmark python benchmark.py

# Download samples
docker compose run --rm download

# Interactive shell
docker compose run --rm benchmark /bin/bash
```

## License

This benchmark suite is provided for testing purposes. The sample PDFs are from public sources (arXiv, government documents, etc.) and are used under their respective licenses.
