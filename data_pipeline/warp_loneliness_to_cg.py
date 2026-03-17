#!/usr/bin/env python3
"""
Warp LONELINESS timestamps onto CGMacros time using DTW mapping.

For each matched CG day, the DTW map (CG minute -> LON minute) is inverted
to map any LON timestamp in that day to a CG timestamp. We apply that mapping
to all LONELINESS CSVs (except weekly), producing per-CG participant outputs
that mirror the LONELINESS folder structure.
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DATA_ROOT = os.path.join(REPO_ROOT, "mergedataPCU")
DEFAULT_MATCHES_CSV = os.path.join(LOCAL_DATA_ROOT, "output", "cg_day_matches.csv")
DEFAULT_LON_ROOT = os.path.join(LOCAL_DATA_ROOT, "LONELINESS-DATASET")
DEFAULT_CG_ROOT = os.path.join(LOCAL_DATA_ROOT, "CGMacros")
DEFAULT_OUTPUT_ROOT = os.path.join(LOCAL_DATA_ROOT, "output", "cg_augmented")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Warp LONELINESS timestamps to CGMacros timeline using DTW map."
    )
    parser.add_argument(
        "--matches-csv",
        type=str,
        default=DEFAULT_MATCHES_CSV,
        help="Path to cg_day_matches.csv.",
    )
    parser.add_argument(
        "--lon-root",
        type=str,
        default=DEFAULT_LON_ROOT,
        help="Root folder of LONELINESS-DATASET.",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default=DEFAULT_OUTPUT_ROOT,
        help="Output root for CG-augmented LONELINESS data.",
    )
    parser.add_argument(
        "--cg-root",
        type=str,
        default=DEFAULT_CG_ROOT,
        help="Root folder of CGMacros dataset.",
    )
    parser.add_argument(
        "--dtw-band",
        type=int,
        default=120,
        help="Sakoe-Chiba band (minutes) for DTW.",
    )
    return parser.parse_args()


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def parse_iso_dt(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_epoch_dt(value: str) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except ValueError:
        return None
    # Heuristic: detect ms vs seconds
    if num > 1e12:
        num = num / 1000.0
    return datetime.fromtimestamp(num)


def parse_timestamp_from_row(row: Dict[str, str]) -> Optional[datetime]:
    if "timestamp_ms" in row:
        dt = parse_epoch_dt(row.get("timestamp_ms", ""))
        if dt:
            return dt
    if "timestamp" in row:
        dt = parse_epoch_dt(row.get("timestamp", ""))
        if dt:
            return dt
        dt = parse_iso_dt(row.get("timestamp", ""))
        if dt:
            return dt
    if "datetime" in row:
        dt = parse_iso_dt(row.get("datetime", ""))
        if dt:
            return dt
    if "date" in row and "time" in row:
        combined = f"{row.get('date', '')} {row.get('time', '')}".strip()
        dt = parse_iso_dt(combined)
        if dt:
            return dt
    return None


def floor_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def format_dt(dt: datetime) -> str:
    return dt.isoformat(sep=" ")


DayKey = Tuple[str, str, str, str]  # (cg_participant, cg_date, lon_participant, lon_date)


def zscore(values: List[float]) -> List[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    std = var ** 0.5
    if std == 0:
        return [0.0 for _ in values]
    return [(v - mean) / std for v in values]


def dtw_path(
    a: List[float],
    b: List[float],
    band: int,
) -> List[Tuple[int, int]]:
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return []
    band = max(band, abs(n - m))
    inf = float("inf")
    dtw = [[inf] * (m + 1) for _ in range(n + 1)]
    dtw[0][0] = 0.0

    for i in range(1, n + 1):
        j_start = max(1, i - band)
        j_end = min(m, i + band)
        for j in range(j_start, j_end + 1):
            cost = abs(a[i - 1] - b[j - 1])
            dtw[i][j] = cost + min(dtw[i - 1][j], dtw[i][j - 1], dtw[i - 1][j - 1])

    i, j = n, m
    path: List[Tuple[int, int]] = []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        steps = [
            (dtw[i - 1][j], i - 1, j),
            (dtw[i][j - 1], i, j - 1),
            (dtw[i - 1][j - 1], i - 1, j - 1),
        ]
        _, i, j = min(steps, key=lambda t: t[0])
    path.reverse()
    return path


def is_weekly_file(rel_path: str) -> bool:
    return os.path.basename(rel_path).lower() == "weekly.csv"


def is_excluded_file(rel_path: str) -> bool:
    rel_norm = rel_path.replace(os.sep, "/").lower()
    base = os.path.basename(rel_norm)
    if rel_norm.endswith("/aware/extracted_features.csv"):
        return True
    if base in {"event_labels.csv", "event_labels_daily.csv"}:
        return True
    return False


def is_daily_file(rel_path: str) -> bool:
    base = os.path.basename(rel_path).lower()
    return "daily" in base


def iter_lon_csv_files(lon_root: str) -> Iterable[Tuple[str, str, str]]:
    participants = sorted(
        d for d in os.listdir(lon_root)
        if d.startswith("pers") and os.path.isdir(os.path.join(lon_root, d))
    )
    for participant in participants:
        base_dir = os.path.join(lon_root, participant)
        for root, _, files in os.walk(base_dir):
            for name in files:
                if not name.lower().endswith(".csv"):
                    continue
                rel_path = os.path.relpath(os.path.join(root, name), lon_root)
                if is_weekly_file(rel_path):
                    continue
                if is_excluded_file(rel_path):
                    continue
                yield participant, os.path.join(root, name), rel_path


class WriterCache:
    def __init__(self) -> None:
        self._handles: Dict[str, Tuple[csv.writer, object]] = {}
        self._headers: Dict[str, List[str]] = {}

    def get_writer(self, path: str, header: List[str]) -> csv.writer:
        if path in self._handles:
            return self._handles[path][0]
        ensure_dir(os.path.dirname(path))
        f = open(path, "w", newline="")
        writer = csv.writer(f)
        writer.writerow(header)
        self._handles[path] = (writer, f)
        self._headers[path] = header
        return writer

    def close_all(self) -> None:
        for _, f in self._handles.values():
            f.close()


def build_output_path(output_root: str, cg_participant: str, rel_path: str) -> str:
    parts = rel_path.split(os.sep)
    if len(parts) <= 1:
        rel_no_participant = rel_path
    else:
        rel_no_participant = os.path.join(*parts[1:])
    return os.path.join(output_root, cg_participant, rel_no_participant)


def build_output_header(
    input_fields: List[str],
    daily: bool,
    cg_fields: List[str],
) -> List[str]:
    if daily:
        base = ["cg_participant", "cg_date", "lon_participant", "lon_date"]
    else:
        base = [
            "cg_participant",
            "cg_date",
            "cg_timestamp",
            "lon_participant",
            "lon_date",
            "lon_timestamp",
        ]
    return base + cg_fields + input_fields


def write_row(
    writer: csv.writer,
    header: List[str],
    row: Dict[str, str],
    cg_row: Optional[Dict[str, str]],
    cg_participant: str,
    cg_date: str,
    cg_ts: Optional[datetime],
    lon_participant: str,
    lon_date: str,
    lon_ts: Optional[datetime],
) -> None:
    out = {k: "" for k in header}
    out.update(
        {
            "cg_participant": cg_participant,
            "cg_date": cg_date,
            "lon_participant": lon_participant,
            "lon_date": lon_date,
        }
    )
    if cg_ts is not None:
        out["cg_timestamp"] = format_dt(cg_ts)
    if lon_ts is not None:
        out["lon_timestamp"] = format_dt(lon_ts)
    if cg_row:
        for k, v in cg_row.items():
            out[k] = v
    for k, v in row.items():
        out[k] = v
    writer.writerow([out.get(k, "") for k in header])


def cg_field_name(field: str) -> str:
    return f"cg_{field}"


def load_cg_participant(
    cg_root: str,
    cg_participant: str,
) -> Tuple[Dict[datetime, Dict[str, str]], List[str]]:
    path = os.path.join(cg_root, cg_participant, f"{cg_participant}.csv")
    if not os.path.exists(path):
        return {}, []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}, []
        input_fields = list(reader.fieldnames)
        skip_fields = {"timestamp", "Timestamp", "Unnamed: 0"}
        cg_fields = [cg_field_name(f) for f in input_fields if f not in skip_fields]
        cg_rows: Dict[datetime, Dict[str, str]] = {}
        for row in reader:
            ts_str = row.get("Timestamp", "")
            ts = parse_iso_dt(ts_str)
            if not ts:
                continue
            ts = floor_to_minute(ts)
            cg_row = {}
            for key, value in row.items():
                if key in skip_fields:
                    continue
                cg_row[cg_field_name(key)] = value
            cg_rows[ts] = cg_row
    return cg_rows, cg_fields


class CGCache:
    def __init__(self, cg_root: str) -> None:
        self.cg_root = cg_root
        self._rows: Dict[str, Dict[datetime, Dict[str, str]]] = {}
        self._fields: Dict[str, List[str]] = {}

    def get(self, cg_participant: str) -> Tuple[Dict[datetime, Dict[str, str]], List[str]]:
        if cg_participant in self._rows:
            return self._rows[cg_participant], self._fields.get(cg_participant, [])
        rows, fields = load_cg_participant(self.cg_root, cg_participant)
        self._rows[cg_participant] = rows
        self._fields[cg_participant] = fields
        return rows, fields


def load_cg_met_series(cg_root: str, cg_participant: str) -> Dict[str, List[Tuple[datetime, float]]]:
    path = os.path.join(cg_root, cg_participant, f"{cg_participant}.csv")
    day_series: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
    if not os.path.exists(path):
        return day_series
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "METs" not in reader.fieldnames:
            return day_series
        for row in reader:
            ts = parse_iso_dt(row.get("Timestamp", ""))
            met_str = row.get("METs", "")
            if not ts or not met_str:
                continue
            try:
                met = float(met_str)
            except ValueError:
                continue
            ts = floor_to_minute(ts)
            day_series[ts.date().isoformat()].append((ts, met))
    for series in day_series.values():
        series.sort(key=lambda x: x[0])
    return day_series


def load_lon_met_series(lon_root: str, lon_participant: str) -> Dict[str, List[Tuple[datetime, float]]]:
    path = os.path.join(lon_root, lon_participant, "Oura", "activity_1min.csv")
    day_series: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
    if not os.path.exists(path):
        return day_series
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "activity_met_1min" not in reader.fieldnames:
            return day_series
        for row in reader:
            ts = parse_epoch_dt(row.get("timestamp", ""))
            met_str = row.get("activity_met_1min", "")
            if not ts or not met_str:
                continue
            try:
                met = float(met_str)
            except ValueError:
                continue
            ts = floor_to_minute(ts)
            day_series[ts.date().isoformat()].append((ts, met))
    for series in day_series.values():
        series.sort(key=lambda x: x[0])
    return day_series


class MetSeriesCache:
    def __init__(self, cg_root: str, lon_root: str) -> None:
        self.cg_root = cg_root
        self.lon_root = lon_root
        self._cg: Dict[str, Dict[str, List[Tuple[datetime, float]]]] = {}
        self._lon: Dict[str, Dict[str, List[Tuple[datetime, float]]]] = {}

    def get_cg_day(self, cg_participant: str, cg_date: str) -> List[Tuple[datetime, float]]:
        if cg_participant not in self._cg:
            self._cg[cg_participant] = load_cg_met_series(self.cg_root, cg_participant)
        return self._cg[cg_participant].get(cg_date, [])

    def get_lon_day(self, lon_participant: str, lon_date: str) -> List[Tuple[datetime, float]]:
        if lon_participant not in self._lon:
            self._lon[lon_participant] = load_lon_met_series(self.lon_root, lon_participant)
        return self._lon[lon_participant].get(lon_date, [])


def build_day_maps_from_matches(
    matches_csv: str,
    cg_root: str,
    lon_root: str,
    band: int,
) -> Tuple[Dict[DayKey, Dict[datetime, datetime]], Dict[Tuple[str, str], List[DayKey]]]:
    day_maps: Dict[DayKey, Dict[datetime, datetime]] = {}
    lon_day_index: Dict[Tuple[str, str], List[DayKey]] = defaultdict(list)
    met_cache = MetSeriesCache(cg_root, lon_root)

    with open(matches_csv, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cg_participant = row.get("cg_participant", "")
            cg_date = row.get("cg_date", "")
            lon_participant = row.get("lon_participant", "")
            lon_date = row.get("lon_date", "")
            if not (cg_participant and cg_date and lon_participant and lon_date):
                continue

            cg_series = met_cache.get_cg_day(cg_participant, cg_date)
            lon_series = met_cache.get_lon_day(lon_participant, lon_date)
            if not cg_series or not lon_series:
                continue

            cg_vals = zscore([v for _, v in cg_series])
            lon_vals = zscore([v for _, v in lon_series])
            path = dtw_path(cg_vals, lon_vals, band=band)
            if not path:
                continue

            day_key = (cg_participant, cg_date, lon_participant, lon_date)
            lon_day_index[(lon_participant, lon_date)].append(day_key)

            last_i_for_j: Dict[int, int] = {}
            for i, j in path:
                last_i_for_j[j] = i

            mapping: Dict[datetime, datetime] = {}
            for j, (lon_ts, _) in enumerate(lon_series):
                if j not in last_i_for_j:
                    continue
                i = last_i_for_j[j]
                cg_ts, _ = cg_series[i]
                mapping[lon_ts] = cg_ts
            day_maps[day_key] = mapping

    return day_maps, lon_day_index


def process_lon_file(
    lon_participant: str,
    file_path: str,
    rel_path: str,
    day_maps: Dict[DayKey, Dict[datetime, datetime]],
    lon_day_index: Dict[Tuple[str, str], List[DayKey]],
    output_root: str,
    writer_cache: WriterCache,
    cg_cache: CGCache,
) -> None:
    daily = is_daily_file(rel_path)

    with open(file_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return
        input_fields = list(reader.fieldnames)

        for row in reader:
            row_date = row.get("date", "")
            if daily:
                lon_date = row_date
                if not lon_date:
                    ts = parse_timestamp_from_row(row)
                    if not ts:
                        continue
                    lon_date = ts.date().isoformat()
                matches = lon_day_index.get((lon_participant, lon_date), [])
                if not matches:
                    continue
                for day_key in matches:
                    cg_participant, cg_date, lon_p, lon_d = day_key
                    _, cg_fields = cg_cache.get(cg_participant)
                    header = build_output_header(input_fields, daily=True, cg_fields=cg_fields)
                    out_path = build_output_path(output_root, cg_participant, rel_path)
                    writer = writer_cache.get_writer(out_path, header)
                    write_row(
                        writer,
                        header,
                        row,
                        None,
                        cg_participant,
                        cg_date,
                        None,
                        lon_p,
                        lon_d,
                        None,
                    )
                continue

            ts = parse_timestamp_from_row(row)
            if not ts:
                continue
            lon_ts = floor_to_minute(ts)
            lon_date = row_date or lon_ts.date().isoformat()

            matches = lon_day_index.get((lon_participant, lon_date), [])
            if not matches:
                continue

            for day_key in matches:
                cg_participant, cg_date, lon_p, lon_d = day_key
                cg_ts = day_maps.get(day_key, {}).get(lon_ts)
                if not cg_ts:
                    continue
                cg_rows, cg_fields = cg_cache.get(cg_participant)
                header = build_output_header(input_fields, daily=False, cg_fields=cg_fields)
                cg_row = cg_rows.get(cg_ts)
                out_path = build_output_path(output_root, cg_participant, rel_path)
                writer = writer_cache.get_writer(out_path, header)
                write_row(
                    writer,
                    header,
                    row,
                    cg_row,
                    cg_participant,
                    cg_date,
                    cg_ts,
                    lon_p,
                    lon_d,
                    lon_ts,
                )


def main() -> None:
    args = parse_args()
    day_maps, lon_day_index = build_day_maps_from_matches(
        args.matches_csv,
        args.cg_root,
        args.lon_root,
        band=args.dtw_band,
    )
    ensure_dir(args.output_root)

    cg_cache = CGCache(args.cg_root)
    writer_cache = WriterCache()
    try:
        for lon_participant, file_path, rel_path in iter_lon_csv_files(args.lon_root):
            process_lon_file(
                lon_participant,
                file_path,
                rel_path,
                day_maps,
                lon_day_index,
                args.output_root,
                writer_cache,
                cg_cache,
            )
    finally:
        writer_cache.close_all()

    print(f"Wrote CG-augmented LONELINESS data to {args.output_root}")


if __name__ == "__main__":
    main()
