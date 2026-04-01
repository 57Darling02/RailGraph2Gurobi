from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.dates import DateFormatter
from matplotlib.patches import Patch, Rectangle

from analysis.io import read_timetable
from core.loader import load_mileage_table
from core.types import AppConfig, TranslatedData

SCENARIO_TYPE_ORDER = ["delay", "speed_limit", "interruption"]
SCENARIO_TYPE_LABEL = {
    "delay": "Delay",
    "speed_limit": "Speed Limit",
    "interruption": "Interruption",
}
SCENARIO_TYPE_COLOR = {
    "delay": "#f28e2b",
    "speed_limit": "#4e79a7",
    "interruption": "#e15759",
}
SPATIAL_BASIS_LABEL = {
    "station": "Station",
    "section": "Section",
    "mixed": "Mixed",
}
TIMETABLE_LINE_COLOR = "#a0a0a0"
TIMETABLE_LABEL_COLOR = "#6b6b6b"
DELAY_DISPLAY_MIN_SECONDS = 300
DELAY_DISPLAY_MAX_SECONDS = 1800


def _time_to_seconds(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    hour, minute, second = [int(part) for part in str(value).split(":")]
    return hour * 3600 + minute * 60 + second


def _seconds_to_hms(seconds: int | None) -> str:
    if seconds is None:
        return ""
    total = max(0, min(86399, int(seconds)))
    hour = total // 3600
    minute = (total % 3600) // 60
    second = total % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _seconds_to_timestamp(seconds: int) -> pd.Timestamp:
    return pd.to_datetime(_seconds_to_hms(seconds), format="%H:%M:%S")


def _read_mileage_order(path: Path, sheet_name: str) -> List[str]:
    raw = load_mileage_table(path, sheet_name)
    records: List[Tuple[str, float]] = []
    for row in raw.rows:
        station = str(row.get("station") or "").strip()
        mileage_text = str(row.get("mileage") or "").strip()
        if not station or mileage_text == "":
            continue
        try:
            mileage = float(mileage_text)
        except ValueError:
            continue
        records.append((station, mileage))
    return [station for station, _ in sorted(records, key=lambda item: item[1])]


def _build_station_order(config: AppConfig, timetable_df: pd.DataFrame) -> List[str]:
    mileage_order = _read_mileage_order(config.input.mileage_path, config.input.mileage_sheet_name)
    if mileage_order:
        timetable_stations = set(timetable_df["station"].dropna().astype(str).tolist())
        ordered = [station for station in mileage_order if station in timetable_stations]
        if ordered:
            return ordered
    return timetable_df["station"].drop_duplicates().astype(str).tolist()


def _build_section_order(station_order: List[str]) -> List[str]:
    return [f"{station_order[idx]}->{station_order[idx + 1]}" for idx in range(len(station_order) - 1)]


def _expand_station_span(start_station: str, end_station: str, station_order: List[str]) -> List[str]:
    if start_station == "" or end_station == "":
        return []
    index_map = {station: idx for idx, station in enumerate(station_order)}
    if start_station not in index_map or end_station not in index_map:
        return [start_station] if start_station == end_station else [start_station, end_station]
    start_idx = index_map[start_station]
    end_idx = index_map[end_station]
    lower = min(start_idx, end_idx)
    upper = max(start_idx, end_idx)
    return station_order[lower : upper + 1]


def _expand_section_span(start_station: str, end_station: str, station_order: List[str]) -> List[str]:
    if start_station == "" or end_station == "" or start_station == end_station:
        return []
    index_map = {station: idx for idx, station in enumerate(station_order)}
    if start_station not in index_map or end_station not in index_map:
        return [f"{start_station}->{end_station}"]
    start_idx = index_map[start_station]
    end_idx = index_map[end_station]
    lower = min(start_idx, end_idx)
    upper = max(start_idx, end_idx)
    return [f"{station_order[idx]}->{station_order[idx + 1]}" for idx in range(lower, upper)]


def _merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    valid = sorted((int(start), int(end)) for start, end in intervals if start is not None and end is not None and end > start)
    if not valid:
        return []
    merged: List[Tuple[int, int]] = [valid[0]]
    for start, end in valid[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _sum_interval_length(intervals: List[Tuple[int, int]]) -> int:
    return int(sum(end - start for start, end in _merge_intervals(intervals)))


def _build_scenario_rows(
    case_id: str,
    scenarios: Dict[str, object],
    translated: TranslatedData,
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []

    for item in scenarios.get("delays", []):
        train_id = str(item["train_id"])
        station = str(item["station"])
        event_type = str(item["event_type"])
        delay_seconds = int(item["seconds"])
        event_key = (train_id, station, event_type)
        planned_time = translated.event_time.get(event_key)
        actual_time = None if planned_time is None else min(86399, planned_time + max(delay_seconds, 0))
        rows.append(
            {
                "case_id": case_id,
                "scenario_type": "delay",
                "location_key": station,
                "section_key": "",
                "train_id": train_id,
                "station": station,
                "event_type": event_type,
                "seconds": delay_seconds,
                "extra_seconds": 0,
                "start_station": station,
                "end_station": station,
                "window_start_sec": planned_time,
                "window_end_sec": actual_time,
                "display_start_sec": planned_time,
                "display_end_sec": actual_time,
                "window_start": _seconds_to_hms(planned_time),
                "window_end": _seconds_to_hms(actual_time),
            }
        )

    for item in scenarios.get("speed_limits", []):
        start_station = str(item["start_station"])
        end_station = str(item["end_station"])
        start_sec = _time_to_seconds(str(item["start_time"]))
        end_sec = _time_to_seconds(str(item["end_time"]))
        rows.append(
            {
                "case_id": case_id,
                "scenario_type": "speed_limit",
                "location_key": f"{start_station}->{end_station}",
                "section_key": f"{start_station}->{end_station}",
                "train_id": "",
                "station": "",
                "event_type": "",
                "seconds": 0,
                "extra_seconds": int(item["extra_seconds"]),
                "start_station": start_station,
                "end_station": end_station,
                "window_start_sec": start_sec,
                "window_end_sec": end_sec,
                "display_start_sec": start_sec,
                "display_end_sec": end_sec,
                "window_start": _seconds_to_hms(start_sec),
                "window_end": _seconds_to_hms(end_sec),
            }
        )

    for item in scenarios.get("interruptions", []):
        start_station = str(item["start_station"])
        end_station = str(item["end_station"])
        start_sec = _time_to_seconds(str(item["start_time"]))
        end_sec = _time_to_seconds(str(item["end_time"]))
        rows.append(
            {
                "case_id": case_id,
                "scenario_type": "interruption",
                "location_key": f"{start_station}->{end_station}",
                "section_key": f"{start_station}->{end_station}",
                "train_id": "",
                "station": "",
                "event_type": "",
                "seconds": 0,
                "extra_seconds": 0,
                "start_station": start_station,
                "end_station": end_station,
                "window_start_sec": start_sec,
                "window_end_sec": end_sec,
                "display_start_sec": start_sec,
                "display_end_sec": end_sec,
                "window_start": _seconds_to_hms(start_sec),
                "window_end": _seconds_to_hms(end_sec),
            }
        )

    columns = [
        "case_id",
        "scenario_type",
        "location_key",
        "section_key",
        "train_id",
        "station",
        "event_type",
        "seconds",
        "extra_seconds",
        "start_station",
        "end_station",
        "window_start_sec",
        "window_end_sec",
        "display_start_sec",
        "display_end_sec",
        "window_start",
        "window_end",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def _build_type_summary(scenario_df: pd.DataFrame) -> pd.DataFrame:
    counts = scenario_df.groupby("scenario_type").size().reindex(SCENARIO_TYPE_ORDER, fill_value=0)
    total = int(counts.sum())
    rows = []
    for scenario_type, count in counts.items():
        ratio = 0.0 if total == 0 else float(count) / float(total)
        rows.append(
            {
                "scenario_type": scenario_type,
                "label": SCENARIO_TYPE_LABEL[scenario_type],
                "count": int(count),
                "ratio": ratio,
            }
        )
    return pd.DataFrame(rows)


def _build_location_summary(scenario_df: pd.DataFrame) -> pd.DataFrame:
    if scenario_df.empty:
        return pd.DataFrame(columns=["location_key", "scenario_type", "count"])
    return (
        scenario_df.groupby(["scenario_type", "location_key"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values(["count", "scenario_type", "location_key"], ascending=[False, True, True])
    )


def _build_coverage_summary(
    scenario_df: pd.DataFrame,
    station_order: List[str],
    timetable_df: pd.DataFrame,
) -> pd.DataFrame:
    all_times = pd.concat([timetable_df["arrival_sec"], timetable_df["departure_sec"]], ignore_index=True).dropna()
    if all_times.empty:
        timetable_start_sec = 0
        timetable_end_sec = 0
        timetable_span_sec = 0
    else:
        timetable_start_sec = int(all_times.min())
        timetable_end_sec = int(all_times.max())
        timetable_span_sec = max(0, timetable_end_sec - timetable_start_sec)

    total_station_count = len(station_order)
    total_section_count = len(_build_section_order(station_order))
    total_mixed_count = total_station_count + total_section_count

    def _coverage_for(df: pd.DataFrame, scope: str, label: str) -> Dict[str, object]:
        if scope == "delay":
            location_basis = "station"
        elif scope in ("speed_limit", "interruption"):
            location_basis = "section"
        else:
            location_basis = "mixed"

        location_units = set()
        intervals: List[Tuple[int, int]] = []
        for row in df.itertuples():
            if location_basis == "station":
                location_units.update(_expand_station_span(str(row.start_station), str(row.end_station), station_order))
            elif location_basis == "section":
                location_units.update(_expand_section_span(str(row.start_station), str(row.end_station), station_order))
            else:
                if str(row.scenario_type) == "delay":
                    location_units.update(f"station:{station}" for station in _expand_station_span(str(row.start_station), str(row.end_station), station_order))
                else:
                    location_units.update(f"section:{section}" for section in _expand_section_span(str(row.start_station), str(row.end_station), station_order))

            if row.display_start_sec is not None and row.display_end_sec is not None and int(row.display_end_sec) > int(row.display_start_sec):
                intervals.append((int(row.display_start_sec), int(row.display_end_sec)))

        covered_time_sec = _sum_interval_length(intervals)
        if location_basis == "station":
            total_location_count = max(total_station_count, len(location_units))
        elif location_basis == "section":
            total_location_count = max(total_section_count, len(location_units))
        else:
            total_location_count = max(total_mixed_count, len(location_units))

        return {
            "scope": scope,
            "label": label,
            "location_basis": location_basis,
            "location_basis_label": SPATIAL_BASIS_LABEL[location_basis],
            "covered_location_count": int(len(location_units)),
            "total_location_count": int(total_location_count),
            "location_coverage_ratio": 0.0 if total_location_count == 0 else float(len(location_units)) / float(total_location_count),
            "covered_time_sec": int(covered_time_sec),
            "timetable_span_sec": int(timetable_span_sec),
            "time_coverage_ratio": 0.0 if timetable_span_sec == 0 else float(covered_time_sec) / float(timetable_span_sec),
            "timetable_start_sec": int(timetable_start_sec),
            "timetable_end_sec": int(timetable_end_sec),
        }

    rows = [_coverage_for(scenario_df, "total", "Total")]
    for scenario_type in SCENARIO_TYPE_ORDER:
        rows.append(_coverage_for(scenario_df[scenario_df["scenario_type"] == scenario_type], scenario_type, SCENARIO_TYPE_LABEL[scenario_type]))
    return pd.DataFrame(rows)


def _plot_type_distribution(type_df: pd.DataFrame, output_path: Path, title: str) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    counts = type_df["count"].tolist()
    labels = type_df["label"].tolist()
    colors = [SCENARIO_TYPE_COLOR[item] for item in type_df["scenario_type"].tolist()]

    if sum(counts) > 0:
        wedges, _, autotexts = axes[0].pie(
            counts,
            labels=None,
            autopct=lambda pct: f"{pct:.1f}%" if pct > 0 else "",
            colors=colors,
            startangle=90,
            textprops={"fontsize": 9},
            wedgeprops={"linewidth": 1.0, "edgecolor": "white"},
        )
        for autotext in autotexts:
            autotext.set_color("white")
            autotext.set_fontsize(9)
        axes[0].legend(
            wedges,
            [f"{label} ({count})" for label, count in zip(labels, counts)],
            loc="center left",
            bbox_to_anchor=(1.0, 0.5),
            frameon=False,
        )
        axes[0].set_title("Scenario Ratio")
    else:
        axes[0].text(0.5, 0.5, "No inferred scenarios", ha="center", va="center")
        axes[0].set_axis_off()

    axes[1].bar(labels, counts, color=colors)
    axes[1].set_title("Scenario Count")
    axes[1].set_ylabel("Count")
    axes[1].grid(axis="y", alpha=0.3)
    for idx, count in enumerate(counts):
        axes[1].text(idx, count, str(count), ha="center", va="bottom", fontsize=9)

    fig.suptitle(title)
    fig.tight_layout(rect=(0.0, 0.0, 0.9, 1.0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return output_path


def _plot_location_distribution(location_df: pd.DataFrame, output_path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(12, 6))
    if location_df.empty:
        ax.text(0.5, 0.5, "No inferred scenarios", ha="center", va="center")
        ax.set_axis_off()
    else:
        top_df = location_df.head(12).copy()
        labels = [f"{row.location_key}\n({SCENARIO_TYPE_LABEL[row.scenario_type]})" for row in top_df.itertuples()]
        colors = [SCENARIO_TYPE_COLOR[row.scenario_type] for row in top_df.itertuples()]
        ax.barh(labels[::-1], top_df["count"].tolist()[::-1], color=colors[::-1])
        ax.set_xlabel("Count")
        ax.set_title("Top Scenario Locations")
        ax.grid(axis="x", alpha=0.3)
    fig.suptitle(title)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return output_path


def _plot_coverage_distribution(coverage_df: pd.DataFrame, output_path: Path, title: str) -> Path:
    plot_df = coverage_df[coverage_df["scope"].isin(SCENARIO_TYPE_ORDER)].copy()
    if plot_df.empty:
        plot_df = coverage_df.copy()

    fig, ax = plt.subplots(figsize=(11, 5.5))
    labels = [f"{row.label}\n({row.location_basis_label})" for row in plot_df.itertuples()]
    x = list(range(len(labels)))
    width = 0.36
    location_values = [float(value) * 100.0 for value in plot_df["location_coverage_ratio"].tolist()]
    time_values = [float(value) * 100.0 for value in plot_df["time_coverage_ratio"].tolist()]

    bars1 = ax.bar([item - width / 2 for item in x], location_values, width=width, color="#59a14f", label="Spatial Coverage")
    bars2 = ax.bar([item + width / 2 for item in x], time_values, width=width, color="#9c755f", label="Time Coverage")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, max([5.0] + location_values + time_values) * 1.2)
    ax.set_ylabel("Coverage (%)")
    ax.set_title("Coverage Ratio by Scenario Type")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    for bars in (bars1, bars2):
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height, f"{height:.1f}%", ha="center", va="bottom", fontsize=8)

    fig.suptitle(title)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return output_path


def _plot_time_distribution(scenario_df: pd.DataFrame, output_path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(14, 6))
    if scenario_df.empty:
        ax.text(0.5, 0.5, "No inferred scenarios", ha="center", va="center")
        ax.set_axis_off()
    else:
        plot_df = scenario_df.copy()
        plot_df["anchor_sec"] = plot_df.apply(
            lambda row: int((int(row["display_start_sec"]) + int(row["display_end_sec"])) / 2)
            if pd.notna(row["display_start_sec"]) and pd.notna(row["display_end_sec"])
            else 0,
            axis=1,
        )
        plot_df["hour"] = (plot_df["anchor_sec"] // 3600).clip(lower=0, upper=23).astype(int)
        hour_labels = [f"{hour:02d}:00" for hour in range(24)]
        bottom = [0] * 24
        for scenario_type in SCENARIO_TYPE_ORDER:
            counts = (
                plot_df[plot_df["scenario_type"] == scenario_type]
                .groupby("hour")
                .size()
                .reindex(range(24), fill_value=0)
                .tolist()
            )
            ax.bar(hour_labels, counts, bottom=bottom, color=SCENARIO_TYPE_COLOR[scenario_type], label=SCENARIO_TYPE_LABEL[scenario_type])
            bottom = [a + b for a, b in zip(bottom, counts)]
        ax.set_title("Scenario Time-of-Day Distribution")
        ax.set_ylabel("Scenario Count")
        ax.set_xlabel("Time")
        ax.grid(axis="y", alpha=0.3)
        ax.legend()
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.suptitle(title)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return output_path


def _compute_overlay_y_bounds(scenario_type: str, y_values: List[int]) -> tuple[float, float] | None:
    if not y_values:
        return None
    lower_y = float(min(y_values))
    upper_y = float(max(y_values))
    if scenario_type == "delay":
        return lower_y - 0.1, 0.2
    if lower_y == upper_y:
        return lower_y - 0.4, 0.8
    return lower_y, max(upper_y - lower_y, 1e-6)


def _plot_timetable_with_scenarios(
    config: AppConfig,
    scenario_df: pd.DataFrame,
    output_path: Path,
    title: str,
) -> Path:
    timetable_df = read_timetable(config.input.timetable_path, sheet_name=config.input.timetable_sheet_name)
    station_order = _build_station_order(config, timetable_df)
    station_to_y = {station: idx for idx, station in enumerate(station_order)}

    df = timetable_df.copy()
    df["arrival_ts"] = pd.to_datetime(df["arrival_time"], format="%H:%M:%S", errors="coerce")
    df["departure_ts"] = pd.to_datetime(df["departure_time"], format="%H:%M:%S", errors="coerce")
    df["station_y"] = df["station"].map(station_to_y)
    df = df.sort_values(["train_id", "arrival_ts", "departure_ts", "station"])

    fig, ax = plt.subplots(figsize=(24, 10))
    for train_id in df["train_id"].drop_duplicates().tolist():
        train_df = df[df["train_id"] == train_id].reset_index(drop=True)
        first_row = train_df.iloc[0]
        if pd.notna(first_row["departure_ts"]) and pd.notna(first_row["station_y"]):
            ax.text(
                first_row["departure_ts"],
                first_row["station_y"],
                train_id,
                fontsize=5,
                rotation=270,
                color=TIMETABLE_LABEL_COLOR,
                ha="center",
                va="bottom",
            )
        for idx in range(len(train_df) - 1):
            dep = train_df.loc[idx, "departure_ts"]
            arr = train_df.loc[idx + 1, "arrival_ts"]
            dep_y = train_df.loc[idx, "station_y"]
            arr_y = train_df.loc[idx + 1, "station_y"]
            if pd.notna(dep) and pd.notna(arr) and pd.notna(dep_y) and pd.notna(arr_y):
                ax.plot([dep, arr], [dep_y, arr_y], color=TIMETABLE_LINE_COLOR, lw=0.8, alpha=0.9, zorder=3)

    for row in scenario_df.itertuples():
        scenario_type = str(row.scenario_type)
        color = SCENARIO_TYPE_COLOR[scenario_type]
        if row.display_start_sec is None or row.display_end_sec is None:
            continue
        span_stations = _expand_station_span(str(row.start_station), str(row.end_station), station_order)
        if not span_stations:
            continue
        y_values = [station_to_y[station] for station in span_stations if station in station_to_y]
        if not y_values:
            continue
        y_bounds = _compute_overlay_y_bounds(scenario_type, y_values)
        if y_bounds is None:
            continue
        lower, height = y_bounds
        start_num = mdates.date2num(_seconds_to_timestamp(int(row.display_start_sec)))
        end_num = mdates.date2num(_seconds_to_timestamp(int(max(row.display_end_sec, row.display_start_sec + 1))))
        rect = Rectangle(
            (start_num, lower),
            max(end_num - start_num, 1e-6),
            height,
            facecolor=color,
            edgecolor=color,
            linewidth=1.0,
            alpha=0.22,
            zorder=1,
        )
        ax.add_patch(rect)

    all_times = pd.concat([df["arrival_ts"], df["departure_ts"]], ignore_index=True).dropna()
    if not all_times.empty:
        ax.set_xlim(all_times.min(), all_times.max())
    ax.set_yticks(list(station_to_y.values()))
    ax.set_yticklabels(station_order)
    ax.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.grid(True, alpha=0.2)
    ax.set_title(title)
    ax.set_xlabel("Time")
    ax.set_ylabel("Station")
    legend_handles = [Patch(facecolor=SCENARIO_TYPE_COLOR[key], edgecolor=SCENARIO_TYPE_COLOR[key], alpha=0.22, label=SCENARIO_TYPE_LABEL[key]) for key in SCENARIO_TYPE_ORDER]
    ax.legend(handles=legend_handles, loc="upper left")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return output_path


def build_case_scenario_report_data(
    case_id: str,
    scenarios: Dict[str, object],
    config: AppConfig,
    translated: TranslatedData,
) -> Dict[str, object]:
    timetable_df = read_timetable(config.input.timetable_path, sheet_name=config.input.timetable_sheet_name)
    timetable_df["arrival_sec"] = timetable_df["arrival_time"].apply(_time_to_seconds)
    timetable_df["departure_sec"] = timetable_df["departure_time"].apply(_time_to_seconds)
    station_order = _build_station_order(config, timetable_df)

    scenario_df = _build_scenario_rows(case_id, scenarios, translated)
    type_df = _build_type_summary(scenario_df)
    location_df = _build_location_summary(scenario_df)
    coverage_df = _build_coverage_summary(scenario_df, station_order, timetable_df)
    total_coverage = coverage_df[coverage_df["scope"] == "total"].iloc[0]

    summary = {
        "case_id": case_id,
        "total_scenarios": int(len(scenario_df)),
        "delay_count": int(type_df.loc[type_df["scenario_type"] == "delay", "count"].iloc[0]),
        "speed_limit_count": int(type_df.loc[type_df["scenario_type"] == "speed_limit", "count"].iloc[0]),
        "interruption_count": int(type_df.loc[type_df["scenario_type"] == "interruption", "count"].iloc[0]),
        "location_basis": str(total_coverage["location_basis"]),
        "covered_location_count": int(total_coverage["covered_location_count"]),
        "total_location_count": int(total_coverage["total_location_count"]),
        "location_coverage_ratio": float(total_coverage["location_coverage_ratio"]),
        "covered_time_sec": int(total_coverage["covered_time_sec"]),
        "timetable_span_sec": int(total_coverage["timetable_span_sec"]),
        "time_coverage_ratio": float(total_coverage["time_coverage_ratio"]),
    }
    return {
        "summary": summary,
        "scenario_rows": scenario_df,
        "type_distribution": type_df,
        "location_distribution": location_df,
        "coverage_distribution": coverage_df,
    }


def generate_case_scenario_report(
    case_id: str,
    scenarios: Dict[str, object],
    config: AppConfig,
    translated: TranslatedData,
    output_dir: Path,
) -> Dict[str, object]:
    report_dir = output_dir / "scenario_analysis"
    report_dir.mkdir(parents=True, exist_ok=True)

    report_data = build_case_scenario_report_data(
        case_id=case_id,
        scenarios=scenarios,
        config=config,
        translated=translated,
    )
    summary = report_data["summary"]
    scenario_df = report_data["scenario_rows"]
    type_df = report_data["type_distribution"]
    location_df = report_data["location_distribution"]
    coverage_df = report_data["coverage_distribution"]

    summary_json_path = report_dir / "scenario_summary.json"
    summary_excel_path = report_dir / "scenario_summary.xlsx"
    type_plot_path = report_dir / "scenario_type_distribution.png"
    location_plot_path = report_dir / "scenario_location_distribution.png"
    coverage_plot_path = report_dir / "scenario_coverage_distribution.png"
    time_plot_path = report_dir / "scenario_time_distribution.png"
    timetable_plot_path = report_dir / "scenario_timetable.png"

    with summary_json_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "summary": summary,
                "type_distribution": type_df.to_dict(orient="records"),
                "location_distribution": location_df.to_dict(orient="records"),
                "coverage_distribution": coverage_df.to_dict(orient="records"),
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    with pd.ExcelWriter(summary_excel_path, engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="summary", index=False)
        type_df.to_excel(writer, sheet_name="type_distribution", index=False)
        location_df.to_excel(writer, sheet_name="location_distribution", index=False)
        coverage_df.to_excel(writer, sheet_name="coverage_distribution", index=False)
        scenario_df.to_excel(writer, sheet_name="scenarios", index=False)

    _plot_type_distribution(type_df, type_plot_path, title=f"Scenario Distribution - {case_id}")
    _plot_location_distribution(location_df, location_plot_path, title=f"Scenario Locations - {case_id}")
    _plot_coverage_distribution(coverage_df, coverage_plot_path, title=f"Scenario Coverage - {case_id}")
    _plot_time_distribution(scenario_df, time_plot_path, title=f"Scenario Time Distribution - {case_id}")
    _plot_timetable_with_scenarios(
        config=config,
        scenario_df=scenario_df,
        output_path=timetable_plot_path,
        title=f"Scenario Timetable Overlay - {case_id}",
    )

    return {
        "case_id": case_id,
        "report_dir": str(report_dir).replace("\\", "/"),
        "summary_json": str(summary_json_path).replace("\\", "/"),
        "summary_excel": str(summary_excel_path).replace("\\", "/"),
        "type_plot": str(type_plot_path).replace("\\", "/"),
        "location_plot": str(location_plot_path).replace("\\", "/"),
        "coverage_plot": str(coverage_plot_path).replace("\\", "/"),
        "timetable_plot": str(timetable_plot_path).replace("\\", "/"),
        "summary": summary,
        "scenario_rows": scenario_df,
        "type_distribution": type_df,
        "location_distribution": location_df,
        "coverage_distribution": coverage_df,
    }


def generate_batch_scenario_report(
    report_items: Sequence[Dict[str, object]],
    output_root: Path,
    config: AppConfig,
) -> Dict[str, object]:
    report_dir = output_root / "scenario_analysis_batch"
    report_dir.mkdir(parents=True, exist_ok=True)

    scenario_frames = [item["scenario_rows"] for item in report_items if isinstance(item.get("scenario_rows"), pd.DataFrame)]
    all_scenarios = pd.concat(scenario_frames, ignore_index=True) if scenario_frames else pd.DataFrame()
    type_df = _build_type_summary(all_scenarios)
    location_df = _build_location_summary(all_scenarios)

    case_rows: List[Dict[str, object]] = []
    for item in report_items:
        summary = dict(item.get("summary", {}))
        if summary:
            case_rows.append(summary)
    case_df = pd.DataFrame(case_rows)
    if not case_df.empty:
        case_df = case_df.sort_values(["total_scenarios", "case_id"], ascending=[False, True])

    timetable_df = read_timetable(config.input.timetable_path, sheet_name=config.input.timetable_sheet_name)
    timetable_df["arrival_sec"] = timetable_df["arrival_time"].apply(_time_to_seconds)
    timetable_df["departure_sec"] = timetable_df["departure_time"].apply(_time_to_seconds)
    station_order = _build_station_order(config, timetable_df)
    coverage_batch_df = _build_coverage_summary(all_scenarios, station_order, timetable_df)
    total_coverage = coverage_batch_df[coverage_batch_df["scope"] == "total"].iloc[0]

    summary_json_path = report_dir / "scenario_batch_summary.json"
    summary_excel_path = report_dir / "scenario_batch_summary.xlsx"
    type_plot_path = report_dir / "scenario_batch_type_distribution.png"
    case_plot_path = report_dir / "scenario_batch_case_distribution.png"
    location_plot_path = report_dir / "scenario_batch_location_distribution.png"
    coverage_plot_path = report_dir / "scenario_batch_coverage_distribution.png"
    timetable_plot_path = report_dir / "scenario_batch_timetable.png"

    payload = {
        "total_cases": int(len(report_items)),
        "cases_with_scenarios": int(sum(1 for item in report_items if int(dict(item.get("summary", {})).get("total_scenarios", 0)) > 0)),
        "total_scenarios": int(len(all_scenarios)) if not all_scenarios.empty else 0,
        "location_basis": str(total_coverage["location_basis"]),
        "covered_location_count": int(total_coverage["covered_location_count"]),
        "total_location_count": int(total_coverage["total_location_count"]),
        "location_coverage_ratio": float(total_coverage["location_coverage_ratio"]),
        "covered_time_sec": int(total_coverage["covered_time_sec"]),
        "timetable_span_sec": int(total_coverage["timetable_span_sec"]),
        "time_coverage_ratio": float(total_coverage["time_coverage_ratio"]),
        "type_distribution": type_df.to_dict(orient="records"),
        "location_distribution": location_df.to_dict(orient="records"),
        "coverage_distribution": coverage_batch_df.to_dict(orient="records"),
    }
    with summary_json_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    with pd.ExcelWriter(summary_excel_path, engine="openpyxl") as writer:
        pd.DataFrame([
            {
                "total_cases": payload["total_cases"],
                "cases_with_scenarios": payload["cases_with_scenarios"],
                "total_scenarios": payload["total_scenarios"],
                "location_basis": payload["location_basis"],
                "covered_location_count": payload["covered_location_count"],
                "total_location_count": payload["total_location_count"],
                "location_coverage_ratio": payload["location_coverage_ratio"],
                "covered_time_sec": payload["covered_time_sec"],
                "timetable_span_sec": payload["timetable_span_sec"],
                "time_coverage_ratio": payload["time_coverage_ratio"],
            }
        ]).to_excel(writer, sheet_name="summary", index=False)
        type_df.to_excel(writer, sheet_name="type_distribution", index=False)
        location_df.to_excel(writer, sheet_name="location_distribution", index=False)
        coverage_batch_df.to_excel(writer, sheet_name="coverage_distribution", index=False)
        case_df.to_excel(writer, sheet_name="case_distribution", index=False)
        all_scenarios.to_excel(writer, sheet_name="all_scenarios", index=False)

    _plot_type_distribution(type_df, type_plot_path, title="Batch Scenario Distribution")
    _plot_location_distribution(location_df, location_plot_path, title="Batch Scenario Locations")
    _plot_coverage_distribution(coverage_batch_df, coverage_plot_path, title="Batch Scenario Coverage")
    _plot_time_distribution(all_scenarios, case_plot_path, title="Batch Scenario Time Distribution")
    _plot_timetable_with_scenarios(config, all_scenarios, timetable_plot_path, title="Batch Scenario Timetable")

    return {
        "report_dir": str(report_dir).replace("\\", "/"),
        "summary_json": str(summary_json_path).replace("\\", "/"),
        "summary_excel": str(summary_excel_path).replace("\\", "/"),
        "type_plot": str(type_plot_path).replace("\\", "/"),
        "location_plot": str(location_plot_path).replace("\\", "/"),
        "coverage_plot": str(coverage_plot_path).replace("\\", "/"),
        "case_plot": str(case_plot_path).replace("\\", "/"),
        "timetable_plot": str(timetable_plot_path).replace("\\", "/"),
    }
