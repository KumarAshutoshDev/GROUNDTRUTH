/**
 * GroundTruth TrustBar Component (DES-7)
 * Enforces rule DES-7: Trust band colors use T_cite and T_auto from domain pack.
 */

export function renderTrustBar(trustValue, tCite = 0.50, tAuto = 0.60) {
  const val = Math.max(0.0, Math.min(1.0, parseFloat(trustValue) || 0.0));
  const pct = Math.round(val * 100);
  const citePct = Math.round(tCite * 100);
  const autoPct = Math.round(tAuto * 100);

  let fillColor = "var(--gt-lime)";
  let isZero = false;

  if (val >= tAuto) {
    fillColor = "var(--gt-lime)";
  } else if (val >= tCite) {
    fillColor = "var(--gt-cobalt-soft)";
  } else if (val > 0.0) {
    fillColor = "var(--gt-amber)";
  } else {
    isZero = true;
    fillColor = "transparent";
  }

  const borderStyle = isZero ? "1px solid var(--gt-coral)" : "none";

  return `
    <div class="gt-trust-bar-container" style="
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      font-family: var(--gt-font-mono);
      font-variant-numeric: tabular-nums;
      color: var(--gt-text-muted);
    ">
      <div class="gt-trust-bar-track" style="
        position: relative;
        flex: 1;
        height: 6px;
        background: var(--gt-line);
        border-radius: var(--gt-radius-pill);
        overflow: visible;
        border: ${borderStyle};
      ">
        <div class="gt-trust-bar-fill" style="
          width: ${pct}%;
          height: 100%;
          background: ${fillColor};
          border-radius: var(--gt-radius-pill);
          transition: width var(--gt-transition-bar), background var(--gt-transition-fast);
        "></div>
        <!-- Tick at T_cite -->
        <span class="gt-tick-cite" title="T_cite (${tCite.toFixed(2)})" style="
          position: absolute;
          left: ${citePct}%;
          top: -2px;
          bottom: -2px;
          width: 1px;
          background: var(--gt-cobalt-soft);
          z-index: 2;
        "></span>
        <!-- Tick at T_auto -->
        <span class="gt-tick-auto" title="T_auto (${tAuto.toFixed(2)})" style="
          position: absolute;
          left: ${autoPct}%;
          top: -2px;
          bottom: -2px;
          width: 1px;
          background: var(--gt-lime);
          z-index: 2;
        "></span>
      </div>
      <span class="gt-trust-score" style="color: ${isZero ? 'var(--gt-coral)' : 'var(--gt-text)'}; min-width: 32px; text-align: right;">
        ${val.toFixed(2)}
      </span>
    </div>
  `;
}
