# PCU Agent Runtime Design (MVP)

## Purpose
Define exactly what agents do after they are triggered, and how they collaborate with:
- Event Extraction & Personiclie Engine
- State Estimation Module
- Contextual Inference Engine
- Knowledge Base
- Guidance Generator
- Orchestration Layer
- Interfacing Layer

This design is optimized for Type II diabetes management with the current objective-only dataset.

## Core Principle
Agents should not directly output user-facing text.

Agents produce **structured intervention proposals**.
Orchestration Layer resolves priorities/conflicts.
Guidance Generator produces final user-facing recommendations.

## Runtime Stages (Per Triggered Event)
1. Event Extraction & Personiclie Engine emits event (meal, glucose-state transition, exercise, wake, pre-bed).
2. State Estimation Module computes current risk/state snapshot.
3. Contextual Inference Engine builds contextual features (time-of-day, sleep context, post-meal window, exercise context).
4. Orchestration Layer decides which agent(s) to call.
5. Called agent(s) read relevant Knowledge Base entries and create structured recommendations.
6. Orchestration Layer merges recommendations into a ranked action plan.
7. Guidance Generator renders patient-facing output (what happened, why, what to do next).
8. Interfacing Layer delivers output to channel(s) and records response metadata.

## Agent Contract
Each called agent must return this payload:

```json
{
  "agent": "Diabetes Agent",
  "trigger_event": "glucose_state_transition",
  "priority": "P1",
  "recommended_actions": [
    {
      "id": "walk_10min",
      "type": "behavioral",
      "timing": "now",
      "instruction": "Take a 10-15 min walk",
      "expected_effect": "reduce post-meal peak",
      "confidence": 0.72
    }
  ],
  "rationale": [
    "glucose changed from TIR to TAR_Level1",
    "post-meal risk pattern present"
  ],
  "evidence_refs": ["ADA-PPG-TARGET", "ADA-SOC-2026-PA"],
  "safety_flags": [],
  "follow_up": {
    "check_after_min": 30,
    "check_signal": "glucose"
  }
}
```

## Priority Policy
- `P0`: immediate safety risk (severe hypo/hyper, rapid fall with low glucose)
- `P1`: near-term actionable risk (state transition to actionable, risky post-meal/exercise pattern)
- `P2`: optimization/coaching (habit and schedule improvements)
- `P3`: informational only

Orchestration always executes the highest-priority safe plan first.

## Agent-Specific Behavior

### Diabetes Agent
Called when:
- Glucose enters actionable state (`TBR*`, `TAR*`, `Hypoglycemic_State`, `Hyperglycemic_State`)
- Rapid glucose rise/fall events
- Post-meal checkpoint risk (e.g., high absolute glucose or large delta)
- During/after exercise with glycemic risk

Must do:
1. Pull event-local objective data window (current, -30m, +planned follow-up).
2. Read KB entries tagged `glucose_state`, `post_meal`, `exercise`, `hypoglycemia`.
3. Generate 1-3 concrete actions with timing + expected effect.
4. Attach follow-up measurement plan.
5. Mark safety escalation if criteria met.

Output focus:
- Immediate stabilization
- Next measurable check
- Short actionable behavior

### Sleep Expert Agent
Called when:
- Wake event detected
- 30 minutes before typical bedtime
- Sleep-linked risk amplification context (e.g., poor sleep + glucose volatility)

Must do:
1. Pull sleep rhythm context (prior sleep score, inferred wake/bed schedule).
2. Read KB entries tagged `sleep`, `diabetes_general`.
3. Produce sleep-aware recommendations that affect next glucose window.
4. Add day-plan (morning) or pre-bed routine (night).

Output focus:
- Morning: day setup (meal load/activity timing)
- Evening: pre-bed routine and risk reduction

### Wellness Agent (optional in MVP)
Called when:
- No immediate medical risk but behavior adherence opportunities exist.

Must do:
- Convert selected plan into low-friction daily habit nudges.

### Medical Agent (optional in MVP)
Called when:
- Repeated P0/P1 events exceed threshold over rolling window.

Must do:
- Produce escalation recommendation (care-team review trigger), not diagnosis.

## Knowledge Base Retrieval Policy
Input to retrieval:
- `event_type`
- `active_tags`
- `priority`
- `agent`

Retrieval rule:
- top-k = 2-3 references with highest tag overlap + priority relevance.

Current local KB file:
- `mvp/backend/knowledge/diabetes_guidelines.json`

Minimum evidence in final recommendation:
- At least 1 guideline reference ID for any P0/P1 recommendation.

## Orchestration Layer Decision Logic
For each event:
1. Build `call_set` of agents from trigger matrix.
2. Invoke agents in priority order (`Diabetes`, `Sleep`, `Wellness`, `Medical` by event context).
3. Collect proposals.
4. Apply conflict rules:
   - Safety actions override optimization actions.
   - If two actions conflict in timing, keep higher priority and defer lower one.
5. Select final plan (max 2 user actions at once for clarity).
6. Send selected plan to Guidance Generator.

## Guidance Generator Responsibilities
Input:
- selected plan + rationale + evidence refs + state snapshot.

Output format:
- `title`
- `what_happened`
- `why` (2 bullets max)
- `try_next_time` (single clear instruction)
- optional `follow_up` instruction

Style rules:
- Action-first, short, non-judgmental.
- Must include concrete timing when available.
- Must not expose internal reasoning chains.

## Interfacing Layer Responsibilities
- Deliver recommendation payload to UI surfaces.
- Preserve provenance metadata (which agent, which KB refs, confidence).
- Log whether recommendation was delivered (for future personalization loop).

## Trigger Matrix (MVP)

| Event | Agent(s) | Expected Action Type |
|---|---|---|
| `glucose_state_transition` actionable | Diabetes | corrective/safety/monitoring |
| `post_meal_check` risky | Diabetes | post-meal intervention |
| `peak_detected` risky | Diabetes | mitigation + next-meal adjustment |
| `exercise_ended` risky | Diabetes | recovery monitoring |
| `sleep_wake_detected` | Sleep Expert | day planning |
| `sleep_pre_bed_reminder` | Sleep Expert | pre-bed routine |
| poor sleep + glucose volatility | Sleep Expert + Diabetes | combined plan |

## Safety and Guardrails
- No diagnosis text.
- No medication dosage instructions.
- For severe risk: suggest immediate care-plan action and escalation pathway.
- Always keep recommendation auditable via `evidence_refs`.

## Data Contract Additions (Recommended)
Add these optional fields to each timeline event:
- `agent_calls`: called agents + trigger + priority
- `kb_refs`: selected guideline IDs
- `final_plan`: structured selected actions
- `delivery`: channel + timestamp + success

These fields make investor demo clearer and support later online learning.

## Why This Design Improves Investor Demo
- Shows clear separation of responsibilities (agents vs guidance rendering).
- Makes orchestration traceable and explainable.
- Demonstrates evidence-grounded personalization, not generic chatbot behavior.
- Supports extensibility to multi-condition care without rewriting UI contract.
