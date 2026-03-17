# PCU MVP Demo Documentation (Professor Review)

## 1) High-Level Idea
The **Personalized Care Unit (PCU)** is an AI-driven health support system that continuously learns from one person’s own day-to-day data and gives timely, personalized guidance.

In this MVP, the use case is Type II diabetes support with safe, behavior-oriented, explainable recommendations.

## 2) Inputs to PCU (Multimodal, User-Owned)
PCU is designed to use **holistic multimodal data from the user themself**, organized into four channels:

- **Objective Data**: wearable/passive streams (glucose, activity, sleep, meal logs).
- **Subjective Data**: self-report (mood, stress, reflections, symptom check-ins).
- **Inferred Data**: model-derived states/risks from observed signals.
- **Conversation Acquired Data**: details gathered during dialogue with PCU.

In the current MVP dataset, Objective Data is the primary populated channel. The other channels are still explicit in the architecture, so they can be added without redesigning the pipeline.

## 3) Component-by-Component Explanation
### 3.1 Event Extraction & Personicle Engine
- Converts continuous raw streams into meaningful events.
- Detects meal events, glucose transitions, rapid rise/fall, exercise start/end, wake-up, and pre-bed windows.
- Includes personal modeling signals in the MVP:
  - personal ML monitoring (day-level loneliness risk),
  - personal causal analysis on meal events (counterfactual meal-response projection).

### 3.2 State Estimation Module
- Maintains current health state from the event context.
- Computes practical metrics such as baseline glucose, post-meal peak, delta, trend risk, exercise recovery context, and sleep recovery indicators.
- Produces structured snapshots that later modules can reason over.

### 3.3 Contextual Inference Engine
- Interprets “what situation the person is in now.”
- Examples: after meal, post-meal trajectory, during exercise, wake-up window, pre-bed window, daytime social-energy monitoring.
- Converts raw numbers into situational meaning for decision logic.

### 3.4 Knowledge Base
- Supplies medically grounded policy context and practical behavior guidance constraints.
- In MVP, this includes local diabetes guideline entries and rule-linked tags (post-meal, glucose-state, hypoglycemia, exercise, sleep).
- Ensures recommendations are anchored to known care principles.

### 3.5 Guidance Generator
- Turns state + context + policy into user-ready actions.
- Creates concise suggestions such as:
  - short post-meal walk,
  - moderate carb adjustment,
  - earlier dinner timing,
  - exercise safety/recovery check,
  - sleep timing support.
- Keeps messages action-focused and low-risk.

### 3.6 Orchestration Layer (Multi-Agent Coordinator)
- Selects which specialist agent(s) should act:
  - **Diabetes Agent** for glucose/meal/exercise glycemic control.
  - **Sleep Expert Agent** for wake and bedtime planning.
  - **Wellness Agent** for behavioral and day-structure support.
  - **Medical Agent** for severe risk escalation contexts.
- Supports single-agent and multi-agent coordination on the same event.

### 3.7 Guardian Agent (Safety Gate)
- Safety-screens generated guidance before delivery.
- Adds caution or urgent framing if risk is high (for example severe hypo/hyperglycemia context).
- Prevents unsafe or overconfident messaging from reaching end users.

### 3.8 Interfacing Layer
- Delivers final guidance in user-facing form.
- MVP supports three views:
  - **Chatbot** (natural-language coaching),
  - **Dashboard** (quick status and key metrics),
  - **Caregiver portal** (risk-oriented handoff summary).
- Standard user message format includes:
  - what happened,
  - why it matters,
  - what to do next.

## 4) One-Day Workflow Example (End-to-End)
Below is an example of how one day can run in PCU:

1. **Morning wake detection (around wake time)**
- Input: sleep and activity-derived wake context.
- PCU action: Sleep Expert Agent triggers a morning check-in plan.
- User deliverable: morning card with recovery-aware guidance for meals and movement.

2. **Breakfast logged**
- Input: meal time, carbs, current glucose, recent activity.
- PCU action: meal event created; baseline glucose state estimated; proactive meal-start plan generated.
- User deliverable: “Meal Start Plan” with a concrete low-risk action.

3. **Post-meal check (~45 minutes later)**
- Input: updated glucose trend after meal.
- PCU action: if above-target/rising too fast, Diabetes Agent (and possibly Wellness/Sleep support) activates.
- User deliverable: post-meal adjustment recommendation and re-check timing.

4. **Exercise period (start and end)**
- Input: MET-based exercise detection + glucose before/during/after activity.
- PCU action: exercise safety context assessment and recovery guidance.
- User deliverable: exercise-start and exercise-recovery coaching.

5. **Daytime continuous monitoring**
- Input: ongoing glucose stream and day activity pattern.
- PCU action: glucose transition alerts and rapid rise/fall detection; daytime well-being monitor checks.
- User deliverable: targeted alerts only when actionable risk or intervention opportunity exists.

6. **Dinner and evening window**
- Input: dinner meal profile and evening glucose behavior.
- PCU action: repeat meal-response analysis; evaluate late-meal effects.
- User deliverable: dinner-specific nudge (portion/timing/movement).

7. **Pre-bed reminder (~30 min before typical bedtime)**
- Input: inferred sleep rhythm and day recovery context.
- PCU action: Sleep Expert Agent sends a wind-down support touchpoint.
- User deliverable: pre-bed recommendation to improve overnight recovery and next-day stability.

This is not a one-time report. It is a loop: **sense -> estimate -> infer context -> orchestrate -> guide -> safety-check -> deliver -> monitor again**.

## 5) Whole-PCU Deliverables to Users
Across the full system, users receive:

- **Continuous personalized monitoring** across daily life events.
- **Actionable micro-guidance** at key moments (meal, glucose change, exercise, sleep windows).
- **Safety-aware escalation framing** when risk becomes severe.
- **Explanation-rich feedback** (what happened, why, what next).
- **Multi-interface access** (chatbot, dashboard, caregiver view) for different decision needs.
- **Longitudinal personalization** that improves relevance from the user’s own historical patterns.

## 6) Scope and Safety Note
This MVP is a **decision-support and behavior-coaching** prototype.  
It does **not** provide diagnosis, medication dosing advice, or replace emergency/clinical care.
