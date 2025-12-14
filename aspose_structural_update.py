from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from chart_llm_models import (
    AsposeBubbleChartUpdate,
    AsposeCategoryChartUpdate,
    AsposeChartUpdate,
    AsposeScatterChartUpdate,
)


@dataclass(frozen=True)
class _SeriesStyleSnapshot:
    series_type: Any
    plot_on_second_axis: bool
    fill_type: Optional[Any] = None
    fill_color: Optional[Any] = None
    line_width: Optional[float] = None
    line_dash_style: Optional[Any] = None
    line_fill_type: Optional[Any] = None
    line_fill_color: Optional[Any] = None
    marker_symbol: Optional[Any] = None
    marker_size: Optional[int] = None
    marker_fill_type: Optional[Any] = None
    marker_fill_color: Optional[Any] = None


def _snapshot_series_style(series) -> _SeriesStyleSnapshot:
    import aspose.slides as slides  # type: ignore

    fill_type = fill_color = None
    line_width = line_dash_style = None
    line_fill_type = line_fill_color = None
    marker_symbol = marker_size = None
    marker_fill_type = marker_fill_color = None

    try:
        fmt = series.format
        try:
            fill_type = fmt.fill.fill_type
            if fill_type == slides.FillType.SOLID:
                fill_color = fmt.fill.solid_fill_color.color
        except Exception:
            pass

        try:
            line = fmt.line
            line_width = getattr(line, "width", None)
            line_dash_style = getattr(line, "dash_style", None)
            lf = getattr(line, "fill_format", None)
            if lf is not None:
                line_fill_type = lf.fill_type
                if line_fill_type == slides.FillType.SOLID:
                    line_fill_color = lf.solid_fill_color.color
        except Exception:
            pass
    except Exception:
        pass

    try:
        marker = series.marker
        marker_symbol = getattr(marker, "symbol", None)
        marker_size = getattr(marker, "size", None)
        try:
            mfill = marker.format.fill
            marker_fill_type = mfill.fill_type
            if marker_fill_type == slides.FillType.SOLID:
                marker_fill_color = mfill.solid_fill_color.color
        except Exception:
            pass
    except Exception:
        pass

    return _SeriesStyleSnapshot(
        series_type=getattr(series, "type", None),
        plot_on_second_axis=bool(getattr(series, "plot_on_second_axis", False)),
        fill_type=fill_type,
        fill_color=fill_color,
        line_width=line_width,
        line_dash_style=line_dash_style,
        line_fill_type=line_fill_type,
        line_fill_color=line_fill_color,
        marker_symbol=marker_symbol,
        marker_size=marker_size,
        marker_fill_type=marker_fill_type,
        marker_fill_color=marker_fill_color,
    )


def _apply_series_style(dst_series, snap: _SeriesStyleSnapshot) -> None:
    import aspose.slides as slides  # type: ignore

    try:
        if snap.series_type is not None:
            dst_series.type = snap.series_type
    except Exception:
        pass
    try:
        dst_series.plot_on_second_axis = bool(snap.plot_on_second_axis)
    except Exception:
        pass

    try:
        fmt = dst_series.format
        if snap.fill_type is not None:
            fmt.fill.fill_type = snap.fill_type
            if snap.fill_type == slides.FillType.SOLID and snap.fill_color is not None:
                fmt.fill.solid_fill_color.color = snap.fill_color

        if snap.line_width is not None:
            fmt.line.width = snap.line_width
        if snap.line_dash_style is not None:
            fmt.line.dash_style = snap.line_dash_style

        lf = getattr(fmt.line, "fill_format", None)
        if lf is not None and snap.line_fill_type is not None:
            lf.fill_type = snap.line_fill_type
            if snap.line_fill_type == slides.FillType.SOLID and snap.line_fill_color is not None:
                lf.solid_fill_color.color = snap.line_fill_color
    except Exception:
        pass

    try:
        marker = dst_series.marker
        if snap.marker_symbol is not None:
            marker.symbol = snap.marker_symbol
        if snap.marker_size is not None:
            marker.size = snap.marker_size
        try:
            mfill = marker.format.fill
            if snap.marker_fill_type is not None:
                mfill.fill_type = snap.marker_fill_type
                if snap.marker_fill_type == slides.FillType.SOLID and snap.marker_fill_color is not None:
                    mfill.solid_fill_color.color = snap.marker_fill_color
        except Exception:
            pass
    except Exception:
        pass


