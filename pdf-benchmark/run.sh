#!/bin/bash
#
# PDF Text Extraction Benchmark Runner
#
# Usage:
#   ./run.sh                    - Run default benchmark (single, parallel, hybrid_50, split_4)
#   ./run.sh download           - Download sample PDFs only
#   ./run.sh single             - Run single-threaded benchmarks only
#   ./run.sh parallel           - Run parallel benchmarks only
#   ./run.sh hybrid             - Run hybrid benchmarks (50 and 100 cutoffs)
#   ./run.sh split              - Run split benchmarks (2, 4, 8 chunks)
#   ./run.sh all                - Run ALL extractors
#   ./run.sh help               - Show help
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
        docker compose run --rm benchmark python benchmark.py --category single "${@:2}"
        ;;

    parallel)
        echo -e "\n${YELLOW}Running parallel benchmarks...${NC}\n"
        docker compose run --rm benchmark python benchmark.py --category parallel "${@:2}"
        ;;

    hybrid)
        echo -e "\n${YELLOW}Running hybrid benchmarks (50 and 100 page cutoffs)...${NC}\n"
        docker compose run --rm benchmark python benchmark.py --category hybrid_50 hybrid_100 "${@:2}"
        ;;

    split)
        echo -e "\n${YELLOW}Running split benchmarks (2, 4, 8 chunks)...${NC}\n"
        docker compose run --rm benchmark python benchmark.py --category split_2 split_4 split_8 "${@:2}"
        ;;

    all)
        echo -e "\n${YELLOW}Running ALL extractors...${NC}\n"
        docker compose run --rm benchmark python benchmark.py --category single parallel hybrid_50 hybrid_100 split_2 split_4 split_8 "${@:2}"
        ;;

    benchmark|run)
        # Check if sample PDFs exist
        PDF_COUNT=$(find sample_pdfs -name "*.pdf" 2>/dev/null | wc -l)
        if [ "$PDF_COUNT" -eq 0 ]; then
            echo -e "${YELLOW}No PDFs found. Downloading samples first...${NC}\n"
            docker compose run --rm download
        fi

        echo -e "\n${YELLOW}Running default benchmark (single, parallel, hybrid_50, split_4)...${NC}\n"
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
  benchmark    Run default benchmark (single, parallel, hybrid_50, split_4)
  single       Run only single-threaded extractors
  parallel     Run only parallel extractors
  hybrid       Run hybrid extractors (50 and 100 page cutoffs)
  split        Run split extractors (2, 4, 8 chunks)
  all          Run ALL extractors (comprehensive)
  build        Build Docker image
  shell        Open shell in container
  clean        Remove Docker images and results
  help         Show this help message

Benchmark Options (passed to benchmark.py):
  --runs N           Number of benchmark runs per test (default: 3)
  --warmup N         Number of warmup runs (default: 1)
  --workers N        Number of workers for thread pool (default: 4)
  --sync             Run in synchronous mode (not async)
  -e, --extractors   Specific extractors to run
  -c, --category     Run specific categories
  -p, --pdfs         Specific PDF files to test
  --group-by         How to group results: pdf, extractor, category, flat
  --no-save          Don't save results to JSON

Environment Variables:
  BENCHMARK_WORKERS     Default worker count (default: 4)
  BENCHMARK_CPU_COUNT   Override detected CPU count

Examples:
  ./run.sh                           # Run default benchmark
  ./run.sh download                  # Download sample PDFs
  ./run.sh all --runs 5              # Run all extractors with 5 iterations
  ./run.sh single --workers 8        # Single-threaded with 8 workers
  ./run.sh hybrid                    # Test hybrid modes
  ./run.sh split                     # Test split modes
  ./run.sh shell                     # Debug in container

Categories:
  single      Single-threaded extractors (6 tools)
  parallel    Parallel extractors with page-range chunking (6 tools)
  hybrid_50   Hybrid: single < 50 pages, parallel >= 50 (6 tools)
  hybrid_100  Hybrid: single < 100 pages, parallel >= 100 (6 tools)
  split_2     Split PDF into 2 files, process in parallel (6 tools)
  split_4     Split PDF into 4 files, process in parallel (6 tools)
  split_8     Split PDF into 8 files, process in parallel (6 tools)

Available Base Extractors:
  pymupdf, pypdfium2, pypdf, pdftext, mutool, pdftotext

EOF
        ;;

    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo "Run './run.sh help' for usage information"
        exit 1
        ;;
esac

echo -e "\n${GREEN}Done!${NC}"
