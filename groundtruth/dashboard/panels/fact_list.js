/**
 * GroundTruth Fact List Panel (DASH-3, DES-6, Design Section 7.1)
 * Displays the current projected facts of a case with interactive filtering and live in-place updates.
 */

import { renderFactCard } from "../components/fact_card.js";

export function createFactListPanel() {
  const panel = document.createElement("section");
  panel.className = "gt-panel gt-fact-list-panel";
  panel.id = "fact-list-panel";

  panel.innerHTML = `
    <div class="gt-panel-header" style="flex-wrap: wrap; gap: 8px;">
      <div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <h2>Admitted Facts</h2>
          <span class="mono text-muted" id="fact-count" style="font-size: 11px;">(0)</span>
        </div>
        <div style="font-size: 11px; color: var(--gt-text-muted); margin-top: 2px;">
          Verified shared context available to agents
        </div>
      </div>
      <!-- Status Filter Tabs -->
      <div class="gt-filter-tabs" id="fact-filter-tabs" style="
        display: flex;
        gap: 4px;
        background: var(--gt-surface-2);
        padding: 3px;
        border-radius: var(--gt-radius-pill);
        border: 1px solid var(--gt-line);
      ">
        <button class="gt-filter-tab active" data-filter="ALL" style="
          background: var(--gt-cobalt-soft);
          color: var(--gt-midnight);
          border: none;
          border-radius: var(--gt-radius-pill);
          padding: 3px 10px;
          font-size: 10px;
          font-weight: 700;
          cursor: pointer;
        ">ALL</button>
        <button class="gt-filter-tab" data-filter="ACTIVE" style="
          background: transparent;
          color: var(--gt-text-muted);
          border: none;
          border-radius: var(--gt-radius-pill);
          padding: 3px 10px;
          font-size: 10px;
          font-weight: 600;
          cursor: pointer;
        ">ACTIVE</button>
        <button class="gt-filter-tab" data-filter="QUARANTINED" style="
          background: transparent;
          color: var(--gt-text-muted);
          border: none;
          border-radius: var(--gt-radius-pill);
          padding: 3px 10px;
          font-size: 10px;
          font-weight: 600;
          cursor: pointer;
        ">QUARANTINED</button>
        <button class="gt-filter-tab" data-filter="CONTESTED" style="
          background: transparent;
          color: var(--gt-text-muted);
          border: none;
          border-radius: var(--gt-radius-pill);
          padding: 3px 10px;
          font-size: 10px;
          font-weight: 600;
          cursor: pointer;
        ">CONTESTED</button>
        <button class="gt-filter-tab" data-filter="TAINTED" style="
          background: transparent;
          color: var(--gt-text-muted);
          border: none;
          border-radius: var(--gt-radius-pill);
          padding: 3px 10px;
          font-size: 10px;
          font-weight: 600;
          cursor: pointer;
        ">TAINTED</button>
      </div>
    </div>
    <div class="gt-panel-body" id="fact-card-list" style="
      display: flex;
      flex-direction: column;
      gap: var(--gt-space-3);
      max-height: 540px;
      overflow-y: auto;
    ">
      <div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">
        No admitted facts in case yet.
      </div>
    </div>
  `;

  // Attach filter tab listeners
  const tabs = panel.querySelectorAll(".gt-filter-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => {
        t.style.background = "transparent";
        t.style.color = "var(--gt-text-muted)";
        t.classList.remove("active");
      });
      tab.style.background = "var(--gt-cobalt-soft)";
      tab.style.color = "var(--gt-midnight)";
      tab.classList.add("active");

      const filter = tab.getAttribute("data-filter");
      filterFacts(panel, filter);
    });
  });

  return panel;
}

export function filterFacts(panel, filter) {
  const cards = panel.querySelectorAll(".gt-fact-card");
  cards.forEach((card) => {
    const cardStatus = card.getAttribute("data-status");
    if (filter === "ALL" || cardStatus === filter) {
      card.style.display = "flex";
    } else {
      card.style.display = "none";
    }
  });
}

export function renderFactList(facts, container, options = {}) {
  const listContainer = container.querySelector("#fact-card-list") || container;
  const countEl = container.querySelector("#fact-count");

  const factArray = Array.isArray(facts) ? facts : Object.values(facts || {});
  if (countEl) {
    countEl.textContent = `(${factArray.length})`;
  }

  if (factArray.length === 0) {
    listContainer.innerHTML = `
      <div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">
        No admitted facts in case yet.
      </div>
    `;
    return;
  }

  // Render cards (newest first based on created_at or fact_id)
  const sorted = [...factArray].sort((a, b) => {
    const tsA = a.created_at || "";
    const tsB = b.created_at || "";
    return tsB.localeCompare(tsA);
  });

  listContainer.innerHTML = sorted.map((f) => renderFactCard(f, options)).join("");

  // Re-apply active filter
  const activeTab = container.querySelector(".gt-filter-tab.active");
  if (activeTab) {
    filterFacts(container, activeTab.getAttribute("data-filter"));
  }
}
