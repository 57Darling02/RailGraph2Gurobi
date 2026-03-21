from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.dates import DateFormatter


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


def plot_timetable(
    file_path: Path,
    output_path: Path,
    show_grid: bool = False,
    title: str = "Train Timetable",
    sheet_name: str = "Sheet1",
) -> Path:
    plt.rcParams["axes.unicode_minus"] = False

    df = _read_and_format(file_path, sheet_name=sheet_name)
    df = df.sort_values(["train_ID", "arrival_time", "departure_time", "station"])

    stations = df["station"].drop_duplicates().tolist()
    if not stations:
        raise ValueError("No stations found for plotting.")

    fig, ax = plt.subplots(figsize=(24, 10))

    for train in df["train_ID"].drop_duplicates().tolist():
        train_data = df[df["train_ID"] == train].copy().reset_index(drop=True)

        first_dep = train_data.loc[0, "departure_time"]
        first_station = train_data.loc[0, "station"]
        if pd.notna(first_dep):
            ax.text(
                first_dep,
                first_station,
                train,
                verticalalignment="bottom",
                horizontalalignment="center",
                fontsize=6,
                color="red",
                rotation=270,
            )

        for i in range(len(train_data) - 1):
            dep = train_data.loc[i, "departure_time"]
            arr = train_data.loc[i + 1, "arrival_time"]
            dep_station = train_data.loc[i, "station"]
            arr_station = train_data.loc[i + 1, "station"]

            if pd.notna(dep) and pd.notna(arr):
                ax.plot([dep, arr], [dep_station, arr_station], color="red", lw=0.8)

    all_times = pd.concat(
        [df["arrival_time"], df["departure_time"]], ignore_index=True
    ).dropna()
    if all_times.empty:
        raise ValueError("No valid arrival/departure times found for plotting.")

    start_time = _floor_10_minutes(all_times.min())
    end_time = _ceil_10_minutes(all_times.max())
    ax.set_xlim(start_time, end_time)

    ax.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.tick_params(axis="x", labelsize=10, pad=20)
    ax.tick_params(axis="both", which="both", length=0)

    ax.set_title(title, pad=20)
    ax.grid(show_grid)
    plt.xticks(rotation=0)
    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=500)
    plt.close()
    return output_path

