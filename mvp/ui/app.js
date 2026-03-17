const state = {
  timeline: [],
  index: 0,
  meta: {},
  dayStarts: [],
  components: [],
  dataChannels: [],
  interfaceView: "chatbot",
  clock: {
    initialized: false,
    lastMs: null,
    hourDeg: 0,
    minuteDeg: 0,
    secondDeg: 0,
  },
};

const defaultComponents = [
  "Event Extraction & Personiclie Engine",
  "State Estimation Module",
  "Contextual Inference Engine",
  "Knowledge Base",
  "Guidance Generator",
  "Orchestration Layer",
  "Guardian Agent",
  "Interfacing Layer",
];

const defaultDataChannels = ["Objective Data", "Subjective Data", "Inferred Data", "Conversation Aquired Data"];

const componentSlots = {
  "Event Extraction & Personiclie Engine": { nodeId: "node-event", outputId: "event-output" },
  "State Estimation Module": { nodeId: "node-state", outputId: "state-output" },
  "Contextual Inference Engine": { nodeId: "node-context", outputId: "context-output" },
  "Knowledge Base": { nodeId: "node-knowledge", outputId: "knowledge-output" },
  "Guidance Generator": { nodeId: "node-guidance", outputId: "guidance-output" },
  "Orchestration Layer": { nodeId: "node-orchestration", outputId: "orchestration-output" },
  "Guardian Agent": { nodeId: "node-guardian", outputId: "guardian-output" },
  "Interfacing Layer": { nodeId: "node-interface", outputId: "interface-component-output" },
};

const orchestrationLinkTargets = [
  "node-personicle",
  "node-guidance",
  "node-guardian",
  "node-interface",
];

