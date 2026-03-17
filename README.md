# PCU MVP

PCU MVP is a minimal end-to-end prototype for a Personal Chronic-care Unit workflow. The repository contains:

- a runnable MVP app under `mvp/`
- a synthetic-data preparation pipeline under `data_pipeline/`
- documentation that explains how the PCU demo and synthetic dataset are constructed

The current local workspace also contains raw and generated datasets under `mergedataPCU/`, plus a local synthetic participant folder at `CGMacros-015/`. Those data directories are intentionally treated as local artifacts first and GitHub content second.

## Repository Layout

```text
.
├── README.md
├── data/
│   ├── README.md
│   └── sample_synthetic/
├── data_pipeline/
│   ├── README.md
│   ├── met_day_match_dtw.py
│   ├── warp_loneliness_to_cg.py
│   └── scripts/
├── docs/
│   ├── architecture.md
│   ├── data-governance.md
│   ├── synthetic-data.md
│   ├── demo/
│   └── design/
├── mergedataPCU/
│   ├── CGMacros/
│   ├── LONELINESS-DATASET/
│   └── output/
└── mvp/
    ├── backend/
    ├── scripts/
    └── ui/
```

## What Belongs In GitHub

Commit these by default:

- `mvp/`
- `data_pipeline/`
- `docs/`
- `data/README.md`
- project metadata such as `.gitignore` and `pyproject.toml`

Do not commit by default:

- raw source datasets in `mergedataPCU/CGMacros/`
- raw source datasets in `mergedataPCU/LONELINESS-DATASET/`
- generated synthetic outputs in `mergedataPCU/output/`
- local sample data in `CGMacros-015/`
- legacy materials in `archive/old_pcu_simple_using_tom/`

Review the policy in `docs/data-governance.md` before the first public push.

## Quick Start

### Run the MVP app

```bash
python -m mvp.backend.server --port 8000
```

Then open `http://localhost:8000/mvp/ui/`.

### Build the synthetic alignment artifacts

```bash
python data_pipeline/met_day_match_dtw.py
python data_pipeline/warp_loneliness_to_cg.py
python data_pipeline/scripts/detect_cgm_events.py
```

By default, those commands read from the local raw-data staging area under `mergedataPCU/` and write outputs to `mergedataPCU/output/`.

## Documentation Map

- `docs/architecture.md`: PCU MVP system overview and runtime structure.
- `docs/synthetic-data.md`: how the synthetic PCU-ready dataset is created from two real datasets.
- `docs/data-governance.md`: what to publish, what to exclude, and how to describe provenance.
- `data_pipeline/README.md`: exact pipeline inputs, outputs, and commands.
- `docs/demo/`: demo playback artifacts and narrative materials.
- `docs/design/`: original design notes kept for reference.

## Recommended First GitHub Commit

Before creating the repo, verify that `git status --short` does not include raw data, generated archives, or sensitive legacy folders. The intended first commit is the code, documentation, and repo scaffolding only.
