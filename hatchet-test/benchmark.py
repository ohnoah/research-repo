#!/usr/bin/env python3
"""Benchmark runner for measuring Hatchet-lite performance."""
import asyncio
import sys
import os
import time
import statistics
from datetime import datetime

# Ensure we can find the local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hatchet_client import hatchet
from workflows import simple_benchmark, work_benchmark, simple_workflow


async def run_single_task_benchmark(num_tasks: int = 100) -> dict:
    """Run single task benchmark to measure queuing latency."""
    print(f"\n{'='*60}")
    print(f"Running Single Task Benchmark ({num_tasks} tasks)")
    print('='*60)

    results = []
    errors = []

    for i in range(num_tasks):
        enqueue_time_ns = time.time_ns()
        try:
            run = await simple_benchmark.aio.run(
                input={
                    "task_id": i,
                    "enqueue_time_ns": enqueue_time_ns,
                }
            )
            result = await run.result()
            results.append(result)
        except Exception as e:
            errors.append(str(e))
            print(f"  Error on task {i}: {e}")

        if (i + 1) % 10 == 0:
            print(f"  Completed {i + 1}/{num_tasks} tasks")

    # Calculate statistics
    if results:
        queuing_latencies = [r.get("queuing_latency_ms", 0) for r in results]
        execution_times = [r.get("execution_time_ms", 0) for r in results]

        stats = {
            "total_tasks": num_tasks,
            "successful_tasks": len(results),
            "failed_tasks": len(errors),
            "queuing_latency_ms": {
                "min": min(queuing_latencies),
                "max": max(queuing_latencies),
                "mean": statistics.mean(queuing_latencies),
                "median": statistics.median(queuing_latencies),
                "stdev": statistics.stdev(queuing_latencies) if len(queuing_latencies) > 1 else 0,
                "p95": sorted(queuing_latencies)[int(len(queuing_latencies) * 0.95)] if queuing_latencies else 0,
                "p99": sorted(queuing_latencies)[int(len(queuing_latencies) * 0.99)] if queuing_latencies else 0,
            },
            "execution_time_ms": {
                "min": min(execution_times),
                "max": max(execution_times),
                "mean": statistics.mean(execution_times),
                "median": statistics.median(execution_times),
            },
        }

        print("\n--- Single Task Results ---")
        print(f"  Successful: {stats['successful_tasks']}/{stats['total_tasks']}")
        print(f"  Queuing Latency (ms):")
        print(f"    Min:    {stats['queuing_latency_ms']['min']:.2f}")
        print(f"    Max:    {stats['queuing_latency_ms']['max']:.2f}")
        print(f"    Mean:   {stats['queuing_latency_ms']['mean']:.2f}")
        print(f"    Median: {stats['queuing_latency_ms']['median']:.2f}")
        print(f"    Stdev:  {stats['queuing_latency_ms']['stdev']:.2f}")
        print(f"    P95:    {stats['queuing_latency_ms']['p95']:.2f}")
        print(f"    P99:    {stats['queuing_latency_ms']['p99']:.2f}")

        return stats
    else:
        print("  No successful results!")
        return {"error": "No successful results", "errors": errors}


