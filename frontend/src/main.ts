import "./styles.css";
import rulesMarkdown from "./rules.md?raw";
import { API_BASE, WS_BASE, createSession, getState, joinSession, playAction, setBot, setSeat, startGame } from "./api";
import { renderBoard } from "./board";
import type { ActionInfo, AppPayload, BotLevel, CardInfo, GamePayload, PawnInfo, Seat, TurnEvent } from "./types";

const app = document.querySelector<HTMLDivElement>("#app")!;
const seats: Seat[] = ["A1", "B1", "A2", "B2"];
const botLevels: BotLevel[] = ["Idiot", "Easy", "Hard", "Cheater"];

let gameId = localStorage.getItem("brandi.gameId") || "";
let token = localStorage.getItem("brandi.token") || "";
let hostToken = localStorage.getItem("brandi.hostToken") || "";
let state: AppPayload | null = null;
let socket: WebSocket | null = null;
let actionInFlight = false;
let replayInProgress = false;
let refreshVersion = 0;
let replayPawns: PawnInfo[] | null = null;
let replayBaseGame: GamePayload | null = null;
let currentReplayEvent: TurnEvent | null = null;
let seenEventIds = new Set<string>();
let currentView: "home" | "rules" = "home";

function saveIdentity(nextGameId: string, nextToken: string, nextHostToken = "") {
  gameId = nextGameId.toUpperCase();
  token = nextToken;
  if (nextHostToken) hostToken = nextHostToken;
  localStorage.setItem("brandi.gameId", gameId);
  localStorage.setItem("brandi.token", token);
  if (hostToken) localStorage.setItem("brandi.hostToken", hostToken);
}

function confirmExitGame() {
  if (window.confirm("Exit this game? You can rejoin later with the same game ID if the table is still running.")) {
    clearIdentity();
  }
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
  replayInProgress = false;
  replayPawns = null;
  replayBaseGame = null;
  currentReplayEvent = null;
  seenEventIds = new Set<string>();
  render();
}

async function refresh() {
  const version = ++refreshVersion;
  if (!gameId) {
    render();
    return;
  }
  if (replayInProgress || actionInFlight) return;
  try {
    const nextState = await getState(gameId, token);
    if (version !== refreshVersion) return;
    state = nextState;
    connectSocket();
  } catch (error) {
    if (version === refreshVersion) toast(error);
  }
  if (version === refreshVersion) render();
}

