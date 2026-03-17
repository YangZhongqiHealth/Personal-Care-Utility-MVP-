import csv
import json
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

MEAL_TYPES = {"Breakfast", "Lunch", "Dinner", "Snack"}
WINDOW_MINUTES = list(range(-30, 181))
WINDOW_SIZE = len(WINDOW_MINUTES)

LAYER_EVENT = "Event Extraction & Personiclie Engine"
LAYER_STATE = "State Estimation Module"
LAYER_CONTEXT = "Contextual Inference Engine"
LAYER_KB = "Knowledge Base"
LAYER_GUIDANCE = "Guidance Generator"
LAYER_ORCH = "Orchestration Layer"
LAYER_GUARDIAN = "Guardian Agent"
LAYER_INTERFACE = "Interfacing Layer"

DATA_OBJECTIVE = "Objective Data"
DATA_SUBJECTIVE = "Subjective Data"
DATA_INFERRED = "Inferred Data"
DATA_CONVERSATION = "Conversation Aquired Data"
GUIDELINE_KB_PATH = Path(__file__).resolve().parent / "knowledge" / "diabetes_guidelines.json"
AGENT_DIABETES = "Diabetes Agent"
AGENT_SLEEP = "Sleep Expert Agent"
AGENT_WELLNESS = "Wellness Agent"
AGENT_MEDICAL = "Medical Agent"

ACTIONABLE_GLUCOSE_STATES = {
    "TAR_State_Level1",
    "TAR_State_Level2",
    "TBR_State_Level1",
    "TBR_State_Level2",
    "Hyperglycemic_State",
    "Hypoglycemic_State",
    "Rapid_Glucose_Rise_State",
    "Rapid_Glucose_Fall_State",
}

STATE_DEFS = {
    "TIR_State": {
        "glycemic_zone": "TIR",
        "severity": None,
        "clinical_meaning": "Desired glycemic control",
    },
    "TAR_State_Level1": {
        "glycemic_zone": "TAR",
        "severity": "Level1",
        "clinical_meaning": "Mild to moderate hyperglycemia",
    },
    "TAR_State_Level2": {
        "glycemic_zone": "TAR",
        "severity": "Level2",
        "clinical_meaning": "Severe hyperglycemia",
    },
    "TBR_State_Level1": {
        "glycemic_zone": "TBR",
        "severity": "Level1",
        "clinical_meaning": "Mild hypoglycemia",
    },
    "TBR_State_Level2": {
        "glycemic_zone": "TBR",
        "severity": "Level2",
        "clinical_meaning": "Clinically significant hypoglycemia",
    },
    "Hyperglycemic_State": {
        "glycemic_zone": "TAR",
        "severity": None,
        "clinical_meaning": "Actionable glucose spike",
    },
    "Hypoglycemic_State": {
        "glycemic_zone": "TBR",
        "severity": None,
        "clinical_meaning": "Acute safety risk",
    },
    "Rapid_Glucose_Rise_State": {
        "glycemic_zone": None,
        "severity": None,
        "clinical_meaning": "Rapid upward glucose trend",
    },
    "Rapid_Glucose_Fall_State": {
        "glycemic_zone": None,
        "severity": None,
        "clinical_meaning": "Rapid downward glucose trend",
    },
}


def load_guideline_kb():
    if not GUIDELINE_KB_PATH.exists():
        return []
    with GUIDELINE_KB_PATH.open() as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        return []
    return data


def select_guidelines(guideline_kb, tags, limit=2):
    if not guideline_kb:
        return []
    tag_set = set(tags or [])
    scored = []
    for entry in guideline_kb:
        entry_tags = set(entry.get("tags", []))
        overlap = len(entry_tags.intersection(tag_set))
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda item: (-item[0], item[1].get("id", "")))
    return [entry for _, entry in scored[:limit]]


def format_kb_output(context_label, guideline_kb, tags):
    selected = select_guidelines(guideline_kb, tags)
    if not selected:
        return f"{context_label}\nSources: local KB unavailable"
    lines = [context_label, "Sources:"]
    for entry in selected:
        lines.append(f"- {entry.get('id')}: {entry.get('title')}")
    return "\n".join(lines)


