/**
 * GroundTruth Button Components (DES-2, DES-3, DES-11)
 * PrimaryButton: Acid Lime fill, Midnight Black text, pill shape.
 * SecondaryButton: Transparent, Cobalt Soft outline, text.
 */

export function renderPrimaryButton({ label, id = "", onClickAttr = "", disabled = false }) {
  const disabledAttr = disabled ? "disabled" : "";
  const idAttr = id ? `id="${id}"` : "";

  return `
    <button class="gt-btn-primary" ${idAttr} ${disabledAttr} ${onClickAttr} style="
      background-color: var(--gt-lime);
      color: var(--gt-midnight);
      border: none;
      border-radius: var(--gt-radius-pill);
      padding: 8px 18px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      cursor: ${disabled ? "not-allowed" : "pointer"};
      opacity: ${disabled ? "0.4" : "1.0"};
      transition: opacity var(--gt-transition-fast), filter var(--gt-transition-fast);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    ">
      ${label}
    </button>
  `;
}

export function renderSecondaryButton({ label, id = "", onClickAttr = "", disabled = false }) {
  const disabledAttr = disabled ? "disabled" : "";
  const idAttr = id ? `id="${id}"` : "";

  return `
    <button class="gt-btn-secondary" ${idAttr} ${disabledAttr} ${onClickAttr} style="
      background-color: transparent;
      color: var(--gt-text);
      border: 1px solid var(--gt-cobalt-soft);
      border-radius: var(--gt-radius-pill);
      padding: 7px 16px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      cursor: ${disabled ? "not-allowed" : "pointer"};
      opacity: ${disabled ? "0.4" : "1.0"};
      transition: background-color var(--gt-transition-fast), border-color var(--gt-transition-fast);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    ">
      ${label}
    </button>
  `;
}
