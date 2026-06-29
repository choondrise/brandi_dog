import type { PawnInfo, Seat } from "./types";

export type PreviewPosition = { kind: "TRACK" | "SAFE"; index: number; owner?: Seat };
export type ReplayAnimationPawn = { id: string; from: PawnInfo; to: PawnInfo };

const entryIndex: Record<Seat, number> = { A1: 0, B1: 16, A2: 32, B2: 48 };
const seatColors: Record<Seat, string> = {
  A1: "#d9443f",
  B1: "#239a59",
  A2: "#315fcb",
  B2: "#d4ae1f",
};

function polarPoint(angleDeg: number, radius: number) {
  const angle = angleDeg * (Math.PI / 180);
  return {
    x: 50 + radius * Math.cos(angle),
    y: 50 + radius * Math.sin(angle),
  };
}

function pointOnCircle(index: number, radius: number) {
  return polarPoint(-90 + (index * 360) / 64, radius);
}

function rotateAroundCenter(point: { x: number; y: number }, quarterTurns: number) {
  let x = point.x - 50;
  let y = point.y - 50;
  for (let turn = 0; turn < quarterTurns; turn += 1) {
    const nextX = -y;
    y = x;
    x = nextX;
  }
  return { x: 50 + x, y: 50 + y };
}

function interpolate(start: number, end: number, t: number) {
  return start + (end - start) * t;
}

function buildQuadrantTemplate() {
  const fields: { x: number; y: number }[] = [];
  const outerStep = 6.5;
  const outerInset = outerStep * 4;
  for (const angle of [0, outerStep, outerStep * 2, outerStep * 3, outerInset]) {
    fields.push(polarPoint(-90 + angle, 37));
  }

  const field4 = fields[4];
  const field12 = polarPoint(-90 + (90 - outerInset), 37);
  const field8 = { x: field4.x, y: field12.y };

  for (const t of [0.25, 0.5, 0.75]) {
    fields.push({ x: field4.x, y: interpolate(field4.y, field8.y, t) });
  }
  fields.push(field8);
  for (const t of [0.25, 0.5, 0.75]) {
    fields.push({ x: interpolate(field8.x, field12.x, t), y: field12.y });
  }

  for (const angle of [90 - outerInset, 90 - outerStep * 3, 90 - outerStep * 2, 90 - outerStep]) {
    fields.push(polarPoint(-90 + angle, 37));
  }
  return fields;
}

const quadrantTemplate = buildQuadrantTemplate();
const MAIN_PATH_POSITIONS = Array.from({ length: 64 }, (_, index) =>
  rotateAroundCenter(quadrantTemplate[index % 16], Math.floor(index / 16)),
);

export function getEntryIndex(seat: Seat) {
  return entryIndex[seat];
}

function mainPathPoint(index: number) {
  return MAIN_PATH_POSITIONS[((index % MAIN_PATH_POSITIONS.length) + MAIN_PATH_POSITIONS.length) % MAIN_PATH_POSITIONS.length];
}

function seatAngle(seat: Seat) {
  return (-90 + (entryIndex[seat] * 360) / 64) * (Math.PI / 180);
}

function safePoint(seat: Seat, index: number) {
  const angle = seatAngle(seat);
  const radius = 37 - (index + 1) * 5.1;
  return {
    x: 50 + radius * Math.cos(angle),
    y: 50 + radius * Math.sin(angle),
  };
}

function basePoint(seat: Seat, index: number) {
  const angle = seatAngle(seat);
  const ux = Math.cos(angle);
  const uy = Math.sin(angle);
  const tx = -uy;
  const ty = ux;
  const offset = (index - 1.5) * 4.5;
  return {
    x: 50 + 46 * ux + offset * tx,
    y: 50 + 46 * uy + offset * ty,
  };
}

