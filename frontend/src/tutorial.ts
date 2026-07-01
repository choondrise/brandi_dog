import { renderBoard, type PreviewPosition } from "./board";
import type { CardInfo, PawnInfo, Seat } from "./types";
import { t, tutorialStepText } from "./i18n";

type TutorialTarget = "board" | "hand" | "controls" | "play" | "card" | "pawn" | "option" | "steps" | "none";
type TutorialAction =
  | { type: "next" }
  | { type: "select-card"; cardId: number }
  | { type: "select-pawn"; pawnId: string }
  | { type: "select-option"; value: string }
  | { type: "select-step"; pawnId: string; steps: number }
  | { type: "play" };

type TutorialStep = {
  title: string;
  body: string;
  target: TutorialTarget;
  scenario: "tour" | "swap" | "enter" | "move" | "four" | "jack" | "seven" | "joker";
  action: TutorialAction;
};

type TutorialState = {
  stepIndex: number;
  selectedCardId: number | null;
  selectedPawns: string[];
  selectedOption: string | null;
  sevenSteps: Record<string, number>;
  completed: Set<number>;
};

const seats: Seat[] = ["A1", "B1", "A2", "B2"];
const colors: Record<Seat, string> = { A1: "#d9443f", B1: "#239a59", A2: "#315fcb", B2: "#d4ae1f" };

let state: TutorialState = initialState();

const steps: TutorialStep[] = [
  {
    title: "The board is your map",
    body: "Your blue pawns start at the bottom. Move them around the track and into the blue finish lane. The lit edge shows whose turn is active.",
    target: "board",
    scenario: "tour",
    action: { type: "next" },
  },
  {
    title: "Your hand drives every move",
    body: "Cards decide what you can do. Pick a card first, then pick the pawn or option that belongs to that card.",
    target: "hand",
    scenario: "tour",
    action: { type: "next" },
  },
  {
    title: "Controls appear when needed",
    body: "Some cards ask how you want to use them. A 4 can move forward or backward. A joker asks which card it should become.",
    target: "controls",
    scenario: "tour",
    action: { type: "next" },
  },
  {
    title: "Swap with your teammate",
    body: "At the start of a round, choose one card to pass to your teammate. Try swapping the 6.",
    target: "card",
    scenario: "swap",
    action: { type: "select-card", cardId: 601 },
  },
  {
    title: "Confirm the swap",
    body: "The button only matters after a valid choice. Press it to lock the selected card.",
    target: "play",
    scenario: "swap",
    action: { type: "play" },
  },
  {
    title: "Enter a pawn with an Ace or King",
    body: "Select the Ace, then tap your first blue pawn in base. The entry field lights up before you commit.",
    target: "card",
    scenario: "enter",
    action: { type: "select-card", cardId: 101 },
  },
  {
    title: "Choose the pawn to enter",
    body: "Tap the highlighted blue pawn. Pawns in base do not jump over each other; entering means moving to the entry field.",
    target: "pawn",
    scenario: "enter",
    action: { type: "select-pawn", pawnId: "A2-0" },
  },
  {
    title: "Move on the track",
    body: "Select the 6, then move the pawn already on the track. The next six playable fields are previewed.",
    target: "card",
    scenario: "move",
    action: { type: "select-card", cardId: 602 },
  },
  {
    title: "Preview before playing",
    body: "Tap the blue pawn on the track. If the path ends on another pawn, that pawn gets highlighted as a capture.",
    target: "pawn",
    scenario: "move",
    action: { type: "select-pawn", pawnId: "A2-1" },
  },
  {
    title: "Fours can go backward",
    body: "Select the 4. Backward movement is often the fastest way to set up your finish lane later.",
    target: "card",
    scenario: "four",
    action: { type: "select-card", cardId: 401 },
  },
  {
    title: "Pick the backward option",
    body: "Choose Move -4. The preview changes to show the backward path.",
    target: "option",
    scenario: "four",
    action: { type: "select-option", value: "backward" },
  },
  {
    title: "Jacks swap two pawns",
    body: "Select the Jack. Then select your pawn and the opponent pawn you want to swap with.",
    target: "card",
    scenario: "jack",
    action: { type: "select-card", cardId: 1101 },
  },
  {
    title: "Select both swap targets",
    body: "Tap the blue pawn and then the green pawn. Jack swaps only pawns on the main track.",
    target: "pawn",
    scenario: "jack",
    action: { type: "select-pawn", pawnId: "A2-1" },
  },
  {
    title: "Complete the Jack pair",
    body: "Now tap the green pawn. Both selected pawns will be involved in the swap.",
    target: "pawn",
    scenario: "jack",
    action: { type: "select-pawn", pawnId: "B1-1" },
  },
  {
    title: "Seven is a split move",
    body: "Select the 7. You can divide seven steps across multiple friendly pawns, in the order you choose them.",
    target: "card",
    scenario: "seven",
    action: { type: "select-card", cardId: 701 },
  },
  {
    title: "Give the first pawn 3 steps",
    body: "Tap the first blue pawn, then choose 3. The remaining step buttons adapt to keep the total legal.",
    target: "steps",
    scenario: "seven",
    action: { type: "select-step", pawnId: "A2-1", steps: 3 },
  },
  {
    title: "Finish the split with 4 steps",
    body: "Tap the second blue pawn and choose 4. Together, 3 plus 4 spends the full seven.",
    target: "steps",
    scenario: "seven",
    action: { type: "select-step", pawnId: "A2-2", steps: 4 },
  },
  {
    title: "Jokers copy a missing card",
    body: "Select the Joker. In a real game you choose what it acts as, then play it like that card.",
    target: "card",
    scenario: "joker",
    action: { type: "select-card", cardId: 1501 },
  },
  {
    title: "Choose a joker value",
    body: "Pick Ace. The joker can now enter a pawn or move like an Ace, depending on the board.",
    target: "option",
    scenario: "joker",
    action: { type: "select-option", value: "ace" },
  },
  {
    title: "You are ready",
    body: "That is the core rhythm: card, option if needed, pawn or pawns, then Play. You can now jump into a real table.",
    target: "none",
    scenario: "tour",
    action: { type: "next" },
  },
];