async def run_concurrent_task_benchmark(num_tasks: int = 50, concurrency: int = 10) -> dict:
    """Run concurrent task benchmark."""
    print(f"\n{'='*60}")
    print(f"Running Concurrent Task Benchmark ({num_tasks} tasks, {concurrency} concurrent)")
    print('='*60)

    start_time = time.time()
    results = []
    errors = []

    # Create semaphore for concurrency control
    sem = asyncio.Semaphore(concurrency)

    async def run_task(task_id: int):
        async with sem:
            enqueue_time_ns = time.time_ns()
            try:
                run = await simple_benchmark.aio.run(
                    input={
                        "task_id": task_id,
                        "enqueue_time_ns": enqueue_time_ns,
                    }
                )
                result = await run.result()
                return result
            except Exception as e:
                return {"error": str(e), "task_id": task_id}

    # Run all tasks concurrently
    tasks = [run_task(i) for i in range(num_tasks)]
    task_results = await asyncio.gather(*tasks)

    for result in task_results:
        if "error" in result:
            errors.append(result)
        else:
            results.append(result)

    elapsed_time = time.time() - start_time

    if results:
        queuing_latencies = [r.get("queuing_latency_ms", 0) for r in results]

        stats = {
            "total_tasks": num_tasks,
            "concurrency": concurrency,
            "successful_tasks": len(results),
            "failed_tasks": len(errors),
            "total_time_seconds": elapsed_time,
            "throughput_tasks_per_second": len(results) / elapsed_time if elapsed_time > 0 else 0,
            "queuing_latency_ms": {
                "min": min(queuing_latencies),
                "max": max(queuing_latencies),
                "mean": statistics.mean(queuing_latencies),
                "median": statistics.median(queuing_latencies),
                "stdev": statistics.stdev(queuing_latencies) if len(queuing_latencies) > 1 else 0,
                "p95": sorted(queuing_latencies)[int(len(queuing_latencies) * 0.95)] if queuing_latencies else 0,
            },
        }

        print("\n--- Concurrent Task Results ---")
        print(f"  Successful: {stats['successful_tasks']}/{stats['total_tasks']}")
        print(f"  Total Time: {stats['total_time_seconds']:.2f}s")
        print(f"  Throughput: {stats['throughput_tasks_per_second']:.2f} tasks/sec")
        print(f"  Queuing Latency (ms):")
        print(f"    Min:    {stats['queuing_latency_ms']['min']:.2f}")
        print(f"    Max:    {stats['queuing_latency_ms']['max']:.2f}")
        print(f"    Mean:   {stats['queuing_latency_ms']['mean']:.2f}")
        print(f"    Median: {stats['queuing_latency_ms']['median']:.2f}")
        print(f"    P95:    {stats['queuing_latency_ms']['p95']:.2f}")

        return stats
    else:
        print("  No successful results!")
        return {"error": "No successful results"}


async def run_workflow_benchmark(num_workflows: int = 20) -> dict:
    """Run multi-step workflow benchmark."""
    print(f"\n{'='*60}")
    print(f"Running Multi-Step Workflow Benchmark ({num_workflows} workflows)")
    print('='*60)

    results = []
    errors = []

    for i in range(num_workflows):
        enqueue_time_ns = time.time_ns()
        try:
            run = await simple_workflow.aio.run(
                input={
                    "workflow_id": i,
                    "enqueue_time_ns": enqueue_time_ns,
                }
            )
            # Wait for completion
            result = await run.result()

            # Get step outputs
            step1_output = result.get("step1", {})
            step2_output = result.get("step2", {})
            step3_output = result.get("step3", {})

            workflow_result = {
                "workflow_id": i,
                "initial_queuing_ms": step1_output.get("queuing_latency_ms", 0),
                "step1_to_step2_ms": step2_output.get("inter_step_latency_ms", 0),
                "step2_to_step3_ms": step3_output.get("inter_step_latency_ms", 0),
                "total_time_ns": step3_output.get("total_time_ns", time.time_ns()) - enqueue_time_ns,
            }
            workflow_result["total_time_ms"] = workflow_result["total_time_ns"] / 1_000_000
            results.append(workflow_result)

        except Exception as e:
            errors.append({"workflow_id": i, "error": str(e)})
            print(f"  Error on workflow {i}: {e}")

        if (i + 1) % 5 == 0:
            print(f"  Completed {i + 1}/{num_workflows} workflows")

    if results:
        initial_queuing = [r["initial_queuing_ms"] for r in results]
        step1_to_step2 = [r["step1_to_step2_ms"] for r in results]
        step2_to_step3 = [r["step2_to_step3_ms"] for r in results]
        total_times = [r["total_time_ms"] for r in results]

        stats = {
            "total_workflows": num_workflows,
            "successful_workflows": len(results),
            "failed_workflows": len(errors),
            "initial_queuing_ms": {
                "mean": statistics.mean(initial_queuing),
                "median": statistics.median(initial_queuing),
                "max": max(initial_queuing),
            },
            "step1_to_step2_ms": {
                "mean": statistics.mean(step1_to_step2),
                "median": statistics.median(step1_to_step2),
                "max": max(step1_to_step2),
            },
            "step2_to_step3_ms": {
                "mean": statistics.mean(step2_to_step3),
                "median": statistics.median(step2_to_step3),
                "max": max(step2_to_step3),
            },
            "total_workflow_time_ms": {
                "mean": statistics.mean(total_times),
                "median": statistics.median(total_times),
                "max": max(total_times),
            },
        }

        print("\n--- Workflow Results ---")
        print(f"  Successful: {stats['successful_workflows']}/{stats['total_workflows']}")
        print(f"  Initial Queuing (ms): mean={stats['initial_queuing_ms']['mean']:.2f}, median={stats['initial_queuing_ms']['median']:.2f}")
        print(f"  Step1->Step2 (ms): mean={stats['step1_to_step2_ms']['mean']:.2f}, median={stats['step1_to_step2_ms']['median']:.2f}")
        print(f"  Step2->Step3 (ms): mean={stats['step2_to_step3_ms']['mean']:.2f}, median={stats['step2_to_step3_ms']['median']:.2f}")
        print(f"  Total Workflow Time (ms): mean={stats['total_workflow_time_ms']['mean']:.2f}, median={stats['total_workflow_time_ms']['median']:.2f}")

        return stats
    else:
        print("  No successful results!")
        return {"error": "No successful results"}


