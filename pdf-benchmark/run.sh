#!/bin/bash
#
# PDF Text Extraction Benchmark Runner
#
# Usage:
#   ./run.sh              - Run full benchmark
#   ./run.sh download     - Download sample PDFs only
#   ./run.sh single       - Run single-threaded benchmarks only
#   ./run.sh parallel     - Run parallel benchmarks only
#   ./run.sh help         - Show help
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}PDF Text Extraction Benchmark${NC}"
echo -e "${GREEN}========================================${NC}"

# Ensure directories exist
mkdir -p sample_pdfs results

case "${1:-benchmark}" in
    download)
        echo -e "\n${YELLOW}Downloading sample PDFs...${NC}\n"
        docker compose run --rm download
        ;;

    single)
        echo -e "\n${YELLOW}Running single-threaded benchmarks...${NC}\n"
        docker compose run --rm benchmark python benchmark.py --single-only "$@"
        ;;

    parallel)
        echo -e "\n${YELLOW}Running parallel benchmarks...${NC}\n"
        docker compose run --rm benchmark python benchmark.py --parallel-only "$@"
        ;;

    benchmark|run)
        # Check if sample PDFs exist
        PDF_COUNT=$(find sample_pdfs -name "*.pdf" 2>/dev/null | wc -l)
        if [ "$PDF_COUNT" -eq 0 ]; then
            echo -e "${YELLOW}No PDFs found. Downloading samples first...${NC}\n"
            docker compose run --rm download
        fi

        echo -e "\n${YELLOW}Running full benchmark...${NC}\n"
        docker compose run --rm benchmark python benchmark.py "${@:2}"
        ;;

    build)
        echo -e "\n${YELLOW}Building Docker image...${NC}\n"
        docker compose build
        ;;

    shell)
        echo -e "\n${YELLOW}Opening shell in container...${NC}\n"
        docker compose run --rm benchmark /bin/bash
        ;;

    clean)
        echo -e "\n${YELLOW}Cleaning up...${NC}\n"
        docker compose down --rmi local
        rm -rf results/*.json
        echo -e "${GREEN}Cleaned up Docker images and results${NC}"
        ;;

    help|--help|-h)
        cat << EOF

Usage: ./run.sh [command] [options]

Commands:
  download     Download sample PDFs for testing
  benchmark    Run full benchmark (default)
  single       Run only single-threaded extractors
  parallel     Run only parallel extractors
  build        Build Docker image
  shell        Open shell in container
  clean        Remove Docker images and results
  help         Show this help message

Benchmark Options (passed to benchmark.py):
  --runs N           Number of benchmark runs per test (default: 3)
  --warmup N         Number of warmup runs (default: 1)
  -e, --extractors   Specific extractors to run
  -p, --pdfs         Specific PDF files to test
  --group-by         How to group results: pdf, extractor, flat
  --no-save          Don't save results to JSON

Examples:
  ./run.sh                           # Run full benchmark
  ./run.sh download                  # Download sample PDFs
  ./run.sh benchmark --runs 5        # Run with 5 iterations
  ./run.sh single -e pymupdf pypdf   # Test specific extractors
  ./run.sh shell                     # Debug in container

Available Extractors:
  Single-threaded: pymupdf, pypdfium2, pypdf, pdftext, mutool, pdftotext
  Parallel: pymupdf_parallel, pypdfium2_parallel, pypdf_parallel,
            pdftext_parallel, mutool_parallel, pdftotext_parallel

EOF
        ;;

    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo "Run './run.sh help' for usage information"
        exit 1
        ;;
esac

echo -e "\n${GREEN}Done!${NC}"
