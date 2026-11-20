/**
 * GroundTruth StatTile Component (DES-8)
 * Enforces rule DES-8: Measured numbers only. Large tabular figure, uppercase caption, thin divider.
 */

export function renderStatTile({ value, label, subtext = "", highlight = false, barPercent = null }) {
  const valueColor = highlight ? "var(--gt-lime)" : "var(--gt-text)";
  const barColor = highlight ? "var(--gt-lime)" : "rgba(138, 148, 168, 0.5)";

  const barMarkup = barPercent !== null ? `
    <div style="width: 100%; height: 4px; background: rgba(255, 255, 255, 0.08); border-radius: 2px; overflow: hidden; margin-top: 6px;">
      <div style="width: ${Math.min(100, Math.max(0, barPercent))}%; height: 100%; background: ${barColor}; border-radius: 2px; transition: width 0.4s ease;"></div>
    </div>
  ` : "";

  return `
    <div class="gt-stat-tile" style="
      background: var(--gt-surface-2);
      border: 1px solid var(--gt-line);
      border-radius: var(--gt-radius-card);
      padding: var(--gt-space-4);
      display: flex;
      flex-direction: column;
      gap: 4px;
    ">
      <div class="mono" style="
        font-size: 28px;
        font-weight: 600;
        line-height: 1.1;
        color: ${valueColor};
        font-variant-numeric: tabular-nums;
      ">
        ${value}
      </div>
      ${barMarkup}
      <div style="
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--gt-text-muted);
        margin-top: 4px;
      ">
        ${label}
      </div>
      ${subtext ? `
        <div style="
          margin-top: 4px;
          padding-top: 4px;
          border-top: 1px solid var(--gt-line);
          font-size: 11px;
          color: ${highlight ? 'var(--gt-lime)' : 'var(--gt-cobalt-soft)'};
          font-variant-numeric: tabular-nums;
        ">
          ${subtext}
        </div>
      ` : ""}
    </div>
  `;
}
