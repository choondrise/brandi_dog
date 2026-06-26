import "./styles.css";
import { API_BASE, WS_BASE, createSession, getState, joinSession, playAction, setBot, setSeat, startGame } from "./api";
import { renderBoard } from "./board";
import type { ActionInfo, AppPayload, BotLevel, CardInfo, GamePayload, Seat } from "./types";

const app = document.querySelector<HTMLDivElement>("#app")!;
const seats: Seat[] = ["A1", "B1", "A2", "B2"];
const botLevels: BotLevel[] = ["Idiot", "Easy", "Hard", "Cheater"];

let gameId = localStorage.getItem("brandi.gameId") || "";
let token = localStorage.getItem("brandi.token") || "";
let hostToken = localStorage.getItem("brandi.hostToken") || "";
let state: AppPayload | null = null;
let socket: WebSocket | null = null;

function saveIdentity(nextGameId: string, nextToken: string, nextHostToken = "") {
  gameId = nextGameId.toUpperCase();
  token = nextToken;
  if (nextHostToken) hostToken = nextHostToken;
  localStorage.setItem("brandi.gameId", gameId);
  localStorage.setItem("brandi.token", token);
  if (hostToken) localStorage.setItem("brandi.hostToken", hostToken);
}

function clearIdentity() {
  gameId = "";
  token = "";
  hostToken = "";
  state = null;
  localStorage.removeItem("brandi.gameId");
  localStorage.removeItem("brandi.token");
  localStorage.removeItem("brandi.hostToken");
  socket?.close();
  socket = null;
  render();
}

async function refresh() {
  if (!gameId) {
    render();
    return;
  }
  try {
    state = await getState(gameId, token);
    connectSocket();
  } catch (error) {
    toast(error);
  }
  render();
}

function connectSocket() {
  if (!gameId || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  socket = new WebSocket(`${WS_BASE}/ws/${gameId}${query}`);
  socket.onmessage = async (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "refresh") {
      state = await getState(gameId, token);
    } else if (payload.session) {
      state = payload;
    }
    render();
  };
  socket.onclose = () => {
    socket = null;
  };
}

function render() {
  if (!gameId || !state) {
    renderHome();
    return;
  }
  if (state.session.phase === "LOBBY") {
    renderLobby();
    return;
  }
  renderGame();
}

function renderHome() {
  app.innerHTML = `
    <main class="home">
      <section class="brand-panel">
        <h1>Brandi Dog</h1>
        <p class="home-subtitle">Start a table, share the game ID, fill empty seats with bots, and play from phone or desktop.</p>
      </section>
      <section class="entry-panel">
        <label>Your name<input id="name" autocomplete="name" maxlength="32" placeholder="Player" /></label>
        <button id="create">Create game</button>
        <div class="join-row">
          <input id="game-id" maxlength="6" placeholder="GAME ID" />
          <button id="join">Join</button>
        </div>
      </section>
    </main>
  `;
  document.querySelector<HTMLButtonElement>("#create")!.onclick = async () => {
    try {
      const name = inputValue("#name", "Host");
      const created = await createSession(name);
      saveIdentity(created.game_id, created.player_token, created.host_token);
      await refresh();
    } catch (error) {
      toast(error);
    }
  };
  document.querySelector<HTMLButtonElement>("#join")!.onclick = async () => {
    try {
      const id = inputValue("#game-id", "").toUpperCase();
      if (!id) throw new Error("Enter a game ID");
      const joined = await joinSession(id, inputValue("#name", "Player"));
      saveIdentity(joined.game_id, joined.player_token);
      await refresh();
    } catch (error) {
      toast(error);
    }
  };
}

function renderLobby() {
  const session = state!.session;
  app.innerHTML = `
    <main class="lobby">
      <header class="topbar">
        <div>
          <span class="eyebrow">Game ID</span>
          <button class="game-code" id="copy-code">${session.game_id}</button>
        </div>
        <button class="ghost" id="leave">Leave</button>
      </header>
      <section class="seat-grid">
        ${seats.map((seat) => renderSeatCard(seat)).join("")}
      </section>
      <section class="lobby-actions">
        <button id="start" ${state!.isHost ? "" : "disabled"}>Start game</button>
        <p>${state!.isHost ? "Empty seats will use their selected bot." : "Waiting for host to start."}</p>
      </section>
    </main>
  `;
  document.querySelector("#leave")!.addEventListener("click", clearIdentity);
  document.querySelector("#copy-code")!.addEventListener("click", async () => {
    await navigator.clipboard?.writeText(session.game_id);
  });
  document.querySelector("#start")!.addEventListener("click", async () => {
    try {
      state = await startGame(gameId, hostToken || token);
      render();
    } catch (error) {
      toast(error);
    }
  });
  seats.forEach((seat) => {
    document.querySelector(`#sit-${seat}`)?.addEventListener("click", async () => {
      try {
        state = await setSeat(gameId, token, seat);
        render();
      } catch (error) {
        toast(error);
      }
    });
    document.querySelector<HTMLSelectElement>(`#bot-${seat}`)?.addEventListener("change", async (event) => {
      try {
        state = await setBot(gameId, hostToken || token, seat, (event.target as HTMLSelectElement).value as BotLevel);
        render();
      } catch (error) {
        toast(error);
      }
    });
  });
}