let plannerLinksRaf = null;

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTimestamp(iso) {
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatClockSubtitle(iso) {
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDateLabel(iso) {
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function formatFieldLabel(key) {
  return key
    .replaceAll("_", " ")
    .replaceAll("mg dL", "mg/dL")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function humanizeReasonText(text) {
  return String(text || "")
    .replaceAll(",", ", ")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim();
}

function formatScalar(value) {
  if (value == null || value === "") return "-";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return String(value);
    return value.toFixed(1);
  }
  return String(value);
}

function getDayPhase(iso) {
  const hour = new Date(iso).getHours();
  if (hour < 6) return "Overnight";
  if (hour < 12) return "Morning";
  if (hour < 17) return "Afternoon";
  if (hour < 21) return "Evening";
  return "Night";
}

function getEventFamily(eventType) {
  const type = String(eventType || "");
  if (type.includes("lonely")) return "Well-being";
  if (type.startsWith("sleep_")) return "Sleep rhythm";
  if (type.startsWith("exercise_")) return "Exercise";
  if (type.includes("meal") || type.includes("peak")) return "Meal response";
  if (type.includes("glucose") || type.includes("rapid")) return "Glucose dynamics";
  return "General";
}

function getNumericValues(entry) {
  const values = [];
  const snapshot = entry.state_snapshot || {};
  Object.values(snapshot).forEach((value) => {
    if (typeof value === "number" && Number.isFinite(value)) {
      values.push(value);
    }
  });
  return values;
}

function getRiskLevel(entry) {
  const snapshot = entry.state_snapshot || {};
  const stateText = String(snapshot.glucose_state || snapshot.current_state || snapshot.previous_state || "");
  if (
    stateText.includes("TBR_State_Level2") ||
    stateText.includes("TAR_State_Level2") ||
    stateText.includes("Hypoglycemic_State") ||
    stateText.includes("Hyperglycemic_State") ||
    stateText.includes("Rapid_Glucose_Fall_State")
  ) {
    return "High";
  }

  const nums = getNumericValues(entry);
  if (nums.some((value) => value < 70 || value > 250)) {
    return "High";
  }
  if (entry.decision_snapshot?.intervention_available) {
    return "Medium";
  }
  return "Low";
}

function estimatePriority(entry) {
  const risk = getRiskLevel(entry);
  if (risk === "High") return "P0";
  if (entry.decision_snapshot?.intervention_available) return "P1";
  if (String(entry.event_type || "").startsWith("sleep_")) return "P2";
  return "P3";
}

function getSelectedAgents(entry) {
  const selected = entry?.decision_snapshot?.selected_agents;
  if (Array.isArray(selected) && selected.length) {
    return [...new Set(selected.filter(Boolean))];
  }
  const single = entry?.decision_snapshot?.selected_agent;
  return single ? [single] : [];
}

function summarizeAgentAction(agent, entry) {
  const eventType = String(entry?.event_type || "");
  const trigger = String(entry?.decision_snapshot?.trigger_reason || "");
  const glucose = entry?.state_snapshot?.glucose_mg_dL;

  if (agent === "Medical Agent") {
    return "Escalating a severe glucose risk and prompting urgent safety steps.";
  }
  if (agent === "Diabetes Agent") {
    if (eventType.includes("rapid_glucose")) return "Interpreting fast glucose change and creating an immediate response plan.";
    if (eventType.includes("peak") || eventType.includes("meal")) return "Reviewing meal response and suggesting the best glucose-control action now.";
    if (eventType.includes("exercise")) return "Checking exercise-related glucose risk and tuning the recovery plan.";
    if (glucose != null) return `Analyzing glucose at ${Math.round(glucose)} mg/dL and tailoring diabetes guidance.`;
    return "Analyzing glucose context and generating personalized diabetes guidance.";
  }
  if (agent === "Sleep Expert Agent") {
    if (eventType === "sleep_wake_detected") return "Building a morning plan from sleep recovery and circadian timing.";
    if (eventType === "sleep_pre_bed_reminder") return "Preparing an easy pre-bed routine to support next-day glucose stability.";
    return "Using sleep rhythm signals to improve daily glucose stability planning.";
  }
  if (agent === "Wellness Agent") {
    if (eventType.includes("meal")) return "Suggesting simple behavior nudges like portion balance and short post-meal movement.";
    if (eventType.includes("exercise")) return "Turning activity signals into practical hydration, movement, and recovery tips.";
    if (trigger.includes("sleep")) return "Adjusting lifestyle suggestions to reduce the impact of low sleep recovery.";
    return "Providing practical day-to-day habit coaching from objective sensor data.";
  }
  return "Reviewing current context and coordinating the next best guidance step.";
}

function parseSignalKeys(entry) {
  const lines = entry.raw_data_received || [];
  const keys = [];
  lines.forEach((line) => {
    const match = /^RAW:\s*([^=]+)=/.exec(String(line));
    if (match) keys.push(match[1].trim());
  });
  return [...new Set(keys)];
}

function parseRawObjectiveMap(entry) {
  const rows = entry.data_channels?.["Objective Data"] || entry.raw_data_received || [];
  const map = {};
  rows.forEach((row) => {
    const match = /^RAW:\s*([^=]+)=(.*)$/.exec(String(row));
    if (!match) return;
    const key = match[1].trim();
    const value = match[2].trim();
    map[key] = value;
  });
  return map;
}

function toFiniteNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  if (!value || value === "NA" || value === "-") return null;
  const cleaned = value.replaceAll(",", "").trim();
  const parsed = Number.parseFloat(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function pickFirstNumber(...values) {
  for (const value of values) {
    const num = toFiniteNumber(value);
    if (num != null) return num;
  }
  return null;
}

function glycemicBand(glucose) {
  if (glucose == null) return "Unknown";
  if (glucose < 54) return "Critical Low";
  if (glucose < 70) return "Low";
  if (glucose <= 180) return "In Range";
  if (glucose <= 250) return "High";
  return "Very High";
}

function glucoseTrendLabel(delta) {
  if (delta == null) return "Unknown";
  if (delta >= 35) return "Rapid rise";
  if (delta >= 12) return "Rising";
  if (delta <= -35) return "Rapid fall";
  if (delta <= -12) return "Falling";
  return "Stable";
}

function metIntensityLabel(met) {
  if (met == null) return "Unknown";
  if (met < 1.5) return "Rest";
  if (met < 3) return "Light activity";
  if (met < 6) return "Moderate activity";
  return "Vigorous activity";
}

function inferKnowledgeTags(entry) {
  const type = String(entry.event_type || "");
  if (type.includes("lonely")) return ["sleep", "diabetes_general"];
  if (type.startsWith("sleep_")) return ["sleep", "diabetes_general"];
  if (type.startsWith("exercise_")) return ["exercise", "hypoglycemia", "diabetes_general"];
  if (type.includes("rapid_glucose")) return ["glucose_state", "hypoglycemia", "diabetes_general"];
  if (type.includes("glucose_state")) return ["glucose_state", "diabetes_general"];
  if (type.includes("meal") || type.includes("peak")) return ["post_meal", "glucose_state", "diabetes_general"];
  return ["diabetes_general"];
}

function deriveObjectiveSummary(entry) {
  const raw = parseRawObjectiveMap(entry);
  const snapshot = entry.state_snapshot || {};

  const glucose = pickFirstNumber(
    snapshot.glucose_mg_dL,
    snapshot.peak_glucose_mg_dL,
    snapshot.glucose_45min_mg_dL,
    snapshot.glucose_at_start_mg_dL,
    snapshot.glucose_end_exercise_mg_dL,
    raw.glucose_mg_dL,
    raw.peak_glucose_mg_dL,
    raw.cg_glucose_mg_dL
  );
  const delta = pickFirstNumber(snapshot.glucose_delta_15min, snapshot.delta_45min_mg_dL, raw.glucose_delta_15min, raw.delta_from_baseline);
  const met = pickFirstNumber(snapshot.activity_met_1min, raw.activity_met_1min);
  const sleepScore = pickFirstNumber(snapshot.sleep_score, raw.sleep_score, raw.prior_sleep_score);
  const carbs = pickFirstNumber(snapshot.cg_carbs_g, raw.cg_carbs_g);
  const duration = pickFirstNumber(snapshot.exercise_duration_min, raw.exercise_duration_min);

  return {
    glucose,
    glycemicBand: glycemicBand(glucose),
    delta,
    trend: glucoseTrendLabel(delta),
    met,
    metIntensity: metIntensityLabel(met),
    sleepScore,
    carbs,
    duration,
    signalCount: Object.keys(raw).length,
  };
}

function standbyText(name) {
  const base = "Waiting for next trigger in objective stream.";
  if (name === "Guidance Generator") return `${base} Guidance emits only when intervention is available.`;
  if (name === "Knowledge Base") return `${base} Retrieval runs only for agent-triggered decisions.`;
  if (name === "Orchestration Layer") return `${base} Agent routing stays idle until risk/context criteria are met.`;
  if (name === "Guardian Agent") return `${base} Safety screening is pending before interface delivery.`;
  if (name === "Interfacing Layer") return `${base} Surface updates when new user/caregiver payload exists.`;
  return base;
}

function componentOutputText(output) {
  if (output == null || output === "") return "-";
  if (Array.isArray(output)) return output.join("; ");
  if (typeof output === "object") return Object.entries(output).map(([k, v]) => `${k}: ${v}`).join("; ");
  return String(output);
}

function buildComponentNarrative(name, entry, isActive) {
  if (!isActive) {
    return standbyText(name);
  }

  const base = componentOutputText(entry.component_outputs?.[name]);
  const objectiveRows = entry.data_channels?.["Objective Data"] || [];
  const keys = parseSignalKeys(entry);
  const derived = deriveObjectiveSummary(entry);
  const prev = state.timeline[state.index - 1];
  const deltaMin = prev ? Math.round((Date.parse(entry.timestamp) - Date.parse(prev.timestamp)) / 60000) : null;
  const nextAgentWindow =
    String(entry.event_type || "").startsWith("sleep_")
      ? "Sleep touchpoint cycle: wake detection and pre-bed reminder."
      : "Glucose touchpoint cycle: meal, transition, exercise, and rapid-change checks.";

  if (name === "Event Extraction & Personiclie Engine") {
    const mlSignal = entry.personicle_signals?.personal_ml_model;
    const causalSignal = entry.personicle_signals?.personal_causal_analysis;
    const lines = [
      `Detected event: ${entry.event_type}`,
      `Event family: ${getEventFamily(entry.event_type)}`,
      `Objective packets parsed: ${objectiveRows.length} (${derived.signalCount} keyed signals)`,
      `Primary physiologic signal: ${derived.glucose == null ? "No glucose sample in this packet" : `${Math.round(derived.glucose)} mg/dL (${derived.glycemicBand})`}`,
      `Primary behavior signal: ${derived.met == null ? "No activity sample in this packet" : `${derived.met.toFixed(2)} MET (${derived.metIntensity})`}`,
      `Time phase: ${getDayPhase(entry.timestamp)}`,
      `Extractor output: ${base}`,
    ];
    if (mlSignal?.triggered) {
      const lvl = mlSignal.predicted_level_today || entry.state_snapshot?.loneliness_current_level || "-";
      const score = typeof mlSignal.prediction_score === "number" ? `${Math.round(mlSignal.prediction_score * 100)}%` : "-";
      lines.push(`Personal ML model trigger: ${mlSignal.trigger || "monitor"} · loneliness=${lvl} (${score})`);
    }
    if (causalSignal?.triggered) {
      const observed = causalSignal.observed_peak_mg_dL;
      const estimated = causalSignal.estimated_peak_mg_dL;
      lines.push(
        `Personal causal trigger: ${causalSignal.trigger || "meal"} · peak ${formatScalar(observed)} -> ${formatScalar(estimated)} mg/dL (${causalSignal.scenario || "counterfactual"})`
      );
    }
    if (keys.length) lines.push(`Signals detected: ${keys.slice(0, 5).join(", ")}`);
    return lines.join("\n");
  }

  if (name === "State Estimation Module") {
    const snapshot = Object.entries(entry.state_snapshot || {})
      .slice(0, 5)
      .map(([k, v]) => `${formatFieldLabel(k)}=${formatScalar(v)}`)
      .join("; ");
    return [
      `Risk level: ${getRiskLevel(entry)}`,
      `Confidence: ${formatScalar(entry.decision_snapshot?.confidence)}`,
      `Glycemic band: ${derived.glycemicBand}`,
      `Trajectory: ${derived.trend}${derived.delta == null ? "" : ` (${derived.delta > 0 ? "+" : ""}${formatScalar(derived.delta)} mg/dL)`}`,
      `Activity intensity: ${derived.metIntensity}`,
      `Sleep recovery signal: ${derived.sleepScore == null ? "Not present in this step" : `Score ${Math.round(derived.sleepScore)}`}`,
      snapshot ? `Key states: ${snapshot}` : "Key states: -",
      `Estimator output: ${base}`,
    ].join("\n");
  }

  if (name === "Contextual Inference Engine") {
    return [
      `Context phase: ${getDayPhase(entry.timestamp)}`,
      `Behavioral context: ${getEventFamily(entry.event_type)} (${derived.metIntensity})`,
      `Physiologic context: ${derived.glycemicBand}${derived.trend === "Unknown" ? "" : `, ${derived.trend.toLowerCase()}`}`,
      `Meal load context: ${derived.carbs == null ? "No meal carbs in this step" : `${Math.round(derived.carbs)}g carbs`}`,
      `Intervention context: ${entry.decision_snapshot?.intervention_available ? "Actionable" : "Monitoring"}`,
      `Stream interval from previous event: ${deltaMin == null ? "-" : `${deltaMin} min`}`,
      `Expected follow-up window: ${nextAgentWindow}`,
      `Inference output: ${base}`,
    ].join("\n");
  }

  if (name === "Knowledge Base") {
    const sourceLines = String(base)
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.startsWith("- "));
    const tags = inferKnowledgeTags(entry);
    return [
      "Knowledge mode: local diabetes guideline KB",
      `Retrieval query tags: ${tags.join(", ")}`,
      `References selected: ${sourceLines.length}`,
      sourceLines.length ? `Top refs: ${sourceLines.slice(0, 3).join(" | ")}` : "Top refs: -",
      `KB output: ${base.split("\n")[0] || "-"}`,
    ].join("\n");
  }

  if (name === "Guidance Generator") {
    const user = entry.user_output;
    return [
      `Guidance status: ${user ? "Generated" : "Not generated"}`,
      `Objective grounding: ${derived.glucose == null ? "Uses non-glucose objective context in this step" : `Grounded on ${Math.round(derived.glucose)} mg/dL and ${derived.trend.toLowerCase()} pattern`}`,
      `Primary recommendation: ${user?.try_next_time || "No user-facing recommendation at this step."}`,
      `Reasoning summary: ${(user?.why || []).slice(0, 2).join(" | ") || "-"}`,
      `Generator output: ${base}`,
    ].join("\n");
  }

  if (name === "Orchestration Layer") {
    const selectedAgents = getSelectedAgents(entry);
    const selectedAgentText = selectedAgents.length ? selectedAgents.join(" + ") : "None";
    const triggerReason = entry.decision_snapshot?.trigger_reason;
    const callReason = triggerReason
      ? `Triggered by: ${humanizeReasonText(triggerReason)}`
      : selectedAgents.length
        ? "Triggered by objective event policy"
        : "No specialist trigger met; monitoring path active";
    return [
      `Priority: ${estimatePriority(entry)}`,
      `Selected agent(s): ${selectedAgentText}`,
      `Routing rationale: ${callReason}`,
      `Escalation level: ${entry.decision_snapshot?.escalation_level || "none"}`,
      `Triggered components: ${entry.activated_components.length}`,
      "Delivery surfaces: Chatbot | Dashboard | Caregiver portal",
      `Orchestrator output: ${base}`,
    ].join("\n");
  }

  if (name === "Interfacing Layer") {
    const modeHint =
      state.interfaceView === "chatbot"
        ? "Conversational guidance card"
        : state.interfaceView === "dashboard"
          ? "Metric-first operational snapshot"
          : "Care escalation handoff summary";
    return [
      `Active interface: ${state.interfaceView}`,
      `Surface payload type: ${modeHint}`,
      `User card available: ${entry.user_output ? "Yes" : "No"}`,
      `Delivery status: ${entry.decision_snapshot?.intervention_available ? "Intervention message prepared" : "Monitoring update"}`,
      `Interface output: ${base}`,
    ].join("\n");
  }

  if (name === "Guardian Agent") {
    const verdict = entry.decision_snapshot?.guardian_verdict || "Pass";
    const gateStatus = verdict === "Escalate" ? "Not passed" : verdict === "Caution" ? "Passed with caution" : "Passed";
    return [
      `Safety verdict: ${verdict}`,
      `Guardian note: ${entry.decision_snapshot?.guardian_note || "Safety screening completed."}`,
      `Escalation alignment: ${entry.decision_snapshot?.escalation_level || "none"}`,
      `Display gate: ${entry.decision_snapshot?.guardian_screened ? gateStatus : "Pending review"}`,
      `Guardian output: ${base}`,
    ].join("\n");
  }

  return `Output: ${base}`;
}

function renderAgentBadges(entry) {
  const badges = Array.from(document.querySelectorAll(".agent-badge"));
  badges.forEach((badge) => {
    badge.classList.remove("active-agent");
    badge.removeAttribute("data-dialog");
  });
  const selected = new Set(getSelectedAgents(entry));
  const dialogShown = new Set();
  badges.forEach((badge) => {
    const agent = badge.getAttribute("data-agent");
    if (agent && selected.has(agent)) {
      badge.classList.add("active-agent");
      if (!dialogShown.has(agent)) {
        badge.setAttribute("data-dialog", summarizeAgentAction(agent, entry));
        dialogShown.add(agent);
      }
    }
  });
}

function renderPersonicleModules(entry) {
  const mlModule = document.getElementById("personicle-ml-module");
  const mlStatus = document.getElementById("personicle-ml-status");
  const mlDetail = document.getElementById("personicle-ml-detail");
  const causalModule = document.getElementById("personicle-causal-module");
  const causalStatus = document.getElementById("personicle-causal-status");
  const causalDetail = document.getElementById("personicle-causal-detail");
  if (!mlModule || !mlStatus || !mlDetail || !causalModule || !causalStatus || !causalDetail) return;

  const ml = entry?.personicle_signals?.personal_ml_model || {};
  const causal = entry?.personicle_signals?.personal_causal_analysis || {};

  const mlTriggered = Boolean(ml.triggered);
  mlModule.classList.toggle("active", mlTriggered);
  if (mlTriggered) {
    const level = ml.predicted_level_today || entry.state_snapshot?.loneliness_predicted_today || entry.state_snapshot?.loneliness_current_level || "Unknown";
    const scoreValue =
      typeof ml.prediction_score === "number"
        ? `${Math.round(ml.prediction_score * 100)}%`
        : (entry.state_snapshot?.loneliness_prediction_score != null
            ? `${Math.round(Number(entry.state_snapshot.loneliness_prediction_score) * 100)}%`
            : "-");
    const trigger = ml.trigger || "monitor";
    mlStatus.textContent = `Triggered · ${trigger}`;
    const lonelyEvent = String(entry.event_type || "") === "feeling_lonely_detected";
    mlDetail.textContent = lonelyEvent
      ? `Detected feeling lonely event. Current loneliness level ${level} (${scoreValue}).`
      : `Loneliness level ${level} (${scoreValue}) from objective sleep/activity pattern.`;
  } else {
    mlStatus.textContent = "Standby";
    mlDetail.textContent = "Predicts daily loneliness level at wake-up and runs daytime loneliness monitoring checks.";
  }

  const causalTriggered = Boolean(causal.triggered);
  causalModule.classList.toggle("active", causalTriggered);
  if (causalTriggered) {
    const observed = causal.observed_peak_mg_dL ?? entry.state_snapshot?.counterfactual_observed_peak_mg_dL;
    const estimated = causal.estimated_peak_mg_dL ?? entry.state_snapshot?.counterfactual_estimated_peak_mg_dL;
    const scenario = causal.scenario || entry.state_snapshot?.counterfactual_scenario || "counterfactual meal scenario";
    causalStatus.textContent = `Triggered · ${causal.trigger || "meal_logged"}`;
    causalDetail.textContent =
      observed != null && estimated != null
        ? `Counterfactual peak: ${Math.round(Number(observed))} -> ${Math.round(Number(estimated))} mg/dL (${scenario}).`
        : `Counterfactual generated for ${scenario}.`;
  } else {
    causalStatus.textContent = "Standby";
    causalDetail.textContent = "On each meal log, estimates counterfactual glucose trajectory for alternative food/activity choices.";
  }
}

function renderGuardianStatus(entry) {
  const status = document.getElementById("guardian-status");
  if (!status) return;
  status.classList.remove("pass", "caution", "fail");
  const verdict = entry?.decision_snapshot?.guardian_verdict || "Pass";
  if (verdict === "Escalate") {
    status.classList.add("fail");
    status.textContent = "Safety Gate: Not Passed";
    return;
  }
  if (verdict === "Caution") {
    status.classList.add("caution");
    status.textContent = "Safety Gate: Passed with Caution";
    return;
  }
  status.classList.add("pass");
  status.textContent = "Safety Gate: Passed";
}

function renderMeta() {
  const meta = document.getElementById("meta");
  const range = state.meta.dateRange ? ` · ${state.meta.dateRange}` : "";
  meta.textContent = `Participant: ${state.meta.participant} · Meals: ${state.meta.mealCount} · Events: ${state.timeline.length}${range}`;
}

function updateClock(iso) {
  const hourEl = document.getElementById("clock-hour");
  const minuteEl = document.getElementById("clock-minute");
  const secondEl = document.getElementById("clock-second");
  const subtitle = document.getElementById("clock-subtitle");
  if (!hourEl || !minuteEl || !secondEl) return;

  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return;

  if (subtitle) {
    subtitle.textContent = `${formatClockSubtitle(iso)} · ${getDayPhase(iso)}`;
  }

  let duration = 0;
  let hourDeg;
  let minuteDeg;
  let secondDeg;

  if (!state.clock.initialized || state.clock.lastMs == null) {
    const d = new Date(ms);
    hourDeg = ((d.getHours() % 12) + d.getMinutes() / 60 + d.getSeconds() / 3600) * 30;
    minuteDeg = (d.getMinutes() + d.getSeconds() / 60) * 6;
    secondDeg = (d.getSeconds() + d.getMilliseconds() / 1000) * 6;
    duration = 0;
  } else {
    const deltaMs = ms - state.clock.lastMs;
    hourDeg = state.clock.hourDeg + deltaMs * (360 / 43200000);
    minuteDeg = state.clock.minuteDeg + deltaMs * (360 / 3600000);
    secondDeg = state.clock.secondDeg + deltaMs * (360 / 60000);
    duration = deltaMs === 0 ? 0 : Math.min(1800, Math.max(260, Math.abs(deltaMs) / 120));
  }

  hourEl.style.transitionDuration = `${duration}ms`;
  minuteEl.style.transitionDuration = `${duration}ms`;
  secondEl.style.transitionDuration = `${duration}ms`;

  hourEl.style.transform = `rotate(${hourDeg}deg)`;
  minuteEl.style.transform = `rotate(${minuteDeg}deg)`;
  secondEl.style.transform = `rotate(${secondDeg}deg)`;

  state.clock.hourDeg = hourDeg;
  state.clock.minuteDeg = minuteDeg;
  state.clock.secondDeg = secondDeg;
  state.clock.lastMs = ms;
  state.clock.initialized = true;
}

function renderTimeCard(entry) {
  const timeCard = document.getElementById("time-card");
  const prev = state.timeline[state.index - 1];
  const interval = prev
    ? `${Math.round((Date.parse(entry.timestamp) - Date.parse(prev.timestamp)) / 60000)} min from previous event`
    : "Start of replay";
  timeCard.innerHTML = `
    <div class="output-section"><strong>${formatTimestamp(entry.timestamp)}</strong></div>
    <div class="muted">Event: ${entry.event_type}</div>
    <div class="muted">Meal/Event ID: ${entry.meal_id}</div>
    <div class="muted">Replay interval: ${interval}</div>
  `;
}

function renderRawData(entry) {
  const nodes = {
    "Objective Data": { body: document.getElementById("objective-data"), node: document.getElementById("node-objective") },
    "Subjective Data": { body: document.getElementById("subjective-data"), node: document.getElementById("node-subjective") },
    "Inferred Data": { body: document.getElementById("inferred-data"), node: document.getElementById("node-inferred") },
    "Conversation Aquired Data": {
      body: document.getElementById("conversation-data"),
      node: document.getElementById("node-conversation"),
    },
  };

  const channels = entry.data_channels || {};
  const hasChannels = Boolean(entry.data_channels);
  const names = state.dataChannels.length ? state.dataChannels : defaultDataChannels;

  names.forEach((name) => {
    const slot = nodes[name];
    if (!slot || !slot.body) return;
    const rows = hasChannels ? channels[name] || [] : [];
    if (slot.node) {
      slot.node.classList.toggle("active", rows.length > 0);
    }
    if (rows.length === 0) {
      slot.body.innerHTML = "<div class='muted'>No records in current dataset for this step.</div>";
      return;
    }
    slot.body.innerHTML = rows.map((line) => `<div>- ${escapeHtml(line)}</div>`).join("");
  });

  if (!hasChannels && entry.raw_data_received && entry.raw_data_received.length > 0 && nodes["Objective Data"]?.body) {
    nodes["Objective Data"].body.innerHTML = entry.raw_data_received
      .map((line) => `<div>- ${escapeHtml(line)}</div>`)
      .join("");
    nodes["Objective Data"].node?.classList.add("active");
  }
}

function renderProcessing(entry) {
  const componentNames = state.components.length ? state.components : defaultComponents;
  componentNames.forEach((name) => {
    const slot = componentSlots[name];
    if (!slot) return;
    const node = document.getElementById(slot.nodeId);
    const outputNode = document.getElementById(slot.outputId);
    if (!node || !outputNode) return;

    const isActive = entry.activated_components.includes(name);
    node.classList.toggle("active", isActive);
    outputNode.textContent = buildComponentNarrative(name, entry, isActive);
  });

  const personicleNode = document.getElementById("node-personicle");
  if (personicleNode) {
    const personicleChildren = ["node-event", "node-state", "node-context", "node-knowledge"];
    const hasActiveChild = personicleChildren.some((id) => document.getElementById(id)?.classList.contains("active"));
    personicleNode.classList.toggle("active", hasActiveChild);
  }
}

function buildConnectionPath(sourceRect, targetRect, containerRect) {
  const sourceCenterX = sourceRect.left + sourceRect.width / 2;
  const sourceCenterY = sourceRect.top + sourceRect.height / 2;
  const targetCenterX = targetRect.left + targetRect.width / 2;
  const targetCenterY = targetRect.top + targetRect.height / 2;
  const dx = targetCenterX - sourceCenterX;
  const dy = targetCenterY - sourceCenterY;

  let sourceX = sourceCenterX;
  let sourceY = sourceCenterY;
  let targetX = targetCenterX;
  let targetY = targetCenterY;

  if (Math.abs(dx) >= Math.abs(dy)) {
    sourceX += dx > 0 ? sourceRect.width / 2 : -sourceRect.width / 2;
    targetX += dx > 0 ? -targetRect.width / 2 : targetRect.width / 2;
  } else {
    sourceY += dy > 0 ? sourceRect.height / 2 : -sourceRect.height / 2;
    targetY += dy > 0 ? -targetRect.height / 2 : targetRect.height / 2;
  }

  const sx = sourceX - containerRect.left;
  const sy = sourceY - containerRect.top;
  const tx = targetX - containerRect.left;
  const ty = targetY - containerRect.top;
  const curveFactor = 0.35;

  let c1x = sx + (tx - sx) * curveFactor;
  let c1y = sy;
  let c2x = tx - (tx - sx) * curveFactor;
  let c2y = ty;

  if (Math.abs(tx - sx) < 90) {
    c1x = sx;
    c1y = sy + (ty - sy) * curveFactor;
    c2x = tx;
    c2y = ty - (ty - sy) * curveFactor;
  }

  return {
    d: `M ${sx.toFixed(1)} ${sy.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${tx.toFixed(1)} ${ty.toFixed(1)}`,
  };
}

function renderPlannerLinks() {
  const layout = document.getElementById("paper-layout");
  const overlay = document.getElementById("planner-flow-overlay");
  const orchestrator = document.getElementById("node-orchestration");
  if (!layout || !overlay || !orchestrator) return;

  if (window.matchMedia("(max-width: 840px)").matches) {
    overlay.innerHTML = "";
    return;
  }

  const layoutRect = layout.getBoundingClientRect();
  if (!layoutRect.width || !layoutRect.height) {
    overlay.innerHTML = "";
    return;
  }

  overlay.setAttribute("viewBox", `0 0 ${layoutRect.width} ${layoutRect.height}`);
  overlay.setAttribute("width", `${layoutRect.width}`);
  overlay.setAttribute("height", `${layoutRect.height}`);

  const sourceRect = orchestrator.getBoundingClientRect();
  const paths = [];

  orchestrationLinkTargets.forEach((nodeId) => {
    const target = document.getElementById(nodeId);
    if (!target) return;
    const targetRect = target.getBoundingClientRect();
    const { d } = buildConnectionPath(sourceRect, targetRect, layoutRect);
    const activeClass = target.classList.contains("active") ? " active" : "";
    paths.push(`<path class="planner-link${activeClass}" d="${d}" marker-end="url(#planner-arrow)" />`);
  });

  overlay.innerHTML = `
    <defs>
      <marker id="planner-arrow" viewBox="0 0 10 10" refX="8.4" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(14, 116, 144, 0.86)"></path>
      </marker>
    </defs>
    ${paths.join("")}
  `;
}

function schedulePlannerLinksRender() {
  if (plannerLinksRaf != null) {
    window.cancelAnimationFrame(plannerLinksRaf);
  }
  plannerLinksRaf = window.requestAnimationFrame(() => {
    plannerLinksRaf = null;
    renderPlannerLinks();
  });
}

function renderState(entry) {
  const stateCard = document.getElementById("state");
  const decisionCard = document.getElementById("decision");

  const stateLines = Object.entries(entry.state_snapshot || {}).map(
    ([key, value]) => `<div>• ${formatFieldLabel(key)}: ${escapeHtml(formatScalar(value))}</div>`
  );
  stateCard.innerHTML = `
    <div class="output-section"><strong>Current State</strong></div>
    ${stateLines.join("") || "<div class='muted'>No derived state.</div>"}
  `;

  const decisionLines = Object.entries(entry.decision_snapshot || {}).map(
    ([key, value]) => `<div>• ${formatFieldLabel(key)}: ${escapeHtml(formatScalar(value))}</div>`
  );
  decisionCard.innerHTML = `
    <div class="output-section"><strong>Decision Summary</strong></div>
    ${decisionLines.join("") || "<div class='muted'>No decisions.</div>"}
  `;
}

function extractRecommendation(entry) {
  return entry.user_output?.try_next_time || "No action recommendation at this step.";
}

function formatTimeOnlyFromDate(dateObj) {
  return dateObj.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function computeChatbotNextCheck(entry) {
  const now = new Date(entry.timestamp);
  const eventType = String(entry.event_type || "");
  let minutes = 60;
  let label = "next glucose/context check";

  if (eventType === "rapid_glucose_rise" || eventType === "rapid_glucose_fall") {
    minutes = 15;
    label = "safety re-check";
  } else if (eventType === "feeling_lonely_detected") {
    minutes = 60;
    label = "social well-being re-check";
  } else if (eventType === "loneliness_monitor_check") {
    minutes = 180;
    label = "well-being monitor check";
  } else if (eventType === "post_meal_check" || eventType === "peak_detected" || eventType === "meal_logged") {
    minutes = 30;
    label = "post-meal trend check";
  } else if (eventType === "exercise_started") {
    minutes = 20;
    label = "exercise trend check";
  } else if (eventType === "exercise_ended") {
    minutes = 20;
    label = "recovery check";
  } else if (eventType === "sleep_wake_detected") {
    minutes = 120;
    label = "morning planning check";
  } else if (eventType === "sleep_pre_bed_reminder") {
    minutes = 8 * 60;
    label = "overnight to morning follow-up";
  }
  const explicitMinutes = Number(entry.decision_snapshot?.next_check_minutes);
  if (Number.isFinite(explicitMinutes) && explicitMinutes > 0) {
    minutes = explicitMinutes;
  }

  const at = new Date(now.getTime() + minutes * 60000);
  return { label, minutes, at };
}

function buildChatbotWhyNow(entry, derived) {
  const reasons = [];
  const eventType = String(entry.event_type || "");
  if (derived.glucose != null) {
    reasons.push(`Glucose is ${Math.round(derived.glucose)} mg/dL (${derived.glycemicBand}).`);
  }
  if (derived.delta != null) {
    reasons.push(`Recent shift is ${derived.delta > 0 ? "+" : ""}${Math.round(derived.delta)} mg/dL (${derived.trend.toLowerCase()}).`);
  }
  if (eventType.startsWith("sleep_")) {
    reasons.push("Sleep timing context was detected from objective sleep signals.");
  } else if (eventType.includes("lonely")) {
    reasons.push("Personal ML flagged loneliness risk from wake/sleep/activity behavior pattern.");
  } else if (eventType.startsWith("exercise_")) {
    reasons.push("Exercise context was detected from objective MET activity signals.");
  } else if (eventType.includes("meal") || eventType.includes("peak")) {
    reasons.push("Post-meal glucose trajectory is in an actionable monitoring window.");
  }
  if (entry.user_output?.why?.length) {
    reasons.push(...entry.user_output.why.slice(0, 1));
  }
  return reasons.slice(0, 3);
}

function renderInterfaceButtons() {
  const map = {
    chatbot: document.getElementById("iface-chatbot"),
    dashboard: document.getElementById("iface-dashboard"),
    caregiver: document.getElementById("iface-caregiver"),
  };
  Object.entries(map).forEach(([key, button]) => {
    if (!button) return;
    button.classList.toggle("active", key === state.interfaceView);
  });
}

function renderChatbotView(entry) {
  const derived = deriveObjectiveSummary(entry);
  const selectedAgent = getSelectedAgents(entry).join(", ") || "the monitoring system";
  const nextCheck = computeChatbotNextCheck(entry);
  const message = entry.user_output || {};
  const guardianVerdict = entry.decision_snapshot?.guardian_verdict || "Pass";
  const intro = message.what_happened
    || (derived.glucose == null
      ? "I am watching your latest sensor stream and no urgent issue is detected right now."
      : `I see your latest glucose is ${Math.round(derived.glucose)} mg/dL, which is ${derived.glycemicBand.toLowerCase()}.`);
  const action = message.try_next_time
    || (entry.decision_snapshot?.intervention_available
      ? "Please follow your care plan now and keep monitoring."
      : "No immediate action needed, just continue your routine.");
  const guardianLine =
    guardianVerdict === "Escalate"
      ? "Safety Keeper has flagged this as urgent."
      : guardianVerdict === "Caution"
        ? "Safety Keeper approved this message with caution."
        : "Safety Keeper approved this message.";
  const opener =
    selectedAgent === "the monitoring system"
      ? "Hi, I’m your PCU assistant."
      : `Hi, I’m your PCU assistant working with ${selectedAgent}.`;
  const finalText = `${opener} ${intro} ${action} ${guardianLine} I will check again around ${formatTimeOnlyFromDate(nextCheck.at)}.`;

  return `
    <div class="iface-title">Chatbot message</div>
    <div class="chat-single">${escapeHtml(finalText)}</div>
  `;
}

function renderDashboardView(entry) {
  const confidence = entry.decision_snapshot?.confidence;
  const intervention = entry.decision_snapshot?.intervention_available ? "Yes" : "No";
  const selectedAgent = getSelectedAgents(entry).join(" + ") || "None";
  const escalation = entry.decision_snapshot?.escalation_level || "none";
  const risk = getRiskLevel(entry);
  const stateItems = Object.entries(entry.state_snapshot || {})
    .slice(0, 6)
    .map(([key, value]) => `<div><strong>${escapeHtml(formatFieldLabel(key))}:</strong> ${escapeHtml(formatScalar(value))}</div>`)
    .join("");

  return `
    <div class="iface-title">Dashboard summary</div>
    <div class="iface-kpis">
      <div><strong>Risk Level</strong><span>${escapeHtml(risk)}</span></div>
      <div><strong>Selected Agent</strong><span>${escapeHtml(selectedAgent)}</span></div>
      <div><strong>Intervention</strong><span>${escapeHtml(intervention)}</span></div>
      <div><strong>Confidence</strong><span>${escapeHtml(formatScalar(confidence))}</span></div>
      <div><strong>Escalation</strong><span>${escapeHtml(escalation)}</span></div>
      <div><strong>Event Type</strong><span>${escapeHtml(entry.event_type || "-")}</span></div>
      <div><strong>Timestamp</strong><span>${escapeHtml(formatTimestamp(entry.timestamp))}</span></div>
    </div>
    <div class="iface-panel">
      <strong>Current state snapshot</strong>
      ${stateItems || "<div class='muted'>No state fields at this step.</div>"}
    </div>
  `;
}

function renderCaregiverView(entry) {
  const risk = getRiskLevel(entry);
  const selectedAgent = getSelectedAgents(entry).join(" + ") || "None";
  const recommendation = extractRecommendation(entry);
  const triggerReason = humanizeReasonText(entry.decision_snapshot?.trigger_reason || "not specified");
  const escalation = entry.decision_snapshot?.escalation_level || "none";
  const kbOutput = String(entry.component_outputs?.["Knowledge Base"] || "");
  const kbLines = kbOutput
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("-"));
  const rationale = (entry.user_output?.why || []).map((line) => `<div>- ${escapeHtml(line)}</div>`).join("");

  return `
    <div class="iface-title">Caregiver portal handoff</div>
    <div class="iface-panel">
      <div><strong>Clinical risk:</strong> ${escapeHtml(risk)}</div>
      <div><strong>Triggered by:</strong> ${escapeHtml(entry.event_type || "-")}</div>
      <div><strong>Active specialist:</strong> ${escapeHtml(selectedAgent)}</div>
      <div><strong>Routing reason:</strong> ${escapeHtml(triggerReason)}</div>
      <div><strong>Escalation level:</strong> ${escapeHtml(escalation)}</div>
      <div><strong>Recommended action:</strong> ${escapeHtml(recommendation)}</div>
      <div><strong>Rationale:</strong></div>
      ${rationale || "<div class='muted'>No additional rationale in this step.</div>"}
      <div><strong>Knowledge references:</strong></div>
      ${kbLines.length ? kbLines.map((line) => `<div>${escapeHtml(line)}</div>`).join("") : "<div class='muted'>No KB references selected.</div>"}
    </div>
  `;
}

function renderOutput(entry) {
  const output = document.getElementById("output");
  if (state.interfaceView === "dashboard") {
    output.innerHTML = renderDashboardView(entry);
    return;
  }
  if (state.interfaceView === "caregiver") {
    output.innerHTML = renderCaregiverView(entry);
    return;
  }
  output.innerHTML = renderChatbotView(entry);
}

function attachInterfaceControls() {
  const chat = document.getElementById("iface-chatbot");
  const dash = document.getElementById("iface-dashboard");
  const care = document.getElementById("iface-caregiver");

  if (chat) {
    chat.addEventListener("click", () => {
      state.interfaceView = "chatbot";
      renderInterfaceButtons();
      render();
    });
  }
  if (dash) {
    dash.addEventListener("click", () => {
      state.interfaceView = "dashboard";
      renderInterfaceButtons();
      render();
    });
  }
  if (care) {
    care.addEventListener("click", () => {
      state.interfaceView = "caregiver";
      renderInterfaceButtons();
      render();
    });
  }
}

function render() {
  const entry = state.timeline[state.index];
  if (!entry) return;

  document.getElementById("timestamp").textContent = formatTimestamp(entry.timestamp);
  updateClock(entry.timestamp);
  renderTimeCard(entry);
  renderRawData(entry);
  renderProcessing(entry);
  renderGuardianStatus(entry);
  renderAgentBadges(entry);
  renderPersonicleModules(entry);
  renderState(entry);
  renderOutput(entry);
  schedulePlannerLinksRender();
}

function jumpToEvent() {
  const start = state.index + 1;
  for (let i = start; i < state.timeline.length; i += 1) {
    if (state.timeline[i].is_event) {
      state.index = i;
      render();
      return;
    }
  }
}

function jumpToInsight() {
  const start = state.index + 1;
  for (let i = start; i < state.timeline.length; i += 1) {
    if (state.timeline[i].user_output) {
      state.index = i;
      render();
      return;
    }
  }
}

function jumpToDay(delta) {
  const dayStarts = state.dayStarts;
  const current = dayStarts.findIndex((idx, i) => {
    const next = dayStarts[i + 1] ?? state.timeline.length;
    return state.index >= idx && state.index < next;
  });
  const target = Math.min(dayStarts.length - 1, Math.max(0, current + delta));
  if (dayStarts[target] != null) {
    state.index = dayStarts[target];
    render();
  }
}

function jumpToTimestamp() {
  const input = document.getElementById("jump-input");
  if (!input.value) return;
  const ms = Date.parse(input.value);
  if (Number.isNaN(ms)) return;
  const idx = state.timeline.findIndex((entry) => Date.parse(entry.timestamp) >= ms);
  if (idx >= 0) {
    state.index = idx;
    render();
  }
}

function attachControls() {
  document.getElementById("prev").addEventListener("click", () => {
    state.index = Math.max(0, state.index - 1);
    render();
  });
  document.getElementById("next").addEventListener("click", () => {
    state.index = Math.min(state.timeline.length - 1, state.index + 1);
    render();
  });
  document.getElementById("prev-day").addEventListener("click", () => jumpToDay(-1));
  document.getElementById("next-day").addEventListener("click", () => jumpToDay(1));
  document.getElementById("jump-ts").addEventListener("click", jumpToTimestamp);
  document.getElementById("jump-event").addEventListener("click", jumpToEvent);
  document.getElementById("jump-insight").addEventListener("click", jumpToInsight);
}

function buildDayStarts(timeline) {
  const starts = [];
  let lastDay = null;
  timeline.forEach((entry, idx) => {
    const day = entry.timestamp.slice(0, 10);
    if (day !== lastDay) {
      starts.push(idx);
      lastDay = day;
    }
  });
  return starts;
}

function getQueryParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    dataset: params.get("dataset") || "CGMacros-015",
    participant: params.get("participant"),
    maxMeals: params.get("max_meals"),
  };
}

async function init() {
  const params = getQueryParams();
  const query = new URLSearchParams({ dataset: params.dataset });
  if (params.participant) query.set("participant", params.participant);
  if (params.maxMeals) query.set("max_meals", params.maxMeals);
  const response = await fetch(`/api/pcu?${query.toString()}`);
  const payload = await response.json();
  const timeline = payload.timeline || [];
  const firstDate = timeline[0]?.timestamp ? formatDateLabel(timeline[0].timestamp) : "";
  const lastDate = timeline[timeline.length - 1]?.timestamp
    ? formatDateLabel(timeline[timeline.length - 1].timestamp)
    : "";

  state.timeline = payload.timeline || [];
  state.meta = {
    participant: payload.meta.participant,
    mealCount: payload.meta.meal_count,
    dateRange: firstDate && lastDate ? `${firstDate} - ${lastDate}` : "",
  };
  state.components = payload.meta.component_names || defaultComponents;
  state.dataChannels = payload.meta.data_channel_names || defaultDataChannels;
  state.dayStarts = buildDayStarts(state.timeline);

  renderMeta();
  attachControls();
  attachInterfaceControls();
  window.addEventListener("resize", schedulePlannerLinksRender);
  window.addEventListener("orientationchange", schedulePlannerLinksRender);
  renderInterfaceButtons();
  render();
}

init();