def parse_float(value):
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_dt(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def parse_day(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def to_iso(ts):
    return ts.replace(microsecond=0).isoformat()


def epoch_to_dt(epoch_value):
    if epoch_value is None:
        return None
    seconds = epoch_value / 1000 if epoch_value > 1e11 else epoch_value
    if seconds < 946684800:  # 2000-01-01
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)


def safe_seconds_of_day(value):
    if value is None:
        return None
    seconds = int(round(value))
    if 0 <= seconds < 86400:
        return seconds
    return None


def normalize_bedtime_seconds(seconds):
    if seconds is None:
        return None
    seconds = seconds % 86400
    if seconds >= 18 * 3600:
        return seconds
    if seconds <= 12 * 3600:
        # Several aligned rows encode evening bedtime in morning-hour offset.
        return seconds + 12 * 3600
    return None


def build_data_channels(objective=None, subjective=None, inferred=None, conversation=None):
    return {
        DATA_OBJECTIVE: objective or [],
        DATA_SUBJECTIVE: subjective or [],
        DATA_INFERRED: inferred or [],
        DATA_CONVERSATION: conversation or [],
    }


def load_meal_participants(activity_path):
    counts = {}
    with activity_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            meal_type = row.get("cg_Meal Type", "").strip()
            if meal_type:
                participant = row.get("participant")
                counts[participant] = counts.get(participant, 0) + 1
    if not counts:
        raise ValueError("No meal entries found in activity_1min.csv.")
    return max(counts.items(), key=lambda item: item[1])[0]


def load_activity(activity_path, participant):
    by_ts = {}
    with activity_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("participant") != participant:
                continue
            ts = parse_dt(row["cg_timestamp"])
            glucose = parse_float(row.get("cg_Dexcom GL"))
            if glucose is None:
                glucose = parse_float(row.get("cg_Libre GL"))
            met = parse_float(row.get("activity_met_1min"))
            meal_type_raw = row.get("cg_Meal Type", "").strip()
            meal_type = meal_type_raw if meal_type_raw in MEAL_TYPES else ("Meal" if meal_type_raw else None)
            carbs = parse_float(row.get("cg_Carbs")) or 0.0
            image_path = row.get("cg_Image path", "").strip()

            entry = by_ts.get(ts)
            if entry is None:
                entry = {
                    "timestamp": ts,
                    "glucose": glucose,
                    "met": met if met is not None else 0.0,
                    "meal_type": meal_type,
                    "carbs_g": carbs,
                    "image_path": image_path,
                }
                by_ts[ts] = entry
                continue

            if glucose is not None:
                entry["glucose"] = glucose
            if met is not None:
                entry["met"] = met
            if meal_type:
                entry["meal_type"] = meal_type
                entry["carbs_g"] = carbs
                entry["image_path"] = image_path

    stream = sorted(by_ts.values(), key=lambda item: item["timestamp"])

    meals = []
    seen = set()
    for entry in stream:
        if not entry["meal_type"]:
            continue
        key = (
            entry["timestamp"],
            entry["meal_type"],
            round(entry["carbs_g"], 1),
            entry["image_path"],
        )
        if key in seen:
            continue
        seen.add(key)
        meals.append(
            {
                "meal_time": entry["timestamp"],
                "meal_type": entry["meal_type"],
                "carbs_g": entry["carbs_g"],
                "image_path": entry["image_path"],
            }
        )
    return stream, by_ts, meals


def load_sleep(sleep_path, participant):
    records = []
    with sleep_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("participant") != participant:
                continue

            cg_day = parse_day(row.get("cg_date")) or parse_day(row.get("date"))
            sleep_score = parse_float(row.get("sleep_score"))
            duration_sec = parse_float(row.get("sleep_duration"))

            wake_delta = safe_seconds_of_day(parse_float(row.get("sleep_bedtime_end_delta")))
            bed_delta = normalize_bedtime_seconds(safe_seconds_of_day(parse_float(row.get("sleep_bedtime_start_delta"))))

            bed_end_epoch = epoch_to_dt(parse_float(row.get("sleep_bedtime_end")))
            bed_start_epoch = epoch_to_dt(parse_float(row.get("sleep_bedtime_start")))

            if wake_delta is None and bed_end_epoch is not None:
                wake_delta = bed_end_epoch.hour * 3600 + bed_end_epoch.minute * 60 + bed_end_epoch.second
            if bed_delta is None and bed_start_epoch is not None:
                bed_delta = normalize_bedtime_seconds(
                    bed_start_epoch.hour * 3600 + bed_start_epoch.minute * 60 + bed_start_epoch.second
                )
            if bed_delta is None and wake_delta is not None and duration_sec is not None:
                bed_delta = normalize_bedtime_seconds(int((wake_delta - duration_sec) % 86400))

            records.append(
                {
                    "cg_day": cg_day,
                    "sleep_score": sleep_score,
                    "wake_seconds": wake_delta,
                    "bed_seconds": bed_delta,
                    "duration_sec": duration_sec,
                }
            )

    records.sort(key=lambda item: item["cg_day"] or date.min)
    return records


def prior_sleep_record(sleep_records, day_value):
    latest = None
    for record in sleep_records:
        record_day = record.get("cg_day")
        if record_day is None:
            continue
        if record_day <= day_value:
            latest = record
        else:
            break
    return latest


def infer_sleep_rhythm(sleep_records):
    wake_seconds = [record["wake_seconds"] for record in sleep_records if record.get("wake_seconds") is not None]
    bed_seconds = [record["bed_seconds"] for record in sleep_records if record.get("bed_seconds") is not None]

    inferred_wake = int(statistics.median(wake_seconds)) if wake_seconds else 7 * 3600
    inferred_bed = int(statistics.median(bed_seconds)) if bed_seconds else 22 * 3600

    # Ensure bedtime stays in evening for reminder use.
    if inferred_bed < 18 * 3600:
        inferred_bed = 22 * 3600

    return {
        "wake_seconds": inferred_wake,
        "bed_seconds": inferred_bed,
    }


def bounded(value, low, high):
    return max(low, min(high, value))


def activity_features_for_day(stream, day_value):
    day_points = [point for point in stream if point["timestamp"].date() == day_value]
    if not day_points:
        return {
            "morning_avg_met": 0.0,
            "day_avg_met": 0.0,
            "afternoon_low_activity_ratio": 1.0,
            "day_active_minutes": 0,
        }

    morning_mets = [point.get("met") or 0.0 for point in day_points if 6 <= point["timestamp"].hour < 11]
    day_mets = [point.get("met") or 0.0 for point in day_points if 9 <= point["timestamp"].hour < 20]
    afternoon_points = [point for point in day_points if 13 <= point["timestamp"].hour < 18]

    morning_avg_met = statistics.mean(morning_mets) if morning_mets else 0.0
    day_avg_met = statistics.mean(day_mets) if day_mets else 0.0
    day_active_minutes = sum(1 for point in day_points if (point.get("met") or 0.0) >= 2.0)
    if afternoon_points:
        low_count = sum(1 for point in afternoon_points if (point.get("met") or 0.0) < 1.3)
        afternoon_low_activity_ratio = low_count / len(afternoon_points)
    else:
        afternoon_low_activity_ratio = 1.0

    return {
        "morning_avg_met": morning_avg_met,
        "day_avg_met": day_avg_met,
        "afternoon_low_activity_ratio": afternoon_low_activity_ratio,
        "day_active_minutes": day_active_minutes,
    }


def loneliness_level_from_score(score):
    if score >= 0.72:
        return "High"
    if score >= 0.46:
        return "Moderate"
    return "Low"


def compute_loneliness_profile(day_value, stream, sleep_records):
    features = activity_features_for_day(stream, day_value)
    prior_sleep = prior_sleep_record(sleep_records, day_value)
    sleep_score = None if prior_sleep is None else prior_sleep.get("sleep_score")

    score = 0.2
    if sleep_score is None:
        score += 0.08
    elif sleep_score < 65:
        score += 0.3
    elif sleep_score < 75:
        score += 0.16

    if features["morning_avg_met"] < 1.2:
        score += 0.16
    elif features["morning_avg_met"] < 1.5:
        score += 0.08

    if features["day_active_minutes"] < 30:
        score += 0.24
    elif features["day_active_minutes"] < 60:
        score += 0.12

    if features["afternoon_low_activity_ratio"] > 0.8:
        score += 0.18
    elif features["afternoon_low_activity_ratio"] > 0.65:
        score += 0.1

    if features["day_avg_met"] < 1.4:
        score += 0.1

    score = bounded(score, 0.05, 0.98)
    return {
        "score": round(score, 2),
        "level": loneliness_level_from_score(score),
        "sleep_score": sleep_score,
        "morning_avg_met": round(features["morning_avg_met"], 2),
        "day_avg_met": round(features["day_avg_met"], 2),
        "day_active_minutes": int(features["day_active_minutes"]),
        "afternoon_low_activity_ratio": round(features["afternoon_low_activity_ratio"], 2),
    }


def classify_glucose_state(glucose):
    if glucose is None:
        return None
    if glucose < 54:
        return "TBR_State_Level2"
    if glucose < 70:
        return "TBR_State_Level1"
    if glucose <= 180:
        return "TIR_State"
    if glucose <= 250:
        return "TAR_State_Level1"
    return "TAR_State_Level2"


def build_window(by_ts, meal_time):
    points = []
    for minute in WINDOW_MINUTES:
        ts = meal_time + timedelta(minutes=minute)
        entry = by_ts.get(ts)
        if entry and entry["glucose"] is not None:
            points.append((minute, entry["glucose"], entry["met"]))

    completeness = len(points) / WINDOW_SIZE
    baseline_values = [g for m, g, _ in points if -30 <= m < 0]
    peak_values = [g for m, g, _ in points if 0 <= m <= 180]
    if not baseline_values or not peak_values:
        return None

    baseline = statistics.mean(baseline_values)
    peak = max(peak_values)
    time_to_peak = None
    for minute, glucose, _ in points:
        if 0 <= minute <= 180 and glucose == peak:
            time_to_peak = minute
            break

    post_meal_activity = sum(met for minute, _, met in points if 0 <= minute <= 120)
    g45_entry = by_ts.get(meal_time + timedelta(minutes=45))

    return {
        "points": points,
        "baseline": baseline,
        "peak": peak,
        "delta": peak - baseline,
        "time_to_peak": time_to_peak,
        "post_meal_activity": post_meal_activity,
        "completeness": completeness,
        "glucose_at_45": None if g45_entry is None else g45_entry["glucose"],
    }


def bucket_carbs(carbs):
    return int(round(carbs / 10.0) * 10)


def compute_group_stats(meals):
    grouped = {}
    for meal in meals:
        key = (meal["meal_type"], meal["carb_bucket"])
        grouped.setdefault(key, []).append(meal)

    stats = {}
    all_sleep_scores = [meal["sleep_score"] for meal in meals if meal.get("sleep_score") is not None]
    sleep_median = statistics.median(all_sleep_scores) if all_sleep_scores else None

    for key, items in grouped.items():
        deltas = [meal["delta_glucose"] for meal in items]
        carbs = [meal["carbs_g"] for meal in items]
        spikes = [meal["spike_label"] for meal in items]
        avg_delta = statistics.mean(deltas) if deltas else 0.0
        spike_prob = sum(1 for spike in spikes if spike) / len(spikes) if spikes else 0.0

        active = [meal["delta_glucose"] for meal in items if meal["post_meal_activity"] >= 30]
        inactive = [meal["delta_glucose"] for meal in items if meal["post_meal_activity"] < 30]
        activity_effect = None
        if len(active) >= 2 and len(inactive) >= 2:
            activity_effect = statistics.mean(inactive) - statistics.mean(active)

        sleep_effect = None
        if sleep_median is not None:
            good = [
                meal["delta_glucose"]
                for meal in items
                if meal.get("sleep_score") is not None and meal["sleep_score"] >= sleep_median
            ]
            poor = [
                meal["delta_glucose"]
                for meal in items
                if meal.get("sleep_score") is not None and meal["sleep_score"] < sleep_median
            ]
            if len(good) >= 2 and len(poor) >= 2:
                sleep_effect = statistics.mean(poor) - statistics.mean(good)

        stats[key] = {
            "count": len(items),
            "avg_delta": avg_delta,
            "spike_prob": spike_prob,
            "activity_effect": activity_effect,
            "sleep_effect": sleep_effect,
            "carb_median": statistics.median(carbs) if carbs else 0.0,
        }
    return stats, sleep_median


def compute_late_dinner_effect(meals):
    dinners = [meal for meal in meals if meal["meal_type"] == "Dinner"]
    if not dinners:
        return None
    early = [meal["delta_glucose"] for meal in dinners if meal["meal_time"].hour < 20]
    late = [meal["delta_glucose"] for meal in dinners if meal["meal_time"].hour >= 20]
    if len(early) >= 2 and len(late) >= 2:
        return statistics.mean(late) - statistics.mean(early)
    return None


def recommend_for_meal(meal, group_stats, late_dinner_effect):
    key = (meal["meal_type"], meal["carb_bucket"])
    stats = group_stats.get(key)
    if stats is None or meal["confidence"] < 0.7:
        return None

    if stats["activity_effect"] is not None and stats["activity_effect"] >= 10 and meal["post_meal_activity"] < 30:
        return {
            "type": "post_meal_walk",
            "text": "Try a 10-15 min walk after this meal.",
            "expected_reduction": stats["activity_effect"],
        }

    if meal["carbs_g"] >= stats["carb_median"] and meal["delta_glucose"] >= stats["avg_delta"]:
        return {
            "type": "reduce_carbs",
            "text": "You could try slightly smaller carbs at this meal.",
            "expected_reduction": max(10.0, stats["avg_delta"] * 0.2),
        }

    if (
        meal["meal_type"] == "Dinner"
        and meal["meal_time"].hour >= 20
        and late_dinner_effect is not None
        and late_dinner_effect >= 10
    ):
        return {
            "type": "shift_earlier",
            "text": "If possible, try shifting dinner a bit earlier.",
            "expected_reduction": late_dinner_effect,
        }

    if stats["sleep_effect"] is not None and stats["sleep_effect"] >= 10:
        return {
            "type": "sleep_support",
            "text": "On lower-sleep nights, consider a gentler meal or a walk.",
            "expected_reduction": stats["sleep_effect"],
        }

    return None


def meal_counterfactual_projection(meal, group_stats):
    stats = group_stats.get((meal["meal_type"], meal["carb_bucket"]), {})
    baseline = meal["baseline_glucose"]
    observed_peak = meal["peak_glucose"]
    observed_delta = max(0.0, meal["delta_glucose"])

    carb_reduction = min(30.0, max(8.0, meal["carbs_g"] * 0.22))
    activity_effect = stats.get("activity_effect")
    walk_reduction = max(0.0, activity_effect if activity_effect is not None else 10.0)
    combined_reduction = min(observed_delta * 0.8, carb_reduction + walk_reduction)

    estimated_delta = max(0.0, observed_delta - combined_reduction)
    estimated_peak = baseline + estimated_delta
    confidence = 0.65 if stats.get("count", 0) >= 2 else 0.45

    return {
        "scenario": "20g fewer carbs + 15-minute post-meal walk",
        "observed_peak_mg_dL": round(observed_peak, 1),
        "estimated_peak_mg_dL": round(estimated_peak, 1),
        "estimated_delta_mg_dL": round(estimated_delta, 1),
        "estimated_change_mg_dL": round(observed_peak - estimated_peak, 1),
        "confidence": round(confidence, 2),
    }


def state_guidance_for_diabetes(state_name):
    guidance = {
        "TAR_State_Level1": "Consider hydration, a brief walk, and monitor your glucose trend.",
        "TAR_State_Level2": "High glucose risk detected. Follow your care plan and monitor closely.",
        "TBR_State_Level1": "Mild low glucose detected. Consider a quick carbohydrate correction.",
        "TBR_State_Level2": "Significant low glucose risk. Take immediate corrective action per your plan.",
        "Hyperglycemic_State": "Hyperglycemia detected. Consider corrective action and monitor closely.",
        "Hypoglycemic_State": "Hypoglycemia detected. Prioritize immediate safety actions.",
        "Rapid_Glucose_Rise_State": "Rapid rise detected. Consider movement and portion adjustments.",
        "Rapid_Glucose_Fall_State": "Rapid drop detected. Monitor closely and prepare a correction.",
    }
    return guidance.get(state_name, "Glucose-related state detected. Review your care plan guidance.")


def unique_agents(agents):
    seen = []
    for agent in agents or []:
        if agent and agent not in seen:
            seen.append(agent)
    return seen


def format_agent_list(agents):
    if not agents:
        return "no specialist agent"
    if len(agents) == 1:
        return agents[0]
    return ", ".join(agents)


def orchestrator_activation_line(primary_agent, supporting_agents, context):
    agents = unique_agents(([primary_agent] if primary_agent else []) + list(supporting_agents or []))
    if not agents:
        return f"Multi Agent Orchestrator monitoring only ({context})"
    return f"Multi Agent Orchestrator activated {format_agent_list(agents)} ({context})"


def build_decision(
    confidence,
    intervention_available,
    primary_agent=None,
    supporting_agents=None,
    trigger_reason=None,
    escalation_level="none",
    next_check_minutes=None,
    extra=None,
):
    agents = unique_agents(([primary_agent] if primary_agent else []) + list(supporting_agents or []))
    selected_agent = primary_agent if primary_agent else (agents[0] if agents else None)
    decision = {
        "confidence": round(confidence, 2),
        "intervention_available": bool(intervention_available),
        "selected_agent": selected_agent,
        "selected_agents": agents,
        "escalation_level": escalation_level,
    }
    if trigger_reason:
        decision["trigger_reason"] = trigger_reason
    if next_check_minutes is not None:
        decision["next_check_minutes"] = int(next_check_minutes)
    if extra:
        decision.update(extra)
    return decision


def apply_guardian_review(activated, outputs, state_snapshot, decision_snapshot, user_output):
    activated = list(activated or [])
    outputs = dict(outputs or {})
    state_snapshot = dict(state_snapshot or {})
    decision_snapshot = dict(decision_snapshot or {})
    safe_user_output = dict(user_output) if isinstance(user_output, dict) else user_output

    if LAYER_INTERFACE not in activated:
        activated.append(LAYER_INTERFACE)
    if LAYER_GUARDIAN not in activated:
        idx = activated.index(LAYER_INTERFACE)
        activated.insert(idx, LAYER_GUARDIAN)

    if LAYER_INTERFACE not in outputs:
        outputs[LAYER_INTERFACE] = "Monitoring update prepared for interface delivery"

    selected_agents = decision_snapshot.get("selected_agents") or []
    escalation = decision_snapshot.get("escalation_level", "none")
    glucose_value = state_snapshot.get("glucose_mg_dL")
    severe_value = isinstance(glucose_value, (int, float)) and (glucose_value <= 60 or glucose_value >= 280)

    if AGENT_MEDICAL in selected_agents or escalation == "urgent" or severe_value:
        verdict = "Escalate"
        note = "High-risk context detected; urgent safety framing enforced."
    elif decision_snapshot.get("intervention_available"):
        verdict = "Caution"
        note = "Actionable guidance allowed with monitoring and follow-up reminder."
    else:
        verdict = "Pass"
        note = "Monitoring summary cleared for normal display."

    if isinstance(safe_user_output, dict):
        reasons = list(safe_user_output.get("why") or [])
        if verdict == "Escalate":
            if not any("urgent" in str(line).lower() for line in reasons):
                reasons.insert(0, "Safety Keeper flagged this as urgent.")
            try_next_time = str(safe_user_output.get("try_next_time") or "").strip()
            if try_next_time:
                if not try_next_time.lower().startswith("urgent"):
                    safe_user_output["try_next_time"] = f"Urgent safety check: {try_next_time}"
            else:
                safe_user_output["try_next_time"] = "Urgent safety check: follow your care plan now and seek professional support if symptoms persist."
        elif verdict == "Caution":
            if not any("monitor" in str(line).lower() for line in reasons):
                reasons.append("Continue monitoring and follow your care plan if symptoms appear.")
        safe_user_output["why"] = reasons[:3]

    outputs[LAYER_GUARDIAN] = f"Safety verdict: {verdict}. {note}"
    decision_snapshot["guardian_verdict"] = verdict
    decision_snapshot["guardian_note"] = note
    decision_snapshot["guardian_screened"] = True

    return activated, outputs, state_snapshot, decision_snapshot, safe_user_output


def event_template(
    timestamp,
    event_type,
    event_id,
    raw_lines,
    activated,
    outputs,
    state_snapshot,
    decision_snapshot,
    user_output,
    is_event=True,
    personicle_signals=None,
):
    activated, outputs, state_snapshot, decision_snapshot, user_output = apply_guardian_review(
        activated, outputs, state_snapshot, decision_snapshot, user_output
    )
    return {
        "timestamp": to_iso(timestamp),
        "event_type": event_type,
        "is_event": is_event,
        "meal_id": event_id,
        "raw_data_received": raw_lines,
        "data_channels": build_data_channels(objective=raw_lines),
        "activated_components": activated,
        "component_outputs": outputs,
        "state_snapshot": state_snapshot,
        "decision_snapshot": decision_snapshot,
        "user_output": user_output,
        "personicle_signals": personicle_signals or {},
    }


def build_meal_episodes(meals, by_ts, sleep_records, max_meals):
    meal_episodes = []
    for meal in meals:
        window = build_window(by_ts, meal["meal_time"])
        if window is None:
            continue
        raw_entry = by_ts.get(meal["meal_time"])
        sleep_record = prior_sleep_record(sleep_records, meal["meal_time"].date())
        sleep_score = None if sleep_record is None else sleep_record.get("sleep_score")

        meal_episodes.append(
            {
                **meal,
                "carb_bucket": bucket_carbs(meal["carbs_g"]),
                "baseline_glucose": window["baseline"],
                "peak_glucose": window["peak"],
                "delta_glucose": window["delta"],
                "time_to_peak": window["time_to_peak"],
                "post_meal_activity": window["post_meal_activity"],
                "confidence": window["completeness"],
                "spike_label": window["peak"] >= 180,
                "sleep_score": sleep_score,
                "glucose_at_meal": None if raw_entry is None else raw_entry.get("glucose"),
                "met_at_meal": None if raw_entry is None else raw_entry.get("met"),
                "glucose_at_45": window["glucose_at_45"],
            }
        )
    return meal_episodes[:max_meals]


def build_meal_events(meal_episodes, group_stats, sleep_median, late_dinner_effect, guideline_kb):
    events = []
    for idx, meal in enumerate(meal_episodes, start=1):
        meal_id = f"meal-{idx}"
        meal_time = meal["meal_time"]
        meal_label = f"{meal['meal_type']} - {meal_time.strftime('%-I:%M %p')} - {int(round(meal['carbs_g']))}g carbs"
        counterfactual = meal_counterfactual_projection(meal, group_stats)

        meal_raw = [
            f"RAW: cg_timestamp={meal_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"RAW: cg_carbs_g={int(round(meal['carbs_g']))}",
            f"RAW: cg_glucose_mg_dL={int(round(meal['glucose_at_meal'])) if meal.get('glucose_at_meal') is not None else 'NA'}",
            f"RAW: activity_met_1min={round(meal['met_at_meal'], 2) if meal.get('met_at_meal') is not None else 'NA'}",
            f"RAW: sleep_score={int(round(meal['sleep_score'])) if meal.get('sleep_score') is not None else 'NA'}",
            f"RAW: cf_estimated_peak_mg_dL={counterfactual['estimated_peak_mg_dL']}",
            f"RAW: cf_scenario={counterfactual['scenario']}",
        ]

        meal_trigger_reason = []
        primary_agent = None
        supporting_agents = []
        escalation_level = "none"
        if meal["baseline_glucose"] >= 250:
            primary_agent = AGENT_MEDICAL
            supporting_agents = [AGENT_DIABETES]
            escalation_level = "urgent"
            meal_trigger_reason.append("very_high_premeal_glucose")
        elif meal["baseline_glucose"] >= 180:
            primary_agent = AGENT_DIABETES
            supporting_agents = [AGENT_WELLNESS]
            meal_trigger_reason.append("high_premeal_glucose")
        elif meal["carbs_g"] >= 60 or meal["baseline_glucose"] >= 140:
            primary_agent = AGENT_WELLNESS
            meal_trigger_reason.append("elevated_postmeal_risk_profile")

        if meal.get("sleep_score") is not None and meal["sleep_score"] < 70:
            if primary_agent is None:
                primary_agent = AGENT_SLEEP
            elif primary_agent != AGENT_SLEEP:
                supporting_agents.append(AGENT_SLEEP)
            meal_trigger_reason.append("low_prior_sleep_score")

        activated = [LAYER_EVENT, LAYER_STATE, LAYER_CONTEXT]
        outputs = {
            LAYER_EVENT: "Meal episode extracted; personal causal analysis generated meal-level counterfactual",
            LAYER_STATE: "Post-meal baseline state initialized",
            LAYER_CONTEXT: "Context = after meal",
        }
        intervention_available = primary_agent is not None
        decision = build_decision(
            confidence=meal["confidence"],
            intervention_available=intervention_available,
            primary_agent=primary_agent,
            supporting_agents=supporting_agents,
            trigger_reason=", ".join(meal_trigger_reason) if meal_trigger_reason else "routine_meal_monitoring",
            escalation_level=escalation_level,
            next_check_minutes=45,
        )
        user_output = None
        if intervention_available:
            activated.extend([LAYER_ORCH, LAYER_KB, LAYER_GUIDANCE, LAYER_INTERFACE])
            outputs[LAYER_ORCH] = orchestrator_activation_line(primary_agent, supporting_agents, "meal logged")
            outputs[LAYER_KB] = format_kb_output(
                "Meal-start planning guidance applied",
                guideline_kb,
                tags=["post_meal", "diabetes_general", "sleep"],
            )
            outputs[LAYER_GUIDANCE] = "Meal-start proactive guidance composed"
            outputs[LAYER_INTERFACE] = "Meal-start proactive guidance delivered"
            if primary_agent == AGENT_MEDICAL:
                next_step = "Pre-meal glucose is very high. Follow urgent care-plan steps and monitor closely."
            elif primary_agent == AGENT_DIABETES:
                next_step = "Start a conservative meal strategy and add light movement after eating."
            elif primary_agent == AGENT_SLEEP:
                next_step = "Because sleep recovery is low, keep this meal moderate and plan a short post-meal walk."
            else:
                next_step = "Use a balanced portion and plan a 10-15 minute walk after this meal."
            user_output = {
                "title": f"{meal_label} · Meal Start Plan",
                "what_happened": (
                    f"PCU detected a meal start with baseline glucose {meal['baseline_glucose']:.0f} mg/dL "
                    f"and {meal['carbs_g']:.0f}g carbs."
                ),
                "why": [
                    "Early context at meal start improves post-meal glucose outcomes.",
                    "Objective signals indicate this meal deserves proactive guidance.",
                    (
                        f"Counterfactual projection: {counterfactual['scenario']} could shift peak from "
                        f"{counterfactual['observed_peak_mg_dL']:.0f} to ~{counterfactual['estimated_peak_mg_dL']:.0f} mg/dL."
                    ),
                ],
                "try_next_time": next_step,
            }

        events.append(
            event_template(
                timestamp=meal_time,
                event_type="meal_logged",
                event_id=meal_id,
                raw_lines=meal_raw,
                activated=activated,
                outputs=outputs,
                state_snapshot={
                    "baseline_glucose_mg_dL": round(meal["baseline_glucose"], 1),
                    "meal_type": meal["meal_type"],
                    "counterfactual_scenario": counterfactual["scenario"],
                    "counterfactual_observed_peak_mg_dL": counterfactual["observed_peak_mg_dL"],
                    "counterfactual_estimated_peak_mg_dL": counterfactual["estimated_peak_mg_dL"],
                    "counterfactual_estimated_change_mg_dL": counterfactual["estimated_change_mg_dL"],
                },
                decision_snapshot=decision,
                user_output=user_output,
                is_event=True,
                personicle_signals={
                    "personal_causal_analysis": {
                        "triggered": True,
                        "trigger": "meal_logged",
                        "scenario": counterfactual["scenario"],
                        "observed_peak_mg_dL": counterfactual["observed_peak_mg_dL"],
                        "estimated_peak_mg_dL": counterfactual["estimated_peak_mg_dL"],
                        "estimated_change_mg_dL": counterfactual["estimated_change_mg_dL"],
                        "confidence": counterfactual["confidence"],
                    }
                },
            )
        )

        check_time = meal_time + timedelta(minutes=45)
        check_glucose = meal.get("glucose_at_45")
        if check_glucose is not None:
            delta_45 = check_glucose - meal["baseline_glucose"]
            severe_risk = check_glucose >= 250 or check_glucose <= 60
            needs_diabetes_agent = check_glucose >= 160 or delta_45 >= 35 or check_glucose < 70
            needs_wellness_agent = delta_45 >= 20 or meal["carbs_g"] >= 60

            activated = [LAYER_STATE, LAYER_CONTEXT]
            outputs = {
                LAYER_STATE: "45-minute post-meal glucose state updated",
                LAYER_CONTEXT: "Context = post-meal trajectory",
            }
            primary_agent = None
            supporting_agents = []
            escalation_level = "none"
            trigger_parts = []
            if severe_risk:
                primary_agent = AGENT_MEDICAL
                supporting_agents = [AGENT_DIABETES]
                escalation_level = "urgent"
                trigger_parts.append("severe_postmeal_glucose")
            elif needs_diabetes_agent:
                primary_agent = AGENT_DIABETES
                trigger_parts.append("postmeal_glucose_above_target")
            if needs_wellness_agent:
                if primary_agent is None:
                    primary_agent = AGENT_WELLNESS
                elif primary_agent != AGENT_WELLNESS:
                    supporting_agents.append(AGENT_WELLNESS)
                trigger_parts.append("behavioral_lever_available")
            if meal.get("sleep_score") is not None and meal["sleep_score"] < 70 and primary_agent is not None:
                if primary_agent != AGENT_SLEEP:
                    supporting_agents.append(AGENT_SLEEP)
                trigger_parts.append("low_prior_sleep_score")
            intervention_available = primary_agent is not None
            decision = build_decision(
                confidence=meal["confidence"],
                intervention_available=intervention_available,
                primary_agent=primary_agent,
                supporting_agents=supporting_agents,
                trigger_reason=", ".join(trigger_parts) if trigger_parts else "post_meal_monitoring",
                escalation_level=escalation_level,
                next_check_minutes=30,
            )
            user_output = None

            if intervention_available:
                activated.extend([LAYER_ORCH, LAYER_KB, LAYER_GUIDANCE, LAYER_INTERFACE])
                outputs[LAYER_ORCH] = orchestrator_activation_line(primary_agent, supporting_agents, "post-meal check")
                outputs[LAYER_KB] = format_kb_output(
                    "Type II diabetes meal-response guidance applied",
                    guideline_kb,
                    tags=["post_meal", "diabetes_general", "glucose_state", "hypoglycemia"],
                )
                outputs[LAYER_GUIDANCE] = "Post-meal intervention nudge composed"
                outputs[LAYER_INTERFACE] = "Post-meal alert delivered"
                if primary_agent == AGENT_MEDICAL:
                    recommendation = "Post-meal glucose is in a severe range. Follow urgent care-plan actions now."
                elif primary_agent == AGENT_DIABETES:
                    recommendation = "Take a 10-15 minute walk and re-check trend in 30-60 minutes."
                else:
                    recommendation = "Use light movement and hydration to blunt the post-meal rise."
                user_output = {
                    "title": f"{meal_label} · Post-Meal Check",
                    "what_happened": (
                        f"45 minutes after this meal, glucose reached {check_glucose:.0f} mg/dL "
                        f"(change {delta_45:+.0f} mg/dL from baseline)."
                    ),
                    "why": [
                        "Early post-meal trajectory predicts later glucose risk.",
                        "Prompt intervention can reduce the upcoming peak.",
                    ],
                    "try_next_time": recommendation,
                }

            check_raw = [
                f"RAW: cg_timestamp={check_time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"RAW: cg_glucose_mg_dL={int(round(check_glucose))}",
                f"RAW: delta_from_baseline={round(delta_45, 1)}",
            ]

            events.append(
                event_template(
                    timestamp=check_time,
                    event_type="post_meal_check",
                    event_id=f"{meal_id}-check",
                    raw_lines=check_raw,
                    activated=activated,
                    outputs=outputs,
                    state_snapshot={
                        "baseline_glucose_mg_dL": round(meal["baseline_glucose"], 1),
                        "glucose_45min_mg_dL": round(check_glucose, 1),
                        "delta_45min_mg_dL": round(delta_45, 1),
                    },
                    decision_snapshot=decision,
                    user_output=user_output,
                    is_event=False,
                )
            )

        time_to_peak = meal.get("time_to_peak")
        if time_to_peak is None:
            continue

        peak_time = meal_time + timedelta(minutes=time_to_peak)
        peak = meal["peak_glucose"]
        baseline = meal["baseline_glucose"]
        recommendation = recommend_for_meal(meal, group_stats, late_dinner_effect)

        stats = group_stats.get((meal["meal_type"], meal["carb_bucket"]), {})
        why_lines = []
        if stats.get("spike_prob") is not None:
            why_lines.append(f"Similar meals spike {stats['spike_prob'] * 100:.0f}% of the time.")
        if stats.get("sleep_effect") is not None:
            why_lines.append(f"Lower sleep is linked to ~{stats['sleep_effect']:.0f} mg/dL higher peaks.")

        severe_peak = peak >= 250 or meal["delta_glucose"] >= 90
        needs_diabetes_agent = peak >= 180 or meal["delta_glucose"] >= 45
        needs_wellness_agent = meal["post_meal_activity"] < 30 or recommendation is not None
        activated = [LAYER_STATE, LAYER_CONTEXT]
        outputs = {
            LAYER_STATE: "Post-meal peak state estimated",
            LAYER_CONTEXT: "Context = post-meal peak",
        }
        primary_agent = None
        supporting_agents = []
        escalation_level = "none"
        trigger_parts = []
        if severe_peak:
            primary_agent = AGENT_MEDICAL
            supporting_agents = [AGENT_DIABETES]
            escalation_level = "urgent"
            trigger_parts.append("severe_glucose_peak")
        elif needs_diabetes_agent:
            primary_agent = AGENT_DIABETES
            trigger_parts.append("postmeal_peak_above_target")
        if needs_wellness_agent:
            if primary_agent is None:
                primary_agent = AGENT_WELLNESS
            elif primary_agent != AGENT_WELLNESS:
                supporting_agents.append(AGENT_WELLNESS)
            trigger_parts.append("behavioral_response_lever_available")
        if meal.get("sleep_score") is not None and meal["sleep_score"] < 70 and primary_agent is not None:
            if primary_agent != AGENT_SLEEP:
                supporting_agents.append(AGENT_SLEEP)
            trigger_parts.append("low_prior_sleep_score")
        intervention_available = primary_agent is not None
        decision = build_decision(
            confidence=meal["confidence"],
            intervention_available=intervention_available,
            primary_agent=primary_agent,
            supporting_agents=supporting_agents,
            trigger_reason=", ".join(trigger_parts) if trigger_parts else "post_meal_peak_monitoring",
            escalation_level=escalation_level,
            next_check_minutes=60,
            extra={"selected_lever": recommendation["type"] if recommendation else None},
        )
        user_output = None

        if intervention_available:
            activated.extend([LAYER_ORCH, LAYER_KB, LAYER_GUIDANCE, LAYER_INTERFACE])
            outputs[LAYER_ORCH] = orchestrator_activation_line(primary_agent, supporting_agents, "post-meal peak")
            outputs[LAYER_KB] = format_kb_output(
                "Type II diabetes evidence and constraints applied",
                guideline_kb,
                tags=["post_meal", "diabetes_general", "glucose_state"],
            )
            outputs[LAYER_GUIDANCE] = "Peak-response recommendation composed"
            outputs[LAYER_INTERFACE] = "Peak-response guidance delivered"
            if primary_agent == AGENT_MEDICAL:
                action_text = "Glucose peak is severe. Use urgent corrective steps and monitor closely."
            elif primary_agent == AGENT_DIABETES:
                action_text = recommendation["text"] if recommendation else "Use a smaller portion or add a short walk after this meal."
            else:
                action_text = recommendation["text"] if recommendation else "Add light activity and meal-balancing strategy at this meal pattern."
            user_output = {
                "title": meal_label,
                "what_happened": (
                    f"Your glucose rose from {baseline:.0f} to {peak:.0f} mg/dL, peaking {time_to_peak} minutes after the meal."
                ),
                "why": why_lines,
                "try_next_time": action_text,
            }

        peak_raw = [
            f"RAW: cg_timestamp={peak_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"RAW: peak_glucose_mg_dL={int(round(peak))}",
            f"RAW: delta_glucose_mg_dL={round(meal['delta_glucose'], 1)}",
        ]

        events.append(
            event_template(
                timestamp=peak_time,
                event_type="peak_detected",
                event_id=f"{meal_id}-peak",
                raw_lines=peak_raw,
                activated=activated,
                outputs=outputs,
                state_snapshot={
                    "baseline_glucose_mg_dL": round(baseline, 1),
                    "peak_glucose_mg_dL": round(peak, 1),
                    "delta_glucose_mg_dL": round(meal["delta_glucose"], 1),
                },
                decision_snapshot=decision,
                user_output=user_output,
                is_event=True,
            )
        )

    return events


def build_glucose_transition_events(stream, by_ts, guideline_kb):
    events = []
    last_state = None
    last_transition_ts = None
    last_rapid_rise_ts = None
    last_rapid_fall_ts = None

    for point in stream:
        ts = point["timestamp"]
        glucose = point["glucose"]
        if glucose is None:
            continue

        state_name = classify_glucose_state(glucose)
        if last_state is None:
            last_state = state_name
        elif state_name != last_state:
            if last_transition_ts is None or ts - last_transition_ts >= timedelta(minutes=10):
                definition = STATE_DEFS.get(state_name, {})
                actionable = state_name in ACTIONABLE_GLUCOSE_STATES
                activated = [LAYER_EVENT, LAYER_STATE, LAYER_CONTEXT]
                outputs = {
                    LAYER_EVENT: "Glucose state transition extracted",
                    LAYER_STATE: "Glycemic state updated",
                    LAYER_CONTEXT: "Context = state transition",
                }
                decision = build_decision(
                    confidence=1.0,
                    intervention_available=False,
                    trigger_reason="state_transition_observed",
                    next_check_minutes=15,
                )
                user_output = None

                if actionable:
                    severe_transition = state_name in {"TAR_State_Level2", "TBR_State_Level2"}
                    primary_agent = AGENT_MEDICAL if severe_transition else AGENT_DIABETES
                    supporting_agents = [AGENT_DIABETES] if primary_agent == AGENT_MEDICAL else []
                    if state_name in {"TAR_State_Level1", "TBR_State_Level1"} and primary_agent != AGENT_WELLNESS:
                        supporting_agents.append(AGENT_WELLNESS)
                    escalation_level = "urgent" if severe_transition else "watch"
                    activated.extend([LAYER_ORCH, LAYER_KB, LAYER_GUIDANCE, LAYER_INTERFACE])
                    outputs[LAYER_ORCH] = orchestrator_activation_line(primary_agent, supporting_agents, "state transition")
                    outputs[LAYER_KB] = format_kb_output(
                        "Type II diabetes transition policy applied",
                        guideline_kb,
                        tags=["glucose_state", "diabetes_general", "hypoglycemia"],
                    )
                    outputs[LAYER_GUIDANCE] = "Actionable transition guidance composed"
                    outputs[LAYER_INTERFACE] = "State-transition alert delivered"
                    decision = build_decision(
                        confidence=1.0,
                        intervention_available=True,
                        primary_agent=primary_agent,
                        supporting_agents=supporting_agents,
                        trigger_reason=f"state_transition_to_{state_name}",
                        escalation_level=escalation_level,
                        next_check_minutes=15,
                    )
                    user_output = {
                        "title": f"Glucose State Change: {state_name}",
                        "what_happened": f"Glucose changed state from {last_state} to {state_name} at {ts.strftime('%H:%M')}.",
                        "why": [
                            definition.get("clinical_meaning") or "Clinically meaningful glucose-state transition.",
                            "State transitions trigger targeted Type II diabetes guidance.",
                        ],
                        "try_next_time": state_guidance_for_diabetes(state_name),
                    }

                raw_lines = [
                    f"RAW: cg_timestamp={ts.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"RAW: glucose_mg_dL={int(round(glucose))}",
                    f"RAW: from_state={last_state}",
                    f"RAW: to_state={state_name}",
                ]

                events.append(
                    event_template(
                        timestamp=ts,
                        event_type="glucose_state_transition",
                        event_id=f"glucose-transition-{len(events) + 1}",
                        raw_lines=raw_lines,
                        activated=activated,
                        outputs=outputs,
                        state_snapshot={
                            "previous_state": last_state,
                            "current_state": state_name,
                            "glycemic_zone": definition.get("glycemic_zone"),
                            "glycemic_severity": definition.get("severity"),
                            "glucose_mg_dL": round(glucose, 1),
                        },
                        decision_snapshot=decision,
                        user_output=user_output,
                        is_event=True,
                    )
                )
                last_transition_ts = ts
            last_state = state_name

        lookback = by_ts.get(ts - timedelta(minutes=15))
        if lookback and lookback.get("glucose") is not None:
            delta_15 = glucose - lookback["glucose"]
            if delta_15 >= 35 and (last_rapid_rise_ts is None or ts - last_rapid_rise_ts >= timedelta(minutes=60)):
                severe_rapid_rise = delta_15 >= 55 or glucose >= 280
                primary_agent = AGENT_MEDICAL if severe_rapid_rise else AGENT_DIABETES
                supporting_agents = [AGENT_DIABETES] if primary_agent == AGENT_MEDICAL else []
                supporting_agents.append(AGENT_WELLNESS)
                escalation_level = "urgent" if severe_rapid_rise else "watch"
                events.append(
                    event_template(
                        timestamp=ts,
                        event_type="rapid_glucose_rise",
                        event_id=f"rapid-rise-{len(events) + 1}",
                        raw_lines=[
                            f"RAW: cg_timestamp={ts.strftime('%Y-%m-%d %H:%M:%S')}",
                            f"RAW: glucose_delta_15min={round(delta_15, 1)}",
                        ],
                        activated=[
                            LAYER_EVENT,
                            LAYER_STATE,
                            LAYER_CONTEXT,
                            LAYER_ORCH,
                            LAYER_KB,
                            LAYER_GUIDANCE,
                            LAYER_INTERFACE,
                        ],
                        outputs={
                            LAYER_EVENT: "Rapid rise event extracted",
                            LAYER_STATE: "Rapid_Glucose_Rise_State detected",
                            LAYER_CONTEXT: "Context = non-meal rapid rise",
                            LAYER_ORCH: orchestrator_activation_line(primary_agent, supporting_agents, "rapid glucose rise"),
                            LAYER_KB: format_kb_output(
                                "Type II rapid-rise policy applied",
                                guideline_kb,
                                tags=["glucose_state", "exercise", "diabetes_general"],
                            ),
                            LAYER_GUIDANCE: "Rapid-rise intervention guidance composed",
                            LAYER_INTERFACE: "Rapid-rise alert delivered",
                        },
                        state_snapshot={
                            "glucose_state": "Rapid_Glucose_Rise_State",
                            "glucose_delta_15min": round(delta_15, 1),
                            "glucose_mg_dL": round(glucose, 1),
                        },
                        decision_snapshot=build_decision(
                            confidence=1.0,
                            intervention_available=True,
                            primary_agent=primary_agent,
                            supporting_agents=supporting_agents,
                            trigger_reason="rapid_glucose_rise",
                            escalation_level=escalation_level,
                            next_check_minutes=15,
                        ),
                        user_output={
                            "title": "Rapid Glucose Rise",
                            "what_happened": f"Glucose rose by {delta_15:.0f} mg/dL in ~15 minutes.",
                            "why": [
                                "Rapid rises can precede hyperglycemic episodes.",
                                "Fast response often reduces peak severity.",
                            ],
                            "try_next_time": state_guidance_for_diabetes("Rapid_Glucose_Rise_State"),
                        },
                        is_event=True,
                    )
                )
                last_rapid_rise_ts = ts

            if delta_15 <= -35 and (last_rapid_fall_ts is None or ts - last_rapid_fall_ts >= timedelta(minutes=60)):
                severe_rapid_fall = abs(delta_15) >= 50 or glucose <= 60
                primary_agent = AGENT_MEDICAL if severe_rapid_fall else AGENT_DIABETES
                supporting_agents = [AGENT_DIABETES] if primary_agent == AGENT_MEDICAL else []
                escalation_level = "urgent" if severe_rapid_fall else "watch"
                events.append(
                    event_template(
                        timestamp=ts,
                        event_type="rapid_glucose_fall",
                        event_id=f"rapid-fall-{len(events) + 1}",
                        raw_lines=[
                            f"RAW: cg_timestamp={ts.strftime('%Y-%m-%d %H:%M:%S')}",
                            f"RAW: glucose_delta_15min={round(delta_15, 1)}",
                        ],
                        activated=[
                            LAYER_EVENT,
                            LAYER_STATE,
                            LAYER_CONTEXT,
                            LAYER_ORCH,
                            LAYER_KB,
                            LAYER_GUIDANCE,
                            LAYER_INTERFACE,
                        ],
                        outputs={
                            LAYER_EVENT: "Rapid fall event extracted",
                            LAYER_STATE: "Rapid_Glucose_Fall_State detected",
                            LAYER_CONTEXT: "Context = non-meal rapid fall",
                            LAYER_ORCH: orchestrator_activation_line(primary_agent, supporting_agents, "rapid glucose fall"),
                            LAYER_KB: format_kb_output(
                                "Type II rapid-fall safety policy applied",
                                guideline_kb,
                                tags=["hypoglycemia", "glucose_state", "diabetes_general"],
                            ),
                            LAYER_GUIDANCE: "Rapid-fall safety guidance composed",
                            LAYER_INTERFACE: "Rapid-fall alert delivered",
                        },
                        state_snapshot={
                            "glucose_state": "Rapid_Glucose_Fall_State",
                            "glucose_delta_15min": round(delta_15, 1),
                            "glucose_mg_dL": round(glucose, 1),
                        },
                        decision_snapshot=build_decision(
                            confidence=1.0,
                            intervention_available=True,
                            primary_agent=primary_agent,
                            supporting_agents=supporting_agents,
                            trigger_reason="rapid_glucose_fall",
                            escalation_level=escalation_level,
                            next_check_minutes=15,
                        ),
                        user_output={
                            "title": "Rapid Glucose Fall",
                            "what_happened": f"Glucose dropped by {abs(delta_15):.0f} mg/dL in ~15 minutes.",
                            "why": [
                                "Rapid falls can lead to hypoglycemia risk.",
                                "Immediate safety action can reduce low-glucose exposure.",
                            ],
                            "try_next_time": state_guidance_for_diabetes("Rapid_Glucose_Fall_State"),
                        },
                        is_event=True,
                    )
                )
                last_rapid_fall_ts = ts

    return events


def detect_exercise_sessions(stream, met_threshold=2.5, min_minutes=12):
    sessions = []
    start_idx = None
    for idx, point in enumerate(stream):
        is_active = point.get("met") is not None and point["met"] >= met_threshold
        if is_active and start_idx is None:
            start_idx = idx
            continue
        if is_active:
            continue
        if start_idx is None:
            continue

        end_idx = idx - 1
        duration = int((stream[end_idx]["timestamp"] - stream[start_idx]["timestamp"]).total_seconds() / 60) + 1
        if duration >= min_minutes:
            sessions.append((start_idx, end_idx, duration))
        start_idx = None

    if start_idx is not None:
        end_idx = len(stream) - 1
        duration = int((stream[end_idx]["timestamp"] - stream[start_idx]["timestamp"]).total_seconds() / 60) + 1
        if duration >= min_minutes:
            sessions.append((start_idx, end_idx, duration))

    return sessions


def build_exercise_events(stream, by_ts, guideline_kb):
    events = []
    sessions = detect_exercise_sessions(stream)

    for idx, (start_idx, end_idx, duration) in enumerate(sessions, start=1):
        start_point = stream[start_idx]
        end_point = stream[end_idx]
        start_ts = start_point["timestamp"]
        end_ts = end_point["timestamp"]

        pre_entry = by_ts.get(start_ts - timedelta(minutes=10))
        post_entry = by_ts.get(end_ts + timedelta(minutes=20))
        g_pre = None if pre_entry is None else pre_entry.get("glucose")
        g_start = start_point.get("glucose")
        g_end = end_point.get("glucose")
        g_post = None if post_entry is None else post_entry.get("glucose")

        start_primary_agent = None
        start_supporting_agents = []
        start_trigger_reason = "exercise_started_monitoring"
        start_escalation = "none"
        if g_start is not None:
            if g_start < 60 or g_start > 280:
                start_primary_agent = AGENT_MEDICAL
                start_supporting_agents = [AGENT_DIABETES]
                start_escalation = "urgent"
                start_trigger_reason = "exercise_start_glucose_extreme"
            elif g_start < 90 or g_start > 180:
                start_primary_agent = AGENT_DIABETES
                start_supporting_agents = [AGENT_WELLNESS]
                start_trigger_reason = "exercise_start_glucose_out_of_target"
            else:
                start_primary_agent = AGENT_WELLNESS
                start_trigger_reason = "exercise_start_behavioral_guidance"

        start_activated = [LAYER_EVENT, LAYER_STATE, LAYER_CONTEXT]
        start_outputs = {
            LAYER_EVENT: "Exercise episode start extracted",
            LAYER_STATE: "Exercise state = active",
            LAYER_CONTEXT: "Context = during exercise",
        }
        start_intervention = start_primary_agent is not None
        start_decision = build_decision(
            confidence=1.0,
            intervention_available=start_intervention,
            primary_agent=start_primary_agent,
            supporting_agents=start_supporting_agents,
            trigger_reason=start_trigger_reason,
            escalation_level=start_escalation,
            next_check_minutes=20,
        )
        start_user_output = None
        if start_intervention:
            start_activated.extend([LAYER_ORCH, LAYER_KB, LAYER_GUIDANCE, LAYER_INTERFACE])
            start_outputs[LAYER_ORCH] = orchestrator_activation_line(start_primary_agent, start_supporting_agents, "exercise start")
            start_outputs[LAYER_KB] = format_kb_output(
                "Exercise start guidance policy applied",
                guideline_kb,
                tags=["exercise", "diabetes_general", "hypoglycemia"],
            )
            start_outputs[LAYER_GUIDANCE] = "Exercise start guidance composed"
            start_outputs[LAYER_INTERFACE] = "Exercise start guidance delivered"
            if start_primary_agent == AGENT_MEDICAL:
                start_next = "Glucose is at an extreme before exercise. Follow urgent safety plan and reassess now."
            elif start_primary_agent == AGENT_DIABETES:
                start_next = "Start carefully, monitor glucose closely during activity, and prepare correction if needed."
            else:
                start_next = "Great timing. Stay hydrated and re-check glucose during or right after exercise."
            start_user_output = {
                "title": "Exercise Start Check",
                "what_happened": "PCU detected exercise start and evaluated pre-exercise glucose context.",
                "why": [
                    "Glucose trend around exercise affects immediate safety.",
                    "Early adaptation reduces exercise-related glycemic risk.",
                ],
                "try_next_time": start_next,
            }

        events.append(
            event_template(
                timestamp=start_ts,
                event_type="exercise_started",
                event_id=f"exercise-{idx}-start",
                raw_lines=[
                    f"RAW: cg_timestamp={start_ts.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"RAW: activity_met_1min={round(start_point.get('met') or 0.0, 2)}",
                ],
                activated=start_activated,
                outputs=start_outputs,
                state_snapshot={
                    "exercise_state": "active",
                    "exercise_duration_min": duration,
                    "glucose_at_start_mg_dL": g_start,
                },
                decision_snapshot=start_decision,
                user_output=start_user_output,
                is_event=True,
            )
        )

        risk_reasons = []
        if g_start is not None and g_start > 180:
            risk_reasons.append("high_glucose_at_exercise_start")
        if g_start is not None and g_start < 80:
            risk_reasons.append("low_glucose_at_exercise_start")
        if g_end is not None and g_end < 80:
            risk_reasons.append("low_glucose_during_exercise")
        if g_end is not None and g_end > 220:
            risk_reasons.append("high_glucose_during_exercise")
        if g_post is not None and (g_post < 80 or g_post > 180):
            risk_reasons.append("out_of_range_after_exercise")
        if g_pre is not None and g_post is not None and abs(g_post - g_pre) >= 30:
            risk_reasons.append("large_post_exercise_shift")

        severe_risk = any(reason in {"low_glucose_during_exercise", "high_glucose_during_exercise"} for reason in risk_reasons)
        if g_end is not None and (g_end < 60 or g_end > 280):
            severe_risk = True
        if g_post is not None and (g_post < 60 or g_post > 280):
            severe_risk = True
        needs_diabetes_agent = bool(risk_reasons)
        needs_wellness_agent = duration >= 20
        activated = [LAYER_EVENT, LAYER_STATE, LAYER_CONTEXT]
        outputs = {
            LAYER_EVENT: "Exercise episode end extracted",
            LAYER_STATE: "Exercise state = recovery",
            LAYER_CONTEXT: "Context = after exercise",
        }
        primary_agent = None
        supporting_agents = []
        escalation_level = "none"
        if severe_risk:
            primary_agent = AGENT_MEDICAL
            supporting_agents = [AGENT_DIABETES, AGENT_WELLNESS]
            escalation_level = "urgent"
        elif needs_diabetes_agent:
            primary_agent = AGENT_DIABETES
            if needs_wellness_agent:
                supporting_agents.append(AGENT_WELLNESS)
        elif needs_wellness_agent:
            primary_agent = AGENT_WELLNESS
        intervention_available = primary_agent is not None
        decision = build_decision(
            confidence=1.0,
            intervention_available=intervention_available,
            primary_agent=primary_agent,
            supporting_agents=supporting_agents,
            trigger_reason=", ".join(risk_reasons) if risk_reasons else "exercise_recovery_window",
            escalation_level=escalation_level,
            next_check_minutes=20,
        )
        user_output = None

        if intervention_available:
            activated.extend([LAYER_ORCH, LAYER_KB, LAYER_GUIDANCE, LAYER_INTERFACE])
            outputs[LAYER_ORCH] = orchestrator_activation_line(primary_agent, supporting_agents, "exercise recovery")
            outputs[LAYER_KB] = format_kb_output(
                "Exercise-glucose interaction policy applied",
                guideline_kb,
                tags=["exercise", "hypoglycemia", "diabetes_general"],
            )
            outputs[LAYER_GUIDANCE] = "Exercise recovery guidance composed"
            outputs[LAYER_INTERFACE] = "Exercise recovery alert delivered"
            if primary_agent == AGENT_MEDICAL:
                recommendation = "Exercise recovery glucose is in severe range. Use urgent safety plan and notify care team if needed."
            elif primary_agent == AGENT_DIABETES:
                recommendation = "Monitor glucose around workouts and use your recovery plan promptly."
            else:
                recommendation = "Use hydration, light cool-down, and a recovery snack strategy aligned with your plan."
            user_output = {
                "title": "Exercise Recovery Glucose Check",
                "what_happened": "PCU detected exercise-related glucose risk during or after activity.",
                "why": [
                    "Glucose can move quickly around exercise windows.",
                    "Targeted guidance reduces hypo/hyperglycemia risk after activity.",
                ],
                "try_next_time": recommendation,
            }

        events.append(
            event_template(
                timestamp=end_ts,
                event_type="exercise_ended",
                event_id=f"exercise-{idx}-end",
                raw_lines=[
                    f"RAW: cg_timestamp={end_ts.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"RAW: exercise_duration_min={duration}",
                    f"RAW: glucose_end_mg_dL={int(round(g_end)) if g_end is not None else 'NA'}",
                    f"RAW: glucose_post20_mg_dL={int(round(g_post)) if g_post is not None else 'NA'}",
                ],
                activated=activated,
                outputs=outputs,
                state_snapshot={
                    "exercise_state": "recovery",
                    "exercise_duration_min": duration,
                    "glucose_before_exercise_mg_dL": g_pre,
                    "glucose_end_exercise_mg_dL": g_end,
                    "glucose_post20_mg_dL": g_post,
                },
                decision_snapshot=decision,
                user_output=user_output,
                is_event=True,
            )
        )

    return events


def build_sleep_events(active_days, sleep_records, guideline_kb, stream):
    events = []
    if not active_days:
        return events

    rhythm = infer_sleep_rhythm(sleep_records)
    wake_seconds = rhythm["wake_seconds"]
    bed_seconds = rhythm["bed_seconds"]

    for idx, day_value in enumerate(sorted(active_days), start=1):
        wake_ts = datetime.combine(day_value, datetime.min.time()) + timedelta(seconds=wake_seconds)
        reminder_ts = datetime.combine(day_value, datetime.min.time()) + timedelta(seconds=bed_seconds) - timedelta(minutes=30)

        prior = prior_sleep_record(sleep_records, day_value)
        sleep_score = None if prior is None else prior.get("sleep_score")
        loneliness = compute_loneliness_profile(day_value, stream, sleep_records)
        loneliness_level = loneliness["level"]
        loneliness_score = loneliness["score"]
        score_text = "NA" if sleep_score is None else str(int(round(sleep_score)))
        wake_supporting_agents = []
        wake_trigger_reason = "wake_context_detected"
        if sleep_score is not None and sleep_score < 70:
            wake_supporting_agents.extend([AGENT_DIABETES, AGENT_WELLNESS])
            wake_trigger_reason = "wake_context_low_sleep_recovery"
        if loneliness_level in {"Moderate", "High"} and AGENT_WELLNESS not in wake_supporting_agents:
            wake_supporting_agents.append(AGENT_WELLNESS)
        if loneliness_level == "High":
            wake_trigger_reason = f"{wake_trigger_reason},wake_loneliness_high_prediction"

        wake_next_step = "Use this check-in to plan breakfast load and movement timing."
        if loneliness_level == "High":
            wake_next_step = "Your morning model predicts high loneliness risk today. Plan two social touchpoints (message/call/walk) and one midday check."
        elif loneliness_level == "Moderate":
            wake_next_step = "Your morning model predicts moderate loneliness risk today. Schedule one social touchpoint and a short daylight walk."

        events.append(
            event_template(
                timestamp=wake_ts,
                event_type="sleep_wake_detected",
                event_id=f"sleep-{idx}-wake",
                raw_lines=[
                    f"RAW: sleep_wake_timestamp={wake_ts.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"RAW: sleep_score={score_text}",
                    f"RAW: loneliness_predicted_today={loneliness_level}",
                    f"RAW: loneliness_prediction_score={loneliness_score}",
                ],
                activated=[
                    LAYER_EVENT,
                    LAYER_STATE,
                    LAYER_CONTEXT,
                    LAYER_ORCH,
                    LAYER_KB,
                    LAYER_GUIDANCE,
                    LAYER_INTERFACE,
                ],
                outputs={
                    LAYER_EVENT: "Wake event inferred; personal ML model predicted today loneliness level",
                    LAYER_STATE: "Morning recovery state updated",
                    LAYER_CONTEXT: "Context = person is up",
                    LAYER_ORCH: orchestrator_activation_line(AGENT_SLEEP, wake_supporting_agents, "wake detection"),
                    LAYER_KB: format_kb_output(
                        "Sleep and circadian guidance policy applied",
                        guideline_kb,
                        tags=["sleep", "diabetes_general"],
                    ),
                    LAYER_GUIDANCE: "Morning plan guidance composed",
                    LAYER_INTERFACE: "Morning guidance delivered",
                },
                state_snapshot={
                    "sleep_score": sleep_score,
                    "detected_wake_time": wake_ts.strftime("%H:%M"),
                    "loneliness_predicted_today": loneliness_level,
                    "loneliness_prediction_score": loneliness_score,
                },
                decision_snapshot=build_decision(
                    confidence=1.0,
                    intervention_available=True,
                    primary_agent=AGENT_SLEEP,
                    supporting_agents=wake_supporting_agents,
                    trigger_reason=wake_trigger_reason,
                    next_check_minutes=120,
                    extra={"loneliness_prediction": loneliness_level},
                ),
                user_output={
                    "title": "Morning Wake Check-in",
                    "what_happened": "PCU detected wake-up context and activated Sleep Expert Agent.",
                    "why": [
                        "Morning recovery state affects glucose variability for the day.",
                        "Early planning improves meal and activity decisions.",
                        f"Personal ML predicts today's loneliness level as {loneliness_level} ({int(round(loneliness_score * 100))}%).",
                    ],
                    "try_next_time": wake_next_step,
                },
                is_event=True,
                personicle_signals={
                    "personal_ml_model": {
                        "triggered": True,
                        "trigger": "wake_up_prediction",
                        "predicted_level_today": loneliness_level,
                        "prediction_score": loneliness_score,
                        "day_active_minutes": loneliness["day_active_minutes"],
                    }
                },
            )
        )

        bed_supporting_agents = []
        bed_trigger_reason = "pre_bed_window_detected"
        if sleep_score is not None and sleep_score < 70:
            bed_supporting_agents.extend([AGENT_DIABETES, AGENT_WELLNESS])
            bed_trigger_reason = "pre_bed_window_after_low_sleep_day"
        events.append(
            event_template(
                timestamp=reminder_ts,
                event_type="sleep_pre_bed_reminder",
                event_id=f"sleep-{idx}-bed",
                raw_lines=[
                    f"RAW: sleep_reminder_timestamp={reminder_ts.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"RAW: typical_bedtime={int(bed_seconds // 3600):02d}:{int((bed_seconds % 3600) // 60):02d}",
                    f"RAW: prior_sleep_score={score_text}",
                ],
                activated=[
                    LAYER_EVENT,
                    LAYER_STATE,
                    LAYER_CONTEXT,
                    LAYER_ORCH,
                    LAYER_KB,
                    LAYER_GUIDANCE,
                    LAYER_INTERFACE,
                ],
                outputs={
                    LAYER_EVENT: "Pre-bed reminder event created",
                    LAYER_STATE: "Evening sleep-readiness state updated",
                    LAYER_CONTEXT: "Context = 30 minutes before typical bedtime",
                    LAYER_ORCH: orchestrator_activation_line(AGENT_SLEEP, bed_supporting_agents, "pre-bed reminder"),
                    LAYER_KB: format_kb_output(
                        "Pre-sleep hygiene guidance policy applied",
                        guideline_kb,
                        tags=["sleep", "diabetes_general"],
                    ),
                    LAYER_GUIDANCE: "Pre-bed routine guidance composed",
                    LAYER_INTERFACE: "Pre-bed reminder delivered",
                },
                state_snapshot={
                    "typical_bedtime": f"{int(bed_seconds // 3600):02d}:{int((bed_seconds % 3600) // 60):02d}",
                    "sleep_score": sleep_score,
                },
                decision_snapshot=build_decision(
                    confidence=1.0,
                    intervention_available=True,
                    primary_agent=AGENT_SLEEP,
                    supporting_agents=bed_supporting_agents,
                    trigger_reason=bed_trigger_reason,
                    next_check_minutes=480,
                ),
                user_output={
                    "title": "Pre-Bed Sleep Reminder",
                    "what_happened": "PCU triggered a pre-bed guidance touchpoint 30 minutes before typical bedtime.",
                    "why": [
                        "Consistent sleep timing supports next-day glucose stability.",
                        "Evening behavior influences overnight recovery quality.",
                    ],
                    "try_next_time": "Start wind-down now and avoid heavy late-night intake.",
                },
                is_event=True,
            )
        )

    return events


def build_loneliness_events(active_days, stream, sleep_records):
    events = []
    for idx, day_value in enumerate(sorted(active_days), start=1):
        monitor_ts = datetime.combine(day_value, datetime.min.time()) + timedelta(hours=15)
        profile = compute_loneliness_profile(day_value, stream, sleep_records)
        level = profile["level"]
        score = profile["score"]
        is_high = level == "High"
        is_moderate = level == "Moderate"
        intervention = is_high or is_moderate

        activated = [LAYER_EVENT, LAYER_STATE, LAYER_CONTEXT]
        outputs = {
            LAYER_EVENT: "Daytime loneliness monitor evaluated personal ML score",
            LAYER_STATE: "Loneliness monitoring state updated",
            LAYER_CONTEXT: "Context = daytime social-energy monitoring",
        }
        primary_agent = AGENT_WELLNESS if intervention else None
        supporting_agents = []
        if profile.get("sleep_score") is not None and profile["sleep_score"] < 70 and intervention:
            supporting_agents.append(AGENT_SLEEP)

        if intervention:
            activated.extend([LAYER_ORCH, LAYER_GUIDANCE, LAYER_INTERFACE])
            outputs[LAYER_ORCH] = orchestrator_activation_line(primary_agent, supporting_agents, "loneliness monitoring")
            outputs[LAYER_GUIDANCE] = (
                "Feeling-lonely proactive guidance composed" if is_high else "Loneliness watch guidance composed"
            )
            outputs[LAYER_INTERFACE] = (
                "Feeling-lonely event delivered" if is_high else "Loneliness watch update delivered"
            )

        event_type = "feeling_lonely_detected" if is_high else "loneliness_monitor_check"
        user_output = None
        if intervention:
            action = "Schedule one message/call in the next hour and pair it with a short walk."
            if is_high:
                action = "Feeling lonely risk is high now. Reach out to one trusted contact within 30 minutes and avoid prolonged isolation."
            user_output = {
                "title": "Daytime Social Well-Being Check",
                "what_happened": f"Personal ML monitor estimated loneliness level {level} at daytime checkpoint.",
                "why": [
                    "The model combines sleep recovery and daytime activity pattern from objective streams.",
                    "Earlier social contact can reduce sustained loneliness risk over the rest of the day.",
                ],
                "try_next_time": action,
            }

        events.append(
            event_template(
                timestamp=monitor_ts,
                event_type=event_type,
                event_id=f"lonely-{idx}",
                raw_lines=[
                    f"RAW: loneliness_monitor_timestamp={monitor_ts.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"RAW: loneliness_level={level}",
                    f"RAW: loneliness_score={score}",
                    f"RAW: day_active_minutes={profile['day_active_minutes']}",
                    f"RAW: morning_avg_met={profile['morning_avg_met']}",
                ],
                activated=activated,
                outputs=outputs,
                state_snapshot={
                    "loneliness_current_level": level,
                    "loneliness_prediction_score": score,
                    "day_active_minutes": profile["day_active_minutes"],
                    "morning_avg_met": profile["morning_avg_met"],
                    "day_avg_met": profile["day_avg_met"],
                },
                decision_snapshot=build_decision(
                    confidence=0.8,
                    intervention_available=intervention,
                    primary_agent=primary_agent,
                    supporting_agents=supporting_agents,
                    trigger_reason="daytime_loneliness_monitor",
                    escalation_level="watch" if is_high else "none",
                    next_check_minutes=180,
                    extra={"loneliness_prediction": level},
                ),
                user_output=user_output,
                is_event=is_high,
                personicle_signals={
                    "personal_ml_model": {
                        "triggered": True,
                        "trigger": "daytime_monitor",
                        "predicted_level_today": level,
                        "prediction_score": score,
                        "loneliness_event": is_high,
                        "day_active_minutes": profile["day_active_minutes"],
                    }
                },
            )
        )

    return events


def build_payload(dataset_root, participant=None, max_meals=6):
    dataset_root = Path(dataset_root)
    activity_path = dataset_root / "Oura" / "activity_1min.csv"
    sleep_path = dataset_root / "Oura" / "sleep_daily.csv"

    participant = participant or load_meal_participants(activity_path)
    stream, by_ts, meals = load_activity(activity_path, participant)
    sleep_records = load_sleep(sleep_path, participant)
    guideline_kb = load_guideline_kb()

    meal_episodes = build_meal_episodes(meals, by_ts, sleep_records, max_meals=max_meals)
    group_stats, sleep_median = compute_group_stats(meal_episodes)
    late_dinner_effect = compute_late_dinner_effect(meal_episodes)

    timeline = []
    timeline.extend(build_meal_events(meal_episodes, group_stats, sleep_median, late_dinner_effect, guideline_kb))
    timeline.extend(build_glucose_transition_events(stream, by_ts, guideline_kb))
    timeline.extend(build_exercise_events(stream, by_ts, guideline_kb))
    active_days = {point["timestamp"].date() for point in stream}
    timeline.extend(build_sleep_events(active_days, sleep_records, guideline_kb, stream))
    timeline.extend(build_loneliness_events(active_days, stream, sleep_records))
    timeline.sort(key=lambda item: item["timestamp"])

    payload = {
        "meta": {
            "participant": participant,
            "source": dataset_root.name,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "meal_count": len(meal_episodes),
            "component_names": [
                LAYER_EVENT,
                LAYER_STATE,
                LAYER_CONTEXT,
                LAYER_KB,
                LAYER_GUIDANCE,
                LAYER_ORCH,
                LAYER_GUARDIAN,
                LAYER_INTERFACE,
            ],
            "data_channel_names": [
                DATA_OBJECTIVE,
                DATA_SUBJECTIVE,
                DATA_INFERRED,
                DATA_CONVERSATION,
            ],
            "knowledge_base_file": str(GUIDELINE_KB_PATH.relative_to(Path(__file__).resolve().parents[2])),
            "knowledge_base_entries": len(guideline_kb),
        },
        "timeline": timeline,
    }
    return payload


def payload_to_json(payload):
    return json.dumps(payload, indent=2)