def _find_chart_aspose(pres, slide_index: int, office_shape_id: int):
    slide = pres.slides[slide_index]
    for shape in slide.shapes:
        try:
            if int(shape.office_interop_shape_id) != int(office_shape_id):  # type: ignore[attr-defined]
                continue
            _ = shape.chart_data  # type: ignore[attr-defined]
            return shape
        except Exception:
            continue
    return None


def _ensure_series_count(chart, desired_count: int, style_snaps: List[_SeriesStyleSnapshot], wb, sheet: int) -> None:
    series_coll = chart.chart_data.series

    while len(series_coll) > desired_count:
        series_coll.remove_at(len(series_coll) - 1)

    while len(series_coll) < desired_count:
        default_type = style_snaps[0].series_type if style_snaps and style_snaps[0].series_type is not None else chart.type
        name_cell = wb.get_cell(sheet, 0, len(series_coll) + 1, f"Series {len(series_coll)+1}")
        series_coll.add(name_cell, default_type)


def _set_series_name(series, name: str) -> None:
    try:
        series.name.as_cells[0].value = name
    except Exception:
        pass


def _clear_datapoints(series) -> None:
    try:
        series.data_points.clear()
        return
    except Exception:
        pass

    try:
        dp = series.data_points
        while len(dp) > 0:
            dp.remove_at(len(dp) - 1)
    except Exception:
        pass


def _add_category_datapoint(series, value_cell) -> None:
    import aspose.slides.charts as charts  # type: ignore

    ct = series.type
    dps = series.data_points

    if charts.ChartTypeCharacterizer.is_chart_type_bar(ct) or charts.ChartTypeCharacterizer.is_chart_type_column(ct):
        dps.add_data_point_for_bar_series(value_cell)
        return
    if charts.ChartTypeCharacterizer.is_chart_type_line(ct):
        dps.add_data_point_for_line_series(value_cell)
        return
    if charts.ChartTypeCharacterizer.is_chart_type_area(ct):
        dps.add_data_point_for_area_series(value_cell)
        return
    if charts.ChartTypeCharacterizer.is_chart_type_pie(ct):
        dps.add_data_point_for_pie_series(value_cell)
        return
    if charts.ChartTypeCharacterizer.is_chart_type_doughnut(ct):
        dps.add_data_point_for_doughnut_series(value_cell)
        return
    if charts.ChartTypeCharacterizer.is_chart_type_radar(ct):
        dps.add_data_point_for_radar_series(value_cell)
        return

    raise NotImplementedError(f"Unsupported category/value chart series type for resizing: {ct}")