export function resetTutorial() {
  state = initialState();
}

export function renderTutorial(root: HTMLElement, onExit: () => void) {
  const step = steps[state.stepIndex];
  const scenario = scenarioFor(step.scenario);
  const stepText = tutorialStepText(state.stepIndex);
  const activePlayer = step.scenario === "tour" ? "A2" : "A2";
  const selectedPawns = selectedPawnIdsFor(step);
  const selectablePawns = selectablePawnIdsFor(step);
  const preview = previewFor(step);
  const pageClasses = ["tutorial-page", step.target === "pawn" && state.selectedCardId ? "tutorial-pawn-focus" : ""].filter(Boolean).join(" ");
  const tableClasses = ["tutorial-table", targetClass(step, "board"), targetClass(step, "pawn")].filter(Boolean).join(" ");

  root.innerHTML = `
    <main class="${pageClasses}">
      <header class="tutorial-header">
        <button id="tutorial-exit" class="ghost">${escapeHtml(t("tutorial.back"))}</button>
      </header>
      <section class="${tableClasses}">
        ${renderBoard(scenario.pawns, activePlayer, tutorialSeatLabels(), selectedPawns, selectablePawns, [], preview.positions, preview.capturePawnIds)}
      </section>
      <section class="tutorial-hand hand-tray ${targetClass(step, "hand")} ${targetClass(step, "card")}">
        <div class="hand-header"><strong>${escapeHtml(t("tutorial.hand"))}</strong><span>${escapeHtml(t("tutorial.cards", { count: scenario.cards.length }))}</span></div>
        <div class="cards">${scenario.cards.map((card) => renderTutorialCard(card, cardSelectable(step, card.id), state.selectedCardId === card.id)).join("")}</div>
        <div class="tutorial-controls selection-panel ${targetClass(step, "controls")} ${targetClass(step, "option")} ${targetClass(step, "steps")}">
          ${renderTutorialControls(step)}
        </div>
      </section>
      <section class="tutorial-play play-bar ${targetClass(step, "play")}">
        <button id="tutorial-back" class="ghost" ${state.stepIndex === 0 ? "disabled" : ""}>${escapeHtml(t("tutorial.backButton"))}</button>
        <button id="tutorial-play" ${canTutorialPlay(step) ? "" : "disabled"}>${state.stepIndex === steps.length - 1 ? escapeHtml(t("tutorial.finish")) : escapeHtml(playLabel(step))}</button>
      </section>
      <div class="tutorial-scrim"></div>
      <aside class="tutorial-card-panel tutorial-panel-${panelPlacement(step)}">
        <div class="tutorial-progress"><span>${state.stepIndex + 1}</span><i style="--tutorial-progress:${((state.stepIndex + 1) / steps.length) * 100}%"></i><span>${steps.length}</span></div>
        <h2>${escapeHtml(stepText.title)}</h2>
        <p>${escapeHtml(stepText.body)}</p>
        <div class="tutorial-panel-actions">
          <button id="tutorial-next" ${step.action.type === "next" ? "" : "disabled"}>${state.stepIndex === steps.length - 1 ? escapeHtml(t("tutorial.done")) : escapeHtml(t("tutorial.next"))}</button>
        </div>
      </aside>
    </main>
  `;

  root.querySelector("#tutorial-exit")?.addEventListener("click", onExit);
  root.querySelector("#tutorial-back")?.addEventListener("click", () => {
    if (state.stepIndex > 0) {
      state.stepIndex -= 1;
      clearStepState();
      renderTutorial(root, onExit);
    }
  });
  root.querySelector("#tutorial-next")?.addEventListener("click", () => completeExpected(root, onExit, { type: "next" }));
  root.querySelector("#tutorial-play")?.addEventListener("click", () => completeExpected(root, onExit, { type: "play" }));
  root.querySelectorAll<HTMLButtonElement>(".tutorial-card").forEach((button) => {
    button.addEventListener("click", () => completeExpected(root, onExit, { type: "select-card", cardId: Number(button.dataset.cardId) }));
  });
  root.querySelectorAll<HTMLButtonElement>(".tutorial-page .pawn.selectable").forEach((button) => {
    button.addEventListener("click", () => completeExpected(root, onExit, { type: "select-pawn", pawnId: button.dataset.pawnId || "" }));
  });
  root.querySelectorAll<HTMLButtonElement>(".tutorial-option").forEach((button) => {
    button.addEventListener("click", () => completeExpected(root, onExit, { type: "select-option", value: button.dataset.value || "" }));
  });
  root.querySelectorAll<HTMLButtonElement>(".tutorial-step-btn").forEach((button) => {
    button.addEventListener("click", () => completeExpected(root, onExit, { type: "select-step", pawnId: button.dataset.pawnId || "", steps: Number(button.dataset.steps) }));
  });
}

