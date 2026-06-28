import type { PawnInfo, Seat } from "./types";

export type PreviewPosition = { kind: "TRACK" | "SAFE"; index: number; owner?: Seat };

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
  const pawnHtml = pawns
    .map((pawn) => {
      const point = pawnPoint(pawn);
      const active = activePlayer === pawn.owner ? " active-owner" : "";
      const selectedClass = selected.has(pawn.id) ? " selected" : "";
      const selectableClass = selectable.has(pawn.id) ? " selectable" : "";
      const replayClass = replayed.has(pawn.id) ? " replayed" : "";
      const previewCapturedClass = previewCaptured.has(pawn.id) ? " preview-capture" : "";
      return `<button type="button" class="pawn${active}${selectedClass}${selectableClass}${replayClass}${previewCapturedClass}" data-pawn-id="${pawn.id}" style="left:${point.x}%;top:${point.y}%;--pawn-color:${pawn.color}">${pawn.number + 1}</button>`;
    })
    .join("");

  const labelFor = (seat: Seat) => escapeHtml(seatLabels[seat] || seat);

  return `
    <div class="board-shell ${activePlayer ? `active-${activePlayer.toLowerCase()}` : ""} ${slowMotion ? "slow-motion" : ""}">
      <div class="board-octagon"></div>
      <div class="board-center">Brandi<br/>Dog</div>
      ${track}${safe}${bases}${pawnHtml}
      <span class="seat-label a1 ${activePlayer === "A1" ? "active" : ""}">${labelFor("A1")}</span>
      <span class="seat-label b1 ${activePlayer === "B1" ? "active" : ""}">${labelFor("B1")}</span>
      <span class="seat-label a2 ${activePlayer === "A2" ? "active" : ""}">${labelFor("A2")}</span>
      <span class="seat-label b2 ${activePlayer === "B2" ? "active" : ""}">${labelFor("B2")}</span>
    </div>
  `;
}
