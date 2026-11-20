/**
 * GroundTruth Sub-Navigation Tab Bar (DASH-NAV)
 * Provides sleek, futuristic tabbed navigation across all system views/pages:
 * - 🌐 Causality Graph
 * - ⚡ Gate Stream
 * - 📋 Admitted Facts
 * - 🎯 Root Cause & Decision
 * - 📊 Benchmark Counters
 * - 📐 Trust Formula
 * - 🧭 All Panels (Cockpit)
 *
 * Enforces DES-1: Zero raw hex codes (all colors use CSS variables).
 */

export const NAV_TABS = [
  { id: "graph", label: "Causality Graph", icon: "🌐", badge: "Interactive DAG" },
  { id: "verdicts", label: "Gate Stream", icon: "⚡", badge: "Live SSE" },
  { id: "facts", label: "Admitted Facts", icon: "📋", badge: "Ledger" },
  { id: "conclusion", label: "Root Cause & Decision", icon: "🎯", badge: "Resolution" },
  { id: "counters", label: "Benchmark Counters", icon: "📊", badge: "Metrics" },
  { id: "formula", label: "Trust Formula", icon: "📐", badge: "TRUST-5" },
  { id: "all", label: "All Panels", icon: "🧭", badge: "Cockpit" },
];

export function createSubNavBar({ onTabSelect = null, initialTab = "graph" } = {}) {
  const nav = document.createElement("nav");
  nav.className = "sub-nav-bar";
  nav.id = "sub-nav-bar";

  const tabsContainer = document.createElement("div");
  tabsContainer.className = "sub-nav-tabs";

  NAV_TABS.forEach((tab) => {
    const btn = document.createElement("button");
    btn.className = `nav-tab ${tab.id === initialTab ? "active" : ""}`;
    btn.dataset.tab = tab.id;
    btn.id = `nav-tab-${tab.id}`;
    btn.title = `Switch to ${tab.label}`;
    btn.innerHTML = `
      <span class="tab-icon" style="font-size: 13px;">${tab.icon}</span>
      <span class="tab-label">${tab.label}</span>
      <span class="tab-badge mono" style="
        font-size: 9px;
        padding: 1px 6px;
        border-radius: var(--gt-radius-pill);
        background: rgba(255, 255, 255, 0.05);
        color: var(--gt-text-muted);
        letter-spacing: 0.04em;
        text-transform: uppercase;
      ">${tab.badge}</span>
    `;

    btn.addEventListener("click", () => {
      if (onTabSelect) onTabSelect(tab.id);
    });

    tabsContainer.appendChild(btn);
  });

  nav.appendChild(tabsContainer);
  return nav;
}

export function setActiveNavTab(tabId, container = document) {
  const tabs = container.querySelectorAll(".nav-tab");
  tabs.forEach((t) => {
    if (t.dataset.tab === tabId) {
      t.classList.add("active");
    } else {
      t.classList.remove("active");
    }
  });
}
