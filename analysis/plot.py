from __future__ import annotations

from pathlib import Path
import textwrap
from typing import Iterable, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.dates import DateFormatter
from matplotlib.patches import Patch, Rectangle

from core.loader import load_mileage_table

SCENARIO_TYPE_COLOR = {
    "delay": "#f28e2b",
    "speed_limit": "#4e79a7",
    "interruption": "#e15759",
}
SCENARIO_TYPE_LABEL = {
    "delay": "Delay",
    "speed_limit": "Speed Limit",
    "interruption": "Interruption",
}


def _read_and_format(path: Path, sheet_name: str = "Sheet1") -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    required = ["train_ID", "station", "arrival_time", "departure_time"]
    if not all(col in df.columns for col in required) and "train_id" in df.columns:
        df = df.rename(columns={"train_id": "train_ID"})
    if not all(col in df.columns for col in required):
        raise ValueError(f"plot input columns must include {required}, got {list(df.columns)}")

    df = df[["train_ID", "station", "arrival_time", "departure_time"]].copy()
    for col in ["arrival_time", "departure_time"]:
        parsed = pd.to_datetime(df[col], errors="coerce")
        parsed = parsed.fillna(pd.to_datetime(df[col].astype(str), format="%H:%M:%S", errors="coerce"))
        parsed = parsed.fillna(pd.to_datetime(df[col].astype(str), format="%H:%M", errors="coerce"))
        df[col] = parsed

    return df


def _floor_10_minutes(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.replace(minute=(ts.minute // 10) * 10, second=0, microsecond=0)


def _ceil_10_minutes(ts: pd.Timestamp) -> pd.Timestamp:
    ts = ts.replace(second=0, microsecond=0)
    minute = ts.minute
    rounded = ((minute + 9) // 10) * 10
    if rounded == 60:
        return (ts + pd.Timedelta(hours=1)).replace(minute=0)
    return ts.replace(minute=rounded)


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


def _build_station_order(df: pd.DataFrame, mileage_path: Path | None, mileage_sheet_name: str) -> list[str]:
    if mileage_path is not None and mileage_path.exists():
        raw = load_mileage_table(mileage_path, mileage_sheet_name)
        records: list[tuple[str, float]] = []
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
        mileage_order = [station for station, _ in sorted(records, key=lambda item: item[1])]
        plotted_stations = set(df["station"].dropna().astype(str).tolist())
        ordered = [station for station in mileage_order if station in plotted_stations]
        if ordered:
            return ordered
    return df["station"].drop_duplicates().astype(str).tolist()


def _expand_station_span(start_station: str, end_station: str, station_order: list[str]) -> list[str]:
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


def _compute_overlay_y_bounds(scenario_type: str, y_values: list[int]) -> tuple[float, float] | None:
    if not y_values:
        return None
    lower_y = float(min(y_values))
    upper_y = float(max(y_values))
    if scenario_type == "delay":
        return lower_y - 0.1, 0.2
    if lower_y == upper_y:
        return lower_y - 0.4, 0.8
    return lower_y, max(upper_y - lower_y, 1e-6)


def _add_scenario_overlay(ax, scenario_overlay: pd.DataFrame, station_order: list[str]) -> None:
    if scenario_overlay.empty:
        return
    station_to_y = {station: idx for idx, station in enumerate(station_order)}
    legend_handles = []
    seen_types = set()

    for row in scenario_overlay.itertuples():
        scenario_type = str(getattr(row, "scenario_type", ""))
        color = SCENARIO_TYPE_COLOR.get(scenario_type)
        if color is None:
            continue
        start_sec = getattr(row, "display_start_sec", None)
        end_sec = getattr(row, "display_end_sec", None)
        if start_sec is None or end_sec is None:
            continue

        span_stations = _expand_station_span(str(getattr(row, "start_station", "")), str(getattr(row, "end_station", "")), station_order)
        y_values = [station_to_y[station] for station in span_stations if station in station_to_y]
        if not y_values:
            continue

        start_num = mdates.date2num(_seconds_to_timestamp(int(start_sec)))
        end_num = mdates.date2num(_seconds_to_timestamp(int(max(end_sec, start_sec + 1))))
        y_bounds = _compute_overlay_y_bounds(scenario_type, y_values)
        if y_bounds is None:
            continue
        lower, height = y_bounds
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

        if scenario_type not in seen_types:
            seen_types.add(scenario_type)
            legend_handles.append(
                Patch(facecolor=color, edgecolor=color, alpha=0.22, label=SCENARIO_TYPE_LABEL[scenario_type])
            )

    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper left")


def plot_timetable(
    file_path: Path,
    output_path: Path,
    show_grid: bool = False,
    title: str = "Train Timetable",
    subtitle: str = "",
    sheet_name: str = "Sheet1",
    scenario_overlay: Optional[pd.DataFrame] = None,
    mileage_path: Path | None = None,
    mileage_sheet_name: str = "Sheet1",
) -> Path:
    plt.rcParams["axes.unicode_minus"] = False

    df = _read_and_format(file_path, sheet_name=sheet_name)
    df = df.sort_values(["train_ID", "arrival_time", "departure_time", "station"])

    stations = _build_station_order(df, mileage_path, mileage_sheet_name)
    if not stations:
        raise ValueError("No stations found for plotting.")
    station_to_y = {station: idx for idx, station in enumerate(stations)}
    df["station_y"] = df["station"].map(station_to_y)

    fig, ax = plt.subplots(figsize=(24, 10))

    if scenario_overlay is not None:
        _add_scenario_overlay(ax, scenario_overlay, stations)

    for train in df["train_ID"].drop_duplicates().tolist():
        train_data = df[df["train_ID"] == train].copy().reset_index(drop=True)

        first_dep = train_data.loc[0, "departure_time"]
        first_station_y = train_data.loc[0, "station_y"]
        if pd.notna(first_dep) and pd.notna(first_station_y):
            ax.text(
                first_dep,
                first_station_y,
                train,
                verticalalignment="bottom",
                horizontalalignment="center",
                fontsize=6,
                color="red",
                rotation=270,
                zorder=4,
            )

        for i in range(len(train_data) - 1):
            dep = train_data.loc[i, "departure_time"]
            arr = train_data.loc[i + 1, "arrival_time"]
            dep_station_y = train_data.loc[i, "station_y"]
            arr_station_y = train_data.loc[i + 1, "station_y"]

            if pd.notna(dep) and pd.notna(arr) and pd.notna(dep_station_y) and pd.notna(arr_station_y):
                ax.plot([dep, arr], [dep_station_y, arr_station_y], color="red", lw=0.8, zorder=3)

    all_times = pd.concat(
        [df["arrival_time"], df["departure_time"]], ignore_index=True
    ).dropna()
    if all_times.empty:
        raise ValueError("No valid arrival/departure times found for plotting.")

    start_time = _floor_10_minutes(all_times.min())
    end_time = _ceil_10_minutes(all_times.max())
    ax.set_xlim(start_time, end_time)

    ax.set_yticks(list(station_to_y.values()))
    ax.set_yticklabels(stations)
    ax.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.tick_params(axis="x", labelsize=10, pad=20)
    ax.tick_params(axis="both", which="both", length=0)

    ax.set_title(title, pad=20)
    ax.grid(show_grid)
    plt.xticks(rotation=0)

    if subtitle:
        subtitle_wrapped = textwrap.fill(subtitle, width=150)
        fig.text(0.01, 0.965, subtitle_wrapped, ha="left", va="top", fontsize=8, color="dimgray")
        plt.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    else:
        plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=500)
    plt.close()
    return output_path
