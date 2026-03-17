# MVP Design Document  
## Post-Meal Glucose Coach for Type II Diabetes

### Audience
- Machine Learning Engineers (MLE)
- Software Engineers (SWE)

### Scope
This document specifies the **minimum viable product (MVP)** design for a **Type II diabetes application** that:
- Analyzes post-meal glucose behavior
- Identifies personalized spike patterns
- Generates a **single, low-risk behavioral recommendation per meal**

This MVP intentionally excludes medication advice, diagnosis, and real-time clinical decision making.

---

## 1. Product Objective

### User Value Proposition
Help a Type II diabetes user understand **why their glucose spikes after meals** and provide **one actionable suggestion** to reduce similar spikes in the future.

### Target Outcome
- Reduce post-prandial glucose excursions (1–3 hours after meals)
- Improve user understanding of personal glucose patterns

---

## 2. Non-Goals (Explicitly Out of Scope)

The MVP **must not**:
- Recommend medication changes or dosing
- Provide diagnosis or emergency medical advice
- Optimize long-term weight loss or HbA1c directly
- Support multi-goal reasoning or clinician workflows
- Perform real-time alerts or continuous nudging

---

## 3. Data Sources (Minimal Subset)

### Required Inputs

#### CGMacros (1-min resolution)
- glucose (mg/dL)
- meal timestamp
- meal carbohydrates (grams)
- METs (activity intensity)

#### Oura
- sleep_daily:
  - sleep duration
  - sleep efficiency
- readiness_daily (optional but recommended)

### Optional (Deferred)
- Samsung HRV
- EMA affect
- AWARE social events

---

## 4. System Overview

### High-Level Pipeline

Raw Data Ingestion
↓
Meal-Centered Event Builder
↓
Post-Meal Glucose Analyzer
↓
Recommendation Generator


Each meal is treated as an independent analysis unit.

---

## 5. Core Data Abstractions

### 5.1 Observation (Raw Input)

Each data source is ingested and stored **without early alignment**.

Fields:
- timestamp_start
- timestamp_end (optional)
- source (CGMacros / Oura)
- values (raw columns)
- quality_flags

---

### 5.2 MealEpisode (Core Working Unit)

All analysis operates on `MealEpisode`.

A `MealEpisode` represents a **single meal and its glucose response window**.

#### Fields
- meal_time
- carbs_g
- glucose_series:
  - window: [−30 min, +180 min] relative to meal_time
  - 1-min resolution
- baseline_glucose:
  - mean glucose in [−30, 0] min window
- peak_glucose:
  - max glucose in [+0, +180] min window
- delta_glucose:
  - peak_glucose − baseline_glucose
- time_to_peak (minutes)
- post_meal_activity:
  - MET-minutes in [+0, +120] min window
- prior_sleep_quality:
  - derived from previous night’s sleep_daily
- spike_label:
  - boolean (e.g., peak_glucose ≥ 180 mg/dL)
- confidence:
  - data completeness and signal quality score

---

## 6. MealEpisode Construction Logic

### Step 1: Detect Meals
- Use CGMacros meal entries as ground truth
- Ignore meals with missing carb values

### Step 2: Extract Glucose Window
- Slice CGM data around each meal
- Reject meals with insufficient glucose coverage

### Step 3: Compute Metrics
- Baseline glucose
- Peak glucose
- Delta glucose
- Time to peak

### Step 4: Attach Context
- Aggregate METs post-meal
- Attach prior night sleep quality

---

## 7. Post-Meal Analysis Module

### Purpose
Identify **personalized patterns** that explain glucose spikes.

### Analysis Strategy (MVP)

All analysis is **within-person** (n-of-1).

For each user:
1. Group MealEpisodes by:
   - similar carb range (e.g., ±10g)
   - time of day (breakfast / lunch / dinner)
2. Compare spike statistics across:
   - with vs without post-meal activity
   - good vs poor sleep nights

### Output
For each meal category:
- spike_probability
- average_delta_glucose
- effect size of post-meal activity
- effect size of sleep quality

---

## 8. Recommendation Generator

### Design Principle
At most **one recommendation per meal**, only when confidence is high.

### Allowed Recommendation Types (MVP)
1. Add a short post-meal walk (10–15 min)
2. Reduce carbohydrate load at that meal
3. Shift meal earlier (for late dinners)

### Selection Logic
Choose the recommendation that:
- Has strongest historical benefit for this user
- Has lowest effort and risk
- Has sufficient supporting data

---

## 9. Recommendation Output Schema

Each recommendation must include:

- **What happened**
  - Objective description of the glucose response
- **Why (personalized explanation)**
  - Reference to user’s own historical data
- **What to try next time**
  - One concrete, low-risk action
- **How success will be evaluated**
  - Specific metric (e.g., peak glucose reduction)

---

## 10. User Interface Contract

### Screen 1: Meal Insight (Required)

For a single meal:
- Glucose curve visualization
- Short textual explanation
- One recommendation

### Screen 2: Daily Summary (Optional)
- Worst spike today
- Best-controlled meal
- Suggested experiment for next day

No additional dashboards are required for MVP.

---

## 11. Safety & Compliance Constraints

The system must:
- Use non-directive language (“may help”, “you could try”)
- Avoid any medication or dosing suggestions
- Escalate only with generic guidance:
  - “Consider following your care plan or contacting your clinician”

---

## 12. MVP Evaluation Metrics (Offline)

### Model-Free Metrics
- Spike vs non-spike separability
- Consistency of personalized patterns
- Coverage (% meals with confident recommendation)

### Behavior Impact Proxies
- Reduction in peak glucose
- Reduction in delta_glucose
- Improved time-to-peak

---

## 13. Deployment Notes

### MVP Assumptions
- Batch processing (daily or weekly)
- No real-time constraints
- Single-user context per pipeline run

### Future Extensions (Not MVP)
- HRV-based stress inference
- Real-time nudges
- Multi-agent orchestration
- Causal modeling

---

## 14. Summary

This MVP:
- Focuses on one high-impact diabetes problem
- Uses minimal data and simple abstractions
- Is fully buildable with current datasets
- Provides clear expansion paths without re-architecture

End of document.
