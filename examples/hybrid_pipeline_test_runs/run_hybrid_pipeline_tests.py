#!/usr/bin/env python3
"""
Runs a lightweight, local-only smoke test of `hybrid_chart_llm_pipeline.py`.

What it does:
- Picks a few template PPTX files from `examples/`
- Discovers chart locators (Aspose)
- Builds per-chart prompt payloads (DSL or workbook snapshot)
- Creates synthetic "LLM output" updates:
    - DSL: modifies values while preserving shape
    - Workbook: patches a handful of editable numeric cells
- Applies updates to produce output PPTX files you can open to visually inspect

All artifacts are written under `examples/hybrid_pipeline_test_runs/_artifacts/...` (gitignored).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = Path(__file__).resolve().parent / "_artifacts"

# Ensure repo root is importable when running from this subdir.
sys.path.insert(0, str(REPO_ROOT))

import hybrid_chart_llm_pipeline as h  # noqa: E402


def _ensure_aspose_license() -> None:
    try:
        import aspose.slides as slides  # type: ignore
    except Exception:
        return

    lic_path = REPO_ROOT / "Aspose.Slides.lic"
    if lic_path.exists():
        lic = slides.License()
        lic.set_license(str(lic_path))


@dataclass(frozen=True)
class ChartTestCase:
    pptx_relpath: str
    slide_index: int = 0


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _make_category_update(dsl: h.CategoryChartDSL) -> h.CategoryChartUpdate:
    categories = [f"{dsl.categories[i]}" for i in range(len(dsl.categories))]
    series: List[h.DslSeriesCategory] = []
    for s_idx, s in enumerate(dsl.series):
        vals: List[Optional[float]] = []
        for i, v in enumerate(s.values):
            base = 0.0 if v is None else float(v)
            vals.append(base + (s_idx + 1) * (i + 1))
        series.append(h.DslSeriesCategory(name=f"{s.name} (test)", values=vals))
    return h.CategoryChartUpdate(categories=categories, series=series)


def _make_xy_update(dsl: h.XyChartDSL) -> h.XyChartUpdate:
    series: List[h.DslSeriesXy] = []
    for s in dsl.series:
        pts: List[Tuple[float, float]] = []
        for x, y in s.points:
            pts.append((float(x) + 1.0, float(y) + 2.0))
        series.append(h.DslSeriesXy(name=f"{s.name} (test)", points=pts))
    return h.XyChartUpdate(series=series)


def _make_bubble_update(dsl: h.BubbleChartDSL) -> h.BubbleChartUpdate:
    series: List[h.DslSeriesBubble] = []
    for s in dsl.series:
        pts: List[Tuple[float, float, float]] = []
        for x, y, size in s.points:
            pts.append((float(x) + 0.5, float(y) + 1.5, max(1.0, float(size) * 1.2)))
        series.append(h.DslSeriesBubble(name=f"{s.name} (test)", points=pts))
    return h.BubbleChartUpdate(series=series)


def _grid_value_at(snapshot: h.WorkbookSnapshot, a1: str) -> Any:
    grid = snapshot.grid
    start_row, start_col = h._a1_to_rowcol(grid.start_cell)  # type: ignore[attr-defined]
    row, col = h._a1_to_rowcol(a1)  # type: ignore[attr-defined]
    r_off = row - start_row
    c_off = col - start_col
    if r_off < 0 or c_off < 0:
        return None
    if r_off >= grid.n_rows or c_off >= grid.n_cols:
        return None
    return grid.values[r_off][c_off]


def _make_workbook_patch(snapshot: h.WorkbookSnapshot, *, max_cells: int = 18) -> h.WorkbookCellPatchUpdate:
    cells: List[h.CellPatch] = []

    for addr in snapshot.editable_cells:
        if len(cells) >= max_cells:
            break
        v = _grid_value_at(snapshot, addr)
        if isinstance(v, (int, float)):
            cells.append(h.CellPatch(address=addr, value=float(v) + 7.0))

    # If the editable list doesn't overlap the grid (or has no numeric cells), still try a few.
    if not cells:
        for addr in snapshot.editable_cells[:max_cells]:
            cells.append(h.CellPatch(address=addr, value=123.0))

    return h.WorkbookCellPatchUpdate(sheet_index=snapshot.grid.sheet_index, cells=cells)


def _apply_one_update(
    pptx_in: Path,
    pptx_out: Path,
    payload: h.ChartPromptPayload,
    update_obj: Any,
) -> None:
    if hasattr(update_obj, "dict"):
        update_payload = update_obj.dict()  # type: ignore[attr-defined]
    else:
        update_payload = update_obj
    update_json = json.dumps(update_payload, indent=2)
    h.apply_chart_update(str(pptx_in), str(pptx_out), payload, update_json)


def _summarize_payload(payload: h.ChartPromptPayload) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "locator": payload.locator.dict(),
        "strategy": payload.strategy.value,
        "chart_type": payload.chart_type,
    }
    if payload.dsl is not None:
        out["dsl_kind"] = payload.dsl.kind  # type: ignore[union-attr]
    if payload.workbook is not None:
        out["workbook_source"] = payload.workbook.chart_data_source
        out["workbook_sheet"] = payload.workbook.grid.sheet_name
        out["workbook_grid_start"] = payload.workbook.grid.start_cell
        out["workbook_grid_shape"] = [payload.workbook.grid.n_rows, payload.workbook.grid.n_cols]
        out["workbook_editable_cells"] = len(payload.workbook.editable_cells)
    return out


def main() -> int:
    _ensure_aspose_license()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ARTIFACTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Keep this list small and representative:
    # - Some Newton charts are EXTERNAL workbook (workbook path will fail, DSL should still work)
    # - Some ClearView charts are EMBEDDED workbook (workbook path should work)
    cases = [
        ChartTestCase("examples/Newton/column/Diagnostic Output (Phase 2) - Hertfordshire_slide101.pptx"),
        ChartTestCase("examples/Newton/bubble/Diagnostic Output (Phase 2) - Hertfordshire_slide71.pptx"),
        ChartTestCase("examples/Newton/pie/Diagnostic Output (Phase 2) - Hertfordshire_slide119.pptx"),
        ChartTestCase("examples/ClearView/area/sharepoint-a905254a59b2a2d284791215d276d9da-159656bce6219f85e2328a81560d7cea_slide5.pptx"),
        ChartTestCase("examples/ClearView/bubble/sharepoint-a905254a59b2a2d284791215d276d9da-159656bce6219f85e2328a81560d7cea_slide38.pptx"),
        ChartTestCase("examples/ClearView/pie/sharepoint-6e0bc89f4d9b0ea12a684883694093ce-792627f728dffa7abe7784885508c626_slide15.pptx"),
    ]

    log_lines: List[str] = []

    for case in cases:
        pptx_path = REPO_ROOT / case.pptx_relpath
        if not pptx_path.exists():
            log_lines.append(f"SKIP missing: {case.pptx_relpath}")
            continue

        case_dir = run_dir / Path(case.pptx_relpath).stem
        case_dir.mkdir(parents=True, exist_ok=True)

        # Work on a local copy so we never mutate the template.
        source_original = case_dir / "source_original.pptx"
        base_for_updates = case_dir / "base_for_updates.pptx"
        shutil.copyfile(pptx_path, source_original)
        shutil.copyfile(pptx_path, base_for_updates)

        locs = h.list_chart_locators_aspose(str(base_for_updates), case.slide_index)
        log_lines.append(f"{case.pptx_relpath}: charts={len(locs)}")
        if not locs:
            continue

        cumulative_in = base_for_updates
        for idx, loc in enumerate(locs, start=1):
            chart_dir = case_dir / f"chart_{idx:02d}_shape_{loc.shape_id}"
            chart_dir.mkdir(parents=True, exist_ok=True)

            aspose_type, src_kind = h.get_chart_type_aspose(str(base_for_updates), loc)
            strategy = h.choose_strategy(str(base_for_updates), loc)

            # Build payload using the module's default logic.
            payload = h.build_llm_prompt_payload(str(base_for_updates), loc)

            _write_json(chart_dir / "payload.json", json.loads(payload.json()))
            _write_json(chart_dir / "payload_summary.json", _summarize_payload(payload))

            update_obj: Any
            if payload.strategy == h.ChartStrategy.PPTX_DSL_SINGLE_SERIES and payload.dsl is not None:
                if payload.dsl.kind == "category_chart_dsl":
                    update_obj = _make_category_update(payload.dsl)  # type: ignore[arg-type]
                elif payload.dsl.kind == "xy_chart_dsl":
                    update_obj = _make_xy_update(payload.dsl)  # type: ignore[arg-type]
                elif payload.dsl.kind == "bubble_chart_dsl":
                    update_obj = _make_bubble_update(payload.dsl)  # type: ignore[arg-type]
                else:
                    raise RuntimeError(f"Unknown DSL kind: {payload.dsl.kind}")

            elif payload.strategy == h.ChartStrategy.ASPOSE_STRUCTURAL:
                if payload.dsl is None or not payload.style_slots:
                    raise RuntimeError("strategy=aspose_structural but missing dsl/style_slots")
                slot_count = len(payload.style_slots)
                if payload.dsl.kind == "category_chart_dsl":
                    series = []
                    for s_idx, s in enumerate(payload.dsl.series):
                        vals = []
                        for j, v in enumerate(s.values):
                            base = 0.0 if v is None else float(v)
                            vals.append(base + (s_idx + 1) * (j + 1) * 1.5)
                        series.append(
                            {"name": f"{s.name} (test)", "style_slot_id": s_idx % slot_count, "values": vals}
                        )
                    update_obj = {"update_kind": "aspose_category", "categories": payload.dsl.categories, "series": series}
                elif payload.dsl.kind == "xy_chart_dsl":
                    series = []
                    for s_idx, s in enumerate(payload.dsl.series):
                        pts = [{"x": x + 1.0, "y": y + 2.0} for x, y in s.points]
                        series.append(
                            {"name": f"{s.name} (test)", "style_slot_id": s_idx % slot_count, "points": pts}
                        )
                    update_obj = {"update_kind": "aspose_scatter", "series": series}
                elif payload.dsl.kind == "bubble_chart_dsl":
                    series = []
                    for s_idx, s in enumerate(payload.dsl.series):
                        pts = [{"x": x + 0.5, "y": y + 1.5, "size": max(1.0, float(sz) * 1.2)} for x, y, sz in s.points]
                        series.append(
                            {"name": f"{s.name} (test)", "style_slot_id": s_idx % slot_count, "points": pts}
                        )
                    update_obj = {"update_kind": "aspose_bubble", "series": series}
                else:
                    raise RuntimeError(f"Unknown DSL kind: {payload.dsl.kind}")

            else:
                if payload.workbook is None:
                    raise RuntimeError("strategy=aspose_workbook_patch but no workbook snapshot")
                update_obj = _make_workbook_patch(payload.workbook)

            if hasattr(update_obj, "dict"):
                _write_json(chart_dir / "synthetic_llm_update.json", update_obj.dict())  # type: ignore[attr-defined]
            else:
                _write_json(chart_dir / "synthetic_llm_update.json", update_obj)

            # Per-chart output (apply update to base copy only)
            per_chart_out = chart_dir / "updated_only_this_chart.pptx"
            _apply_one_update(base_for_updates, per_chart_out, payload, update_obj)

            # Cumulative output (apply sequentially)
            cumulative_out = chart_dir / f"updated_after_chart_{idx:02d}.pptx"
            _apply_one_update(cumulative_in, cumulative_out, payload, update_obj)
            cumulative_in = cumulative_out

            # Best-effort checks
            msg = f"  chart{idx} shape_id={loc.shape_id} aspose_type={aspose_type} src={src_kind} strategy={strategy.value}"
            log_lines.append(msg)

            # Verify workbook availability after DSL update on EXTERNAL charts (python-pptx replace_data tends to embed).
            if payload.strategy == h.ChartStrategy.PPTX_DSL_SINGLE_SERIES and src_kind == "external":
                try:
                    _ = h.read_embedded_workbook_bytes_aspose(str(per_chart_out), loc)
                    log_lines.append("    post-update workbook stream: OK (now readable)")
                except Exception as e:
                    log_lines.append(f"    post-update workbook stream: STILL UNAVAILABLE ({type(e).__name__}: {e})")

    (run_dir / "run_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    print(f"Wrote artifacts to: {run_dir}")
    print(f"Log: {run_dir / 'run_log.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
