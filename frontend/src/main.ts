import "./styles.css";
import rulesMarkdown from "./rules.md?raw";
import { inject } from "@vercel/analytics";
import { API_BASE, WS_BASE, createSession, getState, joinSession, playAction, playSevenSplit, setBot, setSeat, startGame } from "./api";
import { renderBoard } from "./board";
import type { ActionInfo, AppPayload, BotLevel, CardInfo, GamePayload, PawnInfo, Seat, TurnEvent } from "./types";

inject({ framework: "vite" });

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
type FocusOverlay =
  | { kind: "swap"; card: CardInfo; title: string; text: string }
  | { kind: "deal"; count: number; title: string; text: string; rolling: boolean };
let activeOverlay: FocusOverlay | null = null;
let replayHandCards: CardInfo[] | null = null;
let optimisticHandCards: CardInfo[] | null = null;

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
  replayHandCards = null;
  optimisticHandCards = null;
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
    await acceptPayload(nextState, false);
    connectSocket();
  } catch (error) {
    if (version === refreshVersion) {
      if (error instanceof Error && error.message === "Unknown game id") {
        clearIdentity();
        toast("That saved game is no longer available.");
        return;
      }
      toast(error);
      render();
    }
  }
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
      optimisticHandCards = null;
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
  const overlays = payload.game ? focusOverlaysForPayload(previousGame, payload) : [];
  const events = (payload.events || []).filter((event) => !seenEventIds.has(event.id));
  for (const event of events) seenEventIds.add(event.id);
  replayHandCards = replay && events.length && payload.game ? replayHandForPayload(previousGame, payload, events) : null;
  if (!replay) optimisticHandCards = null;
  state = payload;
  if (!replay || !events.length || !payload.game) {
    if (overlays.length) await playFocusOverlays(overlays);
    replayHandCards = null;
    optimisticHandCards = null;
    render();
    return;
  }
  replayBaseGame = previousGame;
  await replayEvents(events, overlays);
}

function focusOverlaysForPayload(previousGame: GamePayload | null, payload: AppPayload) {
  const viewer = payload.viewerSeat;
  const nextGame = payload.game;
  if (!viewer || !nextGame) return [];
  const previousHand = previousGame?.hands[viewer].cards || [];
  const nextHand = nextGame.hands[viewer].cards || [];
  const overlays: FocusOverlay[] = [];
  const added = nextHand.filter((card) => !previousHand.some((oldCard) => oldCard.id === card.id));
  const removed = previousHand.filter((card) => !nextHand.some((newCard) => newCard.id === card.id));
  const swappedCardReceived = previousGame?.phase === "TEAM_SWAPS" && added.length === 1 && removed.length === 1;
  if (swappedCardReceived) {
    overlays.push({
      kind: "swap",
      card: added[0],
      title: "Card received",
      text: `You received ${added[0].label} from your teammate.`,
    });
  }

  const isDiceDeal =
    nextGame.phase === "TEAM_SWAPS" &&
    nextGame.dealRoundIndex >= 5 &&
    nextHand.length > 0 &&
    (!previousGame || previousGame.phase !== "TEAM_SWAPS" || previousGame.dealRoundIndex !== nextGame.dealRoundIndex);
  if (isDiceDeal) {
    overlays.push({
      kind: "deal",
      count: nextGame.activeDealSize,
      title: "New hand",
      text: `${nextGame.activeDealSize} cards dealt. ${displaySeatName(nextGame.roundStarter)} plays first.`,
      rolling: true,
    });
  }
  return overlays;
}

function replayHandForPayload(previousGame: GamePayload | null, payload: AppPayload, events: TurnEvent[]) {
  const viewer = payload.viewerSeat;
  const nextGame = payload.game;
  if (!viewer || !nextGame) return null;
  if (previousGame?.phase === "PLAY_LOOP" && nextGame.phase === "TEAM_SWAPS") {
    let cards = [...(previousGame.hands[viewer].cards || [])];
    for (const event of events) {
      if (event.actor === viewer && event.card) {
        cards = cards.filter((card) => card.id !== event.card!.id);
      }
    }
    return cards;
  }
  return nextGame.hands[viewer].cards || [];
}

async function playFocusOverlays(overlays: FocusOverlay[]) {
  for (const overlay of overlays) {
    activeOverlay = overlay;
    render();
    if (overlay.kind === "deal") {
      await delay(2000);
      activeOverlay = { ...overlay, rolling: false };
      render();
      await delay(700);
    } else {
      await delay(2000);
    }
  }
  activeOverlay = null;
}

