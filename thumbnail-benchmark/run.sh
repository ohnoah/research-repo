#!/bin/bash
# Run the thumbnail benchmark suite
#
# Usage:
#   ./run.sh              # Run full benchmark
#   ./run.sh download     # Only download samples
#   ./run.sh quick        # Quick benchmark (single-threaded only)
#   ./run.sh multiprocess # Only multiprocessing tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if sample PDFs exist
if [ ! -d "sample_pdfs" ] || [ -z "$(ls -A sample_pdfs 2>/dev/null)" ]; then
    echo "Downloading sample PDFs..."
    python download_samples.py
fi

case "${1:-full}" in
    download)
        echo "Downloading sample PDFs..."
        python download_samples.py "$@"
        ;;
    quick)
        echo "Running quick benchmark (single-threaded only)..."
        python benchmark.py --category single --runs 1 --warmup 0
        ;;
    single)
        echo "Running single-threaded benchmark..."
        python benchmark.py --category single
        ;;
    threadpool)
        echo "Running thread pool benchmark..."
        python benchmark.py --category threadpool
        ;;
    multiprocess)
        echo "Running multiprocessing benchmark..."
        python benchmark.py --category multiprocess
        ;;
    full)
        echo "Running full benchmark..."
        python benchmark.py
        ;;
    compare)
        echo "Running comparison (pymupdf vs pypdfium2 vs pdf2image)..."
        python benchmark.py -r pymupdf pypdfium2 pdf2image
        ;;
    *)
        echo "Usage: $0 [download|quick|single|threadpool|multiprocess|full|compare]"
        echo ""
        echo "Commands:"
        echo "  download     Only download sample PDFs"
        echo "  quick        Quick benchmark (single-threaded, 1 run)"
        echo "  single       Single-threaded renderers only"
        echo "  threadpool   Thread pool renderers only"
        echo "  multiprocess Multiprocessing renderers only"
        echo "  full         Full benchmark (all renderers, default)"
        echo "  compare      Compare base renderers (pymupdf vs pypdfium2 vs pdf2image)"
        exit 1
        ;;
esac

echo ""
echo "Done!"
