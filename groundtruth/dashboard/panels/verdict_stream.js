/**
 * GroundTruth Live Verdict Stream Panel (DES-5, DASH-2, GATE-4)
 * Displays gate evaluations in real time.
 * Enforces DES-5: QUARANTINE and REJECT rows are visually louder, taller, and display
 * the explicit reason inline (GATE-4).
 */

import { renderStatusBadge } from "../components/status_badge.js";

export function createVerdictStreamPanel() {
  const panel = document.createElement("section");
  panel.className = "gt-panel gt-verdict-stream-panel";
  panel.id = "verdict-stream-panel";

  panel.innerHTML = `
    <div class="gt-panel-header">
      <div style="display: flex; align-items: center; gap: 8px;">
        <h2>Gate Verdict Stream</h2>
        <span class="mono text-muted" id="verdict-count" style="font-size: 11px;">(0)</span>
      </div>
      <span class="mono" style="font-size: 10px; color: var(--gt-lime); display: flex; align-items: center; gap: 5px;">
        <span style="width: 6px; height: 6px; border-radius: 50%; background: var(--gt-lime); display: inline-block;"></span>
        LIVE SSE
      </span>
    </div>
    <div class="gt-panel-body" id="verdict-stream-list" style="
      display: flex;
      flex-direction: column;
      gap: var(--gt-space-2);
      max-height: 480px;
      overflow-y: auto;
    ">
      <div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">
        Awaiting gate evaluation verdicts…
      </div>
    </div>
  `;

  return panel;
}

export function appendVerdictRow(eventData, container) {
  const list = container.querySelector("#verdict-stream-list") || container;
  const emptyState = list.querySelector(".gt-empty-state");
  if (emptyState) {
    emptyState.remove();
  }

  const payload = eventData.payload || {};
  const verdict = (payload.verdict || "ADMIT").toUpperCase();
  const fact = payload.fact || {};
  const factType = fact.type || payload.type || "unknown_fact";
  const factId = fact.fact_id || payload.fact_id || "";
  const reason = payload.reason || "Admitted to case context";
  const actor = eventData.actor || fact.agent_id || "agent";
  const seq = eventData.seq || "";

  const isReject = verdict === "REJECT";
  const isQuarantine = verdict === "QUARANTINE";
  const isLoud = isReject || isQuarantine;

  const row = document.createElement("div");
  row.className = `gt-verdict-row gt-verdict-${verdict.toLowerCase()} ${isLoud ? 'gt-verdict-loud' : ''}`;
  row.setAttribute("data-verdict", verdict);
  row.setAttribute("data-seq", seq);

  let bg = "var(--gt-surface-2)";
  let border = "1px solid var(--gt-line)";
  let padding = "var(--gt-space-3)";

  if (isReject) {
    bg = "rgba(255, 77, 94, 0.08)";
    border = "1px solid var(--gt-coral)";
    padding = "var(--gt-space-4)";
  } else if (isQuarantine) {
    bg = "rgba(255, 176, 32, 0.08)";
    border = "1px solid var(--gt-amber)";
    padding = "var(--gt-space-4)";
  }

  row.style.cssText = `
    background: ${bg};
    border: ${border};
    border-radius: var(--gt-radius-card);
    padding: ${padding};
    display: flex;
    flex-direction: column;
    gap: 6px;
    animation: slideDown var(--gt-transition-normal);
  `;

  row.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
      <div style="display: flex; align-items: center; gap: 8px;">
        ${renderStatusBadge(verdict)}
        <span class="mono" style="font-size: 13px; font-weight: 600; color: var(--gt-text);">
          ${factType}
        </span>
      </div>
      <span class="mono text-muted" style="font-size: 10px;">
        #${seq} by ${actor}
      </span>
    </div>
    ${isLoud ? `
      <!-- DES-5: Inline prominent reason callout for rejections/quarantines -->
      <div class="gt-verdict-reason" style="
        font-size: 12px;
        line-height: 1.4;
        color: ${isReject ? 'var(--gt-coral)' : 'var(--gt-amber)'};
        background: var(--gt-midnight);
        border-radius: 8px;
        padding: 6px 10px;
        border-left: 3px solid ${isReject ? 'var(--gt-coral)' : 'var(--gt-amber)'};
      ">
        <strong>Reason:</strong> ${reason}
      </div>
    ` : `
      <div class="gt-verdict-reason text-muted" style="font-size: 11px; font-style: italic;">
        ${reason}
      </div>
    `}
  `;

  list.prepend(row);

  // Update counter
  const counter = container.querySelector("#verdict-count");
  if (counter) {
    const total = list.querySelectorAll(".gt-verdict-row").length;
    counter.textContent = `(${total})`;
  }
}
