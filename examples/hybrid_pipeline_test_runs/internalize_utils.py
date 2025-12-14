"""
Offline utilities for converting chart workbooks from EXTERNAL links to embedded XLSX parts.

This is intentionally kept OUT of `hybrid_chart_llm_pipeline.py` so the online pipeline can
simply reject external-workbook charts and require an offline preprocessing step.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Optional, Tuple

import openpyxl
from lxml import etree as ET
from pptx import Presentation  # type: ignore


CHART_NS = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}


def make_minimal_xlsx_bytes(sheet_name: str = "Sheet1") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws["A1"] = "placeholder"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _find_chart_part_paths(pptx_path: str, slide_index: int, shape_id: int) -> Tuple[str, str]:
    """
    Return (chart_xml_path, chart_rels_path) inside the pptx zip.
    """
    prs = Presentation(str(pptx_path))
    slide = prs.slides[slide_index]
    for shape in slide.shapes:
        try:
            if shape.shape_id != shape_id:
                continue
            if not shape.has_chart:
                continue
            partname = str(shape.chart.part.partname)  # e.g. "/ppt/charts/chart1.xml"
            chart_xml_path = partname.lstrip("/")
            chart_rels_path = f"ppt/charts/_rels/{chart_xml_path.split('/')[-1]}.rels"
            return chart_xml_path, chart_rels_path
        except Exception:
            continue
    raise RuntimeError("Chart not found via python-pptx (cannot determine chart part path).")


def internalize_chart_workbook_relationship(
    pptx_in: str,
    pptx_out: str,
    *,
    slide_index: int,
    shape_id: int,
    xlsx_bytes: Optional[bytes] = None,
) -> bool:
    """
    If the chart uses an EXTERNAL workbook relationship (<c:externalData r:id="...">),
    rewrite the chart part rels so the workbook is an embedded XLSX part, and add that XLSX
    under `ppt/embeddings/`.

    Returns True if a patch was applied, False if the chart doesn't have externalData.
    """
    chart_xml_path, chart_rels_path = _find_chart_part_paths(pptx_in, slide_index, shape_id)

    with zipfile.ZipFile(pptx_in, "r") as zin:
        try:
            chart_xml_bytes = zin.read(chart_xml_path)
        except KeyError:
            return False

        try:
            root = ET.fromstring(chart_xml_bytes)
        except Exception:
            return False

        rid_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ext_nodes = root.xpath(".//c:externalData", namespaces=CHART_NS)
        if not ext_nodes:
            return False
        rid = ext_nodes[0].get(rid_attr)
        if not rid:
            return False

        rels_bytes = zin.read(chart_rels_path) if chart_rels_path in zin.namelist() else None

        RELS_NS = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
        if rels_bytes:
            rels_root = ET.fromstring(rels_bytes)
        else:
            rels_root = ET.Element("{http://schemas.openxmlformats.org/package/2006/relationships}Relationships")

        rel = None
        for n in rels_root.xpath("./pr:Relationship", namespaces=RELS_NS):
            if n.get("Id") == rid:
                rel = n
                break
        if rel is None:
            rel = ET.SubElement(
                rels_root,
                "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                Id=rid,
            )

        chart_basename = chart_xml_path.split("/")[-1]  # chartN.xml
        m = re.match(r"chart([0-9]+)\\.xml$", chart_basename)
        n_idx = int(m.group(1)) if m else 1

        existing = {name for name in zin.namelist() if name.startswith("ppt/embeddings/")}
        candidate = f"ppt/embeddings/Microsoft_Excel_Worksheet{n_idx}.xlsx"
        if candidate in existing:
            k = 1
            while True:
                candidate = f"ppt/embeddings/Microsoft_Excel_Worksheet{n_idx}_{k}.xlsx"
                if candidate not in existing:
                    break
                k += 1

        xlsx_bytes = xlsx_bytes or make_minimal_xlsx_bytes()

        rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package")
        rel.set("Target", f"../embeddings/{candidate.split('/')[-1]}")
        if "TargetMode" in rel.attrib:
            del rel.attrib["TargetMode"]

        ct_bytes = zin.read("[Content_Types].xml")
        ct_root = ET.fromstring(ct_bytes)
        CT_NS = {"ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
        defaults = ct_root.xpath("./ct:Default", namespaces=CT_NS)
        has_xlsx = any(d.get("Extension") == "xlsx" for d in defaults)
        if not has_xlsx:
            ET.SubElement(
                ct_root,
                "{http://schemas.openxmlformats.org/package/2006/content-types}Default",
                Extension="xlsx",
                ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        rels_out_bytes = ET.tostring(rels_root, xml_declaration=True, encoding="UTF-8", standalone="yes")
        ct_out_bytes = ET.tostring(ct_root, xml_declaration=True, encoding="UTF-8", standalone="yes")

        with zipfile.ZipFile(pptx_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                name = item.filename
                if name in (chart_rels_path, "[Content_Types].xml"):
                    continue
                if name == candidate:
                    continue
                zout.writestr(item, zin.read(name))

            zout.writestr(chart_rels_path, rels_out_bytes)
            zout.writestr("[Content_Types].xml", ct_out_bytes)
            zout.writestr(candidate, xlsx_bytes)

    return True

