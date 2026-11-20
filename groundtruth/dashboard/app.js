/**
 * GroundTruth Dashboard Single Page Application (ADR 0001)
 * Zero npm build step. Vanilla JS SPA driven by REST APIs and live SSE stream.
 */

import { createTopBar, updateDecisionPill, updateCaseStateDot, getFriendlyCaseName } from "./panels/top_bar.js";
import { createSubNavBar, setActiveNavTab } from "./panels/nav_bar.js";
import { createVerdictStreamPanel, appendVerdictRow } from "./panels/verdict_stream.js";
import { createFactListPanel, renderFactList } from "./panels/fact_list.js";
import { createGraphPanel, renderGraph, animateTaintCascade } from "./panels/graph.js";
import { createReplayPanel } from "./panels/replay.js";
import { createCountersPanel, updateCountersPanel } from "./panels/counters.js";
import { createFormulaPanel, createConclusionPanel, updateConclusionPanel } from "./panels/formula_conclusion.js";

let currentCaseId = "";
let currentEventSource = null;
let packConfig = { tCite: 0.50, tAuto: 0.60 };

export function getTabFromHash() {
  const hash = window.location.hash.replace(/^#\/?/, "").toLowerCase();
  const valid = ["graph", "verdicts", "facts", "conclusion", "counters", "formula", "all"];
  return valid.includes(hash) ? hash : "graph";
}

export function selectTab(tabId, updateHash = true) {
  if (updateHash) {
    window.location.hash = "#/" + tabId;
  }

  setActiveNavTab(tabId);

  const viewsContainer = document.getElementById("dashboard-views");
  if (!viewsContainer) return;

  if (tabId === "all") {
    viewsContainer.className = "dashboard-views mode-all";
  } else {
    viewsContainer.className = "dashboard-views mode-single";
    const panels = viewsContainer.querySelectorAll(".view-panel");
    panels.forEach((p) => {
      if (p.dataset.view === tabId) {
        p.classList.add("active");
      } else {
        p.classList.remove("active");
      }
    });
  }
}

function createPageBanner({ tag, title, desc, badge, badgeColor = "var(--gt-lime)" }) {
  const banner = document.createElement("div");
  banner.className = "page-header-banner";
  banner.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
      <div>
        <div style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: var(--gt-cobalt-soft); letter-spacing: 0.08em; margin-bottom: 4px;">
          ${tag}
        </div>
        <h1 style="font-size: 20px; font-weight: 700; color: var(--gt-text);">${title}</h1>
        <p style="font-size: 12px; color: var(--gt-text-muted); margin-top: 4px; max-width: 900px; line-height: 1.5;">
          ${desc}
        </p>
      </div>
      ${badge ? `
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="mono" style="
            font-size: 11px;
            color: ${badgeColor};
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 4px 12px;
            border-radius: var(--gt-radius-pill);
            font-weight: 600;
          ">${badge}</span>
        </div>
      ` : ""}
    </div>
  `;
  return banner;
}

export async function initApp() {
  const root = document.getElementById("app");
  if (!root) return;

  // 1. Mount Top Navigation Bar
  const topBar = createTopBar({
    onCaseSwitch: (newCaseId) => switchCase(newCaseId),
  });
  root.appendChild(topBar);

  // 2. Mount Sub Navigation Tab Bar
  const initialTab = getTabFromHash();
  const navBar = createSubNavBar({
    onTabSelect: (tabId) => selectTab(tabId),
    initialTab,
  });
  root.appendChild(navBar);

  // 3. Mount Multi-View / Multi-Page Views Container
  const viewsContainer = document.createElement("main");
  viewsContainer.id = "dashboard-views";
  viewsContainer.className = initialTab === "all" ? "dashboard-views mode-all" : "dashboard-views mode-single";

  // Col 1: Verdict Stream + Fact List
  const col1 = document.createElement("div");
  col1.className = "dashboard-col dashboard-col-1";

  const verdictsWrapper = document.createElement("div");
  verdictsWrapper.className = `view-panel ${initialTab === "verdicts" ? "active" : ""}`;
  verdictsWrapper.dataset.view = "verdicts";
  verdictsWrapper.appendChild(createPageBanner({
    tag: "Zero-Trust Admission Pipeline",
    title: "Write Gate Evaluation Stream",
    desc: "Real-time audit log of write gate evaluations. Every LLM claim is validated against domain pack schemas, parent provenance, and deterministic verifiers before state admission.",
    badge: "🛡️ Falsification Active",
    badgeColor: "var(--gt-lime)",
  }));
  const verdictPanel = createVerdictStreamPanel();
  verdictsWrapper.appendChild(verdictPanel);
  col1.appendChild(verdictsWrapper);

  const factsWrapper = document.createElement("div");
  factsWrapper.className = `view-panel ${initialTab === "facts" ? "active" : ""}`;
  factsWrapper.dataset.view = "facts";
  factsWrapper.appendChild(createPageBanner({
    tag: "Verified Context Ledger",
    title: "Admitted Fact Ledger",
    desc: "Cryptographic ledger of facts admitted to the case context. Filter by status, inspect source agent roles, citation bars, and raw tool evidence lines.",
    badge: "📦 Immutable Context",
    badgeColor: "var(--gt-cobalt-soft)",
  }));
  const factListPanel = createFactListPanel();
  factsWrapper.appendChild(factListPanel);
  col1.appendChild(factsWrapper);

  // Col 2: Graph + Scrubber
  const col2 = document.createElement("div");
  col2.className = "dashboard-col dashboard-col-2";

  const graphWrapper = document.createElement("div");
  graphWrapper.className = `view-panel ${initialTab === "graph" ? "active" : ""}`;
  graphWrapper.dataset.view = "graph";
  graphWrapper.appendChild(createPageBanner({
    tag: "Interactive Evidence Graph",
    title: "Causality Graph & Timeline Replay",
    desc: "Directed acyclic graph of admitted facts with weakest-link confidence and taint cascade propagation. Drag the scrubber below to time-travel through DAG evolution.",
    badge: "⚡ Interactive SVG DAG",
    badgeColor: "var(--gt-lime)",
  }));
  const graphPanel = createGraphPanel();
  const replayPanel = createReplayPanel({
    onScrub: (seq) => loadHistoricalState(seq),
    onLive: () => loadCaseData(currentCaseId),
  });
  graphWrapper.appendChild(graphPanel);
  graphWrapper.appendChild(replayPanel);
  col2.appendChild(graphWrapper);

  // Col 3: Conclusion + Counters + Formula
  const col3 = document.createElement("div");
  col3.className = "dashboard-col dashboard-col-3";

  const conclusionWrapper = document.createElement("div");
  conclusionWrapper.className = `view-panel ${initialTab === "conclusion" ? "active" : ""}`;
  conclusionWrapper.dataset.view = "conclusion";
  conclusionWrapper.appendChild(createPageBanner({
    tag: "Epistemic Resolution & Safety Gate",
    title: "Attributable Conclusion & Routing",
    desc: "Deterministic root cause deduction with cryptographic lineage, recommended fixes, and explicit negative knowledge callouts that block ungrounded automated actions.",
    badge: "🎯 Provable Lineage",
    badgeColor: "var(--gt-lime)",
  }));
  const conclusionPanel = createConclusionPanel();
  conclusionWrapper.appendChild(conclusionPanel);
  col3.appendChild(conclusionWrapper);

  const countersWrapper = document.createElement("div");
  countersWrapper.className = `view-panel ${initialTab === "counters" ? "active" : ""}`;
  countersWrapper.dataset.view = "counters";
  countersWrapper.appendChild(createPageBanner({
    tag: "Multi-Agent Efficiency Metrics",
    title: "Benchmark Performance Counters",
    desc: "Measured reductions in tool calls, duplicate queries, and LLM token consumption comparing GroundTruth against the ungoverned baseline across 15 benchmark incidents.",
    badge: "📊 Measured N=15",
    badgeColor: "var(--gt-lime)",
  }));
  const countersPanel = createCountersPanel();
  countersWrapper.appendChild(countersPanel);
  col3.appendChild(countersWrapper);

  const formulaWrapper = document.createElement("div");
  formulaWrapper.className = `view-panel ${initialTab === "formula" ? "active" : ""}`;
  formulaWrapper.dataset.view = "formula";
  formulaWrapper.appendChild(createPageBanner({
    tag: "Mathematical Governance Model",
    title: "Trust Formula & Thresholds",
    desc: "Formal trust algebra enforcing minimum parent chain confidence, temporal half-life decay, and strict citation (T_cite) and auto-fix (T_auto) threshold gating.",
    badge: "📐 Invariant TRUST-5",
    badgeColor: "var(--gt-cobalt-soft)",
  }));
  const formulaPanel = createFormulaPanel();
  formulaWrapper.appendChild(formulaPanel);
  col3.appendChild(formulaWrapper);

  viewsContainer.appendChild(col1);
  viewsContainer.appendChild(col2);
  viewsContainer.appendChild(col3);
  root.appendChild(viewsContainer);

  // 4. Hash change listener for browser navigation
  window.addEventListener("hashchange", () => {
    selectTab(getTabFromHash(), false);
  });

  // 5. Connect decision pill click to jump to conclusion page
  const pill = document.getElementById("decision-pill");
  if (pill) {
    pill.style.cursor = "pointer";
    pill.title = "View Root Cause & Decision Breakdown";
    pill.addEventListener("click", () => selectTab("conclusion"));
  }

  // 6. Load Available Cases
  await loadCaseList();
}

async function loadCaseList() {
  try {
    const res = await fetch("/cases");
    if (!res.ok) return;
    const cases = await res.json();
    const selector = document.getElementById("case-selector");
    if (!selector) return;

    if (cases.length === 0) {
      selector.innerHTML = `<option value="">No cases available</option>`;
      return;
    }

    selector.innerHTML = cases
      .map((c) => {
        const friendly = getFriendlyCaseName(c);
        return `<option value="${c.case_id}">${friendly} (${c.state})</option>`;
      })
      .join("");

    currentCaseId = cases[0].case_id;
    await switchCase(currentCaseId);
  } catch (err) {
    console.error("Failed to load case list:", err);
  }
}

export async function switchCase(caseId) {
  if (!caseId) return;
  currentCaseId = caseId;

  // Disconnect previous SSE stream
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  // Clear verdict stream list
  const vList = document.getElementById("verdict-stream-list");
  if (vList) {
    vList.innerHTML = `<div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">Awaiting gate evaluation verdicts…</div>`;
  }

  // Load all initial case data
  await loadCaseData(caseId);

  // Start live SSE connection
  startSSEStream(caseId);
}

