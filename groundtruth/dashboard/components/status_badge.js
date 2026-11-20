/**
 * GroundTruth StatusBadge Component (DES-3, DES-4)
 * Enforces rule DES-4: Never color alone. Always color + SVG icon + word.
 */

const ICONS = {
  check: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  opposingArrows: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/><line x1="17" y1="7" x2="7" y2="17"/></svg>`,
  boxLock: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`,
  cross: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  warningTriangle: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
};

const STATUS_CONFIG = {
  ACTIVE: {
    colorVar: "var(--gt-lime)",
    bgVar: "rgba(212, 255, 36, 0.12)",
    icon: ICONS.check,
    word: "ACTIVE",
  },
  CONTESTED: {
    colorVar: "var(--gt-amber)",
    bgVar: "rgba(255, 176, 32, 0.12)",
    icon: ICONS.opposingArrows,
    word: "CONTESTED",
  },
  QUARANTINED: {
    colorVar: "var(--gt-amber)",
    bgVar: "rgba(255, 176, 32, 0.12)",
    icon: ICONS.boxLock,
    word: "QUARANTINED",
  },
  RETRACTED: {
    colorVar: "var(--gt-coral)",
    bgVar: "rgba(255, 77, 94, 0.12)",
    icon: ICONS.cross,
    word: "RETRACTED",
  },
  TAINTED: {
    colorVar: "var(--gt-coral)",
    bgVar: "rgba(255, 77, 94, 0.12)",
    icon: ICONS.warningTriangle,
    word: "TAINTED",
  },
  // Gate Verdicts
  ADMIT: {
    colorVar: "var(--gt-lime)",
    bgVar: "var(--gt-lime)",
    textColor: "var(--gt-midnight)",
    icon: ICONS.check,
    word: "ADMIT",
  },
  QUARANTINE: {
    colorVar: "var(--gt-amber)",
    bgVar: "transparent",
    textColor: "var(--gt-amber)",
    icon: ICONS.boxLock,
    word: "QUARANTINE",
  },
  REJECT: {
    colorVar: "var(--gt-coral)",
    bgVar: "transparent",
    textColor: "var(--gt-coral)",
    icon: ICONS.cross,
    word: "REJECT",
  },
};

export function renderStatusBadge(status) {
  const normalized = (status || "ACTIVE").toUpperCase();
  const cfg = STATUS_CONFIG[normalized] || STATUS_CONFIG.ACTIVE;
  const textColor = cfg.textColor || cfg.colorVar;

  return `
    <span class="gt-status-badge status-${normalized.toLowerCase()}" style="
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: var(--gt-radius-pill);
      border: 1px solid ${cfg.colorVar};
      background: ${cfg.bgVar};
      color: ${textColor};
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      line-height: 1;
    " data-status="${normalized}">
      <span class="badge-icon" aria-hidden="true" style="display: flex; align-items: center;">${cfg.icon}</span>
      <span class="badge-word">${cfg.word}</span>
    </span>
  `;
}