function tutorialSeatLabels(): Partial<Record<Seat, string>> {
  return { A1: t("tutorial.partner"), B1: t("tutorial.opponent"), A2: t("tutorial.you"), B2: t("tutorial.opponent") };
}

function initialState(): TutorialState {
  return { stepIndex: 0, selectedCardId: null, selectedPawns: [], selectedOption: null, sevenSteps: {}, completed: new Set() };
}

function scenarioFor(name: TutorialStep["scenario"]) {
  if (name === "swap") return { pawns: basePawns(), cards: [card(601, "6", "H6.png"), card(1201, "Q", "SQ.png"), card(301, "3", "D3.png")] };
  if (name === "enter") return { pawns: basePawns(), cards: [card(101, "A", "HA.png"), card(901, "9", "C9.png"), card(501, "5", "S5.png")] };
  if (name === "move") return { pawns: movePawns(), cards: [card(602, "6", "H6.png"), card(201, "2", "D2.png"), card(1301, "K", "CK.png")] };
  if (name === "four") return { pawns: movePawns(), cards: [card(401, "4", "C4.png"), card(1001, "10", "H10.png"), card(901, "9", "D9.png")] };
  if (name === "jack") return { pawns: jackPawns(), cards: [card(1101, "J", "HJ.png"), card(801, "8", "S8.png"), card(301, "3", "C3.png")] };
  if (name === "seven") return { pawns: sevenPawns(), cards: [card(701, "7", "D7.png"), card(501, "5", "H5.png"), card(1201, "Q", "CQ.png")] };
  if (name === "joker") return { pawns: basePawns(), cards: [card(1501, "Joker", "joker.png"), card(801, "8", "D8.png"), card(301, "3", "S3.png")] };
  return { pawns: movePawns(), cards: [card(101, "A", "HA.png"), card(602, "6", "H6.png"), card(1101, "J", "HJ.png"), card(701, "7", "D7.png")] };
}

function basePawns(): PawnInfo[] {
  return seats.flatMap((seat) => [0, 1, 2, 3].map((number) => pawn(seat, number, "BASE", null)));
}

function movePawns(): PawnInfo[] {
  const pawns = basePawns();
  return replacePositions(pawns, { "A2-1": ["TRACK", 34], "B1-1": ["TRACK", 40], "A1-0": ["TRACK", 4] });
}

function jackPawns(): PawnInfo[] {
  const pawns = basePawns();
  return replacePositions(pawns, { "A2-1": ["TRACK", 36], "B1-1": ["TRACK", 44], "B2-0": ["TRACK", 54] });
}

function sevenPawns(): PawnInfo[] {
  const pawns = basePawns();
  return replacePositions(pawns, { "A2-1": ["TRACK", 29], "A2-2": ["TRACK", 32], "B1-1": ["TRACK", 35] });
}