function pawnPoint(pawn: PawnInfo) {
  if (pawn.position.kind === "TRACK" && pawn.position.index !== null) {
    return mainPathPoint(pawn.position.index);
  }
  if (pawn.position.kind === "SAFE" && pawn.position.index !== null) {
    return safePoint(pawn.owner, pawn.position.index);
  }
  return basePoint(pawn.owner, pawn.number);
}

function activeEdgeSvg(activePlayer: Seat | null) {
  if (!activePlayer) return "";
  const edges: Record<Seat, { full: string; half: string }> = {
    A1: { full: "17.8,17.8 50,4 82.2,17.8", half: activeHalfEdgePoints({ x: 17.8, y: 17.8 }, { x: 50, y: 4 }, { x: 82.2, y: 17.8 }) },
    B1: { full: "82.2,17.8 96,50 82.2,82.2", half: activeHalfEdgePoints({ x: 82.2, y: 17.8 }, { x: 96, y: 50 }, { x: 82.2, y: 82.2 }) },
    A2: { full: "82.2,82.2 50,96 17.8,82.2", half: activeHalfEdgePoints({ x: 82.2, y: 82.2 }, { x: 50, y: 96 }, { x: 17.8, y: 82.2 }) },
    B2: { full: "17.8,82.2 4,50 17.8,17.8", half: activeHalfEdgePoints({ x: 17.8, y: 82.2 }, { x: 4, y: 50 }, { x: 17.8, y: 17.8 }) },
  };
  const edge = edges[activePlayer];
  return `
    <svg class="board-active-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style="--active-seat-color:${seatColors[activePlayer]}">
      <polyline class="active-edge-main" points="${edge.full}" />
      <polyline class="active-edge-secondary" points="${edge.half}" />
    </svg>
  `;
}

function activeHalfEdgePoints(left: { x: number; y: number }, vertex: { x: number; y: number }, right: { x: number; y: number }) {
  const points = [midpoint(left, vertex), vertex, midpoint(vertex, right)].map((point) => stretchFromCenter(point, 1));
  return points.map((point) => `${formatPoint(point.x)},${formatPoint(point.y)}`).join(" ");
}

function midpoint(a: { x: number; y: number }, b: { x: number; y: number }) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function stretchFromCenter(point: { x: number; y: number }, amount: number) {
  const dx = point.x - 50;
  const dy = point.y - 50;
  const length = Math.hypot(dx, dy) || 1;
  return { x: point.x + (dx / length) * amount, y: point.y + (dy / length) * amount };
}

function formatPoint(value: number) {
  return Number(value.toFixed(2));
}

function previewPositionKey(position: PreviewPosition) {
  return position.kind === "TRACK" ? `T:${position.index}` : `S:${position.owner}:${position.index}`;
}

function escapeHtml(value: string) {
  const element = document.createElement("span");
  element.textContent = value;
  return element.innerHTML;
}