function connectSocket() {
  if (!gameId || document.hidden || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  const nextSocket = new WebSocket(`${WS_BASE}/ws/${gameId}${query}`);
  socket = nextSocket;
  nextSocket.onmessage = async (event) => {
    if (socket !== nextSocket) return;
    const payload = JSON.parse(event.data);
    if (payload.type === "refresh") {
      await refresh();
      return;
    }
    if (payload.session && !replayInProgress && !actionInFlight) {
      await acceptPayload(payload, Boolean(payload.events?.length));
    }
  };
  nextSocket.onclose = () => {
    if (socket === nextSocket) socket = null;
  };
}

function disconnectSocket() {
  socket?.close();
  socket = null;
}

function render() {
  if (currentView === "rules") {
    renderRules();
    return;
  }
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
        <button id="how-to-play" class="ghost">How to play</button>
      </section>
    </main>
  `;
  document.querySelector<HTMLButtonElement>("#how-to-play")!.onclick = () => {
    currentView = "rules";
    render();
  };
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

function renderRules() {
  app.innerHTML = `
    <main class="rules-page">
      <header class="rules-header">
        <button id="rules-back" class="ghost">Go back</button>
        <div>
          <span class="eyebrow">Rules</span>
          <strong>How to play Brandi Dog</strong>
        </div>
      </header>
      <section class="rules-content">
        ${renderRulesMarkdown(rulesMarkdown)}
      </section>
    </main>
  `;
  document.querySelector<HTMLButtonElement>("#rules-back")!.onclick = () => {
    currentView = "home";
    render();
  };
}

function renderRulesMarkdown(markdown: string) {
  const lines = markdown.split(/\r?\n/);
  const html: string[] = [];
  let listOpen = false;
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      if (listOpen) {
        html.push("</ul>");
        listOpen = false;
      }
      continue;
    }
    if (line.startsWith("# ")) {
      if (listOpen) {
        html.push("</ul>");
        listOpen = false;
      }
      html.push(`<h1>${escapeHtml(line.slice(2))}</h1>`);
      continue;
    }
    if (line.startsWith("## ")) {
      if (listOpen) {
        html.push("</ul>");
        listOpen = false;
      }
      html.push(`<h2>${escapeHtml(line.slice(3))}</h2>`);
      continue;
    }
    if (line.startsWith("- ")) {
      if (!listOpen) {
        html.push("<ul>");
        listOpen = true;
      }
      html.push(`<li>${escapeHtml(line.slice(2))}</li>`);
      continue;
    }
    if (listOpen) {
      html.push("</ul>");
      listOpen = false;
    }
    html.push(`<p>${escapeHtml(line)}</p>`);
  }
  if (listOpen) html.push("</ul>");
  return html.join("");
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
      await acceptPayload(await startGame(gameId, hostToken || token), true);
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


async function acceptPayload(payload: AppPayload, replay = false) {
  const previousGame = state?.game || null;
  const events = (payload.events || []).filter((event) => !seenEventIds.has(event.id));
  for (const event of events) seenEventIds.add(event.id);
  state = payload;
  if (!replay || !events.length || !payload.game) {
    render();
    return;
  }
  replayBaseGame = previousGame;
  await replayEvents(events);
}

async function replayEvents(events: TurnEvent[]) {
  replayInProgress = true;
  replayPawns = events[0].pawnsBefore;
  currentReplayEvent = null;
  render();
  await delay(260);
  for (const event of events) {
    currentReplayEvent = event;
    replayPawns = event.pawnsBefore;
    render();
    await delay(event.isBot ? 1520 : 360);
    replayPawns = event.pawnsAfter;
    render();
    await delay(event.isBot ? (event.affectedPawns.length ? 1760 : 1460) : event.affectedPawns.length ? 760 : 460);
  }
  currentReplayEvent = null;
  replayPawns = null;
  replayBaseGame = null;
  replayInProgress = false;
  render();
}

function renderReplayBanner() {
  if (!currentReplayEvent) return "";
  const actor = escapeHtml(currentReplayEvent.actorName);
  const label = escapeHtml(currentReplayEvent.label);
  const card = currentReplayEvent.card ? `<img src="/cards/${currentReplayEvent.card.asset}" alt="${escapeHtml(currentReplayEvent.card.label)}" />` : "";
  return `
    <div class="replay-banner ${currentReplayEvent.isBot ? "bot" : "human"}">
      ${card}
      <div>
        <span>${currentReplayEvent.isBot ? "Bot move" : "Your move"}</span>
        <strong>${actor}</strong>
        <p>${label}</p>
      </div>
    </div>
  `;
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function renderGame() {
  const game = replayInProgress && replayBaseGame ? replayBaseGame : state!.game!;
  const displayedPawns = replayPawns || game.pawns;
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
        <button class="ghost player-button" id="back-lobby">${state!.viewerSeat ? displaySeatName(state!.viewerSeat) : "Spectator"}</button>
        <div>
          <span class="eyebrow">${game.phase.replace("_", " ")}</span>
          <strong>${game.winner ? `Team ${game.winner} wins` : game.activePlayer ? `${displaySeatName(game.activePlayer)} to move` : "Game over"}</strong>
        </div>
        <button class="ghost exit-button" id="exit-game">Exit</button>
      </header>
      <section class="table-area">
        ${renderReplayBanner()}
        ${renderBoard(displayedPawns, game.activePlayer, boardSeatLabels(), selectedPawnIds, replayInProgress ? [] : selectablePawnIds, currentReplayEvent?.affectedPawns || [])}
      </section>
      <section class="hand-tray">
        <div class="hand-header">
          <strong>Your hand</strong>
          <span>${hand.length || (state!.viewerSeat ? game.hands[state!.viewerSeat].count : 0)} cards</span>
        </div>
        <div class="cards">${hand.map((card) => renderCard(card, !replayInProgress && cardPlayable(game, card.id), selectedCardId === card.id)).join("") || `<span class="muted">No visible cards</span>`}</div>
        ${replayInProgress ? `<div class="selection-panel"><p class="muted">Resolving moves before the next hand is dealt.</p></div>` : renderSelectionControls(game, actionOptions)}
      </section>
      <section class="play-bar">
        <button id="clear-selection" class="ghost" ${hasSelection() ? "" : "disabled"}>Clear</button>
        <button id="confirm-play" ${canPlay && !actionInFlight && !replayInProgress ? "" : "disabled"}>${replayInProgress ? "Replaying..." : actionInFlight ? "Playing..." : playButtonText(playableNoCardAction, finalAction)}</button>
      </section>
    </main>
  `;
  document.querySelector("#back-lobby")!.addEventListener("click", refresh);
  document.querySelector("#exit-game")!.addEventListener("click", confirmExitGame);
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
    if (actionInFlight || replayInProgress) return;
    const action = playableNoCardAction || selectedPlayableAction(game);
    if (!action) return;
    actionInFlight = true;
    render();
    try {
      const payload = await playAction(gameId, token, action.key);
      clearSelection();
      await acceptPayload(payload, true);
    } catch (error) {
      toast(error);
      actionInFlight = false;
      await refresh();
    } finally {
      actionInFlight = false;
      if (!replayInProgress) render();
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

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearSelection();
    disconnectSocket();
    render();
    return;
  }
  void refresh();
});

window.addEventListener("focus", () => {
  if (!document.hidden) void refresh();
});

window.addEventListener("pageshow", () => {
  if (!document.hidden) void refresh();
});

refresh();
