/**
 * GroundTruth StatTile Component (DES-8)
 * Enforces rule DES-8: Measured numbers only. Large tabular figure, uppercase caption, thin divider.
 */

export function renderStatTile({ value, label, subtext = "", highlight = false }) {
  const valueColor = highlight ? "var(--gt-lime)" : "var(--gt-text)";

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
      <div style="
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--gt-text-muted);
      ">
        ${label}
      </div>
      ${subtext ? `
        <div style="
          margin-top: 4px;
          padding-top: 4px;
          border-top: 1px solid var(--gt-line);
          font-size: 11px;
          color: var(--gt-cobalt-soft);
          font-variant-numeric: tabular-nums;
        ">
          ${subtext}
        </div>
      ` : ""}
    </div>
  `;
}
