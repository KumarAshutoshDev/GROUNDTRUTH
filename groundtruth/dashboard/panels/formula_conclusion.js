/**
 * GroundTruth Formula & Conclusion Panels (TRUST-5, PRD Beat 8)
 * Formula Panel: Transparently explains trust algebra (BASE, T_cite, T_auto, half-lives, min formula).
 * Conclusion Panel: Traces full provenance of the conclusion fact and renders the
 * explicit Amber callout: "WHAT WE COULD NOT DETERMINE".
 */

export function createFormulaPanel() {
  const panel = document.createElement("section");
  panel.className = "gt-panel gt-formula-panel";
  panel.id = "formula-panel";

  panel.innerHTML = `
    <div class="gt-panel-header">
      <h2>Trust Formula & Thresholds</h2>
      <span class="mono text-muted" style="font-size: 10px;">TRUST-5</span>
    </div>
    <div class="gt-panel-body" style="display: flex; flex-direction: column; gap: var(--gt-space-3);">
      <!-- Math formula in mono -->
      <div style="
        background: var(--gt-surface-2);
        border: 1px solid var(--gt-line);
        border-radius: var(--gt-radius-card);
        padding: var(--gt-space-3);
      ">
        <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gt-text-muted); margin-bottom: 4px;">
          Trust Derivation Algebra
        </div>
        <div class="mono" style="font-size: 12px; color: var(--gt-lime); line-height: 1.5;">
          effective_trust(f) = min(own_trust(f), min_{p ∈ parents} effective_trust(p))
        </div>
        <div class="mono text-muted" style="font-size: 11px; margin-top: 4px;">
          own_trust(f) = min(BASE[source_type], self_confidence) × decay(age, half_life)
        </div>
      </div>

      <!-- Threshold Info Cards -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--gt-space-2);">
        <div style="background: var(--gt-surface-2); border: 1px solid var(--gt-line); border-radius: 12px; padding: 10px;">
          <div style="font-size: 10px; color: var(--gt-text-muted); text-transform: uppercase;">Citation Bar (T_cite)</div>
          <div class="mono" style="font-size: 18px; font-weight: 600; color: var(--gt-cobalt-soft);">0.50</div>
        </div>
        <div style="background: var(--gt-surface-2); border: 1px solid var(--gt-line); border-radius: 12px; padding: 10px;">
          <div style="font-size: 10px; color: var(--gt-text-muted); text-transform: uppercase;">Autonomous Fix (T_auto)</div>
          <div class="mono" style="font-size: 18px; font-weight: 600; color: var(--gt-lime);">0.60</div>
        </div>
      </div>

      <!-- Base Trust Table -->
      <div style="font-size: 11px; color: var(--gt-text-muted);">
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>human_input</span>
          <span class="mono" style="color: var(--gt-text);">0.95</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>tool_output</span>
          <span class="mono" style="color: var(--gt-text);">0.90</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>document</span>
          <span class="mono" style="color: var(--gt-text);">0.70</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>agent_inference</span>
          <span class="mono" style="color: var(--gt-text);">0.60</span>
        </div>
      </div>
    </div>
  `;

  return panel;
}

export function createConclusionPanel() {
  const panel = document.createElement("section");
  panel.className = "gt-panel gt-conclusion-panel";
  panel.id = "conclusion-panel";

  panel.innerHTML = `
    <div class="gt-panel-header" style="flex-direction: column; align-items: flex-start; gap: 4px;">
      <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
        <h2>Attributable Conclusion</h2>
        <span class="mono text-muted" id="conclusion-fact-id-label" style="font-size: 10px;">None</span>
      </div>
      <div style="font-size: 11px; color: var(--gt-text-muted);">
        Deterministic root cause with cryptographic provenance chain
      </div>
    </div>
    <div class="gt-panel-body" id="conclusion-body" style="display: flex; flex-direction: column; gap: var(--gt-space-3);">
      <div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">
        No conclusion fact admitted yet.
      </div>
    </div>
  `;

  return panel;
}

