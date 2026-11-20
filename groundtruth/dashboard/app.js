/**
 * GroundTruth Dashboard Single Page Application (ADR 0001)
 * Zero npm build step. Vanilla JS SPA driven by REST APIs and live SSE stream.
 */

import { createTopBar, updateDecisionPill, updateCaseStateDot } from "./panels/top_bar.js";
import { createVerdictStreamPanel, appendVerdictRow } from "./panels/verdict_stream.js";
import { createFactListPanel, renderFactList } from "./panels/fact_list.js";
import { createGraphPanel, renderGraph, animateTaintCascade } from "./panels/graph.js";
import { createReplayPanel } from "./panels/replay.js";
import { createCountersPanel, updateCountersPanel } from "./panels/counters.js";
import { createFormulaPanel, createConclusionPanel, updateConclusionPanel } from "./panels/formula_conclusion.js";

let currentCaseId = "";
let currentEventSource = null;
let packConfig = { tCite: 0.50, tAuto: 0.60 };

export async function initApp() {
  const root = document.getElementById("app");
  if (!root) return;

  // 1. Mount Top Navigation Bar
  const topBar = createTopBar({
    onCaseSwitch: (newCaseId) => switchCase(newCaseId),
  });
  root.appendChild(topBar);

  // 2. Mount Main 3-Column Dashboard Grid
  const mainGrid = document.createElement("main");
  mainGrid.className = "dashboard-grid";

  // Left Column: Stream + Fact List
  const colLeft = document.createElement("div");
  colLeft.style.cssText = "display: flex; flex-direction: column; gap: var(--gt-space-4);";
  const verdictPanel = createVerdictStreamPanel();
  const factListPanel = createFactListPanel();
  colLeft.appendChild(verdictPanel);
  colLeft.appendChild(factListPanel);

  // Center Column: Graph + Scrubber
  const colCenter = document.createElement("div");
  colCenter.style.cssText = "display: flex; flex-direction: column; gap: var(--gt-space-4);";
  const graphPanel = createGraphPanel();
  const replayPanel = createReplayPanel({
    onScrub: (seq) => loadHistoricalState(seq),
    onLive: () => loadCaseData(currentCaseId),
  });
  colCenter.appendChild(graphPanel);
  colCenter.appendChild(replayPanel);

  // Right Column: Counters + Conclusion + Formula
  const colRight = document.createElement("div");
  colRight.style.cssText = "display: flex; flex-direction: column; gap: var(--gt-space-4);";
  const countersPanel = createCountersPanel();
  const conclusionPanel = createConclusionPanel();
  const formulaPanel = createFormulaPanel();
  colRight.appendChild(countersPanel);
  colRight.appendChild(conclusionPanel);
  colRight.appendChild(formulaPanel);

  mainGrid.appendChild(colLeft);
  mainGrid.appendChild(colCenter);
  mainGrid.appendChild(colRight);
  root.appendChild(mainGrid);

  // 3. Load Available Cases
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
      .map((c) => `<option value="${c.case_id}">${c.case_id} (${c.state})</option>`)
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

    // Update graph with historical facts
    const gRes = await fetch(`/cases/${currentCaseId}/graph`);
    if (gRes.ok) {
      const graph = await gRes.json();
      const histFids = new Set(Object.keys(state.facts || {}));
      const filteredNodes = (graph.nodes || [])
        .filter((n) => histFids.has(n.fact_id || n.id))
        .map((n) => {
          const fid = n.fact_id || n.id;
          const histFact = state.facts ? state.facts[fid] : null;
          return {
            ...n,
            id: fid,
            fact_id: fid,
            own_trust: histFact ? histFact.own_trust : n.own_trust,
            effective_trust: histFact ? histFact.effective_trust : n.effective_trust,
            status: histFact ? histFact.status : n.status,
          };
        });
      const filteredEdges = (graph.edges || [])
        .filter((e) => {
          const src = e.from_fact_id || e.source;
          const tgt = e.to_fact_id || e.target;
          return histFids.has(src) && histFids.has(tgt);
        })
        .map((e) => ({
          ...e,
          source: e.from_fact_id || e.source,
          target: e.to_fact_id || e.target,
        }));
      renderGraph({ nodes: filteredNodes, edges: filteredEdges }, document.getElementById("graph-panel"));
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
