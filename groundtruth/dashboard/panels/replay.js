/**
 * GroundTruth Replay Scrubber Panel (FR-6, DASH-5, DES-10)
 * Time-travel scrubber allowing users to inspect the exact historical projection
 * state at any ledger sequence number (GET /cases/{id}/state?at=N) with 0ms easing.
 */

export function createReplayPanel({ onScrub = null, onLive = null } = {}) {
  const panel = document.createElement("section");
  panel.className = "gt-panel gt-replay-panel";
  panel.id = "replay-panel";

  panel.innerHTML = `
    <div class="gt-panel-header" style="padding: var(--gt-space-3) var(--gt-space-4);">
      <div style="display: flex; align-items: center; gap: 8px;">
        <h3 style="font-size: 14px;">Historical Replay Scrubber</h3>
        <span class="mono" id="replay-status-badge" style="
          font-size: 10px;
          padding: 2px 8px;
          border-radius: var(--gt-radius-pill);
          background: var(--gt-lime);
          color: var(--gt-midnight);
          font-weight: 700;
        ">LIVE</span>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        <span class="mono text-muted" style="font-size: 11px;">
          Event <span id="current-seq-display" style="color: var(--gt-text); font-weight: 600;">0</span> / <span id="max-seq-display">0</span>
        </span>
        <button id="btn-return-live" style="
          background: transparent;
          border: 1px solid var(--gt-cobalt-soft);
          color: var(--gt-cobalt-soft);
          border-radius: var(--gt-radius-pill);
          padding: 2px 10px;
          font-size: 10px;
          font-weight: 600;
          cursor: pointer;
        ">Jump to Live</button>
      </div>
    </div>
    <div class="gt-panel-body" style="padding: var(--gt-space-3) var(--gt-space-4); display: flex; flex-direction: column; gap: 8px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <button id="btn-step-prev" title="Step backward (←)" style="
          background: var(--gt-surface-2);
          border: 1px solid var(--gt-line);
          color: var(--gt-text);
          border-radius: var(--gt-radius-pill);
          width: 28px;
          height: 28px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          font-size: 14px;
        ">‹</button>

        <div style="flex: 1; position: relative; display: flex; align-items: center;">
          <input type="range" id="replay-slider" min="1" max="1" value="1" style="
            width: 100%;
            height: 6px;
            background: var(--gt-line);
            border-radius: var(--gt-radius-pill);
            outline: none;
            accent-color: var(--gt-lime);
            cursor: pointer;
            transition: none; /* 0ms easing per DES-10 */
          " />
          <div id="scrubber-ticks-container" style="
            position: absolute;
            left: 0;
            right: 0;
            top: 0;
            bottom: 0;
            pointer-events: none;
          "></div>
        </div>

        <button id="btn-step-next" title="Step forward (→)" style="
          background: var(--gt-surface-2);
          border: 1px solid var(--gt-line);
          color: var(--gt-text);
          border-radius: var(--gt-radius-pill);
          width: 28px;
          height: 28px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          font-size: 14px;
        ">›</button>
      </div>
    </div>
  `;

  const slider = panel.querySelector("#replay-slider");
  const currDisplay = panel.querySelector("#current-seq-display");
  const maxDisplay = panel.querySelector("#max-seq-display");
  const liveBadge = panel.querySelector("#replay-status-badge");
  const btnLive = panel.querySelector("#btn-return-live");
  const btnPrev = panel.querySelector("#btn-step-prev");
  const btnNext = panel.querySelector("#btn-step-next");

  let maxSeq = 1;

  function handleScrub(val) {
    const seq = parseInt(val, 10);
    currDisplay.textContent = seq;
    slider.value = seq;

    if (seq >= maxSeq) {
      liveBadge.textContent = "LIVE";
      liveBadge.style.background = "var(--gt-lime)";
      liveBadge.style.color = "var(--gt-midnight)";
      if (onLive) onLive();
    } else {
      liveBadge.textContent = "HISTORICAL";
      liveBadge.style.background = "var(--gt-amber)";
      liveBadge.style.color = "var(--gt-midnight)";
      if (onScrub) onScrub(seq);
    }
  }

  slider.addEventListener("input", (e) => handleScrub(e.target.value));

  btnPrev.addEventListener("click", () => {
    const nextVal = Math.max(1, parseInt(slider.value, 10) - 1);
    handleScrub(nextVal);
  });

  btnNext.addEventListener("click", () => {
    const nextVal = Math.min(maxSeq, parseInt(slider.value, 10) + 1);
    handleScrub(nextVal);
  });

  btnLive.addEventListener("click", () => {
    handleScrub(maxSeq);
  });

  // Keyboard navigation
  window.addEventListener("keydown", (e) => {
    if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") {
      return;
    }
    if (e.key === "ArrowLeft") {
      btnPrev.click();
    } else if (e.key === "ArrowRight") {
      btnNext.click();
    }
  });

  panel.updateMaxSeq = (newMaxSeq, verdictTicks = []) => {
    maxSeq = Math.max(1, newMaxSeq);
    slider.max = maxSeq;
    maxDisplay.textContent = maxSeq;

    if (liveBadge.textContent === "LIVE") {
      slider.value = maxSeq;
      currDisplay.textContent = maxSeq;
    }

    // Render ticks on scrubber
    const ticksContainer = panel.querySelector("#scrubber-ticks-container");
    if (ticksContainer && verdictTicks.length > 0) {
      ticksContainer.innerHTML = verdictTicks
        .map((tickSeq) => {
          const pct = ((tickSeq - 1) / Math.max(1, maxSeq - 1)) * 100;
          return `<span style="position: absolute; left: ${pct}%; top: -2px; bottom: -2px; width: 2px; background: var(--gt-cobalt-soft); opacity: 0.6;"></span>`;
        })
        .join("");
    }
  };

  return panel;
}