export function updateConclusionPanel({ conclusionFact, lineageFacts = [], missingChecks = [], contestedFacts = [] }, container) {
  const body = container.querySelector("#conclusion-body") || container;
  const idLabel = container.querySelector("#conclusion-fact-id-label");

  if (!conclusionFact) {
    if (idLabel) idLabel.textContent = "None";
    body.innerHTML = `
      <div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">
        No attributable conclusion admitted yet.
      </div>
      ${renderUndeterminedBlock(missingChecks, contestedFacts)}
    `;
    return;
  }

  if (idLabel) idLabel.textContent = conclusionFact.fact_id;

  const val = conclusionFact.value || {};
  const rootCause = val.root_cause || JSON.stringify(val);
  const fixRec = val.fix_recommendation || "";
  const effTrust = Number(conclusionFact.effective_trust || 0).toFixed(2);
  const status = (conclusionFact.status || "ACTIVE").toUpperCase();

  const isTainted = status === "TAINTED" || Number(effTrust) === 0;
  const isLowTrust = Number(effTrust) < 0.60;

  let borderColor = "var(--gt-lime)";
  let badgeColor = "var(--gt-lime)";
  let cardTitle = "VALIDATED ROOT CAUSE";
  let cardBg = "var(--gt-surface-2)";
  let glowStyle = "var(--gt-glow-lime)";

  if (isTainted) {
    borderColor = "var(--gt-coral)";
    badgeColor = "var(--gt-coral)";
    cardTitle = "TAINTED CLAIM (TRUST COLLAPSED)";
    cardBg = "repeating-linear-gradient(45deg, var(--gt-surface-2), var(--gt-surface-2) 10px, rgba(255, 42, 85, 0.06) 10px, rgba(255, 42, 85, 0.06) 20px)";
    glowStyle = "0 0 16px rgba(255, 42, 85, 0.3)";
  } else if (isLowTrust) {
    borderColor = "var(--gt-amber)";
    badgeColor = "var(--gt-amber)";
    cardTitle = "UNVERIFIED CLAIM";
    glowStyle = "0 0 16px rgba(255, 183, 3, 0.3)";
  }

  body.innerHTML = `
    <!-- Conclusion Card -->
    <div style="
      background: ${cardBg};
      border: 1px solid ${borderColor};
      border-radius: var(--gt-radius-card);
      padding: var(--gt-space-4);
      display: flex;
      flex-direction: column;
      gap: 8px;
      box-shadow: ${glowStyle};
      transition: all 0.3s ease;
    ">
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
        <span style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: ${badgeColor}; display: flex; align-items: center; gap: 4px;">
          ${isTainted ? '⚠️' : '🎯'} ${cardTitle}
        </span>
        <span class="mono" style="font-size: 12px; color: ${badgeColor}; font-weight: 700; background: rgba(255,255,255,0.06); padding: 2px 8px; border-radius: 999px;">
          Trust: ${effTrust}
        </span>
      </div>

      <div style="font-size: 14px; font-weight: 600; color: var(--gt-text); line-height: 1.4;">
        ${rootCause}
      </div>

      ${isTainted ? `
        <div style="font-size: 11px; color: var(--gt-coral); background: rgba(255, 42, 85, 0.1); border: 1px solid rgba(255, 42, 85, 0.25); border-radius: 6px; padding: 6px 10px; line-height: 1.4;">
          🛡️ <strong>Taint Cascade (INV-9):</strong> An upstream premise was retracted. Trust automatically collapsed to 0.00 to block ungrounded automated fixes.
        </div>
      ` : ""}

      ${fixRec ? `
        <div style="font-size: 12px; color: var(--gt-cobalt-soft); margin-top: 2px;">
          <strong>Recommendation:</strong> ${fixRec}
        </div>
      ` : ""}
    </div>

    <!-- Provenance Lineage Chain -->
    ${lineageFacts.length > 0 ? `
      <div>
        <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--gt-text-muted); margin-bottom: 6px;">
          Provenance Chain
        </div>
        <div style="display: flex; flex-direction: column; gap: 4px;">
          ${lineageFacts.map((lf) => `
            <div class="mono" style="font-size: 11px; background: var(--gt-surface-1); border: 1px solid var(--gt-line); border-radius: 6px; padding: 4px 8px; display: flex; justify-content: space-between;">
              <span style="color: var(--gt-text);">${lf.type}</span>
              <span style="color: var(--gt-text-muted);">${lf.fact_id} (${Number(lf.effective_trust || 0).toFixed(2)})</span>
            </div>
          `).join("")}
        </div>
      </div>
    ` : ""}

    <!-- Explicit Amber Block: WHAT WE COULD NOT DETERMINE (PRD Beat 8) -->
    ${renderUndeterminedBlock(missingChecks, contestedFacts)}
  `;
}

function renderUndeterminedBlock(missingChecks = [], contestedFacts = []) {
  const items = [];
  missingChecks.forEach((c) => items.push(`Unverified check: <code>${c}</code>`));
  contestedFacts.forEach((cf) => items.push(`Unresolved conflicting claim: <code>${cf}</code>`));

  if (items.length === 0) {
    items.push("All required fixture checks verified with valid provenance.");
  }

  return `
    <div class="gt-undetermined-block" style="
      background: rgba(255, 176, 32, 0.08);
      border: 1px solid var(--gt-amber);
      border-radius: var(--gt-radius-card);
      padding: var(--gt-space-3);
      display: flex;
      flex-direction: column;
      gap: 6px;
    ">
      <div style="
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--gt-amber);
        display: flex;
        align-items: center;
        gap: 6px;
      ">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        WHAT WE COULD NOT DETERMINE
      </div>
      <ul style="padding-left: 18px; font-size: 11px; color: var(--gt-text); line-height: 1.5;">
        ${items.map((it) => `<li>${it}</li>`).join("")}
      </ul>
    </div>
  `;
}