function renderSeatCard(seat: Seat) {
  const info = state!.session.seats[seat];
  const mine = state!.viewerSeat === seat;
  const human = info.occupant === "human";
  return `
    <article class="seat-card ${mine ? "mine" : ""}">
      <div class="seat-head">
        <strong>${seat}</strong>
        <span>Team ${info.team}</span>
      </div>
      <p class="occupant">${human ? info.human_name : `${info.bot_level} bot`}</p>
      <button id="sit-${seat}" ${human && !mine ? "disabled" : ""}>${mine ? "Your seat" : "Take seat"}</button>
      <label class="bot-select">
        Bot
        <select id="bot-${seat}" ${state!.isHost && !human ? "" : "disabled"}>
          ${botLevels.map((level) => `<option value="${level}" ${info.bot_level === level ? "selected" : ""}>${level}</option>`).join("")}
        </select>
      </label>
    </article>
  `;
}


function renderGame() {
  const game = state!.game!;
  const hand = state!.viewerSeat ? game.hands[state!.viewerSeat].cards || [] : [];
  normalizeSelection(game, hand);
  const playableNoCardAction = noCardAction(game);
  const finalAction = selectedPlayableAction(game);
  const actionOptions = selectionOptions(game);
  const selectablePawnIds = selectablePawns(game);
  const canPlay = Boolean(finalAction || playableNoCardAction);
  app.innerHTML = `
    <main class="game">
      <header class="game-status">
        <button class="ghost" id="back-lobby">${state!.session.game_id}</button>
        <div>
          <span class="eyebrow">${game.phase.replace("_", " ")}</span>
          <strong>${game.winner ? `Team ${game.winner} wins` : game.activePlayer ? `${displaySeatName(game.activePlayer)} to move` : "Game over"}</strong>
        </div>
        <span class="seat-pill">${state!.viewerSeat ? displaySeatName(state!.viewerSeat) : "Spectator"}</span>
      </header>
      <section class="table-area">${renderBoard(game.pawns, game.activePlayer, boardSeatLabels(), selectedPawnIds, selectablePawnIds)}</section>
      <section class="hand-tray">
        <div class="hand-header">
          <strong>Your hand</strong>
          <span>${hand.length || (state!.viewerSeat ? game.hands[state!.viewerSeat].count : 0)} cards</span>
        </div>
        <div class="cards">${hand.map((card) => renderCard(card, cardPlayable(game, card.id), selectedCardId === card.id)).join("") || `<span class="muted">No visible cards</span>`}</div>
        ${renderSelectionControls(game, actionOptions)}
      </section>
      <section class="play-bar">
        <button id="clear-selection" class="ghost" ${hasSelection() ? "" : "disabled"}>Clear</button>
        <button id="confirm-play" ${canPlay ? "" : "disabled"}>${playButtonText(playableNoCardAction, finalAction)}</button>
      </section>
    </main>
  `;
  document.querySelector("#back-lobby")!.addEventListener("click", refresh);
  document.querySelector("#clear-selection")!.addEventListener("click", () => {
    clearSelection();
    render();
  });
  document.querySelectorAll<HTMLButtonElement>(".card.selectable").forEach((button) => {
    button.addEventListener("click", () => {
      const cardId = Number(button.dataset.cardId);
      if (selectedCardId === cardId) {
        clearSelection();
      } else {
        selectedCardId = cardId;
        selectedRank = null;
        selectedVariant = null;
        selectedPawnIds = [];
        selectedSevenActionId = null;
      }
      render();
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".pawn.selectable").forEach((button) => {
    button.addEventListener("click", () => {
      const pawnId = button.dataset.pawnId;
      if (!pawnId) return;
      if (selectedPawnIds.includes(pawnId)) {
        selectedPawnIds = selectedPawnIds.filter((id) => id !== pawnId);
      } else {
        selectedPawnIds = [...selectedPawnIds, pawnId];
      }
      selectedSevenActionId = null;
      render();
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".choice-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const kind = button.dataset.kind;
      if (kind === "rank") {
        selectedRank = button.dataset.value || null;
        selectedVariant = null;
        selectedPawnIds = [];
        selectedSevenActionId = null;
      }
      if (kind === "variant") {
        selectedVariant = button.dataset.value || null;
        selectedPawnIds = [];
        selectedSevenActionId = null;
      }
      if (kind === "seven") {
        selectedSevenActionId = Number(button.dataset.value);
      }
      render();
    });
  });
  document.querySelector("#confirm-play")!.addEventListener("click", async () => {
    const action = playableNoCardAction || selectedPlayableAction(game);
    if (!action) return;
    try {
      state = await playAction(gameId, token, action.id);
      clearSelection();
      render();
    } catch (error) {
      toast(error);
    }
  });
}

let selectedCardId: number | null = null;
let selectedRank: string | null = null;
let selectedVariant: string | null = null;
let selectedPawnIds: string[] = [];
let selectedSevenActionId: number | null = null;

function normalizeSelection(game: GamePayload, hand: CardInfo[]) {
  if (selectedCardId !== null && !hand.some((card) => card.id === selectedCardId)) {
    clearSelection();
    return;
  }
  if (selectedCardId !== null && !game.legalActions.some((action) => action.card?.id === selectedCardId)) {
    clearSelection();
  }
}

function clearSelection() {
  selectedCardId = null;
  selectedRank = null;
  selectedVariant = null;
  selectedPawnIds = [];
  selectedSevenActionId = null;
}

function hasSelection() {
  return selectedCardId !== null || selectedPawnIds.length > 0 || selectedRank !== null || selectedVariant !== null || selectedSevenActionId !== null;
}

function noCardAction(game: GamePayload) {
  return game.legalActions.length === 1 && !game.legalActions[0].card ? game.legalActions[0] : null;
}

function cardPlayable(game: GamePayload, cardId: number) {
  return game.legalActions.some((action) => action.card?.id === cardId);
}

function selectedCardActions(game: GamePayload) {
  if (selectedCardId === null) return [];
  return game.legalActions.filter((action) => action.card?.id === selectedCardId);
}

function rankFilteredActions(game: GamePayload) {
  const actions = selectedCardActions(game);
  const ranks = unique(actions.map((action) => action.representedRank).filter(Boolean) as string[]);
  if (ranks.length <= 1) return actions;
  if (!selectedRank) return [];
  return actions.filter((action) => action.representedRank === selectedRank);
}

function variantFilteredActions(game: GamePayload) {
  const actions = rankFilteredActions(game);
  const variants = unique(actions.map(actionVariantKey));
  if (variants.length <= 1) return actions;
  if (!selectedVariant) return [];
  return actions.filter((action) => actionVariantKey(action) === selectedVariant);
}

function selectedPlayableAction(game: GamePayload) {
  const actions = variantFilteredActions(game);
  if (selectedCardId === null) return null;
  if (actions.length === 1 && actions[0].type === "SwapCardAction") return actions[0];
  const selectedSet = normalizedPawnSet(selectedPawnIds);
  const matching = actions.filter((action) => normalizedPawnSet(action.pawns.map((pawn) => pawn.id)) === selectedSet);
  if (matching.length === 1 && matching[0].type !== "PlaySevenSplitAction") return matching[0];
  if (selectedSevenActionId !== null) return matching.find((action) => action.id === selectedSevenActionId) || null;
  return null;
}

function selectionOptions(game: GamePayload) {
  const cardActions = selectedCardActions(game);
  const rankOptions = unique(cardActions.map((action) => action.representedRank).filter(Boolean) as string[]);
  const rankedActions = rankFilteredActions(game);
  const variantOptions = unique(rankedActions.map(actionVariantKey));
  const variantActions = variantFilteredActions(game);
  const selectedSet = normalizedPawnSet(selectedPawnIds);
  const sevenOptions = variantActions.filter(
    (action) => action.type === "PlaySevenSplitAction" && selectedSet && normalizedPawnSet(action.pawns.map((pawn) => pawn.id)) === selectedSet,
  );
  return { rankOptions, variantOptions, sevenOptions };
}

function selectablePawns(game: GamePayload) {
  const actions = variantFilteredActions(game);
  return unique(actions.flatMap((action) => action.pawns.map((pawn) => pawn.id)));
}

function renderSelectionControls(game: GamePayload, options: ReturnType<typeof selectionOptions>) {
  if (!selectedCardId && !noCardAction(game)) {
    return `<div class="selection-panel"><p class="muted">Select a card to begin.</p></div>`;
  }
  if (noCardAction(game)) {
    return `<div class="selection-panel"><p class="muted">No card play is available. Confirm to continue.</p></div>`;
  }
  const parts: string[] = [];
  if (options.rankOptions.length > 1) {
    parts.push(renderChoiceGroup("Choose joker value", "rank", options.rankOptions, selectedRank, rankLabel));
  }
  if (options.variantOptions.length > 1 && (options.rankOptions.length <= 1 || selectedRank)) {
    parts.push(renderChoiceGroup("Choose how to play it", "variant", options.variantOptions, selectedVariant, variantLabel));
  }
  const actions = variantFilteredActions(game);
  if (actions.some((action) => action.type === "PlaySevenSplitAction")) {
    parts.push(`<div class="choice-group"><span>Select all figures used by the 7.</span>${options.sevenOptions.length ? options.sevenOptions.map((action) => `<button class="choice-btn ${selectedSevenActionId === action.id ? "selected" : ""}" data-kind="seven" data-value="${action.id}">${escapeHtml(action.label)}</button>`).join("") : `<p class="muted">Matching 7 options will appear here.</p>`}</div>`);
  } else if (actions.some((action) => action.type !== "SwapCardAction")) {
    parts.push(`<p class="muted">Select the involved figure${actions.some((action) => action.type === "PlayJackSwapAction") ? "s" : ""} on the board.</p>`);
  }
  return `<div class="selection-panel">${parts.join("")}</div>`;
}

function renderChoiceGroup(title: string, kind: string, values: string[], selected: string | null, labeler: (value: string) => string) {
  return `<div class="choice-group"><span>${title}</span>${values.map((value) => `<button class="choice-btn ${selected === value ? "selected" : ""}" data-kind="${kind}" data-value="${value}">${labeler(value)}</button>`).join("")}</div>`;
}

function playButtonText(noCard: ActionInfo | null, action: ActionInfo | null) {
  if (noCard) return noCard.type === "SkipTurnAction" ? "Skip" : "Discard hand";
  if (!action) return "Play";
  if (action.type === "SwapCardAction") return "Swap card";
  return "Play";
}

function actionVariantKey(action: ActionInfo) {
  if (action.type === "PlayEnterAction") return "enter";
  if (action.type === "PlayStepCardAction") return `step:${action.direction}:${action.steps}:${action.preferSafeEntry}`;
  if (action.type === "PlayJackSwapAction") return "jack";
  if (action.type === "PlaySevenSplitAction") return "seven";
  if (action.type === "SwapCardAction") return "swap";
  return action.type;
}

function variantLabel(value: string) {
  if (value === "enter") return "Enter pawn";
  if (value === "jack") return "Jack swap";
  if (value === "seven") return "Split 7";
  if (value === "swap") return "Swap with teammate";
  const [, direction, steps, preferSafe] = value.split(":");
  if (direction === "BACKWARD") return `Move -${steps}`;
  return preferSafe === "false" ? `Move +${steps} on track` : `Move +${steps}`;
}

function rankLabel(value: string) {
  return value === "JK" ? "Joker" : value;
}

function normalizedPawnSet(ids: string[]) {
  if (!ids.length) return "";
  return [...ids].sort().join("|");
}

function unique<T>(values: T[]) {
  return Array.from(new Set(values));
}

function escapeHtml(value: string) {
  const element = document.createElement("span");
  element.textContent = value;
  return element.innerHTML;
}

function displaySeatName(seat: Seat) {
  return escapeHtml(state?.session.seats[seat].human_name || seat);
}

function boardSeatLabels(): Partial<Record<Seat, string>> {
  if (!state) return {};
  const labels: Partial<Record<Seat, string>> = {};
  for (const seat of seats) {
    labels[seat] = state.session.seats[seat].human_name || seat;
  }
  return labels;
}

function renderCard(card: CardInfo, playable: boolean, selected: boolean) {
  const isJoker = card.asset === "joker.png";
  return `
    <button type="button" class="card ${playable ? "selectable" : ""} ${selected ? "selected" : ""} ${isJoker ? "joker-card" : ""}" data-card-id="${card.id}" ${playable ? "" : "disabled"}>
      <img src="/cards/${card.asset}" alt="${card.label}" onerror="this.style.display='none'" />
      ${isJoker ? `<span>${card.label}</span>` : ""}
    </button>
  `;
}

function inputValue(selector: string, fallback: string) {
  return document.querySelector<HTMLInputElement>(selector)?.value.trim() || fallback;
}

function toast(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 3200);
}

refresh();
