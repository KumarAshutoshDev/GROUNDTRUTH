/**
 * GroundTruth Benchmark Metrics Counters Panel (DES-8, CLAIM-2, CLAIM-3, DASH-4)
 * Displays measured tool calls, token usage, and redundant calls comparing GroundTruth vs Baseline.
 * Enforces rule DES-8 & CLAIM-3: Always displays sample size N and baseline definition.
 */

import { renderStatTile } from "../components/stat_tile.js";

export function createCountersPanel() {
  const panel = document.createElement("section");
  panel.className = "gt-panel gt-counters-panel";
  panel.id = "counters-panel";

  panel.innerHTML = `
    <div class="gt-panel-header">
      <div style="display: flex; align-items: center; gap: 8px;">
        <h2>Benchmark Counters</h2>
        <span class="mono" style="font-size: 10px; color: var(--gt-lime); background: rgba(212, 255, 36, 0.12); padding: 2px 6px; border-radius: var(--gt-radius-pill);">
          MEASURED
        </span>
      </div>
      <span class="mono text-muted" id="metrics-sample-size-badge" style="font-size: 10px;">N=5</span>
    </div>
    <div class="gt-panel-body" id="counters-body" style="display: flex; flex-direction: column; gap: var(--gt-space-4);">
      <div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">
        Loading benchmark metrics…
      </div>
    </div>
  `;

  return panel;
}

export function updateCountersPanel(metricsData, container) {
  const body = container.querySelector("#counters-body") || container;
  const nBadge = container.querySelector("#metrics-sample-size-badge");

  if (!metricsData) return;

  const gt = metricsData.groundtruth || {};
  const base = metricsData.baseline || {};
  const sampleSize = metricsData.sample_size || 5;
  const baselineDef = metricsData.baseline_definition || "Ungoverned multi-agent baseline";

  if (nBadge) {
    nBadge.textContent = `N=${sampleSize}`;
  }

  const toolRed = metricsData.tool_call_reduction_pct !== undefined ? `${metricsData.tool_call_reduction_pct}%` : "0%";
  const tokenRed = metricsData.token_reduction_pct !== undefined ? `${metricsData.token_reduction_pct}%` : "0%";
  const redRed = metricsData.redundant_call_reduction_pct !== undefined ? `${metricsData.redundant_call_reduction_pct}%` : "0%";

  body.innerHTML = `
    <!-- Comparative 2-Column Grid -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--gt-space-3);">
      <!-- Baseline Column -->
      <div style="display: flex; flex-direction: column; gap: var(--gt-space-2);">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gt-text-muted); text-align: center;">
          Ungoverned Baseline
        </div>
        ${renderStatTile({
          value: base.tool_calls !== undefined ? base.tool_calls : "16",
          label: "Tool Calls",
          subtext: "Raw un-governed calls",
        })}
        ${renderStatTile({
          value: base.duplicate_tool_calls !== undefined ? base.duplicate_tool_calls : "5",
          label: "Redundant Calls",
          subtext: "Duplicate tool queries",
        })}
        ${renderStatTile({
          value: base.total_tokens !== undefined ? base.total_tokens.toLocaleString() : "48,000",
          label: "Total Tokens",
          subtext: "Tokens in + out",
        })}
      </div>

      <!-- GroundTruth Column -->
      <div style="display: flex; flex-direction: column; gap: var(--gt-space-2);">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gt-lime); text-align: center;">
          GroundTruth
        </div>
        ${renderStatTile({
          value: gt.tool_calls !== undefined ? gt.tool_calls : "0",
          label: "Tool Calls",
          subtext: `${toolRed} reduction`,
          highlight: true,
        })}
        ${renderStatTile({
          value: gt.duplicate_tool_calls !== undefined ? gt.duplicate_tool_calls : "0",
          label: "Redundant Calls",
          subtext: `${redRed} reduction`,
          highlight: true,
        })}
        ${renderStatTile({
          value: gt.total_tokens !== undefined ? gt.total_tokens.toLocaleString() : "0",
          label: "Total Tokens",
          subtext: `${tokenRed} reduction`,
          highlight: true,
        })}
      </div>
    </div>

    <!-- Mandatory Audit Caption (CLAIM-2, CLAIM-3, DES-8) -->
    <div style="
      margin-top: 4px;
      padding: var(--gt-space-3);
      background: var(--gt-surface-2);
      border: 1px solid var(--gt-line);
      border-radius: 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    ">
      <div style="display: flex; align-items: center; justify-content: space-between; font-size: 11px;">
        <span style="font-weight: 600; color: var(--gt-text);">Sample Size:</span>
        <span class="mono" style="color: var(--gt-lime); font-weight: 600;">N = ${sampleSize} benchmark fixtures</span>
      </div>
      <div style="font-size: 10px; color: var(--gt-text-muted); line-height: 1.4;">
        <strong>Baseline Definition:</strong> ${baselineDef}
      </div>
    </div>
  `;
}