export async function loadCaseData(caseId) {
  try {
    const [stateRes, graphRes, decRes, metricsRes, eventsRes] = await Promise.all([
      fetch(`/cases/${caseId}/state`),
      fetch(`/cases/${caseId}/graph`),
      fetch(`/cases/${caseId}/decision`),
      fetch(`/metrics/${caseId}`),
      fetch(`/cases/${caseId}/events`),
    ]);

    if (stateRes.ok) {
      const state = await stateRes.json();
      updateCaseStateDot(state.case?.state);
      renderFactList(state.facts, document.getElementById("fact-list-panel"), packConfig);

      // Conclusion resolution
      const concId = state.case?.conclusion_fact_id;
      const concFact = concId ? state.facts[concId] : null;
      const contested = Object.values(state.facts).filter((f) => f.status === "CONTESTED").map((f) => f.fact_id);

      if (decRes.ok) {
        const dec = await decRes.json();
        updateDecisionPill(dec);
        updateConclusionPanel({
          conclusionFact: concFact,
          missingChecks: dec.missing_checks || [],
          contestedFacts: contested,
        }, document.getElementById("conclusion-panel"));
      }
    }

    if (graphRes.ok) {
      const graph = await graphRes.json();
      renderGraph(graph, document.getElementById("graph-panel"));
    }

    if (metricsRes.ok) {
      const metrics = await metricsRes.json();
      updateCountersPanel(metrics, document.getElementById("counters-panel"));
    }

    if (eventsRes.ok) {
      const events = await eventsRes.json();
      const replayPanel = document.getElementById("replay-panel");
      if (replayPanel && replayPanel.updateMaxSeq) {
        const verdictTicks = events.filter((e) => e.event_type === "GATE_VERDICT").map((e) => e.seq);
        replayPanel.updateMaxSeq(events.length, verdictTicks);
      }
    }
  } catch (err) {
    console.error("Error loading case data:", err);
  }
}

