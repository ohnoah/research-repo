# PDF Text Extraction Benchmark

A Dockerized benchmark suite for comparing PDF text extraction performance across various Python libraries and CLI tools.

## Tools Benchmarked

### Python Libraries
| Tool | Engine | Thread Safety | Parallelization Strategy |
|------|--------|---------------|-------------------------|
| **PyMuPDF** (`fitz`) | MuPDF | Not thread-safe | ProcessPoolExecutor |
| **pypdfium2** | PDFium | Not thread-safe | ProcessPoolExecutor |
| **pypdf** | Pure Python | Thread-safe | ThreadPoolExecutor |
| **pdftext** | pypdfium2 | Not thread-safe | ProcessPoolExecutor |

### CLI Tools
| Tool | Engine | Parallelization Strategy |
|------|--------|-------------------------|
| **mutool draw** | MuPDF | ThreadPoolExecutor (subprocess) |
| **pdftotext** | Poppler | ThreadPoolExecutor (subprocess) |

## Quick Start

```bash
# 1. Download sample PDFs
./run.sh download

# 2. Run full benchmark
./run.sh benchmark

# Or do both in one step (auto-downloads if no PDFs found)
./run.sh
```

## Usage

```bash
# Run all benchmarks (single + parallel)
./run.sh benchmark

# Run only single-threaded benchmarks
./run.sh single

# Run only parallel benchmarks
./run.sh parallel

# Run specific extractors
./run.sh benchmark -e pymupdf pypdfium2 pdftotext

# Run with more iterations for accuracy
./run.sh benchmark --runs 5 --warmup 2

# Test specific PDFs
./run.sh benchmark -p paper1.pdf paper2.pdf

# Open shell in container for debugging
./run.sh shell
```

## Project Structure

```
pdf-benchmark/
├── Dockerfile           # Container definition
├── docker-compose.yml   # Docker services
├── requirements.txt     # Python dependencies
├── run.sh              # Runner script
├── benchmark.py        # Main benchmark script
├── extractors.py       # All extraction functions
├── download_samples.py # Sample PDF downloader
├── sample_pdfs/        # Test PDFs (downloaded)
└── results/            # Benchmark results (JSON)
```

## Available Extractors

### Single-threaded
- `pymupdf` - PyMuPDF (MuPDF engine)
- `pypdfium2` - pypdfium2 (PDFium engine)
- `pypdf` - pypdf (pure Python)
- `pdftext` - pdftext (pypdfium2 wrapper)
- `mutool` - mutool draw CLI
- `pdftotext` - pdftotext CLI (Poppler)

### Parallel
- `pymupdf_parallel` - ProcessPoolExecutor with page chunks
- `pypdfium2_parallel` - ProcessPoolExecutor with page chunks
- `pypdf_parallel` - ThreadPoolExecutor with page chunks
- `pdftext_parallel` - ProcessPoolExecutor with page chunks
- `mutool_parallel` - ThreadPoolExecutor with CLI page ranges
- `pdftotext_parallel` - ThreadPoolExecutor with CLI page ranges

## Sample PDFs

The benchmark includes various public domain PDFs:

- **Small** (<500 KB): W3C dummy PDF, simple documents
- **Medium** (500 KB - 5 MB): Research papers (Attention, BERT, GPT-2, ResNet)
- **Large** (5+ MB): GPT-3 paper, CLIP paper, documentation

## Results

Results are saved as JSON files in `results/` with:
- Extraction time (seconds)
- Pages per second
- MB per second
- Text length extracted
- Success/failure status

Example output:
```
arxiv_attention_paper.pdf (2200.0 KB, 15 pages)
------------------------------------------------------------
Extractor          Mode      Time       Pages/s  MB/s   Status
pymupdf            single    45.2 ms    331.9    47.43  OK
pymupdf_parallel   parallel  28.1 ms    533.8    76.31  OK
pypdfium2          single    52.3 ms    286.8    41.00  OK
pdftotext          single    38.4 ms    390.6    55.83  OK
```

## Thread Safety Notes

- **PyMuPDF**, **pypdfium2**, and **pdftext** are NOT thread-safe
  - Use ProcessPoolExecutor for parallelization
  - Each worker opens its own copy from bytes

- **pypdf** is thread-safe for reading
  - Can use ThreadPoolExecutor
  - Limited speedup due to GIL

- **CLI tools** (`mutool`, `pdftotext`) are safe with ThreadPoolExecutor
  - Each call spawns a separate process
  - Good parallelization via native page range options

## Building Manually

```bash
# Build image
docker compose build

# Run benchmark
docker compose run --rm benchmark python benchmark.py

# Download samples
docker compose run --rm download
```

## License

This benchmark suite is provided for testing purposes. The sample PDFs are from public sources (arXiv, government documents, etc.) and are used under their respective licenses.
