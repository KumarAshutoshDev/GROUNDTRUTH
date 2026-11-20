/**
 * GroundTruth Causality Graph Visualization Panel (FR-7, DES-10, Design Section 5.2)
 * Renders pure SVG DAG showing facts as nodes, derivation edges, weakest link glow,
 * and animated 150ms step-by-step taint cascade.
 */

export function createGraphPanel() {
  const panel = document.createElement("section");
  panel.className = "gt-panel gt-graph-panel";
  panel.id = "graph-panel";

  panel.innerHTML = `
    <div class="gt-panel-header">
      <div style="display: flex; align-items: center; gap: 8px;">
        <h2>Causality Graph</h2>
        <span class="mono text-muted" id="graph-node-count" style="font-size: 11px;">(0 nodes)</span>
      </div>
      <div style="display: flex; align-items: center; gap: 12px; font-size: 10px;" class="mono text-muted">
        <span style="display: flex; align-items: center; gap: 4px;">
          <span style="width: 12px; height: 2px; background: var(--gt-cobalt); box-shadow: var(--gt-glow-cobalt); display: inline-block;"></span>
          Weakest Link
        </span>
        <span style="display: flex; align-items: center; gap: 4px;">
          <span style="width: 8px; height: 8px; border-radius: 50%; background: var(--gt-coral); display: inline-block;"></span>
          Tainted
        </span>
      </div>
    </div>
    <div class="gt-panel-body" id="graph-container" style="
      min-height: 380px;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: auto;
      background: var(--gt-midnight);
    ">
      <div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">
        Awaiting causality graph data…
      </div>
    </div>
  `;

  return panel;
}

