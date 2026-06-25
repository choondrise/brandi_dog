import type { PawnInfo, Seat } from "./types";

const entryIndex: Record<Seat, number> = { A1: 0, B1: 16, A2: 32, B2: 48 };
const seatColors: Record<Seat, string> = {
  A1: "#d9443f",
  B1: "#239a59",
  A2: "#315fcb",
  B2: "#d4ae1f",
};

function pointOnCircle(index: number, radius: number) {
  const angle = (-90 + (index * 360) / 64) * (Math.PI / 180);
  return {
    x: 50 + radius * Math.cos(angle),
    y: 50 + radius * Math.sin(angle),
  };
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
    return pointOnCircle(pawn.position.index, 37);
  }
  if (pawn.position.kind === "SAFE" && pawn.position.index !== null) {
    return safePoint(pawn.owner, pawn.position.index);
  }
  return basePoint(pawn.owner, pawn.number);
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
) {
  const track = Array.from({ length: 64 }, (_, index) => {
    const point = pointOnCircle(index, 37);
    const owner = (Object.keys(entryIndex) as Seat[]).find((seat) => entryIndex[seat] === index);
    const style = `left:${point.x}%;top:${point.y}%;${owner ? `--seat-color:${seatColors[owner]}` : ""}`;
    return `<span class="hole ${owner ? "entry" : ""}" style="${style}"></span>`;
  }).join("");

  const safe = (Object.keys(entryIndex) as Seat[])
    .flatMap((seat) =>
      Array.from({ length: 4 }, (_, index) => {
        const point = safePoint(seat, index);
        return `<span class="hole safe" style="left:${point.x}%;top:${point.y}%;--seat-color:${seatColors[seat]}"></span>`;
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
  const pawnHtml = pawns
    .map((pawn) => {
      const point = pawnPoint(pawn);
      const active = activePlayer === pawn.owner ? " active-owner" : "";
      const selectedClass = selected.has(pawn.id) ? " selected" : "";
      const selectableClass = selectable.has(pawn.id) ? " selectable" : "";
      return `<button type="button" class="pawn${active}${selectedClass}${selectableClass}" data-pawn-id="${pawn.id}" style="left:${point.x}%;top:${point.y}%;--pawn-color:${pawn.color}">${pawn.number + 1}</button>`;
    })
    .join("");

  const labelFor = (seat: Seat) => escapeHtml(seatLabels[seat] || seat);

  return `
    <div class="board-shell">
      <div class="board-octagon"></div>
      <div class="board-center">Brandi<br/>Dog</div>
      ${track}${safe}${bases}${pawnHtml}
      <span class="seat-label a1">${labelFor("A1")}</span>
      <span class="seat-label b1">${labelFor("B1")}</span>
      <span class="seat-label a2">${labelFor("A2")}</span>
      <span class="seat-label b2">${labelFor("B2")}</span>
    </div>
  `;
}
