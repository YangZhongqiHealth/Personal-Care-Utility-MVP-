# Synthetic Data Construction

This project uses a synthetic multimodal fusion process to create PCU-ready participant folders from two real datasets:

- `CGMacros`: glucose-centered records with meals, METs, and related physiological/contextual fields
- `LONELINESS-DATASET`: multimodal behavioral sensing data including AWARE, EMA, Oura, and Samsung-derived features

The output is not a naturally co-collected single-cohort dataset. It is a synthetic alignment product.

## Core Idea

For each CGMacros participant-day:

1. find the most behaviorally similar day in the loneliness dataset
2. align the minute-level activity traces with dynamic time warping
3. rewrite loneliness-study rows onto the CGMacros timeline
4. preserve provenance fields so every synthetic row can still be traced back to its source participant-day

## Pipeline Stages

### 1. Day-level matching

`data_pipeline/met_day_match_dtw.py` computes a 24-hour activity profile for each day in both datasets:

- `CGMacros` uses `METs`
- `LONELINESS-DATASET` uses `activity_met_1min`

The script z-scores each daily profile and picks the best source day by cosine similarity. It writes:

- `mergedataPCU/output/cg_day_matches.csv`

### 2. Minute-level alignment

The same script performs dynamic time warping on the matched minute-level MET traces. It writes:

- `mergedataPCU/output/cg_to_lon_dtw_map.csv`

Those mappings let the later warp step translate loneliness-study timestamps onto the CGMacros timeline.

### 3. Synthetic export

`data_pipeline/warp_loneliness_to_cg.py` uses the day matches and DTW map to produce:

- `mergedataPCU/output/cg_augmented/`

Each synthetic participant folder is named after a CGMacros participant and mirrors the loneliness dataset modality layout:

- `AWARE/`
- `Ema/`
- `Oura/`
- `Samsung/`
- `cg_events.csv`

## Provenance Fields

Synthetic CSVs intentionally carry both target identity and source identity:

- `cg_participant`
- `cg_date`
- `cg_timestamp`
- `lon_participant`
- `lon_date`
- `lon_timestamp`

Many files also include `cg_*` feature columns copied from the aligned CGMacros row. That allows downstream code to reason jointly over the synthetic behavioral data and the matched glucose context.

## CGM Event Derivation

After the synthetic export is written, `data_pipeline/scripts/detect_cgm_events.py` scans each subject folder and produces `cg_events.csv` from the aligned glucose signals. This creates event labels such as:

- `Rapid_Glucose_Rise`
- `Rapid_Glucose_Fall`
- `Hyperglycemic_Excursion`
- `Hypoglycemic_Event`

## How To Describe The Dataset Publicly

Use language like:

- "synthetic multimodal fusion dataset"
- "cross-study alignment product"
- "time-warped synchronization of independently collected datasets"

Avoid language that implies the modalities were observed in the same individual at the same real-world moment.

## Recommended Public Release Pattern

- Publish the pipeline code and documentation in GitHub.
- Publish only a small redacted sample in-repo.
- Host the full synthetic release outside git history if redistribution is allowed.
- Keep the raw source datasets outside the public repository unless you have explicit permission to redistribute them.