function replacePositions(pawns: PawnInfo[], positions: Record<string, ["BASE" | "TRACK" | "SAFE", number | null]>) {
  return pawns.map((item) => {
    const next = positions[item.id];
    return next ? { ...item, position: { kind: next[0], index: next[1] } } : item;
  });
}

function pawn(owner: Seat, number: number, kind: "BASE" | "TRACK" | "SAFE", index: number | null): PawnInfo {
  return { id: `${owner}-${number}`, owner, number, color: colors[owner], position: { kind, index } };
}

function card(id: number, label: string, asset: string): CardInfo {
  return { id, rank: label === "Joker" ? "JK" : label, label, asset };
}

function renderTutorialCard(card: CardInfo, selectable: boolean, selected: boolean) {
  const isJoker = card.asset === "joker.png";
  return `
    <button type="button" class="card tutorial-card ${selectable ? "selectable" : ""} ${selected ? "selected" : ""} ${isJoker ? "joker-card" : ""}" data-card-id="${card.id}" ${selectable ? "" : "disabled"}>
      <img src="/cards/${card.asset}" alt="${escapeHtml(card.label)}" onerror="this.style.display='none'" />
      ${isJoker ? `<span>${escapeHtml(card.label)}</span>` : ""}
    </button>
  `;
}

function renderTutorialControls(step: TutorialStep) {
  if (step.scenario === "tour") return `<p class="muted">${escapeHtml(t("tutorial.reveals"))}</p>`;
  if (step.scenario === "four") {
    return `<div class="choice-group"><span>${escapeHtml(t("tutorial.chooseDirection"))}</span><button class="choice-btn tutorial-option ${state.selectedOption === "forward" ? "selected" : ""}" data-value="forward">${escapeHtml(t("variant.moveForward", { steps: 4 }))}</button><button class="choice-btn tutorial-option ${state.selectedOption === "backward" ? "selected" : ""}" data-value="backward">${escapeHtml(t("variant.moveBackward", { steps: 4 }))}</button></div>`;
  }
  if (step.scenario === "joker") {
    return `<div class="choice-group"><span>${escapeHtml(t("tutorial.chooseJoker"))}</span><button class="choice-btn tutorial-option ${state.selectedOption === "ace" ? "selected" : ""}" data-value="ace">${escapeHtml(t("rank.ace"))}</button><button class="choice-btn tutorial-option" data-value="jack">J</button><button class="choice-btn tutorial-option" data-value="seven">7</button></div>`;
  }
  if (step.scenario === "seven") {
    const rows = ["A2-1", "A2-2"].map((pawnId) => {
      const chosen = state.sevenSteps[pawnId];
      return `<div class="seven-move"><div class="seven-move-head"><span>${pawnId === "A2-1" ? escapeHtml(t("tutorial.firstPawn")) : escapeHtml(t("tutorial.secondPawn"))}</span><span class="pawn-badge" style="--pawn-color:${colors.A2}">${pawnId.endsWith("1") ? 2 : 3}</span></div><div class="step-grid">${[1, 2, 3, 4, 5, 6, 7].map((steps) => `<button class="step-btn tutorial-step-btn ${chosen === steps ? "selected" : ""}" data-pawn-id="${pawnId}" data-steps="${steps}">${steps}</button>`).join("")}</div></div>`;
    });
    return `<div class="seven-builder"><div class="seven-summary"><span>${escapeHtml(t("tutorial.split7"))}</span><strong>${Object.values(state.sevenSteps).reduce((a, b) => a + b, 0)}/7</strong></div>${rows.join("")}</div>`;
  }
  if (state.selectedCardId) return `<p class="muted">${escapeHtml(t("tutorial.tapPawn"))}</p>`;
  return `<p class="muted">${escapeHtml(t("tutorial.selectCard"))}</p>`;
}

function cardSelectable(step: TutorialStep, cardId: number) {
  return step.action.type === "select-card" ? step.action.cardId === cardId : state.selectedCardId === cardId;
}

function selectablePawnIdsFor(step: TutorialStep) {
  if (step.action.type === "select-pawn") return [step.action.pawnId];
  if (step.action.type === "select-step") return [step.action.pawnId];
  return [];
}

function selectedPawnIdsFor(step: TutorialStep) {
  if (step.scenario === "seven") return Object.keys(state.sevenSteps);
  return state.selectedPawns;
}