def apply_aspose_chart_update(
    pptx_in: str,
    pptx_out: str,
    slide_index: int,
    office_shape_id: int,
    update: AsposeChartUpdate,
    *,
    single_series_mode: bool,
) -> None:
    import aspose.slides as slides  # type: ignore

    with slides.Presentation(str(pptx_in)) as pres:
        chart = _find_chart_aspose(pres, slide_index, office_shape_id)
        if chart is None:
            raise ValueError(f"Chart with office_interop_shape_id={office_shape_id} not found on slide {slide_index}")

        template_series = list(chart.chart_data.series)
        style_snaps = [_snapshot_series_style(s) for s in template_series]

        def slot_snap(slot_id: int) -> _SeriesStyleSnapshot:
            if slot_id < 0 or slot_id >= len(style_snaps):
                raise ValueError(
                    f"style_slot_id={slot_id} out of range. Template has {len(style_snaps)} style slots."
                )
            return style_snaps[slot_id]

        wb = chart.chart_data.chart_data_workbook
        sheet = 0

        if isinstance(update, AsposeCategoryChartUpdate):
            desired_series_count = len(update.series)
            if single_series_mode and desired_series_count != 1:
                raise ValueError("Single-series mode: update must contain exactly 1 series for category charts.")

            cats = list(update.categories)

            try:
                chart.chart_data.categories.clear()
            except Exception:
                while len(chart.chart_data.categories) > 0:
                    chart.chart_data.categories.remove_at(len(chart.chart_data.categories) - 1)

            for i, cat_label in enumerate(cats):
                chart.chart_data.categories.add(wb.get_cell(sheet, i + 1, 0, str(cat_label)))

            _ensure_series_count(chart, desired_series_count, style_snaps, wb, sheet)

            for s_idx, s_spec in enumerate(update.series):
                s = chart.chart_data.series[s_idx]
                snap = slot_snap(s_spec.style_slot_id)

                _apply_series_style(s, snap)
                _set_series_name(s, s_spec.name)
                _clear_datapoints(s)

                values = list(s_spec.values)
                if len(values) < len(cats):
                    values += [None] * (len(cats) - len(values))
                if len(values) > len(cats):
                    values = values[: len(cats)]

                for p_idx, v in enumerate(values):
                    cell = wb.get_cell(sheet, p_idx + 1, s_idx + 1, v)
                    _add_category_datapoint(s, cell)

                try:
                    s.order = s_idx
                except Exception:
                    pass

            if desired_series_count == 0:
                while len(chart.chart_data.series) > 0:
                    chart.chart_data.series.remove_at(len(chart.chart_data.series) - 1)

        elif isinstance(update, AsposeScatterChartUpdate):
            desired_series_count = len(update.series)
            if single_series_mode and desired_series_count != 1:
                raise ValueError("Single-series mode: update must contain exactly 1 series for scatter charts.")

            _ensure_series_count(chart, desired_series_count, style_snaps, wb, sheet)

            for s_idx, s_spec in enumerate(update.series):
                s = chart.chart_data.series[s_idx]
                snap = slot_snap(s_spec.style_slot_id)
                _apply_series_style(s, snap)
                _set_series_name(s, s_spec.name)
                _clear_datapoints(s)

                for p_idx, pt in enumerate(s_spec.points):
                    x_cell = wb.get_cell(sheet, p_idx + 1, 2 * s_idx + 1, pt.x)
                    y_cell = wb.get_cell(sheet, p_idx + 1, 2 * s_idx + 2, pt.y)
                    s.data_points.add_data_point_for_scatter_series(x_cell, y_cell)

                try:
                    s.order = s_idx
                except Exception:
                    pass

            if desired_series_count == 0:
                while len(chart.chart_data.series) > 0:
                    chart.chart_data.series.remove_at(len(chart.chart_data.series) - 1)

        elif isinstance(update, AsposeBubbleChartUpdate):
            desired_series_count = len(update.series)
            if single_series_mode and desired_series_count != 1:
                raise ValueError("Single-series mode: update must contain exactly 1 series for bubble charts.")

            _ensure_series_count(chart, desired_series_count, style_snaps, wb, sheet)

            for s_idx, s_spec in enumerate(update.series):
                s = chart.chart_data.series[s_idx]
                snap = slot_snap(s_spec.style_slot_id)
                _apply_series_style(s, snap)
                _set_series_name(s, s_spec.name)
                _clear_datapoints(s)

                for p_idx, pt in enumerate(s_spec.points):
                    base = 3 * s_idx + 1
                    x_cell = wb.get_cell(sheet, p_idx + 1, base + 0, pt.x)
                    y_cell = wb.get_cell(sheet, p_idx + 1, base + 1, pt.y)
                    s_cell = wb.get_cell(sheet, p_idx + 1, base + 2, pt.size)
                    s.data_points.add_data_point_for_bubble_series(x_cell, y_cell, s_cell)

                try:
                    s.order = s_idx
                except Exception:
                    pass

            if desired_series_count == 0:
                while len(chart.chart_data.series) > 0:
                    chart.chart_data.series.remove_at(len(chart.chart_data.series) - 1)

        else:
            raise TypeError(f"Unknown update type: {type(update)}")

        pres.save(str(pptx_out), slides.export.SaveFormat.PPTX)

