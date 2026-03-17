import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path


def parse_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def bounded(value, low, high):
    return max(low, min(high, value))


def minute_noise(minute_of_day, offset, amplitude):
    seed = (minute_of_day * 37 + offset * 17 + 11) % 1000
    ratio = seed / 999.0
    return (ratio * 2.0 - 1.0) * amplitude


def shift_epoch_ms(raw, offset_days, minute_shift=0):
    value = parse_float(raw)
    if value is None:
        return raw
    shifted = value + offset_days * 86400000 + minute_shift * 60000
    return str(int(round(shifted)))


def shift_dt_text(raw, offset_days):
    text = str(raw or "").strip()
    if not text:
        return raw
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return raw
    return (dt + timedelta(days=offset_days)).strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path):
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return reader.fieldnames or [], rows


def write_csv(path, fieldnames, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def unique_participant_dates(rows, participant):
    dates = set()
    for row in rows:
        if row.get("participant") != participant:
            continue
        ts = (row.get("cg_timestamp") or "").strip()
        if ts:
            dates.add(ts[:10])
    return dates


def augment_activity_rows(activity_rows, participant, target_days):
    existing_dates = unique_participant_dates(activity_rows, participant)
    if len(existing_dates) >= target_days:
        return activity_rows, 0

    base_date = min(existing_dates)
    template = [
        row
        for row in activity_rows
        if row.get("participant") == participant and (row.get("cg_timestamp") or "").startswith(base_date)
    ]
    if not template:
        return activity_rows, 0

    base_dt = datetime.strptime(base_date, "%Y-%m-%d")
    desired_dates = [(base_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(target_days)]
    offsets = []
    for i, day_str in enumerate(desired_dates):
        if i == 0:
            continue
        if day_str not in existing_dates:
            offsets.append(i)

    if not offsets:
        return activity_rows, 0

    day_glucose_bias = [-0.06, -0.02, 0.01, 0.04, 0.08, -0.01, 0.03]
    day_activity_scale = [0.94, 1.01, 1.07, 0.9, 1.03, 1.1, 0.97]
    meal_day_bias = [-0.08, 0.0, 0.07, -0.04, 0.11, -0.02, 0.05]
    meal_type_bias = {"breakfast": 0.0, "lunch": 0.03, "dinner": 0.05, "snack": -0.04, "meal": 0.0}

    generated = []
    for offset in offsets:
        for row in template:
            new_row = dict(row)
            old_ts = datetime.strptime(row["cg_timestamp"], "%Y-%m-%d %H:%M:%S")
            new_ts = old_ts + timedelta(days=offset)
            minute_of_day = new_ts.hour * 60 + new_ts.minute
            g_bias = day_glucose_bias[(offset - 1) % len(day_glucose_bias)]
            a_scale = day_activity_scale[(offset - 1) % len(day_activity_scale)]

            met = parse_float(row.get("activity_met_1min"))
            met_value = met if met is not None else 1.0
            met_noise = minute_noise(minute_of_day, offset, 0.12)
            new_met = bounded(met_value * a_scale + met_noise, 0.4, 12.0)
            if met is not None:
                new_row["activity_met_1min"] = f"{new_met:.1f}"

            hr = parse_float(row.get("cg_HR"))
            if hr is not None:
                hr_noise = minute_noise(minute_of_day + 17, offset, 2.7)
                new_row["cg_HR"] = f"{bounded(hr + g_bias * 22 + hr_noise, 45, 170):.1f}"

            for field in ("cg_Dexcom GL", "cg_Libre GL"):
                glucose = parse_float(row.get(field))
                if glucose is None:
                    continue
                circadian = 0.02 if (new_ts.hour >= 20 or new_ts.hour < 6) else (0.01 if 11 <= new_ts.hour < 14 else -0.004)
                activity_pull = -min(0.04, max(0.0, new_met - 2.5) * 0.012)
                noise = minute_noise(minute_of_day + 29, offset, 0.015)
                adjusted = bounded(glucose * (1 + g_bias + circadian + activity_pull + noise), 55.0, 320.0)
                new_row[field] = f"{adjusted:.1f}"

            meal_type = (row.get("cg_Meal Type") or "").strip()
            carbs = parse_float(row.get("cg_Carbs"))
            if meal_type and carbs is not None and carbs > 0:
                key = meal_type.lower()
                scale = 1 + meal_type_bias.get(key, 0.0) + meal_day_bias[(offset - 1) % len(meal_day_bias)]
                new_carbs = bounded(carbs * scale, 4.0, 140.0)
                new_row["cg_Carbs"] = f"{new_carbs:.1f}"

                calories = parse_float(row.get("cg_Calories"))
                if calories is not None and calories > 0:
                    new_row["cg_Calories"] = f"{bounded(calories * (new_carbs / carbs), 30.0, 1500.0):.1f}"
                for macro in ("cg_Protein", "cg_Fat", "cg_Fiber"):
                    macro_val = parse_float(row.get(macro))
                    if macro_val is not None and macro_val > 0:
                        new_row[macro] = f"{bounded(macro_val * (new_carbs / carbs), 0.1, 300.0):.1f}"

            new_row["cg_timestamp"] = new_ts.strftime("%Y-%m-%d %H:%M:%S")
            new_row["cg_date"] = new_ts.strftime("%Y-%m-%d")
            if (new_row.get("lon_date") or "").strip():
                new_row["lon_date"] = new_ts.strftime("%Y-%m-%d")
            if (new_row.get("lon_timestamp") or "").strip():
                new_row["lon_timestamp"] = shift_dt_text(new_row.get("lon_timestamp"), offset)
            if (new_row.get("timestamp") or "").strip():
                new_row["timestamp"] = shift_epoch_ms(new_row.get("timestamp"), offset)

            generated.append(new_row)

    return activity_rows + generated, len(generated)


def augment_sleep_rows(sleep_rows, participant, target_days):
    participant_rows = [row for row in sleep_rows if row.get("participant") == participant]
    if not participant_rows:
        return sleep_rows, 0

    existing_dates = {((row.get("cg_date") or row.get("date") or "").strip()) for row in participant_rows}
    existing_dates.discard("")
    if len(existing_dates) >= target_days:
        return sleep_rows, 0

    base_date = min(existing_dates)
    template = [
        row
        for row in participant_rows
        if (row.get("cg_date") or row.get("date") or "").strip() == base_date
    ]
    if not template:
        template = [participant_rows[0]]

    base_dt = datetime.strptime(base_date, "%Y-%m-%d")
    desired_dates = [(base_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(target_days)]
    offsets = []
    for i, day_str in enumerate(desired_dates):
        if i == 0:
            continue
        if day_str not in existing_dates:
            offsets.append(i)

    if not offsets:
        return sleep_rows, 0

    score_shift = [-4, 2, 5, -6, 3, 1, -2]
    duration_shift_min = [-42, 15, 28, -55, 22, -10, 12]
    bedtime_shift_min = [-25, 10, 20, -35, 15, -5, 12]

    generated = []
    for offset in offsets:
        for row in template:
            new_row = dict(row)
            new_date = (base_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
            day_idx = (offset - 1) % len(score_shift)

            new_row["cg_date"] = new_date
            if (new_row.get("date") or "").strip():
                new_row["date"] = new_date
            if (new_row.get("lon_date") or "").strip():
                new_row["lon_date"] = new_date

            score = parse_float(row.get("sleep_score"))
            if score is not None:
                new_row["sleep_score"] = f"{bounded(score + score_shift[day_idx], 55.0, 96.0):.1f}"

            duration = parse_float(row.get("sleep_duration"))
            if duration is not None:
                shifted = bounded(duration + duration_shift_min[day_idx] * 60, 18000.0, 42000.0)
                new_row["sleep_duration"] = f"{shifted:.1f}"

            awake = parse_float(row.get("sleep_awake"))
            if awake is not None:
                awake_shift = -duration_shift_min[day_idx] * 20
                new_row["sleep_awake"] = f"{bounded(awake + awake_shift, 1200.0, 9000.0):.1f}"

            for field in ("sleep_total", "sleep_light", "sleep_rem", "sleep_deep"):
                value = parse_float(row.get(field))
                if value is None:
                    continue
                scale = 1 + score_shift[day_idx] * 0.003
                new_row[field] = f"{bounded(value * scale, 600.0, 43000.0):.1f}"

            minute_shift = bedtime_shift_min[day_idx]
            for delta_field in ("sleep_bedtime_start_delta", "sleep_bedtime_end_delta", "sleep_midpoint_at_delta"):
                delta_val = parse_float(row.get(delta_field))
                if delta_val is None:
                    continue
                new_row[delta_field] = f"{(delta_val + minute_shift * 60) % 86400:.1f}"

            if (new_row.get("timestamp") or "").strip():
                new_row["timestamp"] = shift_epoch_ms(new_row.get("timestamp"), offset)

            for epoch_field in ("sleep_bedtime_start", "sleep_bedtime_end", "sleep_timestamp"):
                epoch_val = parse_float(new_row.get(epoch_field))
                if epoch_val is None:
                    continue
                if epoch_val > 1e11:
                    new_row[epoch_field] = f"{epoch_val + offset * 86400000 + minute_shift * 60000:.1f}"

            generated.append(new_row)

    return sleep_rows + generated, len(generated)


def ensure_backup(path):
    backup = path.with_suffix(path.suffix + ".bak.before_week_aug")
    if not backup.exists():
        backup.write_bytes(path.read_bytes())
    return backup


def main():
    parser = argparse.ArgumentParser(description="Synthesize participant objective data to one-week coverage.")
    parser.add_argument("--dataset-root", required=True, help="Path to dataset root folder (e.g., CGMacros-015).")
    parser.add_argument("--participant", default="pers2019", help="Participant id to augment.")
    parser.add_argument("--target-days", type=int, default=7, help="Target day coverage.")
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    activity_path = dataset_root / "Oura" / "activity_1min.csv"
    sleep_path = dataset_root / "Oura" / "sleep_daily.csv"
    if not activity_path.exists() or not sleep_path.exists():
        raise FileNotFoundError("Expected Oura/activity_1min.csv and Oura/sleep_daily.csv under dataset root.")

    ensure_backup(activity_path)
    ensure_backup(sleep_path)

    activity_fields, activity_rows = read_csv(activity_path)
    sleep_fields, sleep_rows = read_csv(sleep_path)

    augmented_activity, added_activity = augment_activity_rows(activity_rows, args.participant, args.target_days)
    augmented_sleep, added_sleep = augment_sleep_rows(sleep_rows, args.participant, args.target_days)

    write_csv(activity_path, activity_fields, augmented_activity)
    write_csv(sleep_path, sleep_fields, augmented_sleep)

    dates = sorted(unique_participant_dates(augmented_activity, args.participant))
    print(f"participant={args.participant}")
    print(f"added_activity_rows={added_activity}")
    print(f"added_sleep_rows={added_sleep}")
    print(f"covered_days={len(dates)}")
    if dates:
        print(f"date_range={dates[0]} -> {dates[-1]}")


if __name__ == "__main__":
    main()
