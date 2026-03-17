# Synthetic Data Pipeline

This folder contains the publishable code that turns two local real-data sources into a PCU-ready synthetic multimodal dataset.

## Local Inputs

By default, the scripts expect these local folders to exist:

- `mergedataPCU/CGMacros/`
- `mergedataPCU/LONELINESS-DATASET/`

Outputs are written to:

- `mergedataPCU/output/`

## Pipeline Order

### 1. Match participant-days and generate DTW mappings

```bash
python data_pipeline/met_day_match_dtw.py
```

Main outputs:

- `mergedataPCU/output/cg_day_matches.csv`
- `mergedataPCU/output/cg_to_lon_dtw_map.csv`

### 2. Warp loneliness-study rows onto the CGMacros timeline

```bash
python data_pipeline/warp_loneliness_to_cg.py
```

Main output:

- `mergedataPCU/output/cg_augmented/`

### 3. Derive CGM event labels for each synthetic participant

```bash
python data_pipeline/scripts/detect_cgm_events.py
```

Main output:

- `mergedataPCU/output/cg_augmented/<participant>/cg_events.csv`

## Important Notes

- The scripts are designed for local reproduction, not direct publication of the raw datasets.
- The synthetic export should preserve provenance fields linking every row back to its source participant-day.
- If you change local data locations, use the command-line flags on the scripts rather than editing paths inline.
