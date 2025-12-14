#!/usr/bin/env python3
"""
Internalize chart workbooks for the Newton templates (which currently reference EXTERNAL workbooks).

Writes outputs under:
  examples/hybrid_pipeline_test_runs/_artifacts/<run_id>/internalized_newton/...

This does NOT apply any data updates; it only rewrites chart workbook relationships so:
- python-pptx `Chart.replace_data()` can operate (it requires an internal xlsx part)
- Aspose can access `chart_data_workbook` / `read_workbook_stream()` without an external path
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = Path(__file__).resolve().parent / "_artifacts"

import sys
sys.path.insert(0, str(REPO_ROOT))

import hybrid_chart_llm_pipeline as h  # noqa: E402
from internalize_utils import internalize_chart_workbook_relationship  # noqa: E402


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
class ResultRow:
    relpath: str
    charts: int
    external_before: int
    embedded_after: int
    external_after: int
    out_dir_relpath: str


def _internalize_one_pptx(src: Path, dst: Path) -> ResultRow:
    dst.mkdir(parents=True, exist_ok=True)
    original = dst / "source_original.pptx"
    internalized = dst / "internalized_embedded_workbook.pptx"
    shutil.copyfile(src, original)
    shutil.copyfile(src, internalized)

    locs = h.list_chart_locators_aspose(str(internalized), 0)
    external_before = 0
    for loc in locs:
        _ct, src_kind = h.get_chart_type_aspose(str(internalized), loc)
        if src_kind == "external":
            external_before += 1

    # Patch charts one-by-one, cumulatively, to avoid multi-chart collisions.
    current = internalized
    for loc in locs:
        _ct, src_kind = h.get_chart_type_aspose(str(current), loc)
        if src_kind != "external":
            continue

        # Rewrite into a temp path then replace.
        tmp = current.with_suffix(".tmp.pptx")
        changed = internalize_chart_workbook_relationship(
            str(current),
            str(tmp),
            slide_index=loc.slide_index,
            shape_id=loc.shape_id,
        )
        if changed:
            tmp.replace(current)
        else:
            if tmp.exists():
                tmp.unlink()

    embedded_after = 0
    external_after = 0
    for loc in locs:
        _ct, src_kind = h.get_chart_type_aspose(str(internalized), loc)
        if src_kind == "embedded":
            embedded_after += 1
        elif src_kind == "external":
            external_after += 1

    return ResultRow(
        relpath=str(src.relative_to(REPO_ROOT)),
        charts=len(locs),
        external_before=external_before,
        embedded_after=embedded_after,
        external_after=external_after,
        out_dir_relpath=str(dst.relative_to(REPO_ROOT)),
    )


def main() -> int:
    _ensure_aspose_license()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = ARTIFACTS_ROOT / run_id / "internalized_newton"
    out_root.mkdir(parents=True, exist_ok=True)

    src_root = REPO_ROOT / "examples" / "Newton"
    pptxs = sorted(src_root.rglob("*.pptx"))

    rows: List[ResultRow] = []
    for src in pptxs:
        rel = src.relative_to(src_root)
        dst = out_root / rel.parent / rel.stem
        rows.append(_internalize_one_pptx(src, dst))

    log = out_root / "internalize_log.txt"
    lines = []
    for r in rows:
        lines.append(
            f"{r.relpath}: charts={r.charts} external_before={r.external_before} embedded_after={r.embedded_after} external_after={r.external_after} -> {r.out_dir_relpath}"
        )
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote internalized Newton PPTX files under: {out_root}")
    print(f"Log: {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
