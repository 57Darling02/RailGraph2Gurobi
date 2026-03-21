from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from analysis.io import read_timetable


def _time_to_seconds(value: str | None) -> float:
    if value is None or str(value).strip() == "":
        return float("nan")
    hour, minute, second = [int(part) for part in str(value).split(":")]
    return float(hour * 3600 + minute * 60 + second)


def analyze_timetable(
    plan_path: Path,
    adjusted_path: Path,
    output_path: Path,
    plan_sheet_name: str = "Sheet1",
    adjusted_sheet_name: str = "Sheet1",
) -> Path:
    plan_df = read_timetable(plan_path, sheet_name=plan_sheet_name)
    adjusted_df = read_timetable(adjusted_path, sheet_name=adjusted_sheet_name)

    for df in (plan_df, adjusted_df):
        df["arrival_sec"] = df["arrival_time"].apply(_time_to_seconds)
        df["departure_sec"] = df["departure_time"].apply(_time_to_seconds)

    canceled_trains = sorted(set(plan_df["train_id"]) - set(adjusted_df["train_id"]))

    merged = pd.merge(
        plan_df[["train_id", "station", "arrival_sec", "departure_sec"]],
        adjusted_df[["train_id", "station", "arrival_sec", "departure_sec"]],
        on=["train_id", "station"],
        suffixes=("_plan", "_adjusted"),
        how="left",
    )

    merged = merged.dropna(subset=["arrival_sec_adjusted", "departure_sec_adjusted"], how="all")

    merged["arrival_late_sec"] = (
        (merged["arrival_sec_adjusted"] - merged["arrival_sec_plan"]).clip(lower=0).fillna(0)
    )
    merged["departure_late_sec"] = (
        (merged["departure_sec_adjusted"] - merged["departure_sec_plan"]).clip(lower=0).fillna(0)
    )
    merged["arrival_dev_sec"] = (merged["arrival_sec_adjusted"] - merged["arrival_sec_plan"]).abs().fillna(0)
    merged["departure_dev_sec"] = (
        (merged["departure_sec_adjusted"] - merged["departure_sec_plan"]).abs().fillna(0)
    )

    merged["is_late_event"] = (merged["arrival_late_sec"] > 0) | (merged["departure_late_sec"] > 0)
    train_late = merged.groupby("train_id")["is_late_event"].any().reset_index(name="is_late")
    late_train_ids = train_late.loc[train_late["is_late"], "train_id"].tolist()

    last_station = (
        plan_df.groupby("train_id", as_index=False).last()[["train_id", "station"]].rename(columns={"station": "end_station"})
    )
    merged_end = pd.merge(merged, last_station, on="train_id", how="left")
    end_rows = merged_end[merged_end["station"] == merged_end["end_station"]]
    end_late_train_ids = sorted(end_rows.loc[end_rows["arrival_late_sec"] > 0, "train_id"].unique().tolist())

    station_stats = (
        merged.groupby("station", as_index=False)
        .agg(
            late_train_count=("is_late_event", lambda x: int(x.sum())),
            total_arrival_late_sec=("arrival_late_sec", "sum"),
            total_departure_late_sec=("departure_late_sec", "sum"),
        )
    )
    station_stats["total_late_sec"] = (
        station_stats["total_arrival_late_sec"] + station_stats["total_departure_late_sec"]
    )
    station_stats = station_stats.drop(columns=["total_arrival_late_sec", "total_departure_late_sec"])

    summary: Dict[str, object] = {
        "total_late_sec": float(merged["arrival_late_sec"].sum() + merged["departure_late_sec"].sum()),
        "total_deviation_sec": float(merged["arrival_dev_sec"].sum() + merged["departure_dev_sec"].sum()),
        "late_train_count": int(len(late_train_ids)),
        "late_train_ids": ",".join(late_train_ids),
        "end_late_train_count": int(len(end_late_train_ids)),
        "end_late_train_ids": ",".join(end_late_train_ids),
        "canceled_train_count": int(len(canceled_trains)),
        "canceled_train_ids": ",".join(canceled_trains),
    }
    summary_df = pd.DataFrame([summary])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        station_stats.to_excel(writer, sheet_name="station_stats", index=False)
        train_late.to_excel(writer, sheet_name="train_late", index=False)
        pd.DataFrame({"canceled_train_id": canceled_trains}).to_excel(
            writer, sheet_name="canceled_trains", index=False
        )

    return output_path