async function loadHistoricalState(seq) {
  try {
    const res = await fetch(`/cases/${currentCaseId}/state?at=${seq}`);
    if (!res.ok) return;
    const state = await res.json();

    // Update fact list with historical facts
    renderFactList(state.facts, document.getElementById("fact-list-panel"), packConfig);

    // Update graph with historical facts directly from backend replay
    const gRes = await fetch(`/cases/${currentCaseId}/graph?at=${seq}`);
    if (gRes.ok) {
      const graph = await gRes.json();
      renderGraph(graph, document.getElementById("graph-panel"));
    }
  } catch (err) {
    console.error("Failed to load historical state:", err);
  }
}

function startSSEStream(caseId) {
  currentEventSource = new EventSource(`/cases/${caseId}/stream`);

  currentEventSource.addEventListener("GATE_VERDICT", async (e) => {
    try {
      const data = JSON.parse(e.data);
      appendVerdictRow(data, document.getElementById("verdict-stream-panel"));
      await refreshAfterEvent();
    } catch (err) {
      console.error("SSE parse error on GATE_VERDICT:", err);
    }
  });

  currentEventSource.addEventListener("FACT_TAINTED", async (e) => {
    try {
      const data = JSON.parse(e.data);
      const payload = data.payload || {};
      await animateTaintCascade(payload.root_cause_fact_id, [payload.fact_id]);
      await refreshAfterEvent();
    } catch (err) {
      console.error("SSE parse error on FACT_TAINTED:", err);
    }
  });

  currentEventSource.addEventListener("TRUST_RECOMPUTED", async () => {
    await refreshAfterEvent();
  });

  currentEventSource.addEventListener("CASE_STATE_CHANGED", async (e) => {
    try {
      const data = JSON.parse(e.data);
      updateCaseStateDot(data.payload?.to);
    } catch (err) {}
  });

  currentEventSource.onerror = () => {
    console.warn("SSE stream connection lost; auto-reconnecting…");
  };
}

