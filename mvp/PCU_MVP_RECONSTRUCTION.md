# PCU MVP Reconstruction (Paper-Aligned Components)

## Goal

This document reconstructs the current MVP around the component names in the PCU paper figure, while staying faithful to the datasets currently available in this repository.

## Paper Component Names Used As-Is

1. Event Extraction & Personiclie Engine
2. State Estimation Module
3. Contextual Inference Engine
4. Knowledge Base
5. Guidance Generator
6. Orchestration Layer
7. Interfacing Layer

Data channels used as-is:

1. Objective Data
2. Subjective Data
3. Inferred Data
4. Conversation Aquired Data

## Current MVP System Boundary

- Runtime: static batch replay, no live streaming.
- Main API: `GET /api/pcu`.
- Primary dataset: `CGMacros-015`.
- Primary implementation file: `mvp/backend/pcu_pipeline.py`.
- UI renderer: `mvp/ui/app.js`.

## End-to-End Dataflow (Current MVP)

1. Objective Data ingestion from `Oura/activity_1min.csv` and `Oura/sleep_daily.csv`.
2. Event Extraction & Personiclie Engine detects:
   - meal episodes,
   - glucose-state transitions from CGM values,
   - exercise start/end windows from MET stream,
   - sleep wake/pre-bed touchpoints from sleep rhythm signals.
3. State Estimation Module computes glucose trajectory metrics and contextual state snapshots.
4. Contextual Inference Engine tags event context (`after meal`, `during exercise`, `person is up`, etc.).
5. Knowledge Base applies Type II diabetes and sleep guidance policies to actionable events.
6. Guidance Generator composes event-specific nudges.
7. Orchestration Layer selects specialized agents:
   - Diabetes Agent for actionable glucose and meal/exercise risk events,
   - Sleep Expert Agent for wake-up and pre-bed interventions.
8. Interfacing Layer emits user-facing cards via `user_output`.

## Component-by-Component Reconstruction

### 1) Event Extraction & Personiclie Engine

Implemented behavior:

- Detect meal events using `cg_Meal Type`.
- Deduplicate repeated meal rows.
- Build `MealEpisode` windows over `[-30, +180]` minutes.
- Detect glucose-state transitions directly from CGM stream.
- Detect rapid glucose rise/fall events with lookback deltas.
- Detect exercise session start/end from MET windows.
- Detect sleep wake and pre-bed reminder events from sleep rhythm signals.

Current output artifacts:

- `event_type` values include `meal_logged`, `post_meal_check`, `peak_detected`, `glucose_state_transition`, `rapid_glucose_*`, `exercise_*`, `sleep_*`.
- Timeline-level `raw_data_received`.
- Timeline-level `data_channels`.

### 2) State Estimation Module

Implemented behavior:

- Baseline glucose from pre-meal window.
- Peak glucose and time-to-peak from post-meal window.
- Delta glucose and post-meal activity summary.
- Glycemic-state classification directly from objective glucose values (`TIR`, `TBR`, `TAR` + severity).
- Exercise and sleep contextual state snapshots.

Current output artifacts:

- `state_snapshot` with baseline/peak/delta/activity/state semantics.
- `decision_snapshot` confidence and intervention flags.

### 3) Contextual Inference Engine

Implemented behavior:

- Event context tagging (`after meal`, `post-meal trajectory`, `during exercise`, `after exercise`, `person is up`, `pre-bed routine`).
- Sleep rhythm inference from available sleep timing fields.

Current output artifacts:

- `component_outputs["Contextual Inference Engine"]`.

### 4) Knowledge Base

Implemented behavior:

- Loads local guideline entries from `mvp/backend/knowledge/diabetes_guidelines.json`.
- Uses in-memory statistical evidence from participant history:
  - spike probability by meal type and carb bucket,
  - activity effect,
  - sleep effect,
  - late-dinner effect.

Current output artifacts:

- `why` lines in `user_output`.
- `component_outputs["Knowledge Base"]` for diabetes and sleep policies.

### 5) Guidance Generator

Implemented behavior:

- Allowed recommendation types:
  - post-meal walk,
  - reduce carbs,
  - shift dinner earlier,
  - exercise recovery guidance,
  - sleep wake/pre-bed guidance.
- Guidance emitted when event context is actionable.

Current output artifacts:

- `decision_snapshot.selected_lever`.
- `user_output.try_next_time`.

### 6) Orchestration Layer

Implemented behavior:

- Routes specialized agents by event trigger:
  - Diabetes Agent on actionable glucose-state transitions, meal risk checkpoints, and exercise-related risk.
  - Sleep Expert Agent on detected wake-up and 30-minute pre-bed reminders.

Current output artifacts:

- `component_outputs["Orchestration Layer"]` with event-specific agent activation reasons.
- `decision_snapshot.selected_agent` set per actionable event.

### 7) Interfacing Layer

Implemented behavior:

- Emits user-facing event cards (`title`, `what_happened`, `why`, `try_next_time`).
- UI renders cards for sleep, meal, glucose-transition, and exercise risk interventions.

Current output artifacts:

- `user_output` object.
- `component_outputs["Interfacing Layer"]` marks delivery to user-facing surfaces when active.

## Data Channel Reconstruction With Current Dataset

### Objective Data

- Populated from meal/carbs/glucose/MET/sleep timestamp records and state timestamps.

### Subjective Data

- Not present in this MVP dataset path.
- Channel remains explicit and visible as empty when unavailable.

### Inferred Data

- Kept explicit but empty in this dataset-backed MVP run.

### Conversation Aquired Data

- Not present in this MVP dataset path.
- Channel remains explicit and visible as empty when unavailable.

## API Contract Notes (Current)

- `meta.component_names` returns the paper component names used by the UI.
- `meta.data_channel_names` returns the paper data-channel names used by the UI.
- Every timeline entry may include:
  - `raw_data_received` (legacy compatibility),
  - `data_channels` (paper-aligned grouped representation),
  - `activated_components`,
  - `component_outputs`,
  - `state_snapshot`,
  - `decision_snapshot`,
  - `user_output` (Interfacing Layer output).

## What Is Still Out of Scope

- Live streaming and real-time adaptation.
- Multimodal inferred data from voice/facial channels.
- True conversation memory channel.
- Full multi-agent specialization with independent model policies.

## Summary

The MVP is now reconstructed around the PCU paper component names and data channel labels while preserving the existing dataset-driven implementation.