export function renderBoard(
  pawns: PawnInfo[],
  activePlayer: Seat | null,
  seatLabels: Partial<Record<Seat, string>> = {},
  selectedPawnIds: string[] = [],
  selectablePawnIds: string[] = [],
  replayPawnIds: string[] = [],
  previewPositions: PreviewPosition[] = [],
  previewCapturePawnIds: string[] = [],
  slowMotion = false,
  replayAnimations: ReplayAnimationPawn[] = [],
  replayAnimationDurationMs: number | null = null,
) {
  const previewKeys = new Set(previewPositions.map((position) => previewPositionKey(position)));
  const track = Array.from({ length: 64 }, (_, index) => {
    const point = mainPathPoint(index);
    const owner = (Object.keys(entryIndex) as Seat[]).find((seat) => entryIndex[seat] === index);
    const previewClass = previewKeys.has(previewPositionKey({ kind: "TRACK", index })) ? " preview" : "";
    const style = `left:${point.x}%;top:${point.y}%;${owner ? `--seat-color:${seatColors[owner]}` : ""}`;
    return `<span class="hole ${owner ? "entry" : ""}${previewClass}" style="${style}"></span>`;
  }).join("");

  const safe = (Object.keys(entryIndex) as Seat[])
    .flatMap((seat) =>
      Array.from({ length: 4 }, (_, index) => {
        const point = safePoint(seat, index);
        const previewClass = previewKeys.has(previewPositionKey({ kind: "SAFE", owner: seat, index })) ? " preview" : "";
        return `<span class="hole safe${previewClass}" style="left:${point.x}%;top:${point.y}%;--seat-color:${seatColors[seat]}"></span>`;
      }),
    )
    .join("");

  const bases = (Object.keys(entryIndex) as Seat[])
    .flatMap((seat) =>
      Array.from({ length: 4 }, (_, index) => {
        const point = basePoint(seat, index);
        return `<span class="hole base" style="left:${point.x}%;top:${point.y}%;--seat-color:${seatColors[seat]}"></span>`;
      }),
    )
    .join("");

  const selected = new Set(selectedPawnIds);
  const selectable = new Set(selectablePawnIds);
  const replayed = new Set(replayPawnIds);
  const previewCaptured = new Set(previewCapturePawnIds);
  const endpointAnimated = new Set(replayAnimations.map((item) => item.id));
  const pawnHtml = pawns
    .map((pawn) => {
      const point = pawnPoint(pawn);
      const active = activePlayer === pawn.owner ? " active-owner" : "";
      const selectedClass = selected.has(pawn.id) ? " selected" : "";
      const selectableClass = selectable.has(pawn.id) ? " selectable" : "";
      const replayClass = replayed.has(pawn.id) ? " replayed" : "";
      const previewCapturedClass = previewCaptured.has(pawn.id) ? " preview-capture" : "";
      const endpointClass = endpointAnimated.has(pawn.id) ? " endpoint-hidden" : "";
      return `<button type="button" class="pawn${active}${selectedClass}${selectableClass}${replayClass}${previewCapturedClass}${endpointClass}" data-pawn-id="${pawn.id}" style="left:${point.x}%;top:${point.y}%;--pawn-color:${pawn.color}">${pawn.number + 1}</button>`;
    })
    .join("");

  const replayEndpointHtml = replayAnimations
    .filter((item) => item.from.position.kind !== item.to.position.kind || item.from.position.index !== item.to.position.index)
    .flatMap((item) => {
      const fromPoint = pawnPoint(item.from);
      const toPoint = pawnPoint(item.to);
      const number = item.from.number + 1;
      const styleBase = `--pawn-color:${item.from.color}`;
      return [
        `<span class="pawn replay-endpoint replay-endpoint-source" style="left:${fromPoint.x}%;top:${fromPoint.y}%;${styleBase}">${number}</span>`,
        `<span class="pawn replay-endpoint replay-endpoint-target" style="left:${toPoint.x}%;top:${toPoint.y}%;${styleBase}">${number}</span>`,
      ];
    })
    .join("");

  const labelFor = (seat: Seat) => escapeHtml(seatLabels[seat] || seat);

  const animationStyle = replayAnimationDurationMs === null ? "" : ` style="--replay-endpoint-duration:${replayAnimationDurationMs}ms"`;

  return `
    <div class="board-shell ${activePlayer ? `active-${activePlayer.toLowerCase()}` : ""} ${slowMotion ? "slow-motion" : ""}"${animationStyle}>
      <div class="board-octagon"></div>
      ${activeEdgeSvg(activePlayer)}
      <div class="board-center">Brandi<br/>Dog</div>
      ${track}${safe}${bases}${pawnHtml}${replayEndpointHtml}
      <span class="seat-label a1 ${activePlayer === "A1" ? "active" : ""}">${labelFor("A1")}</span>
      <span class="seat-label b1 ${activePlayer === "B1" ? "active" : ""}">${labelFor("B1")}</span>
      <span class="seat-label a2 ${activePlayer === "A2" ? "active" : ""}">${labelFor("A2")}</span>
      <span class="seat-label b2 ${activePlayer === "B2" ? "active" : ""}">${labelFor("B2")}</span>
    </div>
  `;
}
