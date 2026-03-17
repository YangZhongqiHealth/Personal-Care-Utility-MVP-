# PCU MVP (Minimal)

This MVP includes:
- A backend that replays objective sensor streams and exposes paper-aligned PCU outputs via JSON.
- A static UI that replays those outputs using the same component names shown in the PCU paper figure:
  - Event Extraction & Personiclie Engine
  - State Estimation Module
  - Contextual Inference Engine
  - Knowledge Base
  - Guidance Generator
  - Orchestration Layer
  - Guardian Agent
  - Interfacing Layer
- Data channels grouped as:
  - Objective Data
  - Subjective Data
  - Inferred Data
  - Conversation Aquired Data

Current dataset behavior:
- Objective Data is populated from CGM/activity/sleep streams.
- Subjective Data, Inferred Data, and Conversation Aquired Data remain empty for this dataset.
- Agent routing is event-driven:
  - Sleep Expert Agent on detected wake-up and pre-bed reminder timing.
  - Diabetes Agent on glucose-state transitions, post-meal risk, and exercise glucose-risk windows.
  - Wellness Agent on proactive meal/exercise behavior optimization windows.
  - Medical Agent on severe glucose excursions (e.g., very high/very low thresholds) with escalation.
- Knowledge Base uses local curated entries from **ADA Standards of Care in Diabetes-2026** (Section 5/6 recommendations) in `mvp/backend/knowledge/diabetes_guidelines.json`.
- Personal Machine Learning model (inside Personicle engine) predicts daily loneliness level at wake-up and runs daytime loneliness monitoring (`feeling_lonely_detected` is emitted when high risk is detected).
- Personal Causal Analysis (inside Personicle engine) triggers on every `meal_logged` event and emits a counterfactual glucose trajectory.
- Guardian Agent safety-screens every timeline step before interface rendering and applies urgent framing when risk is severe.
- Interfacing Layer supports UI switching across:
  - `Chatbot`: patient-facing conversational recommendation.
  - `Dashboard`: compact KPI/state snapshot for self-tracking.
  - `Caregiver portal`: risk-oriented handoff with rationale and knowledge references.

## Run the backend + UI

Serve the repo root and the API:

```
python -m mvp.backend.server --port 8000
```

Then visit `http://localhost:8000/mvp/ui/`.

Optional query params:
- `?dataset=CGMacros-015`
- `&participant=pers2003`
- `&max_meals=6`