async def main():
    """Run all benchmarks."""
    print("\n" + "="*60)
    print("HATCHET-LITE PERFORMANCE BENCHMARK")
    print(f"Started at: {datetime.now().isoformat()}")
    print("="*60)

    all_results = {}

    # Warm-up run
    print("\n--- Warm-up (5 tasks) ---")
    try:
        for i in range(5):
            run = await simple_benchmark.aio.run(
                input={"task_id": -1, "enqueue_time_ns": time.time_ns()}
            )
            await run.result()
        print("  Warm-up complete")
    except Exception as e:
        print(f"  Warm-up failed: {e}")

    # Run benchmarks
    try:
        all_results["single_task"] = await run_single_task_benchmark(num_tasks=50)
    except Exception as e:
        print(f"Single task benchmark failed: {e}")
        all_results["single_task"] = {"error": str(e)}

    try:
        all_results["concurrent_task"] = await run_concurrent_task_benchmark(num_tasks=50, concurrency=10)
    except Exception as e:
        print(f"Concurrent task benchmark failed: {e}")
        all_results["concurrent_task"] = {"error": str(e)}

    try:
        all_results["workflow"] = await run_workflow_benchmark(num_workflows=20)
    except Exception as e:
        print(f"Workflow benchmark failed: {e}")
        all_results["workflow"] = {"error": str(e)}

    # Summary
    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)

    if "single_task" in all_results and "queuing_latency_ms" in all_results["single_task"]:
        st = all_results["single_task"]["queuing_latency_ms"]
        print(f"\nSingle Task Queuing Latency:")
        print(f"  Median: {st['median']:.2f} ms")
        print(f"  P95:    {st['p95']:.2f} ms")
        print(f"  P99:    {st['p99']:.2f} ms")

    if "concurrent_task" in all_results and "throughput_tasks_per_second" in all_results["concurrent_task"]:
        ct = all_results["concurrent_task"]
        print(f"\nConcurrent Task Performance:")
        print(f"  Throughput: {ct['throughput_tasks_per_second']:.2f} tasks/sec")
        print(f"  Median Latency: {ct['queuing_latency_ms']['median']:.2f} ms")

    if "workflow" in all_results and "total_workflow_time_ms" in all_results["workflow"]:
        wf = all_results["workflow"]
        print(f"\nMulti-Step Workflow Performance:")
        print(f"  Median Total Time: {wf['total_workflow_time_ms']['median']:.2f} ms")
        print(f"  Median Step-to-Step: {wf['step1_to_step2_ms']['median']:.2f} ms")

    print("\n" + "="*60)
    print(f"Completed at: {datetime.now().isoformat()}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