export function renderGraph(graphData, container) {
  const svgContainer = container.querySelector("#graph-container") || container;
  const countEl = container.querySelector("#graph-node-count");

  const nodes = graphData.nodes || [];
  const edges = graphData.edges || [];

  if (countEl) {
    countEl.textContent = `(${nodes.length} nodes, ${edges.length} edges)`;
  }

  if (nodes.length === 0) {
    svgContainer.innerHTML = `
      <div class="gt-empty-state" style="color: var(--gt-text-muted); font-size: 12px; text-align: center; padding: 24px;">
        No causality nodes found for this case.
      </div>
    `;
    return;
  }

  // 1. Layered topological layout: compute rank per node
  const nodeMap = new Map();
  nodes.forEach((n) => nodeMap.set(n.id, { ...n, children: [], parents: [], rank: 0 }));

  edges.forEach((e) => {
    const parent = nodeMap.get(e.source);
    const child = nodeMap.get(e.target);
    if (parent && child) {
      parent.children.push(e.target);
      child.parents.push(e.source);
    }
  });

  // Assign ranks (BFS from root premises)
  const roots = Array.from(nodeMap.values()).filter((n) => n.parents.length === 0);
  const queue = roots.map((r) => r.id);
  while (queue.length > 0) {
    const currId = queue.shift();
    const curr = nodeMap.get(currId);
    if (!curr) continue;
    curr.children.forEach((cid) => {
      const child = nodeMap.get(cid);
      if (child && child.rank <= curr.rank) {
        child.rank = curr.rank + 1;
        queue.push(cid);
      }
    });
  }

  // Group by rank
  const ranks = new Map();
  nodeMap.forEach((node) => {
    if (!ranks.has(node.rank)) ranks.set(node.rank, []);
    ranks.get(node.rank).push(node);
  });

  // Coordinates calculation
  const nodeWidth = 140;
  const nodeHeight = 54;
  const rankGapX = 220;
  const nodeGapY = 80;

  const maxRank = Math.max(...Array.from(ranks.keys()), 0);
  const svgWidth = Math.max(680, (maxRank + 1) * rankGapX + 100);

  let maxNodesInRank = 0;
  ranks.forEach((list) => {
    maxNodesInRank = Math.max(maxNodesInRank, list.length);
  });
  const svgHeight = Math.max(360, maxNodesInRank * nodeGapY + 80);

  // Position nodes
  ranks.forEach((list, rankIdx) => {
    const x = 50 + rankIdx * rankGapX;
    const startY = (svgHeight - (list.length * nodeGapY)) / 2 + 30;
    list.forEach((node, i) => {
      node.x = x;
      node.y = startY + i * nodeGapY;
    });
  });

  // 2. Generate SVG markup
  let edgesMarkup = "";
  edges.forEach((edge) => {
    const u = nodeMap.get(edge.source);
    const v = nodeMap.get(edge.target);
    if (!u || !v) return;

    const x1 = u.x + nodeWidth;
    const y1 = u.y + nodeHeight / 2;
    const x2 = v.x;
    const y2 = v.y + nodeHeight / 2;

    const isWeakest = edge.is_weakest_link;
    const strokeColor = isWeakest ? "var(--gt-cobalt)" : "var(--gt-line)";
    const strokeWidth = isWeakest ? "2.5" : "1.5";
    const filterAttr = isWeakest ? 'filter="url(#cobalt-glow)"' : "";
    const markerAttr = isWeakest ? 'marker-end="url(#arrow-weakest)"' : 'marker-end="url(#arrow-normal)"';

    // Cubic bezier curve
    const dx = (x2 - x1) * 0.5;
    const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

    edgesMarkup += `
      <path id="edge-${edge.source}-${edge.target}"
            data-source="${edge.source}"
            data-target="${edge.target}"
            d="${d}"
            fill="none"
            stroke="${strokeColor}"
            stroke-width="${strokeWidth}"
            ${filterAttr}
            ${markerAttr}
            class="gt-graph-edge ${isWeakest ? 'weakest-link' : ''}" />
    `;
  });

  let nodesMarkup = "";
  nodeMap.forEach((n) => {
    const status = (n.status || "ACTIVE").toUpperCase();
    let borderCol = "var(--gt-line)";
    let bgCol = "var(--gt-surface-2)";

    if (status === "TAINTED") {
      borderCol = "var(--gt-coral)";
      bgCol = "rgba(255, 77, 94, 0.15)";
    } else if (status === "ACTIVE") {
      borderCol = "var(--gt-line)";
    } else if (status === "CONTESTED" || status === "QUARANTINED") {
      borderCol = "var(--gt-amber)";
    }

    const fidShort = n.id.length > 14 ? n.id.slice(0, 6) + "…" + n.id.slice(-4) : n.id;
    const effTrust = (n.effective_trust !== undefined ? Number(n.effective_trust).toFixed(2) : "1.00");

    nodesMarkup += `
      <g class="gt-graph-node" id="node-${n.id}" data-node-id="${n.id}" transform="translate(${n.x}, ${n.y})">
        <rect width="${nodeWidth}" height="${nodeHeight}" rx="12" ry="12"
              fill="${bgCol}" stroke="${borderCol}" stroke-width="1.5"
              class="gt-node-box" />
        <text x="12" y="22" font-size="11" font-weight="600" fill="var(--gt-text)" font-family="var(--gt-font-sans)">
          ${n.type.length > 15 ? n.type.slice(0, 14) + '…' : n.type}
        </text>
        <text x="12" y="38" font-size="10" fill="var(--gt-text-muted)" font-family="var(--gt-font-mono)">
          ${fidShort}
        </text>
        <text x="${nodeWidth - 12}" y="38" text-anchor="end" font-size="10" font-weight="600" fill="var(--gt-lime)" font-family="var(--gt-font-mono)">
          ${effTrust}
        </text>
      </g>
    `;
  });

  svgContainer.innerHTML = `
    <svg width="${svgWidth}" height="${svgHeight}" viewBox="0 0 ${svgWidth} ${svgHeight}" style="display: block; margin: auto;">
      <defs>
        <!-- Cobalt Glow Filter (FR-7) -->
        <filter id="cobalt-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="rgba(21, 88, 201, 0.6)" />
        </filter>
        <!-- Arrow markers -->
        <marker id="arrow-normal" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M 0 1 L 9 5 L 0 9 z" fill="var(--gt-line)" />
        </marker>
        <marker id="arrow-weakest" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M 0 1 L 9 5 L 0 9 z" fill="var(--gt-cobalt)" />
        </marker>
        <marker id="arrow-coral" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M 0 1 L 9 5 L 0 9 z" fill="var(--gt-coral)" />
        </marker>
      </defs>
      <g class="graph-edges">${edgesMarkup}</g>
      <g class="graph-nodes">${nodesMarkup}</g>
    </svg>
  `;
}

/**
 * Animated 150ms per edge hop taint cascade (Design Section 5.2, DES-10).
 */
export async function animateTaintCascade(rootFactId, affectedFactIds, container = document) {
  const isReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const delayMs = isReducedMotion ? 0 : 150;

  for (const fid of affectedFactIds) {
    const nodeEl = container.querySelector(`#node-${fid}`);
    if (nodeEl) {
      const rect = nodeEl.querySelector(".gt-node-box");
      if (rect) {
        rect.style.transition = isReducedMotion ? "none" : "stroke var(--gt-transition-taint), fill var(--gt-transition-taint)";
        rect.setAttribute("stroke", "var(--gt-coral)");
        rect.setAttribute("fill", "rgba(255, 77, 94, 0.2)");
      }
    }

    // Color outgoing edges
    const edges = container.querySelectorAll(`[data-source="${fid}"]`);
    edges.forEach((edge) => {
      edge.setAttribute("stroke", "var(--gt-coral)");
      edge.setAttribute("marker-end", "url(#arrow-coral)");
    });

    if (delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
}
