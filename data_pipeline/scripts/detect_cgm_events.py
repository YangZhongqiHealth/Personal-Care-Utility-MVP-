#!/usr/bin/env python3
import argparse
import csv
import statistics
from collections import deque
from datetime import datetime, time
from pathlib import Path


CGM_COLUMNS = ("cg_Libre GL", "cg_Dexcom GL")
TIMESTAMP_COLUMNS = ("cg_timestamp", "timestamp")

TIR_RANGE = (70.0, 180.0)
TAR_L1_RANGE = (181.0, 250.0)
TAR_L2_MIN = 250.0
TBR_L1_RANGE = (54.0, 69.0)
TBR_L2_MAX = 54.0

RAPID_RATE_THRESHOLD = 2.0  # mg/dL per minute
SUSTAINED_MINUTES = 15.0
HV_WINDOW_MINUTES = 60.0
HV_CV_THRESHOLD = 36.0
OVERNIGHT_START = time(0, 0, 0)
OVERNIGHT_END = time(6, 0, 0)


def parse_float(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_timestamp(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.isdigit():
            ts = int(text)
            if ts > 1_000_000_000_000:
                ts /= 1000.0
            return datetime.fromtimestamp(ts)
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def csv_has_cgm(path):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
    except OSError:
        return False
    return any(col in header for col in CGM_COLUMNS)


def load_samples(csv_paths):
    samples = {}
    for path in csv_paths:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    continue
                for row in reader:
                    ts_value = None
                    for ts_col in TIMESTAMP_COLUMNS:
                        if row.get(ts_col):
                            ts_value = row.get(ts_col)
                            break
                    ts = parse_timestamp(ts_value)
                    if ts is None:
                        continue

                    glucose = parse_float(row.get(CGM_COLUMNS[0]))
                    source_rank = 2
                    if glucose is None:
                        glucose = parse_float(row.get(CGM_COLUMNS[1]))
                        source_rank = 1
                    if glucose is None:
                        continue

                    existing = samples.get(ts)
                    if existing is None or source_rank > existing[1]:
                        samples[ts] = (glucose, source_rank)
        except OSError:
            continue
    ordered = sorted(((ts, g) for ts, (g, _) in samples.items()), key=lambda item: item[0])
    return ordered


def median_interval_minutes(samples):
    if len(samples) < 2:
        return None
    deltas = []
    for idx in range(1, len(samples)):
        delta = (samples[idx][0] - samples[idx - 1][0]).total_seconds() / 60.0
        if delta > 0:
            deltas.append(delta)
    if not deltas:
        return None
    return statistics.median(deltas)


def iter_episodes(samples, predicate, max_gap_minutes):
    current_start = None
    current_last = None
    prev_ts = None
    for ts, glucose in samples:
        if prev_ts is not None:
            gap = (ts - prev_ts).total_seconds() / 60.0
            if gap > max_gap_minutes and current_start is not None:
                yield current_start, current_last
                current_start = None
                current_last = None
        if predicate(glucose):
            if current_start is None:
                current_start = ts
            current_last = ts
        else:
            if current_start is not None:
                yield current_start, current_last
                current_start = None
                current_last = None
        prev_ts = ts
    if current_start is not None:
        yield current_start, current_last


def episode_duration_minutes(start, end):
    return (end - start).total_seconds() / 60.0


def detect_events(samples):
    events = []
    if not samples:
        return events

    median_gap = median_interval_minutes(samples)
    max_gap = (median_gap * 2.5) if median_gap else 60.0

    def add_episode_events(episodes, name):
        for start, _ in episodes:
            events.append((start, name))

    add_episode_events(
        iter_episodes(samples, lambda g: TIR_RANGE[0] <= g <= TIR_RANGE[1], max_gap),
        "TIR_Episode",
    )
    add_episode_events(
        iter_episodes(samples, lambda g: TAR_L1_RANGE[0] <= g <= TAR_L1_RANGE[1], max_gap),
        "TAR_Episode_Level1",
    )
    add_episode_events(
        iter_episodes(samples, lambda g: g > TAR_L2_MIN, max_gap),
        "TAR_Episode_Level2",
    )
    add_episode_events(
        iter_episodes(samples, lambda g: TBR_L1_RANGE[0] <= g <= TBR_L1_RANGE[1], max_gap),
        "TBR_Episode_Level1",
    )
    add_episode_events(
        iter_episodes(samples, lambda g: g < TBR_L2_MAX, max_gap),
        "TBR_Episode_Level2",
    )

    for start, end in iter_episodes(samples, lambda g: g > TIR_RANGE[1], max_gap):
        if episode_duration_minutes(start, end) >= SUSTAINED_MINUTES:
            events.append((start, "Hyperglycemic_Excursion"))

    for start, end in iter_episodes(samples, lambda g: g < TIR_RANGE[0], max_gap):
        if episode_duration_minutes(start, end) >= SUSTAINED_MINUTES:
            events.append((start, "Hypoglycemic_Event"))

    prev_ts = None
    prev_g = None
    for ts, g in samples:
        if prev_ts is not None and prev_g is not None:
            delta = (ts - prev_ts).total_seconds() / 60.0
            if delta > 0 and delta <= max_gap:
                rate = (g - prev_g) / delta
                if rate >= RAPID_RATE_THRESHOLD:
                    events.append((ts, "Rapid_Glucose_Rise"))
                elif rate <= -RAPID_RATE_THRESHOLD:
                    events.append((ts, "Rapid_Glucose_Fall"))
        prev_ts = ts
        prev_g = g

    overnight_samples = [
        (ts, g)
        for ts, g in samples
        if OVERNIGHT_START <= ts.time() <= OVERNIGHT_END
    ]
    add_episode_events(
        iter_episodes(overnight_samples, lambda g: g > TIR_RANGE[1], max_gap),
        "Overnight_Hyperglycemia",
    )

    window = deque()
    hv_active = False
    prev_ts = None
    for ts, g in samples:
        if prev_ts is not None:
            gap = (ts - prev_ts).total_seconds() / 60.0
            if gap > max_gap:
                window.clear()
                hv_active = False
        window.append((ts, g))
        while window and (ts - window[0][0]).total_seconds() / 60.0 > HV_WINDOW_MINUTES:
            window.popleft()

        if len(window) >= 3:
            values = [val for _, val in window]
            mean = statistics.fmean(values)
            if mean > 0:
                cv = statistics.pstdev(values) / mean * 100.0
                if cv >= HV_CV_THRESHOLD:
                    if not hv_active:
                        events.append((ts, "High_Variability_Window"))
                    hv_active = True
                else:
                    hv_active = False
            else:
                hv_active = False
        else:
            hv_active = False
        prev_ts = ts

    return events


def write_events(path, events):
    events.sort(key=lambda item: (item[0], item[1]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "event"])
        for ts, event in events:
            writer.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), event])


def main():
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Detect CGM events per subject.")
    parser.add_argument(
        "--input-root",
        type=Path,
        default=repo_root / "mergedataPCU" / "output" / "cg_augmented",
        help="Path to cg_augmented folder.",
    )
    parser.add_argument(
        "--output-name",
        default="cg_events.csv",
        help="Filename for event output in each subject folder.",
    )
    args = parser.parse_args()

    input_root = args.input_root
    for subject_dir in sorted(p for p in input_root.iterdir() if p.is_dir()):
        csv_paths = [p for p in subject_dir.rglob("*.csv") if csv_has_cgm(p)]
        if not csv_paths:
            continue
        samples = load_samples(csv_paths)
        if not samples:
            continue
        events = detect_events(samples)
        if not events:
            continue
        output_path = subject_dir / args.output_name
        write_events(output_path, events)


if __name__ == "__main__":
    main()