async function replayEvents(events: TurnEvent[], overlays: FocusOverlay[] = []) {
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
  if (overlays.length) await playFocusOverlays(overlays);
  replayHandCards = null;
  optimisticHandCards = null;
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

function renderFocusOverlay() {
  if (!activeOverlay) return "";
  if (activeOverlay.kind === "deal") {
    return `
      <div class="focus-overlay">
        <div class="focus-card deal-focus">
          <div class="die ${activeOverlay.rolling ? "rolling" : ""}">${activeOverlay.rolling ? "?" : activeOverlay.count}</div>
        </div>
      </div>
    `;
  }
  return `
    <div class="focus-overlay">
      <div class="focus-card swap-focus">
        <img src="/cards/${activeOverlay.card.asset}" alt="${escapeHtml(activeOverlay.card.label)}" />
        <span>${escapeHtml(activeOverlay.title)}</span>
        <strong>${escapeHtml(activeOverlay.card.label)}</strong>
        <p>${escapeHtml(activeOverlay.text)}</p>
      </div>
    </div>
  `;
}

function renderGame() {
  const game = replayInProgress && replayBaseGame ? replayBaseGame : state!.game!;
  const latestGame = state!.game!;
  const displayedPawns = replayPawns || game.pawns;
  const hand = state!.viewerSeat ? optimisticHandCards ?? replayHandCards ?? latestGame.hands[state!.viewerSeat].cards ?? [] : [];
  normalizeSelection(game, hand);
  const playableNoCardAction = noCardAction(game);
  const finalAction = selectedPlayableAction(game);
  const actionOptions = selectionOptions(game);
  const customSevenReady = customSevenActionReady(game);
  const selectablePawnIds = selectablePawns(game);
  const canPlay = Boolean(finalAction || playableNoCardAction || customSevenReady);
  app.innerHTML = `
    <main class="game">
      <header class="game-status">
        <button class="ghost player-button" id="back-lobby">${state!.viewerSeat ? displaySeatName(state!.viewerSeat) : "Spectator"}</button>
        <div>
          <span class="eyebrow">${game.phase.replace("_", " ")}</span>
          <strong>${game.winner ? `Team ${game.winner} wins` : game.activePlayer ? `${displaySeatName(game.activePlayer)} to move` : "Game over"}</strong>
          ${game.phase === "TEAM_SWAPS" ? `<p class="round-note">First to play: ${displaySeatName(game.roundStarter)} - ${game.activeDealSize} cards</p>` : ""}
        </div>
        <button class="ghost exit-button" id="exit-game">Exit</button>
      </header>
      <section class="table-area">
        ${renderReplayBanner()}
        ${renderBoard(displayedPawns, game.activePlayer, boardSeatLabels(), boardSelectedPawnIds(game), replayInProgress ? [] : selectablePawnIds, currentReplayEvent?.affectedPawns || [])}
      </section>
      <section class="hand-tray">
        <div class="hand-header">
          <strong>Your hand</strong>
          <span>${hand.length} cards</span>
        </div>
        <div class="cards">${hand.map((card) => renderCard(card, !replayInProgress && cardPlayable(game, card.id), selectedCardId === card.id)).join("") || `<span class="muted">No visible cards</span>`}</div>
        ${replayInProgress ? `<div class="selection-panel"><p class="muted">Resolving moves before the next hand is dealt.</p></div>` : renderSelectionControls(game, actionOptions)}
      </section>
      <section class="play-bar">
        <button id="clear-selection" class="ghost" ${hasSelection() ? "" : "disabled"}>Clear</button>
        <button id="confirm-play" ${canPlay && !actionInFlight && !replayInProgress ? "" : "disabled"}>${replayInProgress ? "Playing..." : actionInFlight ? "Playing..." : playButtonText(playableNoCardAction, finalAction)}</button>
      </section>
      ${renderFocusOverlay()}
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
        selectedSevenMoves = [];
      }
      render();
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".pawn.selectable").forEach((button) => {
    button.addEventListener("click", () => {
      const pawnId = button.dataset.pawnId;
      if (!pawnId) return;
      if (isCustomSevenMode(game)) {
        toggleSevenPawn(pawnId);
      } else if (selectedPawnIds.includes(pawnId)) {
        selectedPawnIds = selectedPawnIds.filter((id) => id !== pawnId);
      } else {
        selectedPawnIds = [...selectedPawnIds, pawnId];
      }
      selectedSevenActionId = null;
      render();
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".choice-btn, .step-btn").forEach((button) => {
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
      if (kind === "seven-step") {
        setSevenMoveSteps(Number(button.dataset.index), Number(button.dataset.value));
      }
      render();
    });
  });
  document.querySelector("#confirm-play")!.addEventListener("click", async () => {
    if (actionInFlight || replayInProgress) return;
    const sevenAction = customSevenActionPayload(game);
    const action = playableNoCardAction || selectedPlayableAction(game);
    if (!action && !sevenAction) return;
    if (action && !action.card && action.type !== "SkipTurnAction") optimisticHandCards = [];
    actionInFlight = true;
    render();
    try {
      const payload = sevenAction
        ? await playSevenSplit(gameId, token, sevenAction.cardId, sevenAction.representedRank, sevenAction.moves)
        : await playAction(gameId, token, action!.key);
      clearSelection();
      await acceptPayload(payload, true);
    } catch (error) {
      optimisticHandCards = null;
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
type SevenDraftMove = { pawnId: string; steps: number | null };
let selectedSevenMoves: SevenDraftMove[] = [];

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
  selectedSevenMoves = [];
}

function hasSelection() {
  return selectedCardId !== null || selectedPawnIds.length > 0 || selectedRank !== null || selectedVariant !== null || selectedSevenActionId !== null || selectedSevenMoves.length > 0;
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

function isCustomSevenMode(game: GamePayload) {
  return variantFilteredActions(game).some((action) => action.type === "PlaySevenSplitAction");
}

function boardSelectedPawnIds(game: GamePayload) {
  return isCustomSevenMode(game) ? selectedSevenMoves.map((move) => move.pawnId) : selectedPawnIds;
}

function sevenSelectablePawnIds(game: GamePayload) {
  if (!game.activePlayer) return [];
  const active = game.players.find((player) => player.id === game.activePlayer);
  if (!active) return [];
  return game.pawns
    .filter((pawn) => pawn.position.kind !== "BASE")
    .filter((pawn) => game.players.find((player) => player.id === pawn.owner)?.team === active.team)
    .map((pawn) => pawn.id);
}

function toggleSevenPawn(pawnId: string) {
  if (selectedSevenMoves.some((move) => move.pawnId === pawnId)) {
    selectedSevenMoves = selectedSevenMoves.filter((move) => move.pawnId !== pawnId);
    return;
  }
  selectedSevenMoves = [...selectedSevenMoves, { pawnId, steps: null }];
}

function setSevenMoveSteps(index: number, steps: number) {
  selectedSevenMoves = selectedSevenMoves.map((move, moveIndex) => (moveIndex === index ? { ...move, steps } : move));
  normalizeSevenSteps();
}

function normalizeSevenSteps() {
  let total = 0;
  selectedSevenMoves = selectedSevenMoves.map((move) => {
    if (move.steps === null) return move;
    if (total + move.steps > 7) return { ...move, steps: null };
    total += move.steps;
    return move;
  });
}

function customSevenActionReady(game: GamePayload) {
  return Boolean(customSevenActionPayload(game));
}

function customSevenActionPayload(game: GamePayload) {
  if (!isCustomSevenMode(game) || selectedCardId === null) return null;
  if (!selectedSevenMoves.length || selectedSevenMoves.some((move) => move.steps === null)) return null;
  const total = selectedSevenMoves.reduce((sum, move) => sum + (move.steps || 0), 0);
  if (total !== 7) return null;
  const representedRank = variantFilteredActions(game).find((action) => action.type === "PlaySevenSplitAction")?.representedRank || "7";
  return {
    cardId: selectedCardId,
    representedRank,
    moves: selectedSevenMoves.map((move) => ({ pawn_id: move.pawnId, steps: move.steps!, prefer_safe_entry: true })),
  };
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
  if (isCustomSevenMode(game)) return sevenSelectablePawnIds(game);
  const actions = variantFilteredActions(game);
  return unique(actions.flatMap((action) => action.pawns.map((pawn) => pawn.id)));
}

function renderSelectionControls(game: GamePayload, options: ReturnType<typeof selectionOptions>) {
  if (selectedCardId === null && !noCardAction(game)) {
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
    parts.push(renderSevenBuilder(game));
  } else if (actions.some((action) => action.type !== "SwapCardAction")) {
    parts.push(`<p class="muted">Select the involved figure${actions.some((action) => action.type === "PlayJackSwapAction") ? "s" : ""} on the board.</p>`);
  }
  return `<div class="selection-panel">${parts.join("")}</div>`;
}

function renderSevenBuilder(game: GamePayload) {
  const remaining = 7 - selectedSevenMoves.reduce((total, move) => total + (move.steps || 0), 0);
  const total = 7 - remaining;
  const parts = selectedSevenMoves.map((move, index) => {
    const pawn = game.pawns.find((item) => item.id === move.pawnId);
    if (!pawn) return "";
    const otherTotal = selectedSevenMoves.reduce((sum, other, otherIndex) => sum + (otherIndex === index ? 0 : other.steps || 0), 0);
    const maxForMove = 7 - otherTotal;
    return `
      <div class="seven-move">
        <div class="seven-move-head">
          <span class="order-pill">${index + 1}</span>
          ${renderPawnBadge(pawn)}
        </div>
        <div class="step-grid">
          ${[1, 2, 3, 4, 5, 6, 7]
            .map((step) => `<button type="button" class="step-btn ${move.steps === step ? "selected" : ""}" data-kind="seven-step" data-index="${index}" data-value="${step}" ${step > maxForMove ? "disabled" : ""}>${step}</button>`)
            .join("")}
        </div>
      </div>
    `;
  });
  return `
    <div class="seven-builder">
      <div class="seven-summary">
        <span>Select figures in move order</span>
        <strong>${total}/7</strong>
      </div>
      ${parts.length ? parts.join("") : `<p class="muted">Tap the figures on the board in the order they should move.</p>`}
      ${remaining < 0 ? `<p class="muted">The split must total exactly 7.</p>` : remaining > 0 ? `<p class="muted">${remaining} step${remaining === 1 ? "" : "s"} remaining.</p>` : `<p class="muted">Ready to play this split.</p>`}
    </div>
  `;
}

function renderPawnBadge(pawn: PawnInfo) {
  return `<span class="pawn-badge" style="--pawn-color:${pawn.color}">${pawn.number + 1}</span>`;
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
