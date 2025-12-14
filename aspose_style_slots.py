from __future__ import annotations

from typing import List, Optional

from chart_llm_models import StyleSlot


def extract_style_slots_aspose(
    pptx_path: str,
    slide_index: int,
    office_shape_id: int,
) -> List[StyleSlot]:
    import aspose.slides as slides  # type: ignore

    with slides.Presentation(str(pptx_path)) as pres:
        slide = pres.slides[slide_index]

        chart_shape = None
        for shape in slide.shapes:
            try:
                if int(shape.office_interop_shape_id) != int(office_shape_id):  # type: ignore[attr-defined]
                    continue
                _ = shape.chart_data  # type: ignore[attr-defined]
                chart_shape = shape
                break
            except Exception:
                continue

        if chart_shape is None:
            raise ValueError(
                f"Chart with office_interop_shape_id={office_shape_id} not found on slide {slide_index}"
            )

        slots: List[StyleSlot] = []
        for i, s in enumerate(list(chart_shape.chart_data.series)):  # type: ignore[attr-defined]
            template_name: Optional[str]
            try:
                template_name = s.name.as_cells[0].value
            except Exception:
                template_name = None

            slots.append(
                StyleSlot(
                    slot_id=i,
                    series_type=str(getattr(s, "type", "")),
                    plot_on_second_axis=bool(getattr(s, "plot_on_second_axis", False)),
                    template_series_name=template_name,
                    notes=None,
                )
            )

        return slots

