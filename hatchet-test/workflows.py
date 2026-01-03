"""Test workflows for benchmarking hatchet-lite performance."""
import time
from datetime import datetime
from pydantic import BaseModel
from hatchet_sdk import Context

from hatchet_client import hatchet


class BenchmarkInput(BaseModel):
    """Input for benchmark tasks."""
    task_id: int
    enqueue_time_ns: int  # nanoseconds since epoch when task was enqueued


class BenchmarkOutput(BaseModel):
    """Output from benchmark tasks."""
    task_id: int
    enqueue_time_ns: int
    start_time_ns: int
    end_time_ns: int
    queuing_latency_ms: float
    execution_time_ms: float


# Simple task that immediately returns - measures pure queuing overhead
@hatchet.task(name="simple_benchmark")
def simple_benchmark(input: dict, ctx: Context) -> dict:
    """Simple task that records timing."""
    start_time_ns = time.time_ns()

    enqueue_time_ns = input.get("enqueue_time_ns", start_time_ns)
    task_id = input.get("task_id", 0)

    # Calculate queuing latency
    queuing_latency_ms = (start_time_ns - enqueue_time_ns) / 1_000_000

    # Simulate minimal work
    result = {"status": "completed", "task_id": task_id}

    end_time_ns = time.time_ns()
    execution_time_ms = (end_time_ns - start_time_ns) / 1_000_000

    return {
        "task_id": task_id,
        "enqueue_time_ns": enqueue_time_ns,
        "start_time_ns": start_time_ns,
        "end_time_ns": end_time_ns,
        "queuing_latency_ms": queuing_latency_ms,
        "execution_time_ms": execution_time_ms,
    }


# Task with simulated work
@hatchet.task(name="work_benchmark")
def work_benchmark(input: dict, ctx: Context) -> dict:
    """Task that does some work to simulate real workloads."""
    start_time_ns = time.time_ns()

    enqueue_time_ns = input.get("enqueue_time_ns", start_time_ns)
    task_id = input.get("task_id", 0)
    work_duration_ms = input.get("work_duration_ms", 10)

    # Calculate queuing latency
    queuing_latency_ms = (start_time_ns - enqueue_time_ns) / 1_000_000

    # Simulate work
    time.sleep(work_duration_ms / 1000)

    end_time_ns = time.time_ns()
    execution_time_ms = (end_time_ns - start_time_ns) / 1_000_000

    return {
        "task_id": task_id,
        "enqueue_time_ns": enqueue_time_ns,
        "start_time_ns": start_time_ns,
        "end_time_ns": end_time_ns,
        "queuing_latency_ms": queuing_latency_ms,
        "execution_time_ms": execution_time_ms,
    }


# Multi-step workflow
simple_workflow = hatchet.workflow(name="simple_workflow")


@simple_workflow.task()
def step1(input: dict, ctx: Context) -> dict:
    """First step of workflow."""
    start_time_ns = time.time_ns()
    enqueue_time_ns = input.get("enqueue_time_ns", start_time_ns)
    queuing_latency_ms = (start_time_ns - enqueue_time_ns) / 1_000_000

    return {
        "step": 1,
        "queuing_latency_ms": queuing_latency_ms,
        "timestamp_ns": time.time_ns(),
    }


@simple_workflow.task()
def step2(input: dict, ctx: Context) -> dict:
    """Second step of workflow."""
    start_time_ns = time.time_ns()
    step1_data = ctx.task_output("step1")

    # Time between steps
    inter_step_latency_ms = (start_time_ns - step1_data.get("timestamp_ns", start_time_ns)) / 1_000_000

    return {
        "step": 2,
        "inter_step_latency_ms": inter_step_latency_ms,
        "timestamp_ns": time.time_ns(),
    }


@simple_workflow.task()
def step3(input: dict, ctx: Context) -> dict:
    """Third step of workflow."""
    start_time_ns = time.time_ns()
    step2_data = ctx.task_output("step2")

    inter_step_latency_ms = (start_time_ns - step2_data.get("timestamp_ns", start_time_ns)) / 1_000_000

    return {
        "step": 3,
        "inter_step_latency_ms": inter_step_latency_ms,
        "total_time_ns": time.time_ns(),
    }
