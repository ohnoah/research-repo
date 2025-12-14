#!/usr/bin/env python3
"""
Apply synthetic data updates to ALL internalized Newton PPTX copies.

Input: a folder produced by `internalize_newton_workbooks.py`:
  examples/hybrid_pipeline_test_runs/_artifacts/<run_id>/internalized_newton

Output:
  examples/hybrid_pipeline_test_runs/_artifacts/<run_id>/updated_internalized_newton

Updates are applied chart-by-chart (cumulative) on slide 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import hybrid_chart_llm_pipeline as h  # noqa: E402


def _ensure_aspose_license() -> None:
    try:
        import aspose.slides as slides  # type: ignore
    except Exception:
        return

    lic_path = REPO_ROOT / "Aspose.Slides.lic"
    if lic_path.exists():
        slides.License().set_license(str(lic_path))


def _synthetic_update(payload: h.ChartPromptPayload) -> Dict[str, Any]:
    if payload.strategy == h.ChartStrategy.PPTX_DSL_SINGLE_SERIES and payload.dsl is not None:
        if payload.dsl.kind == "category_chart_dsl":
            cats = payload.dsl.categories
            series = []
            for s_idx, s in enumerate(payload.dsl.series[:1]):
                vals = []
                for j, v in enumerate(s.values):
                    base = 0.0 if v is None else float(v)
                    vals.append(base + (s_idx + 1) * (j + 1) * 2.5)
                series.append({"name": f"{s.name} (upd)", "values": vals})
            return {"kind": "category_chart_update", "categories": cats, "series": series}

        if payload.dsl.kind == "xy_chart_dsl":
            series = []
            for s in payload.dsl.series[:1]:
                pts = [[x + 1.0, y + 1.0] for x, y in s.points]
                series.append({"name": f"{s.name} (upd)", "points": pts})
            return {"kind": "xy_chart_update", "series": series}

        if payload.dsl.kind == "bubble_chart_dsl":
            series = []
            for s in payload.dsl.series[:1]:
                pts = [[x + 0.25, y + 0.5, max(1.0, sz * 1.1)] for x, y, sz in s.points]
                series.append({"name": f"{s.name} (upd)", "points": pts})
            return {"kind": "bubble_chart_update", "series": series}

        raise RuntimeError(f"Unknown DSL kind: {payload.dsl.kind}")

    if payload.strategy == h.ChartStrategy.ASPOSE_STRUCTURAL:
        if payload.dsl is None:
            raise RuntimeError("strategy=aspose_structural but no DSL snapshot available for synthetic update")
        if not payload.style_slots:
            raise RuntimeError("strategy=aspose_structural but style_slots missing")

        if payload.dsl.kind == "category_chart_dsl":
            cats = payload.dsl.categories
            series = []
            for s_idx, s in enumerate(payload.dsl.series):
                vals = []
                for j, v in enumerate(s.values):
                    base = 0.0 if v is None else float(v)
                    vals.append(base + (s_idx + 1) * (j + 1) * 1.25)
                series.append({"name": f"{s.name} (upd)", "style_slot_id": s_idx % len(payload.style_slots), "values": vals})
            return {"update_kind": "aspose_category", "categories": cats, "series": series}

        if payload.dsl.kind == "xy_chart_dsl":
            series = []
            for s_idx, s in enumerate(payload.dsl.series):
                pts = [{"x": x + 1.0, "y": y + 1.0} for x, y in s.points]
                series.append({"name": f"{s.name} (upd)", "style_slot_id": s_idx % len(payload.style_slots), "points": pts})
            return {"update_kind": "aspose_scatter", "series": series}

        if payload.dsl.kind == "bubble_chart_dsl":
            series = []
            for s_idx, s in enumerate(payload.dsl.series):
                pts = [{"x": x + 0.25, "y": y + 0.5, "size": max(1.0, float(sz) * 1.1)} for x, y, sz in s.points]
                series.append({"name": f"{s.name} (upd)", "style_slot_id": s_idx % len(payload.style_slots), "points": pts})
            return {"update_kind": "aspose_bubble", "series": series}

        raise RuntimeError(f"Unknown DSL kind: {payload.dsl.kind}")

    if payload.workbook is None:
        raise RuntimeError("strategy=aspose_workbook_patch but workbook snapshot missing")

    cells = []
    for addr in payload.workbook.editable_cells[:20]:
        cells.append({"address": addr, "value": 55.0})
    return {
        "kind": "workbook_cell_patch_update",
        "sheet_index": payload.workbook.grid.sheet_index,
        "cells": cells,
    }


def main() -> int:
    _ensure_aspose_license()

    if len(sys.argv) >= 2:
        in_dir = Path(sys.argv[1]).resolve()
    else:
        roots = sorted((REPO_ROOT / "examples" / "hybrid_pipeline_test_runs" / "_artifacts").glob("*/internalized_newton"))
        if not roots:
            print("No internalized_newton folder found under examples/hybrid_pipeline_test_runs/_artifacts/")
            return 2
        in_dir = roots[-1].resolve()

    run_root = in_dir.parent
    out_dir = run_root / "updated_internalized_newton"
    out_dir.mkdir(parents=True, exist_ok=True)

    internalized_pptxs = sorted(in_dir.rglob("internalized_embedded_workbook.pptx"))
    log_lines: List[str] = []
    ok = 0
    fail = 0

    for internalized_src in internalized_pptxs:
        case_rel_dir = internalized_src.parent.relative_to(in_dir)
        dst_dir = out_dir / case_rel_dir
        dst_dir.mkdir(parents=True, exist_ok=True)

        original_src = internalized_src.parent / "source_original.pptx"
        dst_original = dst_dir / "source_original.pptx"
        dst_internalized = dst_dir / "internalized_embedded_workbook.pptx"
        if original_src.exists():
            dst_original.write_bytes(original_src.read_bytes())
        dst_internalized.write_bytes(internalized_src.read_bytes())

        current = str(dst_internalized)
        try:
            locs = h.list_chart_locators_aspose(current, 0)
            if not locs:
                log_lines.append(f"SKIP no charts: {case_rel_dir}")
                continue

            for i, loc in enumerate(locs, start=1):
                payload = h.build_llm_prompt_payload(current, loc)
                upd = _synthetic_update(payload)
                out_pptx = dst_dir / f"updated_after_chart_{i:02d}.pptx"
                h.apply_chart_update(current, str(out_pptx), payload, json.dumps(upd))
                current = str(out_pptx)

            ok += 1
            final_copy = dst_dir / "updated_after_all_charts.pptx"
            final_copy.write_bytes(Path(current).read_bytes())
            log_lines.append(f"OK  {case_rel_dir} charts={len(locs)} -> {final_copy.relative_to(REPO_ROOT)}")
        except Exception as e:
            fail += 1
            log_lines.append(f"FAIL {case_rel_dir}: {type(e).__name__}: {e}")

    (out_dir / "update_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(f"Input: {in_dir}")
    print(f"Output: {out_dir}")
    print(f"OK={ok} FAIL={fail}")
    print(f"Log: {out_dir / 'update_log.txt'}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
