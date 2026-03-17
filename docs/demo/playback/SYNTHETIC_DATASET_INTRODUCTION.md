# Synthetic Dataset Introduction

## What This Synthetic Dataset Is

The synthetic dataset in this project is the **CG-augmented dataset** under `output/cg_augmented/`.

It is not a purely simulated dataset created from scratch. Instead, it is a **synthetic multimodal fusion dataset** built by:

1. taking real participant-day records from the `CGMacros/` study,
2. matching each CGMacros day to the most behaviorally similar day from `LONELINESS-DATASET/`, and
3. warping the loneliness-study timestamps onto the CGMacros timeline so that the merged records can be analyzed as if they belonged to the same synchronized participant-day.

The result is a dataset where each output participant folder is named after a **CGMacros participant**, but most behavioral, EMA, Oura, and Samsung rows inside that folder come from an anonymized **LONELINESS-DATASET participant/day** that has been temporally aligned to the CGMacros day.

This means the dataset is best understood as a **cross-study synthetic alignment product** rather than a natural, originally collected single-cohort dataset.

## Main Source Data in This Project

The project combines two major data sources:

- `CGMacros/`
  - Real CG study data, including participant CSVs and photos.
  - The central per-participant CSV appears to contain glucose, heart rate, METs, meal information, and image-path references.
- `LONELINESS-DATASET/`
  - A real multimodal sensing dataset organized by participant IDs such as `pers2001`.
  - Includes `AWARE/`, `Ema/`, `Oura/`, `Samsung/`, plus derived event-label artifacts and documentation.

The synthetic export is written to:

- `output/cg_augmented/`
- supporting alignment artifacts:
  - `output/cg_day_matches.csv`
  - `output/cg_to_lon_dtw_map.csv`
  - `output/dataset_cgmacros_augmented_for_pcu.zip`

## How The Synthetic Dataset Is Constructed

The synthetic construction pipeline is implemented mainly by:

- `met_day_match_dtw.py`
- `warp_loneliness_to_cg.py`

### Step 1: Day-level matching

`met_day_match_dtw.py` loads:

- `CGMacros/<participant>/<participant>.csv`
- `LONELINESS-DATASET/<participant>/Oura/activity_1min.csv`

For each day, it extracts a 24-dimensional hourly activity profile based on MET values:

- CGMacros uses `METs`
- LONELINESS uses `activity_met_1min`

The script z-scores each daily hourly profile and computes **cosine similarity** between each CGMacros day and all available loneliness-study days. The highest-similarity day is selected as the match.

The matched day pairs are saved in `output/cg_day_matches.csv` with:

- `cg_participant`
- `cg_date`
- `lon_participant`
- `lon_date`
- `cosine_similarity`

### Step 2: Minute-level temporal warping

After the best day pair is selected, the script applies **dynamic time warping (DTW)** to the minute-level MET sequences of the matched days.

This produces a many-to-many alignment path between:

- CGMacros minute timestamps
- LONELINESS minute timestamps

The minute-level mapping is written to `output/cg_to_lon_dtw_map.csv` with:

- `cg_participant`
- `cg_date`
- `cg_timestamp`
- `lon_participant`
- `lon_date`
- `lon_timestamp`
- `dtw_cost`

### Step 3: Writing the synthetic export

`warp_loneliness_to_cg.py` uses the matched days and the DTW path to rewrite LONELINESS rows into CGMacros participant folders.

For non-daily files, each mapped row gets:

- CG identity fields such as `cg_participant`, `cg_date`, `cg_timestamp`
- source-tracking fields such as `lon_participant`, `lon_date`, `lon_timestamp`
- copied CGMacros row features prefixed with `cg_`
- the original LONELINESS row fields

For daily files, the merge happens only at the day level:

- the output includes `cg_participant`, `cg_date`, `lon_participant`, `lon_date`
- the `cg_*` fields remain present in the header but are typically blank because there is no single minute-level CG row attached to a daily summary row

## What Makes It “Synthetic”

This dataset is synthetic in three important ways:

1. **Cross-participant synthesis**
   - A row in `output/cg_augmented/CGMacros-001/...` may come from a different source participant such as `pers2002`.
2. **Cross-study synthesis**
   - The CG study and the loneliness study were collected independently.
3. **Time-warped synchronization**
   - Source timestamps are not simply copied; they are mapped onto another study’s timeline through DTW alignment.

Because of this, the dataset should be used as a **research or prototyping dataset for multimodal fusion**, not as ground-truth evidence that the original signals were co-measured in the same individual at the same real-world moment.

## Coverage Summary

The synthetic dataset currently present in this repository has the following observed coverage:

