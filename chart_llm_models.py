from __future__ import annotations

from typing import List, Literal, Optional, Tuple, Union

# --- Pydantic compat (v1/v2) ---
try:
    from pydantic.v1 import BaseModel, Field, parse_obj_as
except Exception:  # pragma: no cover
    from pydantic import BaseModel, Field, parse_obj_as

Number = Union[int, float]


class StyleSlot(BaseModel):
    """
    Template style slot for a chart series (sent to the LLM as context).

    The LLM references `slot_id` to indicate which template style/type/axis assignment
    should be cloned onto a new or updated series.
    """

    slot_id: int
    series_type: str
    plot_on_second_axis: bool = False
    template_series_name: Optional[str] = None
    notes: Optional[str] = None


class CategorySeriesSpec(BaseModel):
    name: str = Field(..., description="Legend/series name")
    style_slot_id: int = Field(..., description="Which template style slot to clone")
    values: List[Optional[Number]] = Field(..., description="One value per category; None for blanks")


class AsposeCategoryChartUpdate(BaseModel):
    update_kind: Literal["aspose_category"] = "aspose_category"
    categories: List[str]
    series: List[CategorySeriesSpec]


class XYPoint(BaseModel):
    x: Number
    y: Number


class ScatterSeriesSpec(BaseModel):
    name: str
    style_slot_id: int
    points: List[XYPoint]


class AsposeScatterChartUpdate(BaseModel):
    update_kind: Literal["aspose_scatter"] = "aspose_scatter"
    series: List[ScatterSeriesSpec]


class BubblePoint(BaseModel):
    x: Number
    y: Number
    size: Number


class BubbleSeriesSpec(BaseModel):
    name: str
    style_slot_id: int
    points: List[BubblePoint]


class AsposeBubbleChartUpdate(BaseModel):
    update_kind: Literal["aspose_bubble"] = "aspose_bubble"
    series: List[BubbleSeriesSpec]


AsposeChartUpdate = Union[
    AsposeCategoryChartUpdate,
    AsposeScatterChartUpdate,
    AsposeBubbleChartUpdate,
]


def parse_aspose_chart_update(payload: dict) -> AsposeChartUpdate:
    """
    Parse a dict into the appropriate AsposeChartUpdate variant based on `update_kind`.
    """

    return parse_obj_as(AsposeChartUpdate, payload)