async function refreshAfterEvent() {
  if (!currentCaseId) return;
  try {
    const [stateRes, graphRes, decRes, metricsRes] = await Promise.all([
      fetch(`/cases/${currentCaseId}/state`),
      fetch(`/cases/${currentCaseId}/graph`),
      fetch(`/cases/${currentCaseId}/decision`),
      fetch(`/metrics/${currentCaseId}`),
    ]);

    if (stateRes.ok) {
      const state = await stateRes.json();
      renderFactList(state.facts, document.getElementById("fact-list-panel"), packConfig);
      const concId = state.case?.conclusion_fact_id;
      const concFact = concId ? state.facts[concId] : null;
      const contested = Object.values(state.facts).filter((f) => f.status === "CONTESTED").map((f) => f.fact_id);

      if (decRes.ok) {
        const dec = await decRes.json();
        updateDecisionPill(dec);
        updateConclusionPanel({
          conclusionFact: concFact,
          missingChecks: dec.missing_checks || [],
          contestedFacts: contested,
        }, document.getElementById("conclusion-panel"));
      }
    }

    if (graphRes.ok) {
      const graph = await graphRes.json();
      renderGraph(graph, document.getElementById("graph-panel"));
    }

    if (metricsRes.ok) {
      const metrics = await metricsRes.json();
      updateCountersPanel(metrics, document.getElementById("counters-panel"));
    }
  } catch (err) {}
}

document.addEventListener("DOMContentLoaded", () => {
  initApp();
});