| Item | Value |
|---|---:|
| CGMacros participant CSVs present in `CGMacros/` | 45 |
| Synthetic participant folders generated in `output/cg_augmented/` | 34 |
| Missing CGMacros IDs from synthetic export | 11 (`CGMacros-011`, `026`, `027`, `031`, `032`, `033`, `034`, `035`, `038`, `042`, `046`) |
| Matched CG participant-days | 375 |
| Unique CG participant IDs represented | 34 |
| Unique LONELINESS participant IDs used as source templates | 31 |
| CSV files in synthetic export | 616 |
| Minute-level DTW mappings | 501,078 |
| Mean cosine similarity across matched days | 0.8604 |
| Min / max cosine similarity | 0.6556 / 1.0000 |
| Mean DTW cost across mapped minutes | 606.24 |
| CG date range in matches | 2019-11-15 to 2025-11-10 |
| LONELINESS source date range in matches | 2021-11-20 to 2022-07-02 |

Source LONELINESS participants are reused across multiple CG participant-days. For example, `pers2003` is used heavily as a template in the current output.

## Synthetic Participant Structure

Each synthetic participant folder mirrors the LONELINESS folder layout and adds CG-specific files:

```text
output/cg_augmented/CGMacros-XXX/
├── cg_events.csv
├── AWARE/
│   ├── battery.csv
│   ├── calls.csv
│   ├── device_usage.csv
│   ├── messages.csv
│   ├── notifications.csv
│   ├── screen.csv
│   └── touch.csv
├── Ema/
│   ├── daily.csv
│   └── reflection.csv
├── Oura/
│   ├── activity_1min.csv
│   ├── activity_5min.csv
│   ├── activity_daily.csv
│   ├── readiness_daily.csv
│   ├── sleep_5min.csv
│   └── sleep_daily.csv
└── Samsung/
    ├── Watch_Features.csv
    ├── hrv_5min.csv
    └── hrv_12min.csv
```

Observed file presence across the 34 generated synthetic participants:

| File | Participants with file |
|---|---:|
| `cg_events.csv` | 34 |
| `AWARE/battery.csv` | 34 |
| `AWARE/calls.csv` | 29 |
| `AWARE/device_usage.csv` | 34 |
| `AWARE/messages.csv` | 34 |
| `AWARE/notifications.csv` | 34 |
| `AWARE/screen.csv` | 34 |
| `AWARE/touch.csv` | 34 |
| `Ema/daily.csv` | 34 |
| `Ema/reflection.csv` | 9 |
| `Oura/activity_1min.csv` | 34 |
| `Oura/activity_5min.csv` | 34 |
| `Oura/activity_daily.csv` | 34 |
| `Oura/readiness_daily.csv` | 34 |
| `Oura/sleep_5min.csv` | 34 |
| `Oura/sleep_daily.csv` | 34 |
| `Samsung/Watch_Features.csv` | 34 |
| `Samsung/hrv_5min.csv` | 34 |
| `Samsung/hrv_12min.csv` | 34 |

This means the export is structurally consistent, but some optional source modalities such as calls and reflection EMAs are not available for every synthetic participant.

## Row Semantics And Field Layout

The synthetic CSVs combine three kinds of information:

### 1. Synthetic CG identity and alignment fields

These fields indicate where the row lives in the synthetic output:

- `cg_participant`
- `cg_date`
- `cg_timestamp` for mapped event/minute-level files

### 2. Provenance fields from the source LONELINESS day

These fields preserve the original source identity:

- `lon_participant`
- `lon_date`
- `lon_timestamp` for mapped event/minute-level files

These provenance fields are critical. They are what let you determine which original participant/day was borrowed to create the synthetic row.

### 3. CGMacros feature columns

Fields copied from the matched CGMacros minute row are added with the `cg_` prefix. Example columns observed in `Oura/activity_1min.csv` and AWARE files include:

- `cg_Libre GL`
- `cg_Dexcom GL`
- `cg_HR`
- `cg_Calories (Activity)`
- `cg_METs`
- `cg_Meal Type`
- `cg_Calories`
- `cg_Carbs`
- `cg_Protein`
- `cg_Fat`
- `cg_Fiber`
- `cg_Amount Consumed `
- `cg_Image path`

These columns allow each synthetic behavioral row to be analyzed alongside the aligned CGMacros signal state.

### 4. Original LONELINESS row payload

After the synthetic and CG fields, the original row from the source dataset is preserved. Examples:

- AWARE files keep fields like `application_category`, `call_duration`, `touch_action`
- EMA files keep survey responses such as `feel_lonely`, `feel_connected`, PANAS items, and sleep-report items
- Oura files keep activity, sleep, and readiness metrics
- Samsung files keep watch-derived physiological features

## Included Modalities In Practice

Below is the observed row volume across the generated synthetic export:

| File | Total rows |
|---|---:|
| `AWARE/battery.csv` | 648 |
| `AWARE/calls.csv` | 234 |
| `AWARE/device_usage.csv` | 27,344 |
| `AWARE/messages.csv` | 4,090 |
| `AWARE/notifications.csv` | 19,810 |
| `AWARE/screen.csv` | 78,072 |
| `AWARE/touch.csv` | 179,955 |
| `Ema/daily.csv` | 847 |
| `Ema/reflection.csv` | 18 |
| `Oura/activity_1min.csv` | 536,220 |
| `Oura/activity_5min.csv` | 106,897 |
| `Oura/activity_daily.csv` | 374 |
| `Oura/readiness_daily.csv` | 331 |
| `Oura/sleep_5min.csv` | 30,436 |
| `Oura/sleep_daily.csv` | 317 |
| `Samsung/Watch_Features.csv` | 1,038 |
| `Samsung/hrv_12min.csv` | 667 |
| `Samsung/hrv_5min.csv` | 713 |
| `cg_events.csv` | 26,158 |

