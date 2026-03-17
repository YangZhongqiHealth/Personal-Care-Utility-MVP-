#!/usr/bin/env python3
"""
Day-level MET matching (cosine) + DTW alignment for datapoint mapping.

CGMacros is the root dataset: for each CGMacros day we find the most similar
LONELINESS day based on normalized hourly MET profiles, then align the minute-
level MET sequences with DTW to map datapoints.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple, Iterable


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DATA_ROOT = os.path.join(REPO_ROOT, "mergedataPCU")
DEFAULT_LONELY_ROOT = os.path.join(LOCAL_DATA_ROOT, "LONELINESS-DATASET")
DEFAULT_CG_ROOT = os.path.join(LOCAL_DATA_ROOT, "CGMacros")
DEFAULT_OUTPUT_DIR = os.path.join(LOCAL_DATA_ROOT, "output")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Day-level cosine matching + DTW alignment for MET data."
    )
    parser.add_argument(
        "--lon-root",
        type=str,
        default=DEFAULT_LONELY_ROOT,
        help="Root folder of the LONELINESS-DATASET source data.",
    )
    parser.add_argument(
        "--cg-root",
        type=str,
        default=DEFAULT_CG_ROOT,
        help="Root folder of the CGMacros source data.",
    )
    parser.add_argument(
        "--max-cg-days",
        type=int,
        default=None,
        help="Limit number of CGMacros days to process (for testing).",
    )
    parser.add_argument(
        "--dtw-band",
        type=int,
        default=120,
        help="Sakoe-Chiba band in minutes for DTW (limits warping).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for match and mapping CSVs.",
    )
    return parser.parse_args()


def zscore(values: List[float]) -> List[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(var)
    if std == 0:
        return [0.0 for _ in values]
    return [(v - mean) / std for v in values]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return -1.0
    return dot / (norm_a * norm_b)


def dtw_path(
    a: List[float], b: List[float], band: int
) -> Tuple[float, List[Tuple[int, int]]]:
    """
    DTW with Sakoe-Chiba band. Returns (cost, path) where path is list of (i, j).
    """
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return float("inf"), []

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

    # Backtrack
    i, j = n, m
    path = []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        steps = [
            (dtw[i - 1][j], i - 1, j),
            (dtw[i][j - 1], i, j - 1),
            (dtw[i - 1][j - 1], i - 1, j - 1),
        ]
        _, i, j = min(steps, key=lambda t: t[0])
    path.reverse()
    return dtw[n][m], path


def load_loneliness_days(lonely_root: str) -> Tuple[
    Dict[Tuple[str, str], List[Tuple[datetime, float]]],
    Dict[Tuple[str, str], List[float]],
]:
    """
    Returns:
      - day_series[(participant, date)]: list of (timestamp, met) sorted by time
      - day_profile[(participant, date)]: 24-dim hourly mean MET vector (zscored)
    """
    day_series: Dict[Tuple[str, str], List[Tuple[datetime, float]]] = defaultdict(list)
    hourly_sum = defaultdict(lambda: [0.0] * 24)
    hourly_cnt = defaultdict(lambda: [0] * 24)

    participants = sorted(
        d for d in os.listdir(lonely_root)
        if d.startswith("pers") and os.path.isdir(os.path.join(lonely_root, d))
    )
    for p in participants:
        path = os.path.join(lonely_root, p, "Oura", "activity_1min.csv")
        if not os.path.exists(path):
            continue
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                met_str = row.get("activity_met_1min", "")
                ts_str = row.get("timestamp", "")
                if not met_str or not ts_str:
                    continue
                try:
                    met = float(met_str)
                    ts = datetime.fromtimestamp(int(ts_str) / 1000)
                except ValueError:
                    continue
                date = ts.date().isoformat()
                key = (p, date)
                day_series[key].append((ts, met))
                hour = ts.hour
                hourly_sum[key][hour] += met
                hourly_cnt[key][hour] += 1

    day_profile: Dict[Tuple[str, str], List[float]] = {}
    for key, sums in hourly_sum.items():
        counts = hourly_cnt[key]
        vec = [
            (sums[h] / counts[h]) if counts[h] > 0 else 0.0
            for h in range(24)
        ]
        day_profile[key] = zscore(vec)

    # Sort series by timestamp
    for key in list(day_series.keys()):
        day_series[key].sort(key=lambda x: x[0])

    return day_series, day_profile


def load_cgmacros_days(cg_root: str) -> Tuple[
    Dict[Tuple[str, str], List[Tuple[datetime, float]]],
    Dict[Tuple[str, str], List[float]],
]:
    day_series: Dict[Tuple[str, str], List[Tuple[datetime, float]]] = defaultdict(list)
    hourly_sum = defaultdict(lambda: [0.0] * 24)
    hourly_cnt = defaultdict(lambda: [0] * 24)

    participants = sorted(
        d for d in os.listdir(cg_root)
        if d.startswith("CGMacros-") and os.path.isdir(os.path.join(cg_root, d))
    )
    for p in participants:
        path = os.path.join(cg_root, p, f"{p}.csv")
        if not os.path.exists(path):
            continue
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            if "METs" not in reader.fieldnames or "Timestamp" not in reader.fieldnames:
                continue
            for row in reader:
                met_str = row.get("METs", "")
                ts_str = row.get("Timestamp", "")
                if not met_str or not ts_str:
                    continue
                try:
                    met = float(met_str)
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                date = ts.date().isoformat()
                key = (p, date)
                day_series[key].append((ts, met))
                hour = ts.hour
                hourly_sum[key][hour] += met
                hourly_cnt[key][hour] += 1

    day_profile: Dict[Tuple[str, str], List[float]] = {}
    for key, sums in hourly_sum.items():
        counts = hourly_cnt[key]
        vec = [
            (sums[h] / counts[h]) if counts[h] > 0 else 0.0
            for h in range(24)
        ]
        day_profile[key] = zscore(vec)

    for key in list(day_series.keys()):
        day_series[key].sort(key=lambda x: x[0])

    return day_series, day_profile


def find_best_match(
    cg_profile: List[float],
    lon_profiles: Dict[Tuple[str, str], List[float]],
) -> Tuple[Tuple[str, str], float]:
    best_key = None
    best_sim = -1.0
    for key, vec in lon_profiles.items():
        sim = cosine_similarity(cg_profile, vec)
        if sim > best_sim:
            best_sim = sim
            best_key = key
    return best_key, best_sim


def build_dtw_mapping(
    cg_series: List[Tuple[datetime, float]],
    lon_series: List[Tuple[datetime, float]],
    band: int,
) -> Tuple[float, List[Tuple[int, int]]]:
    cg_vals = zscore([v for _, v in cg_series])
    lon_vals = zscore([v for _, v in lon_series])
    return dtw_path(cg_vals, lon_vals, band=band)


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def main() -> None:
    args = parse_args()

    print("Loading LONELINESS days...")
    lon_series, lon_profiles = load_loneliness_days(args.lon_root)
    print(f"Loaded {len(lon_profiles)} LONELINESS days")

    print("Loading CGMacros days...")
    cg_series, cg_profiles = load_cgmacros_days(args.cg_root)
    print(f"Loaded {len(cg_profiles)} CGMacros days")

    ensure_dir(args.output_dir)
    matches_path = os.path.join(args.output_dir, "cg_day_matches.csv")
    mapping_path = os.path.join(args.output_dir, "cg_to_lon_dtw_map.csv")

    with open(matches_path, "w", newline="") as f_matches, open(
        mapping_path, "w", newline=""
    ) as f_map:
        matches_writer = csv.writer(f_matches)
        map_writer = csv.writer(f_map)

        matches_writer.writerow(
            [
                "cg_participant",
                "cg_date",
                "lon_participant",
                "lon_date",
                "cosine_similarity",
            ]
        )
        map_writer.writerow(
            [
                "cg_participant",
                "cg_date",
                "cg_timestamp",
                "lon_participant",
                "lon_date",
                "lon_timestamp",
                "dtw_cost",
            ]
        )

        processed = 0
        for cg_key, cg_profile in cg_profiles.items():
            if args.max_cg_days is not None and processed >= args.max_cg_days:
                break
            cg_participant, cg_date = cg_key
            cg_day_series = cg_series.get(cg_key, [])
            if not cg_day_series:
                continue

            best_key, best_sim = find_best_match(cg_profile, lon_profiles)
            if best_key is None:
                continue

            lon_participant, lon_date = best_key
            lon_day_series = lon_series.get(best_key, [])
            if not lon_day_series:
                continue

            matches_writer.writerow(
                [cg_participant, cg_date, lon_participant, lon_date, best_sim]
            )

            dtw_cost, path = build_dtw_mapping(
                cg_day_series, lon_day_series, band=args.dtw_band
            )

            # Map each CGMacros index to the last matched LONELINESS index in the path
            last_j_for_i = {}
            for i, j in path:
                last_j_for_i[i] = j

            for i, (cg_ts, _) in enumerate(cg_day_series):
                if i not in last_j_for_i:
                    continue
                j = last_j_for_i[i]
                lon_ts, _ = lon_day_series[j]
                map_writer.writerow(
                    [
                        cg_participant,
                        cg_date,
                        cg_ts.isoformat(sep=" "),
                        lon_participant,
                        lon_date,
                        lon_ts.isoformat(sep=" "),
                        dtw_cost,
                    ]
                )

            processed += 1

    print(f"Wrote matches to {matches_path}")
    print(f"Wrote DTW mapping to {mapping_path}")


if __name__ == "__main__":
    main()