function previewFor(step: TutorialStep): { positions: PreviewPosition[]; capturePawnIds: string[] } {
  if (step.scenario === "enter" && state.selectedCardId === 101) return { positions: [{ kind: "TRACK", index: 32 }], capturePawnIds: [] };
  if (step.scenario === "move" && state.selectedPawns.includes("A2-1")) return { positions: [35, 36, 37, 38, 39, 40].map((index) => ({ kind: "TRACK", index })), capturePawnIds: ["B1-1"] };
  if (step.scenario === "four" && state.selectedOption === "backward") return { positions: [33, 32, 31, 30].map((index) => ({ kind: "TRACK", index })), capturePawnIds: [] };
  if (step.scenario === "seven") {
    const positions: PreviewPosition[] = [];
    if (state.sevenSteps["A2-1"]) positions.push(...[30, 31, 32].slice(0, state.sevenSteps["A2-1"]).map((index) => ({ kind: "TRACK" as const, index })));
    if (state.sevenSteps["A2-2"]) positions.push(...[{ kind: "SAFE" as const, owner: "A2" as const, index: 0 }, { kind: "SAFE" as const, owner: "A2" as const, index: 1 }, { kind: "SAFE" as const, owner: "A2" as const, index: 2 }, { kind: "SAFE" as const, owner: "A2" as const, index: 3 }].slice(0, state.sevenSteps["A2-2"]));
    return { positions, capturePawnIds: state.sevenSteps["A2-1"] === 3 ? ["B1-1"] : [] };
  }
  return { positions: [], capturePawnIds: [] };
}

function targetClass(step: TutorialStep, target: TutorialTarget) {
  if (step.target !== target) return "";
  if (target === "pawn") return state.selectedCardId ? "tutorial-spotlight" : "";
  return "tutorial-spotlight";
}

function panelPlacement(step: TutorialStep) {
  if (step.target === "play" || step.target === "hand" || step.target === "card" || step.target === "controls" || step.target === "option" || step.target === "steps") {
    return "top";
  }
  if (step.target === "none") return "middle";
  return "bottom";
}

function canTutorialPlay(step: TutorialStep) {
  return step.action.type === "play";
}

function playLabel(step: TutorialStep) {
  if (step.action.type === "play") return step.scenario === "swap" ? t("tutorial.swapCard") : t("tutorial.play");
  return t("tutorial.play");
}

function completeExpected(root: HTMLElement, onExit: () => void, action: TutorialAction) {
  const expected = steps[state.stepIndex].action;
  if (!actionMatches(expected, action)) return;
  if (action.type === "select-card") state.selectedCardId = action.cardId;
  if (action.type === "select-pawn" && !state.selectedPawns.includes(action.pawnId)) state.selectedPawns.push(action.pawnId);
  if (action.type === "select-option") state.selectedOption = action.value;
  if (action.type === "select-step") state.sevenSteps[action.pawnId] = action.steps;
  advance(root, onExit);
}

function actionMatches(expected: TutorialAction, actual: TutorialAction) {
  if (expected.type !== actual.type) return false;
  if (expected.type === "next" || expected.type === "play") return true;
  if (expected.type === "select-card" && actual.type === "select-card") return expected.cardId === actual.cardId;
  if (expected.type === "select-pawn" && actual.type === "select-pawn") return expected.pawnId === actual.pawnId;
  if (expected.type === "select-option" && actual.type === "select-option") return expected.value === actual.value;
  if (expected.type === "select-step" && actual.type === "select-step") return expected.pawnId === actual.pawnId && expected.steps === actual.steps;
  return false;
}

function advance(root: HTMLElement, onExit: () => void) {
  state.completed.add(state.stepIndex);
  if (state.stepIndex >= steps.length - 1) {
    onExit();
    return;
  }
  const previousStep = steps[state.stepIndex];
  state.stepIndex += 1;
  clearStepState(previousStep);
  renderTutorial(root, onExit);
}

function clearStepState(previousStep?: TutorialStep) {
  const step = steps[state.stepIndex];
  const sameScenario = Boolean(previousStep && step && previousStep.scenario === step.scenario);
  const keepCard = sameScenario && step.action.type !== "select-card";
  const keepPawns = sameScenario && (step.scenario === "jack" || step.action.type === "play");
  const keepOption = sameScenario && step.action.type === "play";

  if (!keepCard) state.selectedCardId = null;
  if (!keepPawns) state.selectedPawns = [];
  if (!keepOption) state.selectedOption = null;
  if (step?.scenario !== "seven") state.sevenSteps = {};
}

function escapeHtml(value: string) {
  const element = document.createElement("span");
  element.textContent = value;
  return element.innerHTML;
}
