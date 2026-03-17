
# UI Design Document  
## PCU Dataflow Explorer (Time-Based Playback UI)

### Audience
- Machine Learning Engineers (MLE)
- Software Engineers (SWE)
- Researchers / Demo Viewers

### Purpose
This UI visualizes **how PCU processes personal health data over time**.

It allows a user to:
- Step through time
- Observe which data arrive at each time step
- See how PCU components process that data
- Understand how internal state leads to a final user-facing recommendation

This UI is **not a consumer health interface**.  
It is a **debugger / explainer UI** for PCU.

---

## 1. Design Goals

1. Make PCU **transparent and inspectable**
2. Show **data → processing → decision → output**
3. Support **step-by-step time progression**
4. Be simple enough to implement in a few days
5. Use deterministic, replayable data

---

## 2. High-Level Layout (Single Screen)

The UI consists of **five vertical columns**, arranged left to right:

```

| Time Control | New Data | PCU Processing | Internal State | User Output |

```

Each column updates when time advances.

---

## 3. Column 1 — Time Controller

### Purpose
Control simulated time and playback.

### UI Elements
- Current timestamp display  
  Example:
```

Day 12 · 7:14 PM

```

- Control buttons:
- ◀ Prev
- ▶ Next (primary)
- ⏩ Jump to Event

### Behavior
- Clicking **Next** advances to the next meaningful event:
- meal logged
- glucose threshold crossed
- sleep episode start/end
- Time does **not** advance by fixed intervals.

---

## 4. Column 2 — New Data Ingested

### Purpose
Show exactly **what raw data arrived** at this time step.

### UI
A simple, read-only list.

Example:
```

New data received:
• CGMacros: meal logged (Dinner, 72g carbs)
• CGMacros: glucose = 121 mg/dL
• Oura: sleep_daily (sleep quality = low)

```

### Rules
- Raw data only
- No interpretation or aggregation
- Each item corresponds to a real data record

---

## 5. Column 3 — PCU Component Processing

### Purpose
Visualize **which PCU components activate** and what they produce.

### Layout
Stacked component cards:

```

[ Event Builder ]
Input: Meal log
Output: MealEpisode created

[ State Estimator ]
Input: Glucose, sleep
Output: Baseline glucose updated

[ Context Inference ]
Input: MealEpisode, sleep
Output: Context = just ate, poor sleep

[ Agent Orchestrator ]
Input: State, context
Output: Post-Meal Agent activated

```

### Behavior
- Only active components are highlighted
- Inactive components remain dimmed
- Each component shows **input → output**

---

## 6. Column 4 — Internal State & Decisions

### Purpose
Expose **internal PCU representations** in a human-readable form.

### State Section
```

Current State:
• Baseline glucose: 114 mg/dL
• Glucose trend: rising fast
• Sleep quality: below personal baseline
• Similar past meals: 18

```

### Decision Section
```

Decision Summary:
• Confidence: high
• Intervention available: yes
• Selected lever: post-meal activity
• Action timing: after peak confirmation

```

### Rules
- Text only (no charts)
- Derived values only
- No raw sensor data

---

## 7. Column 5 — User-Facing Output

### Purpose
Show the **exact content** delivered to the end user.

### UI
Render the real consumer-facing card.

Example:
```

What the user sees:

Dinner · 7:14 PM · 72g carbs

Your glucose rose from 118 → 196 mg/dL,
peaking 84 minutes after dinner.

Based on your past data:
• Similar dinners spike 2.4× more often
• Poor sleep increases peaks by ~18 mg/dL

Try this next time:
A 10–15 min walk after dinner reduced
your spike by ~25% on similar days.

```

### Rules
- No internal jargon
- No confidence scores
- No component names

---

## 8. Interaction Flow Example

### Step 1 — Meal Logged
- New data: meal entry
- PCU: Event Builder activates
- State updated
- No user output

### Step 2 — Glucose Rising
- New data: glucose trend
- PCU: State Estimator + Context Inference
- Decision pending
- No user output

### Step 3 — Peak Detected
- New data: glucose peak
- PCU: Agent Orchestrator triggers
- Recommendation generated
- User output displayed

---

## 9. Data Contract (UI Input)

The UI consumes a **time-indexed PCU log**.

Each timestep contains:
- timestamp
- raw_data_received[]
- activated_components[]
- component_outputs{}
- state_snapshot{}
- user_output (optional)

This enables:
- deterministic replay
- offline demos
- debugging

---

## 10. Implementation Notes

### MVP Constraints
- Static data (JSON playback)
- No live backend required
- No user input beyond time controls

### Suggested Tech
- React / Vue / Svelte
- JSON-driven rendering
- Monospaced or neutral typography

---

## 11. Non-Goals

The UI should not:
- Allow editing parameters
- Show real-time streaming
- Provide analytics dashboards
- Replace the consumer UI

---

## 12. Summary

This UI is a **PCU time-based debugger** that:
- Makes personal health reasoning transparent
- Shows how data becomes decisions
- Builds trust and alignment across engineering and research

End of document.
```

---
