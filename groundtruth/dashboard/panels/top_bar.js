/**
 * GroundTruth Top Navigation Bar & Decision Banner (Design Section 7.3, Architecture Section 13)
 * Renders the headline, case switcher, state dot, and prominent Decision Pill.
 * Enforces high-visibility transition on signal flip from AUTO_FIX to ESCALATE.
 */

export function createTopBar({ onCaseSwitch = null } = {}) {
  const header = document.createElement("header");
  header.className = "top-bar";
  header.id = "dashboard-top-bar";

  header.innerHTML = `
    <!-- Left: Brand and Case Switcher -->
    <div style="display: flex; align-items: center; gap: 16px;">
      <div style="display: flex; align-items: baseline; gap: 4px;">
        <span style="font-size: 18px; font-weight: 700; letter-spacing: -0.02em; color: var(--gt-text);">GroundTruth</span>
        <span class="accent-lime" style="font-size: 16px;">context</span>
      </div>

      <div style="height: 18px; width: 1px; background: var(--gt-line);"></div>

      <!-- Case Switcher & State Dot -->
      <div style="display: flex; align-items: center; gap: 8px;">
        <span class="gt-state-dot" id="case-state-dot" title="Case Status" style="
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--gt-cobalt-soft);
          display: inline-block;
          box-shadow: 0 0 8px rgba(91, 141, 239, 0.4);
        "></span>
        <select id="case-selector" class="mono" style="
          background: var(--gt-surface-2);
          color: var(--gt-text);
          border: 1px solid var(--gt-line);
          border-radius: var(--gt-radius-pill);
          padding: 4px 12px;
          font-size: 12px;
          cursor: pointer;
          outline: none;
        ">
          <option value="">Loading cases…</option>
        </select>
      </div>
    </div>

    <!-- Right: Decision Signal Banner & Pill -->
    <div style="display: flex; align-items: center; gap: 12px;" id="decision-banner-container">
      <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 2px;">
        <span style="font-size: 9px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--gt-text-muted);">
          Autonomous Routing
        </span>
        <div id="decision-missing-checks" class="mono text-muted" style="font-size: 10px; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"></div>
      </div>
      <div id="decision-pill" class="gt-decision-pill" style="
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 18px;
        border-radius: var(--gt-radius-pill);
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        background: transparent;
        border: 1px solid var(--gt-cobalt-soft);
        color: var(--gt-cobalt-soft);
        transition: all var(--gt-transition-normal);
      ">
        <span id="decision-icon">○</span>
        <span id="decision-text">INITIALIZING</span>
      </div>
    </div>
  `;

  if (onCaseSwitch) {
    const selector = header.querySelector("#case-selector");
    selector.addEventListener("change", (e) => onCaseSwitch(e.target.value));
  }

  return header;
}

export function updateDecisionPill(decisionData, container = document) {
  const pill = container.querySelector("#decision-pill");
  const icon = container.querySelector("#decision-icon");
  const text = container.querySelector("#decision-text");
  const missingEl = container.querySelector("#decision-missing-checks");

  if (!pill || !text) return;

  const signal = (decisionData.signal || "NEED_MORE").toUpperCase();
  const reasons = decisionData.reasons || [];
  const missingChecks = decisionData.missing_checks || [];

  if (signal === "AUTO_FIX") {
    // Lime fill pill (DES-2, Section 7.3)
    pill.style.background = "var(--gt-lime)";
    pill.style.border = "1px solid var(--gt-lime)";
    pill.style.color = "var(--gt-midnight)";
    pill.style.boxShadow = "var(--gt-glow-lime)";
    if (icon) icon.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>`;
    text.textContent = "AUTO_FIX";
    if (missingEl) missingEl.textContent = "Ready for execution";
  } else if (signal === "ESCALATE") {
    // Loud Alert Coral fill pill (PRD Beat 6: largest visual change in product)
    pill.style.background = "var(--gt-coral)";
    pill.style.border = "1px solid var(--gt-coral)";
    pill.style.color = "var(--gt-text)";
    pill.style.boxShadow = "var(--gt-glow-coral)";
    if (icon) icon.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    text.textContent = "ESCALATE";
    if (missingEl) missingEl.textContent = reasons.length > 0 ? reasons[0] : "Requires human intervention";
  } else {
    // NEED_MORE: Cobalt Soft outline pill (Section 7.3)
    pill.style.background = "transparent";
    pill.style.border = "1px solid var(--gt-cobalt-soft)";
    pill.style.color = "var(--gt-cobalt-soft)";
    pill.style.boxShadow = "none";
    if (icon) icon.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
    text.textContent = "NEED_MORE";
    if (missingEl) {
      missingEl.textContent = missingChecks.length > 0
        ? `Missing: ${missingChecks.slice(0, 2).join(", ")}${missingChecks.length > 2 ? '…' : ''}`
        : "Investigating facts";
    }
  }
}

export function updateCaseStateDot(state, container = document) {
  const dot = container.querySelector("#case-state-dot");
  if (!dot) return;

  const st = (state || "OPEN").toUpperCase();
  if (st === "CONCLUDED") {
    dot.style.background = "var(--gt-lime)";
    dot.style.boxShadow = "var(--gt-glow-lime)";
  } else if (st === "CLOSED") {
    dot.style.background = "var(--gt-text-muted)";
    dot.style.boxShadow = "none";
  } else {
    dot.style.background = "var(--gt-cobalt-soft)";
    dot.style.boxShadow = "0 0 8px rgba(91, 141, 239, 0.4)";
  }
}
