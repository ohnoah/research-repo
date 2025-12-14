#!/usr/bin/env python3
"""
Comprehensive local test runner for the hybrid chart pipeline.

Runs on:
  - examples/ClearView (embedded workbooks)
  - examples/Newton   (often external workbooks; internalized offline first)

Output organization (what you asked for):
  - Group outputs at the same level as area/bar/etc.
  - Only include multi-series outputs for templates that contain at least one chart
    with >1 series, and only apply the new multi-series structural updater to those
    multi-series charts (skip single-series charts).
  - Only include multi-plot outputs for templates that contain at least one combo/
    multi-plot chart, and only apply structural updates to those charts.

Outputs are written under:
  examples/hybrid_pipeline_test_runs/_artifacts/<run_id>/

Layout:
  <run_id>/
    ClearView/
      smoke/<orig tree>/<pptx stem>/
      multi-series/<orig tree>/<pptx stem>/
      multi-plot/<orig tree>/<pptx stem>/
    Newton/
      smoke/...
      multi-series/...
      multi-plot/...
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import hybrid_chart_llm_pipeline as h  # noqa: E402
from internalize_utils import internalize_chart_workbook_relationship  # noqa: E402


ARTIFACTS_ROOT = Path(__file__).resolve().parent / "_artifacts"


def _ensure_aspose_license() -> None:
    try:
        import aspose.slides as slides  # type: ignore
    except Exception:
        return

    lic_path = REPO_ROOT / "Aspose.Slides.lic"
    if lic_path.exists():
        slides.License().set_license(str(lic_path))


def _is_combo_or_multi_plot(payload: h.ChartPromptPayload) -> bool:
    if payload.template_plot_count > 1:
        return True
    if payload.style_slots:
        types = {str(s.get("series_type", "")) for s in payload.style_slots}
        axes = {bool(s.get("plot_on_second_axis", False)) for s in payload.style_slots}
        return (len(types) > 1) or (len(axes) > 1)
    return False


def _vary_categories(base: List[str], *, mode: str, chart_idx: int) -> List[str]:
    if not base:
        base = ["Category 1", "Category 2", "Category 3"]

    if mode == "smoke":
        return list(base)

    if mode == "multi-series":
        # Alternate shorten vs extend to exercise both directions.
        if chart_idx % 2 == 0 and len(base) > 2:
            return list(base[: max(2, len(base) // 2)])
        return list(base) + [f"Extra {i+1}" for i in range(3)]

    if mode == "multi-plot":
        # Keep this small to reduce risk of layout issues, but still vary.
        if len(base) > 3:
            return list(base[:3])
        return list(base) + ["Extra 1", "Extra 2"]

    return list(base)


def _vary_points_xy(base: List[Tuple[float, float]], *, mode: str, chart_idx: int) -> List[Tuple[float, float]]:
    if not base:
        base = [(1.0, 1.0), (2.0, 1.5), (3.0, 2.0)]

    if mode == "smoke":
        return [(x + 1.0, y + 1.0) for x, y in base]

    if mode == "multi-series":
        if chart_idx % 2 == 0 and len(base) > 2:
            base = base[: max(2, len(base) // 2)]
        else:
            base = list(base) + [(float(len(base) + 1), float(len(base) + 2)), (float(len(base) + 2), float(len(base) + 3))]
        return [(x + 0.5, y + 0.75) for x, y in base]

    if mode == "multi-plot":
        base = list(base) + [(float(len(base) + 1), float(len(base) + 1.25))]
        return [(x + 0.25, y + 0.25) for x, y in base]

    return base


def _vary_points_bubble(base: List[Tuple[float, float, float]], *, mode: str, chart_idx: int) -> List[Tuple[float, float, float]]:
    if not base:
        base = [(1.0, 1.0, 5.0), (2.0, 1.5, 7.0), (3.0, 2.0, 9.0)]

    if mode == "smoke":
        return [(x + 0.3, y + 0.6, max(1.0, float(sz) * 1.05)) for x, y, sz in base]

    if mode == "multi-series":
        if chart_idx % 2 == 0 and len(base) > 2:
            base = base[: max(2, len(base) // 2)]
        else:
            base = list(base) + [
                (float(len(base) + 1), float(len(base) + 2), float(10 + len(base))),
                (float(len(base) + 2), float(len(base) + 3), float(12 + len(base))),
            ]
        return [(x + 0.25, y + 0.5, max(1.0, float(sz) * 1.1)) for x, y, sz in base]

    if mode == "multi-plot":
        base = list(base) + [(float(len(base) + 1), float(len(base) + 1.25), float(8 + len(base)))]
        return [(x + 0.15, y + 0.15, max(1.0, float(sz) * 1.05)) for x, y, sz in base]

    return base


def _desired_series_count(payload: h.ChartPromptPayload, *, mode: str, chart_idx: int) -> int:
    n = int(payload.template_total_series or 0)
    if n <= 0:
        return 0
    if mode == "smoke":
        return n
    if mode == "multi-series":
        if n == 1:
            return 1
        # Alternate add/remove to exercise growth and shrink.
        if chart_idx % 2 == 0:
            return max(1, n - 1)
        return n + 1
    if mode == "multi-plot":
        if _is_combo_or_multi_plot(payload) and n >= 2:
            return n + 1
        return n
    return n


def _make_update(payload: h.ChartPromptPayload, *, mode: str, chart_idx: int) -> Dict[str, Any]:
    if payload.strategy == h.ChartStrategy.PPTX_DSL_SINGLE_SERIES:
        if payload.dsl is None:
            raise RuntimeError("strategy=pptx_dsl_single_series but dsl missing")

        if payload.dsl.kind == "category_chart_dsl":
            cats = _vary_categories(payload.dsl.categories, mode=mode, chart_idx=chart_idx)
            s = payload.dsl.series[0] if payload.dsl.series else h.DslSeriesCategory(name="Series 1", values=[1.0] * len(cats))
            vals: List[Optional[float]] = []
            for j in range(len(cats)):
                base = 0.0
                if j < len(s.values) and s.values[j] is not None:
                    base = float(s.values[j])
                vals.append(base + (j + 1) * 3.0)
            return {"kind": "category_chart_update", "categories": cats, "series": [{"name": f"{s.name} ({mode})", "values": vals}]}

        if payload.dsl.kind == "xy_chart_dsl":
            s = payload.dsl.series[0] if payload.dsl.series else h.DslSeriesXy(name="Series 1", points=[])
            pts = _vary_points_xy(list(s.points), mode=mode, chart_idx=chart_idx)
            return {"kind": "xy_chart_update", "series": [{"name": f"{s.name} ({mode})", "points": [[x, y] for x, y in pts]}]}

        if payload.dsl.kind == "bubble_chart_dsl":
            s = payload.dsl.series[0] if payload.dsl.series else h.DslSeriesBubble(name="Series 1", points=[])
            pts = _vary_points_bubble(list(s.points), mode=mode, chart_idx=chart_idx)
            return {
                "kind": "bubble_chart_update",
                "series": [{"name": f"{s.name} ({mode})", "points": [[x, y, sz] for x, y, sz in pts]}],
            }

        raise RuntimeError(f"Unknown DSL kind: {payload.dsl.kind}")

    if payload.strategy == h.ChartStrategy.ASPOSE_STRUCTURAL:
        if payload.dsl is None:
            raise RuntimeError("strategy=aspose_structural but dsl missing (needed for synthetic updates)")
        if not payload.style_slots:
            raise RuntimeError("strategy=aspose_structural but style_slots missing")

        slot_count = len(payload.style_slots)
        desired_series = _desired_series_count(payload, mode=mode, chart_idx=chart_idx)

        if payload.dsl.kind == "category_chart_dsl":
            cats = _vary_categories(payload.dsl.categories, mode=mode, chart_idx=chart_idx)
            series_specs: List[Dict[str, Any]] = []
            for s_idx in range(desired_series):
                slot_id = s_idx % slot_count
                vals = [float((s_idx + 1) * (j + 1)) for j in range(len(cats))]
                series_specs.append(
                    {"name": f"Series {s_idx+1} ({mode})", "style_slot_id": slot_id, "values": vals}
                )
            return {"update_kind": "aspose_category", "categories": cats, "series": series_specs}

        if payload.dsl.kind == "xy_chart_dsl":
            series_specs = []
            base_series = payload.dsl.series or []
            for s_idx in range(desired_series):
                slot_id = s_idx % slot_count
                base_points = list(base_series[s_idx % len(base_series)].points) if base_series else []
                pts = _vary_points_xy(base_points, mode=mode, chart_idx=chart_idx)
                series_specs.append(
                    {
                        "name": f"Series {s_idx+1} ({mode})",
                        "style_slot_id": slot_id,
                        "points": [{"x": x, "y": y} for x, y in pts],
                    }
                )
            return {"update_kind": "aspose_scatter", "series": series_specs}

        if payload.dsl.kind == "bubble_chart_dsl":
            series_specs = []
            base_series = payload.dsl.series or []
            for s_idx in range(desired_series):
                slot_id = s_idx % slot_count
                base_points = list(base_series[s_idx % len(base_series)].points) if base_series else []
                pts = _vary_points_bubble(base_points, mode=mode, chart_idx=chart_idx)
                series_specs.append(
                    {
                        "name": f"Series {s_idx+1} ({mode})",
                        "style_slot_id": slot_id,
                        "points": [{"x": x, "y": y, "size": sz} for x, y, sz in pts],
                    }
                )
            return {"update_kind": "aspose_bubble", "series": series_specs}

        raise RuntimeError(f"Unknown DSL kind: {payload.dsl.kind}")

    if payload.workbook is None:
        raise RuntimeError("strategy=aspose_workbook_patch but workbook snapshot missing")

    cells = []
    for addr in payload.workbook.editable_cells[:15]:
        cells.append({"address": addr, "value": 77.0})
    return {"kind": "workbook_cell_patch_update", "sheet_index": payload.workbook.grid.sheet_index, "cells": cells}


def _internalize_newton_if_needed(source_original: Path, internalized_out: Path) -> None:
    shutil.copyfile(source_original, internalized_out)
    locs = h.list_chart_locators_aspose(str(internalized_out), 0)
    for loc in locs:
        _ct, src_kind = h.get_chart_type_aspose(str(internalized_out), loc)
        if src_kind != "external":
            continue
        tmp = internalized_out.with_suffix(".tmp.pptx")
        changed = internalize_chart_workbook_relationship(
            str(internalized_out),
            str(tmp),
            slide_index=loc.slide_index,
            shape_id=loc.shape_id,
        )
        if changed:
            tmp.replace(internalized_out)
        else:
            if tmp.exists():
                tmp.unlink()


def _run_mode_for_case(
    *,
    base_for_updates: Path,
    mode_out_dir: Path,
    mode: str,
    should_update_chart,
) -> Tuple[int, List[str]]:
    mode_out_dir.mkdir(parents=True, exist_ok=True)

    locs = h.list_chart_locators_aspose(str(base_for_updates), 0)
    if not locs:
        return (0, [f"SKIP no charts: {mode_out_dir}"])

    current = str(base_for_updates)
    lines: List[str] = []
    updated_any = False
    for idx, loc in enumerate(locs, start=1):
        payload = h.build_llm_prompt_payload(current, loc)
        lines.append(
            f"chart{idx:02d} shape_id={loc.shape_id} strategy={payload.strategy.value} total_series={payload.template_total_series} plots={payload.template_plot_count}"
        )

        if not should_update_chart(payload):
            continue

        update = _make_update(payload, mode=mode, chart_idx=idx)
        out_pptx = mode_out_dir / f"updated_after_chart_{idx:02d}.pptx"
        h.apply_chart_update(current, str(out_pptx), payload, json.dumps(update))
        current = str(out_pptx)
        updated_any = True

    final_copy = mode_out_dir / "updated_after_all_charts.pptx"
    final_copy.write_bytes(Path(current).read_bytes())
    return (len(locs), lines if updated_any else lines + ["(no charts updated in this mode)"])


def main() -> int:
    _ensure_aspose_license()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = ARTIFACTS_ROOT / run_id
    out_root.mkdir(parents=True, exist_ok=True)

    datasets = [
        ("ClearView", REPO_ROOT / "examples" / "ClearView"),
        ("Newton", REPO_ROOT / "examples" / "Newton"),
    ]

    all_logs: List[str] = []
    ok = 0
    fail = 0

    for dataset_name, dataset_root in datasets:
        pptxs = sorted(dataset_root.rglob("*.pptx"))
        pptxs = [p for p in pptxs if "_artifacts" not in p.parts]

        for src in pptxs:
            rel = src.relative_to(REPO_ROOT)
            rel_within_dataset = src.relative_to(dataset_root)
            # Prepare base-for-updates (internalize Newton charts once per template).
            prep_dir = out_root / dataset_name / "_prepared" / rel_within_dataset.parent / rel_within_dataset.stem
            prep_dir.mkdir(parents=True, exist_ok=True)

            source_original = prep_dir / "source_original.pptx"
            shutil.copyfile(src, source_original)

            if dataset_name == "Newton":
                internalized = prep_dir / "internalized_embedded_workbook.pptx"
                _internalize_newton_if_needed(source_original, internalized)
                base_for_updates = internalized
            else:
                base_for_updates = source_original

            # First pass: decide whether this template belongs in multi-series / multi-plot groups.
            locs = h.list_chart_locators_aspose(str(base_for_updates), 0)
            has_multi_series = False
            has_multi_plot = False
            for loc in locs:
                payload0 = h.build_llm_prompt_payload(str(base_for_updates), loc)
                if int(payload0.template_total_series or 0) > 1:
                    has_multi_series = True
                if _is_combo_or_multi_plot(payload0):
                    has_multi_plot = True

            def _out_dir(group: str) -> Path:
                return out_root / dataset_name / group / rel_within_dataset.parent / rel_within_dataset.stem

            groups: List[Tuple[str, bool]] = [
                ("smoke", True),
                ("multi-series", has_multi_series),
                ("multi-plot", has_multi_plot),
            ]

            for group_name, should_run in groups:
                if not should_run:
                    continue

                group_dir = _out_dir(group_name)
                group_dir.mkdir(parents=True, exist_ok=True)

                # Copy inputs for side-by-side inspection.
                shutil.copyfile(source_original, group_dir / "source_original.pptx")
                if dataset_name == "Newton":
                    shutil.copyfile(base_for_updates, group_dir / "internalized_embedded_workbook.pptx")
                shutil.copyfile(base_for_updates, group_dir / "base_for_updates.pptx")

                if group_name == "smoke":
                    mode = "smoke"

                    def should_update_chart(payload: h.ChartPromptPayload) -> bool:
                        return True

                elif group_name == "multi-series":
                    mode = "multi-series"

                    def should_update_chart(payload: h.ChartPromptPayload) -> bool:
                        # Only exercise the new structural multi-series logic on charts that actually have >1 series.
                        return (
                            payload.strategy == h.ChartStrategy.ASPOSE_STRUCTURAL
                            and int(payload.template_total_series or 0) > 1
                            and payload.dsl is not None
                            and bool(payload.style_slots)
                        )

                elif group_name == "multi-plot":
                    mode = "multi-plot"

                    def should_update_chart(payload: h.ChartPromptPayload) -> bool:
                        return (
                            payload.strategy == h.ChartStrategy.ASPOSE_STRUCTURAL
                            and _is_combo_or_multi_plot(payload)
                            and payload.dsl is not None
                            and bool(payload.style_slots)
                        )

                else:
                    raise RuntimeError(f"Unknown group: {group_name}")

                try:
                    n_charts, lines = _run_mode_for_case(
                        base_for_updates=Path(group_dir / "base_for_updates.pptx"),
                        mode_out_dir=group_dir,
                        mode=mode,
                        should_update_chart=should_update_chart,
                    )
                    ok += 1
                    all_logs.append(
                        f"OK  {rel} group={group_name} charts={n_charts} -> {group_dir.relative_to(REPO_ROOT)}"
                    )
                    all_logs.extend([f"  {ln}" for ln in lines])
                except Exception as e:
                    fail += 1
                    all_logs.append(f"FAIL {rel} group={group_name}: {type(e).__name__}: {e}")

    (out_root / "run_log.txt").write_text("\n".join(all_logs) + "\n", encoding="utf-8")

    readme = out_root / "README.txt"
    readme.write_text(
        "\n".join(
            [
                "Comprehensive chart pipeline run",
                "",
                f"Outputs: {out_root.relative_to(REPO_ROOT)}",
                "",
                "Outputs are grouped by category at the same level as area/bar/etc:",
                "- smoke/",
                "- multi-series/ (only templates with >1-series charts)",
                "- multi-plot/   (only templates with combo/multi-plot charts)",
                "",
                "Each template folder contains:",
                "- source_original.pptx",
                "- base_for_updates.pptx (internalized for Newton)",
                "- updated_after_chart_XX.pptx",
                "- updated_after_all_charts.pptx",
                "",
                "Log:",
                f"- {out_root.relative_to(REPO_ROOT)}/run_log.txt",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Outputs: {out_root}")
    print(f"OK={ok} FAIL={fail}")
    print(f"Log: {out_root / 'run_log.txt'}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
