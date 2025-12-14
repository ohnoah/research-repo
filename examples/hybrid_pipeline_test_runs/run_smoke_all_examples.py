#!/usr/bin/env python3
"""
End-to-end smoke test across *all* PPTX templates in examples/Newton + examples/ClearView.

For each PPTX:
- Discover chart locators on slide 0 (Aspose)
- Build prompt payload (DSL or workbook snapshot)
- Create synthetic "LLM output" update
- Apply update to produce an output PPTX

Additionally:
- For Newton (external-linked charts), it writes an internalized-only copy first.

Outputs are written under:
  examples/hybrid_pipeline_test_runs/_artifacts/<run_id>/smoke_all/...
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


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


def _synthetic_update_from_payload(payload: h.ChartPromptPayload) -> Dict[str, Any]:
    if payload.strategy == h.ChartStrategy.PPTX_DSL_SINGLE_SERIES and payload.dsl is not None:
        if payload.dsl.kind == "category_chart_dsl":
            cats = payload.dsl.categories
            series = []
            for s_idx, s in enumerate(payload.dsl.series[:1]):
                vals = []
                for j, v in enumerate(s.values):
                    base = 0.0 if v is None else float(v)
                    vals.append(base + (s_idx + 1) * (j + 1) * 2.0)
                series.append({"name": f"{s.name} (smoke)", "values": vals})
            return {"kind": "category_chart_update", "categories": cats, "series": series}

        if payload.dsl.kind == "xy_chart_dsl":
            series = []
            for s in payload.dsl.series[:1]:
                pts = [[x + 1.0, y + 1.0] for x, y in s.points]
                series.append({"name": f"{s.name} (smoke)", "points": pts})
            return {"kind": "xy_chart_update", "series": series}

        if payload.dsl.kind == "bubble_chart_dsl":
            series = []
            for s in payload.dsl.series[:1]:
                pts = [[x + 0.3, y + 0.6, max(1.0, sz * 1.05)] for x, y, sz in s.points]
                series.append({"name": f"{s.name} (smoke)", "points": pts})
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
                    vals.append(base + (s_idx + 1) * (j + 1) * 1.5)
                series.append({"name": f"{s.name} (smoke)", "style_slot_id": s_idx % len(payload.style_slots), "values": vals})
            return {"update_kind": "aspose_category", "categories": cats, "series": series}

        if payload.dsl.kind == "xy_chart_dsl":
            series = []
            for s_idx, s in enumerate(payload.dsl.series):
                pts = [{"x": x + 1.0, "y": y + 1.0} for x, y in s.points]
                series.append({"name": f"{s.name} (smoke)", "style_slot_id": s_idx % len(payload.style_slots), "points": pts})
            return {"update_kind": "aspose_scatter", "series": series}

        if payload.dsl.kind == "bubble_chart_dsl":
            series = []
            for s_idx, s in enumerate(payload.dsl.series):
                pts = [{"x": x + 0.3, "y": y + 0.6, "size": max(1.0, float(sz) * 1.05)} for x, y, sz in s.points]
                series.append({"name": f"{s.name} (smoke)", "style_slot_id": s_idx % len(payload.style_slots), "points": pts})
            return {"update_kind": "aspose_bubble", "series": series}

        raise RuntimeError(f"Unknown DSL kind: {payload.dsl.kind}")

    if payload.workbook is None:
        raise RuntimeError("strategy=aspose_workbook_patch but workbook snapshot missing")

    # Patch a handful of editable cells. Keep small to reduce risk of breaking structure.
    cells = []
    for addr in payload.workbook.editable_cells[:15]:
        cells.append({"address": addr, "value": 77.0})
    return {
        "kind": "workbook_cell_patch_update",
        "sheet_index": payload.workbook.grid.sheet_index,
        "cells": cells,
    }


def main() -> int:
    _ensure_aspose_license()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = ARTIFACTS_ROOT / run_id / "smoke_all"
    out_root.mkdir(parents=True, exist_ok=True)

    pptxs = sorted((REPO_ROOT / "examples").rglob("*.pptx"))
    # Exclude prior artifacts to avoid recursion.
    pptxs = [p for p in pptxs if "_artifacts" not in p.parts]

    lines: List[str] = []
    ok = 0
    fail = 0

    for src in pptxs:
        rel = src.relative_to(REPO_ROOT)
        if rel.parts[:2] not in (("examples", "Newton"), ("examples", "ClearView")):
            continue

        case_dir = out_root / rel.parent.relative_to("examples") / rel.stem
        case_dir.mkdir(parents=True, exist_ok=True)

        source_original = case_dir / "source_original.pptx"
        shutil.copyfile(src, source_original)

        # For Newton charts: create an internalized-only copy (no data updates).
        internalized = None
        if "Newton" in rel.parts:
            internalized = case_dir / "internalized_embedded_workbook.pptx"
            shutil.copyfile(source_original, internalized)
            locs = h.list_chart_locators_aspose(str(internalized), 0)
            for loc in locs:
                _ct, src_kind = h.get_chart_type_aspose(str(internalized), loc)
                if src_kind == "external":
                    tmp = internalized.with_suffix(".tmp.pptx")
                    changed = internalize_chart_workbook_relationship(
                        str(internalized),
                        str(tmp),
                        slide_index=loc.slide_index,
                        shape_id=loc.shape_id,
                    )
                    if changed:
                        tmp.replace(internalized)
                    else:
                        if tmp.exists():
                            tmp.unlink()

        base_for_update = internalized if internalized is not None else source_original

        try:
            locs = h.list_chart_locators_aspose(str(base_for_update), 0)
            if not locs:
                lines.append(f"SKIP no charts: {rel}")
                continue

            current = str(base_for_update)
            for i, loc in enumerate(locs, start=1):
                payload = h.build_llm_prompt_payload(current, loc)
                update = _synthetic_update_from_payload(payload)
                out_pptx = case_dir / f"updated_after_chart_{i:02d}.pptx"
                h.apply_chart_update(current, str(out_pptx), payload, json.dumps(update))
                current = str(out_pptx)

            final_copy = case_dir / "updated_after_all_charts.pptx"
            final_copy.write_bytes(Path(current).read_bytes())
            ok += 1
            lines.append(f"OK  {rel} charts={len(locs)} -> {case_dir.relative_to(REPO_ROOT)}")
        except Exception as e:
            fail += 1
            lines.append(f"FAIL {rel}: {type(e).__name__}: {e}")

    (out_root / "smoke_log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Outputs: {out_root}")
    print(f"OK={ok} FAIL={fail}")
    print(f"Log: {out_root / 'smoke_log.txt'}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
