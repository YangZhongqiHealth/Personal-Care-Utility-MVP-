# Architecture Overview

The repository has two main execution paths:

- `mvp/`: the runnable PCU MVP application
- `data_pipeline/`: the synthetic-data preparation pipeline used to build PCU-ready multimodal inputs

## MVP Runtime

The MVP app is served by `mvp/backend/server.py`. It exposes:

- static UI assets from `mvp/ui/`
- a JSON API at `/api/pcu`

The API delegates payload construction to `mvp/backend/pcu_pipeline.py`, which:

- loads a dataset directory
- derives meal- and glucose-centered events
- builds state, context, knowledge-base, and guidance outputs
- returns a paper-aligned payload for the frontend replay UI

## Synthetic Data Pipeline

The synthetic-data flow is intentionally separate from the app runtime:

1. `data_pipeline/met_day_match_dtw.py`
   matches CGMacros participant-days to the most similar day from the loneliness dataset using hourly MET profiles and minute-level DTW.
2. `data_pipeline/warp_loneliness_to_cg.py`
   rewrites loneliness-study rows onto the CGMacros timeline using the alignment outputs.
3. `data_pipeline/scripts/detect_cgm_events.py`
   derives CGM event labels from the resulting synthetic multimodal export.

## Local Data Staging

The current workspace keeps local source datasets and outputs under `mergedataPCU/`:

- `mergedataPCU/CGMacros/`
- `mergedataPCU/LONELINESS-DATASET/`
- `mergedataPCU/output/`

This staging area is useful for local reproduction but should not be treated as public-by-default content.
