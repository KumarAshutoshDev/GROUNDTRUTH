/**
 * GroundTruth SourceChip Component (DES-3)
 * Enforces rule DES-3: Source chips use Cobalt Soft outline only. Never lime, amber, or coral.
 */

const SOURCE_ICONS = {
  tool_output: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`,
  document: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
  agent_inference: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="3"/><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48 2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48 2.83-2.83"/></svg>`,
  human_input: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
};

export function renderSourceChip(sourceType) {
  const normType = (sourceType || "tool_output").toLowerCase();
  const icon = SOURCE_ICONS[normType] || SOURCE_ICONS.tool_output;
  const label = normType.replace("_", " ").toUpperCase();

  return `
    <span class="gt-source-chip" style="
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 2px 8px;
      border-radius: var(--gt-radius-pill);
      border: 1px solid var(--gt-cobalt-soft);
      background: transparent;
      color: var(--gt-cobalt-soft);
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      line-height: 1;
    " data-source-type="${normType}">
      <span aria-hidden="true" style="display: flex; align-items: center;">${icon}</span>
      <span>${label}</span>
    </span>
  `;
}