The largest modality by far is `Oura/activity_1min.csv`, which makes sense because the day matching and DTW alignment both depend on minute-level MET activity.

## Synthetic-Only File: `cg_events.csv`

Each synthetic participant also contains `cg_events.csv`, which is separate from the warped LONELINESS files.

Observed schema:

- `timestamp`
- `event`

Observed event types include:

- `TIR_Episode`
- `Rapid_Glucose_Rise`
- `Rapid_Glucose_Fall`
- `TBR_Episode_Level1`
- `TBR_Episode_Level2`
- `TAR_Episode_Level1`
- `TAR_Episode_Level2`
- `Hypoglycemic_Event`
- `Hyperglycemic_Excursion`
- `Overnight_Hyperglycemia`
- `High_Variability_Window`

Most common event in the current export:

- `TIR_Episode`: 16,898 rows

This file gives the synthetic dataset a direct glucose-event channel that can be analyzed together with the aligned phone, EMA, ring, and watch data.

## What Is Explicitly Excluded During Synthesis

`warp_loneliness_to_cg.py` deliberately skips:

- `weekly.csv`
- `AWARE/extracted_features.csv`
- `event_labels.csv`
- `event_labels_daily.csv`

This means the synthetic export contains the rawer event-based and summary streams, but not the precomputed weekly surveys or the LONELINESS event-detection outputs.

## Important Interpretation Notes

### 1. Synthetic participant identity is not biological identity

`CGMacros-001` in the synthetic export is not the original LONELINESS participant whose data appears inside the folder. It is a synthetic container keyed to a CG study participant/day schedule.

### 2. Alignment is activity-driven

The matching objective is based on activity MET patterns, not on demographics, sleep chronotype, meal timing, or psychological similarity.

### 3. The merge is asymmetric

The export primarily takes LONELINESS modalities and re-times them into CGMacros space. It is not a full bidirectional reconciliation of all modalities.

### 4. Daily files are day-matched, not minute-matched

Files such as:

- `Oura/activity_daily.csv`
- `Oura/readiness_daily.csv`
- `Oura/sleep_daily.csv`
- `Ema/daily.csv`

are attached to the synthetic CG day as daily summaries. Their `cg_*` feature columns are present in the header but are typically empty because there is no single aligned CG minute row used to populate them.

### 5. Privacy-sensitive raw signals are already abstracted

The original `LONELINESS-DATASET` documentation indicates that:

- raw GPS is removed
- app names are mapped into categories
- raw watch signals are not released
- some text fields are de-identified

The synthetic export inherits these privacy-preserving limitations.

## Recommended Uses

This synthetic dataset is well suited for:

- multimodal feature engineering
- prototyping loneliness or social-state prediction models with CG context
- event-conditioned analysis around glucose excursions
- representation learning across phone, EMA, Oura, Samsung, and CG channels
- pipeline testing for downstream PCU workflows

It is less appropriate for:

- causal inference about real same-person physiology and behavior
- validating clinical associations as if the streams were natively co-collected
- participant-level interpretation without checking provenance fields

## How To Read The Dataset Safely

When using the synthetic export, a good minimum practice is:

1. join or filter using `cg_participant` and `cg_date` for the synthetic analysis view,
2. retain `lon_participant` and `lon_date` for provenance tracking,
3. treat `cg_timestamp` and `lon_timestamp` as an alignment relationship, not as original co-measured time,
4. handle daily files separately from minute/event-level files,
5. avoid assuming that missing files imply missing CG data; some absences come from the source LONELINESS participant template.

## Regenerating The Synthetic Dataset

The current repository suggests the following generation order:

1. run `met_day_match_dtw.py`
2. run `warp_loneliness_to_cg.py`

Key defaults from the code:

- LONELINESS root: `LONELINESS-DATASET`
- CG root: `CGMacros`
- output root: `output/cg_augmented`
- match table: `output/cg_day_matches.csv`
- DTW band: 120 minutes

## Related Project Documentation

For the source datasets and derived labels, the most relevant existing files in this project are:

- `LONELINESS-DATASET/README.md`
- `LONELINESS-DATASET/DATASET_SUMMARY.md`
- `LONELINESS-DATASET/AWARE_FEATURE_GLOSSARY.md`
- `LONELINESS-DATASET/EVENT_LABELS_README.md`
- `output/cg_augmented/README.md`

## Bottom Line

The synthetic dataset in this project is a **CGMacros-timeline version of the LONELINESS multimodal dataset**, created by MET-based day matching plus DTW timestamp warping. It provides a practical fused dataset for modeling and exploratory analysis, but it must always be interpreted as a **synthetic alignment artifact with explicit provenance**, not as naturally co-collected real-world ground truth.
