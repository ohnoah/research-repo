#!/usr/bin/env python3
"""Worker process that runs the benchmark workflows."""
import sys
import os

# Ensure we can find the local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hatchet_client import hatchet
from workflows import simple_benchmark, work_benchmark, simple_workflow


def main():
    """Start the worker."""
    print("Starting Hatchet worker...")
    print(f"Connecting to: {os.environ.get('HATCHET_CLIENT_GRPC_HOST', 'localhost')}:{os.environ.get('HATCHET_CLIENT_GRPC_PORT', '7077')}")

    worker = hatchet.worker(
        "benchmark-worker",
        workflows=[simple_benchmark, work_benchmark, simple_workflow],
        slots=10,  # Allow 10 concurrent tasks
    )

    print("Worker started. Waiting for tasks...")
    worker.start()


if __name__ == "__main__":
    main()
