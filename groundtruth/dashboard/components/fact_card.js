/**
 * GroundTruth FactCard Component (DES-6, DASH-3)
 * Enforces rule DES-6: Always shows source type, trust, status, and provenance.
 */

import { renderStatusBadge } from "./status_badge.js";
import { renderSourceChip } from "./source_chip.js";
import { renderTrustBar } from "./trust_bar.js";

export function renderFactCard(fact, options = {}) {
  const tCite = options.tCite || 0.50;
  const tAuto = options.tAuto || 0.60;

  const status = (fact.status || "ACTIVE").toUpperCase();
  const fid = fact.fact_id || "fact_unknown";
  const type = fact.type || "unknown_type";

  // Visual treatments (Section 7.1)
  let cardBorder = "1px solid var(--gt-line)";
  let cardBg = "var(--gt-surface-1)";
  let valueStyle = "";

  if (status === "TAINTED") {
    cardBg = "repeating-linear-gradient(45deg, var(--gt-surface-1), var(--gt-surface-1) 10px, rgba(255, 77, 94, 0.08) 10px, rgba(255, 77, 94, 0.08) 20px)";
    cardBorder = "1px solid var(--gt-coral)";
  } else if (status === "QUARANTINED") {
    cardBorder = "1px dashed var(--gt-amber)";
  } else if (status === "RETRACTED") {
    valueStyle = "text-decoration: line-through; opacity: 0.6;";
    cardBorder = "1px solid var(--gt-coral)";
  } else if (status === "CONTESTED") {
    cardBorder = "1px solid var(--gt-amber)";
  }

  // Format value representation
  let valText = "";
  if (typeof fact.value === "string") {
    valText = fact.value;
  } else if (typeof fact.value === "object" && fact.value !== null) {
    if (fact.value.error) valText = fact.value.error;
    else if (fact.value.summary) valText = fact.value.summary;
    else if (fact.value.message) valText = fact.value.message;
    else if (fact.value.root_cause) valText = fact.value.root_cause;
    else if (fact.value.check_type) valText = `Ruled out: ${fact.value.check_type} (${(fact.value.scope || []).length} items)`;
    else valText = JSON.stringify(fact.value);
  }

  const derivedFromList = fact.derived_from || [];
  const provenanceText = derivedFromList.length > 0
    ? `Derived from: ${derivedFromList.join(", ")}`
    : (fact.evidence_ref ? `Evidence: ${fact.evidence_ref}` : "Root premise");

  return `
    <div class="gt-fact-card" data-fact-id="${fid}" data-status="${status}" style="
      background: ${cardBg};
      border: ${cardBorder};
      border-radius: var(--gt-radius-card);
      padding: var(--gt-space-4);
      display: flex;
      flex-direction: column;
      gap: var(--gt-space-3);
      position: relative;
      transition: border-color var(--gt-transition-normal), box-shadow var(--gt-transition-fast);
    ">
      <!-- Top Row: Type and Status Badge -->
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
        <span class="mono" style="font-size: 13px; font-weight: 600; color: var(--gt-text);">
          ${type}
        </span>
        ${renderStatusBadge(status)}
      </div>

      <!-- Middle: Value -->
      <div class="gt-fact-value" style="font-size: 13px; color: var(--gt-text); line-height: 1.4; ${valueStyle}">
        ${valText}
      </div>

      <!-- Bottom Row: Source Chip, Trust Bar, and Fact ID -->
      <div style="display: flex; flex-direction: column; gap: var(--gt-space-2); margin-top: 4px; border-top: 1px solid var(--gt-line); padding-top: var(--gt-space-2);">
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
          ${renderSourceChip(fact.source_type)}
          <span class="mono text-muted" style="font-size: 11px;" title="${fid}">
            ${fid.length > 18 ? fid.slice(0, 8) + '…' + fid.slice(-6) : fid}
          </span>
        </div>
        <div>
          ${renderTrustBar(fact.effective_trust, tCite, tAuto)}
        </div>
        <div class="mono text-muted" style="font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          ${provenanceText}
        </div>
      </div>
    </div>
  `;
}
