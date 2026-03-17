# Data Governance And Publishing Rules

This repository mixes code with data-adjacent materials. Before making the repo public, separate content into three categories.

## Safe To Commit

- application code in `mvp/`
- synthetic-data pipeline code in `data_pipeline/`
- markdown documentation in `docs/`
- small, intentionally prepared sample data in `data/sample_synthetic/`

## Keep Out Of Public Git By Default

- `mergedataPCU/CGMacros/`
- `mergedataPCU/LONELINESS-DATASET/`
- `mergedataPCU/output/`
- `CGMacros-015/`
- `archive/old_pcu_simple_using_tom/`

These folders may contain real data, generated derivatives, or legacy materials that are not appropriate for broad redistribution.

## Public Documentation Requirements

When documenting the synthetic dataset, explicitly state:

- it is derived from two real datasets
- rows are aligned across studies by similarity matching plus DTW
- provenance fields are retained
- the result is suitable for prototyping and systems research, not for claims of original co-measurement

## Before First Push

Run these checks locally:

```bash
git init
git status --short
```

Review every staged path before the first commit. If raw data appears, add or tighten ignore rules before proceeding.
