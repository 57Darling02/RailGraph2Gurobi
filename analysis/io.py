from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

REQUIRED_COLUMNS = ["train_id", "station", "arrival_time", "departure_time"]


def _normalize_columns(columns: List[str]) -> List[str]:
    mapping = {
        "train_id": "train_id",
        "trainid": "train_id",
        "train_ID": "train_id",
        "station": "station",
        "arrival_time": "arrival_time",
        "arrivaltime": "arrival_time",
        "departure_time": "departure_time",
        "departuretime": "departure_time",
    }
    normalized: List[str] = []
    for col in columns:
        key = str(col).strip()
        lookup = key.lower()
        normalized.append(mapping.get(key, mapping.get(lookup, lookup)))
    return normalized


def _parse_time_column(df: pd.DataFrame, column: str) -> pd.Series:
    text = df[column].astype(str).str.strip()
    text = text.replace({"": pd.NA, "nan": pd.NA, "NaT": pd.NA})
    parsed = pd.to_datetime(text, format="%H:%M:%S", errors="coerce")
    fallback = pd.to_datetime(text, format="%H:%M", errors="coerce")
    parsed = parsed.fillna(fallback)
    return parsed.dt.strftime("%H:%M:%S").where(parsed.notna(), None)


def read_timetable(path: Path, sheet_name: str = "Sheet1") -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    df.columns = _normalize_columns(df.columns.tolist())

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {path}: {missing}")

    df = df[REQUIRED_COLUMNS].copy()
    df["train_id"] = df["train_id"].astype(str).str.strip()
    df["station"] = df["station"].astype(str).str.strip()
    df["arrival_time"] = _parse_time_column(df, "arrival_time")
    df["departure_time"] = _parse_time_column(df, "departure_time")
    return df
