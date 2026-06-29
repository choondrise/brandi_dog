import "./styles.css";
import rulesMarkdown from "./rules.md?raw";
import { inject } from "@vercel/analytics";
import { API_BASE, WS_BASE, createSession, getState, joinSession, playAction, playSevenSplit, previewSevenSplit, setBot, setSeat, startGame } from "./api";
import { renderBoard, type PreviewPosition, type ReplayAnimationPawn } from "./board";
import { renderTutorial, resetTutorial } from "./tutorial";
import { playSound, soundEnabled, toggleSound } from "./sounds";
import type { ActionInfo, ActionPreview, AppPayload, BotLevel, CardInfo, GamePayload, PawnInfo, Seat, TurnEvent } from "./types";

inject({ framework: "vite" });

const app = document.querySelector<HTMLDivElement>("#app")!;
const seats: Seat[] = ["A1", "B1", "A2", "B2"];
const botLevels: BotLevel[] = ["Idiot", "Easy", "Medium", "Hard", "Cheater"];

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
let replayEndpointEventId: string | null = null;
let replayPathEventId: string | null = null;
let replaySettleEventId: string | null = null;
let seenEventIds = new Set<string>();
let currentView: "home" | "rules" | "tutorial" = "home";
type FocusOverlay =
  | { kind: "swap"; card: CardInfo; title: string; text: string }
  | { kind: "deal"; count: number; title: string; text: string; rolling: boolean };
let activeOverlay: FocusOverlay | null = null;
let replayHandCards: CardInfo[] | null = null;
let optimisticHandCards: CardInfo[] | null = null;
type EndGameOverlay = { gameId: string; outcome: "win" | "lose"; phase: "splash" | "prompt" };
let endGameOverlay: EndGameOverlay | null = null;
let handledEndGameId = "";
let endGameFlowInProgress = false;
type PathPreview = Pick<ActionPreview, "positions" | "capturePawnIds" | "valid">;
const sevenPreviewCache = new Map<string, PathPreview>();
let pendingSevenPreviewKey = "";
let sevenPreviewTimer: number | null = null;

function saveIdentity(nextGameId: string, nextToken: string, nextHostToken = "") {
  socket?.close();
  socket = null;
  endGameOverlay = null;
  handledEndGameId = "";
  endGameFlowInProgress = false;
  resetSevenPreviewCache();
  gameId = nextGameId.toUpperCase();
  token = nextToken;
  hostToken = nextHostToken;
  localStorage.setItem("brandi.gameId", gameId);
  localStorage.setItem("brandi.token", token);
  if (hostToken) {
    localStorage.setItem("brandi.hostToken", hostToken);
  } else {
    localStorage.removeItem("brandi.hostToken");
  }
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
  replayEndpointEventId = null;
  replayPathEventId = null;
  replaySettleEventId = null;
  replayHandCards = null;
  optimisticHandCards = null;
  endGameOverlay = null;
  handledEndGameId = "";
  endGameFlowInProgress = false;
  resetSevenPreviewCache();
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
  if (currentView === "tutorial") {
    renderTutorial(app, () => {
      currentView = "home";
      render();
    });
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
    <main class="home home-intro">
      <section class="brand-panel">
        <h1 class="brand-title" aria-label="Brandi Dog">
          <span class="sr-only">Brandi Dog</span>
          <svg class="brand-title-svg" viewBox="10 0 315 210" role="img" aria-hidden="true">
            <text class="brand-title-letter l1" x="16" y="86">B</text>
            <text class="brand-title-letter l2 reverse" x="70" y="86">r</text>
            <text class="brand-title-letter l3" x="106" y="86">a</text>
            <text class="brand-title-letter l4 reverse" x="156" y="86">n</text>
            <text class="brand-title-letter l5" x="208" y="86">d</text>
            <text class="brand-title-letter l6 reverse" x="260" y="86">i</text>
            <text class="brand-title-letter l7 reverse" x="16" y="178">D</text>
            <text class="brand-title-letter l8" x="74" y="178">o</text>
            <text class="brand-title-letter l9 reverse" x="128" y="178">g</text>
          </svg>
        </h1>
        <p class="home-subtitle" aria-label="Start a table, share the game ID, fill empty seats with bots, and play from phone or desktop.">
          <span>Start a table</span><span>share the game ID</span><span>fill empty seats with bots</span><span>and play from phone or desktop.</span>
        </p>
      </section>
      <div class="home-divider" aria-hidden="true"></div>
      <section class="entry-panel home-entry-panel">
        <label>Your name<input id="name" autocomplete="name" maxlength="32" placeholder="Player" /></label>
        <button id="create">Create game</button>
        <div class="join-row">
          <input id="game-id" maxlength="6" placeholder="GAME ID" />
          <button id="join">Join</button>
        </div>
        <div class="home-link-row">
          <button id="how-to-play" class="ghost">How to play</button>
          <button id="tutorial-start" class="ghost">Tutorial (Beta)</button>
        </div>
      </section>
    </main>
  `;
  document.querySelector<HTMLButtonElement>("#how-to-play")!.onclick = () => {
    currentView = "rules";
    render();
  };
  document.querySelector<HTMLButtonElement>("#tutorial-start")!.onclick = () => {
    resetTutorial();
    currentView = "tutorial";
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
        <div class="header-actions">
          ${renderSoundToggle()}
          <button class="ghost" id="leave">Leave</button>
        </div>
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
  bindLobbyEvents();
}

function bindLobbyEvents() {
  bindSoundToggle();
  document.querySelector<HTMLElement>("#leave")!.onclick = clearIdentity;
  document.querySelector<HTMLElement>("#copy-code")!.onclick = async () => {
    await navigator.clipboard?.writeText(state!.session.game_id);
  };
  document.querySelector<HTMLElement>("#start")!.onclick = async () => {
    try {
      await acceptPayload(await startGame(gameId, hostToken || token), true);
    } catch (error) {
      toast(error);
    }
  };
  seats.forEach((seat) => {
    const sitButton = document.querySelector<HTMLButtonElement>(`#sit-${seat}`);
    if (sitButton) {
      sitButton.onclick = async () => {
        try {
          const payload = await setSeat(gameId, token, seat);
          const previous = state;
          state = payload;
          if (previous && canPatchLobby(previous, payload)) patchLobby(previous, payload);
          else render();
        } catch (error) {
          toast(error);
        }
      };
    }
    const botSelect = document.querySelector<HTMLSelectElement>(`#bot-${seat}`);
    if (botSelect) {
      botSelect.onchange = async (event) => {
        try {
          const payload = await setBot(gameId, hostToken || token, seat, (event.target as HTMLSelectElement).value as BotLevel);
          const previous = state;
          state = payload;
          if (previous && canPatchLobby(previous, payload)) patchLobby(previous, payload);
          else render();
        } catch (error) {
          toast(error);
        }
      };
    }
  });
}

function canPatchLobby(previous: AppPayload | null, next: AppPayload) {
  return Boolean(
    previous &&
      previous.session.phase === "LOBBY" &&
      next.session.phase === "LOBBY" &&
      !previous.game &&
      !next.game &&
      document.querySelector(".lobby"),
  );
}

function patchLobby(previous: AppPayload, next: AppPayload) {
  for (const seat of seats) {
    const beforeSeat = previous.session.seats[seat];
    const afterSeat = next.session.seats[seat];
    const viewerSeatChanged = previous.viewerSeat !== next.viewerSeat && (previous.viewerSeat === seat || next.viewerSeat === seat);
    if (viewerSeatChanged || JSON.stringify(beforeSeat) !== JSON.stringify(afterSeat)) {
      patchSeatCard(seat);
    }
  }
  bindLobbyEvents();
}

function patchSeatCard(seat: Seat) {
  const card = document.querySelector<HTMLElement>(`[data-seat-card="${seat}"]`);
  if (!card || !state) return;
  const info = state.session.seats[seat];
  const mine = state.viewerSeat === seat;
  const human = info.occupant === "human";

  card.classList.toggle("mine", mine);
  card.classList.toggle("occupied", human);

  const occupant = card.querySelector<HTMLElement>("[data-seat-occupant]");
  if (occupant) occupant.textContent = human ? info.human_name || "Player" : `${botLevelLabel(info.bot_level)} bot`;

  const sitButton = card.querySelector<HTMLButtonElement>("[data-seat-button]");
  if (sitButton) {
    sitButton.disabled = human;
    sitButton.textContent = mine ? "Your seat" : "Take seat";
  }

  const botSelect = card.querySelector<HTMLSelectElement>("[data-seat-bot]");
  if (botSelect) {
    botSelect.disabled = !state.isHost || human;
    if (botSelect.value !== info.bot_level) botSelect.value = info.bot_level;
  }
}

function renderSeatCard(seat: Seat) {
  const info = state!.session.seats[seat];
  const mine = state!.viewerSeat === seat;
  const human = info.occupant === "human";
  return `
    <article class="seat-card ${mine ? "mine" : ""} ${human ? "occupied" : ""}" data-seat-card="${seat}">
      <div class="seat-head">
        <strong>${seat}</strong>
        <span>Team ${info.team}</span>
      </div>
      <p class="occupant" data-seat-occupant>${human ? info.human_name : `${botLevelLabel(info.bot_level)} bot`}</p>
      <button id="sit-${seat}" data-seat-button ${human ? "disabled" : ""}>${mine ? "Your seat" : "Take seat"}</button>
      <label class="bot-select">
        Bot
        <select id="bot-${seat}" data-seat-bot ${state!.isHost && !human ? "" : "disabled"}>
          ${botLevels.map((level) => `<option value="${level}" ${info.bot_level === level ? "selected" : ""}>${botLevelLabel(level)}</option>`).join("")}
        </select>
      </label>
    </article>
  `;
}


async function acceptPayload(payload: AppPayload, replay = false) {
  const previousPayload = state;
  const previousGame = state?.game || null;
  const overlays = payload.game ? focusOverlaysForPayload(previousGame, payload) : [];
  const shouldPlayDealSound = payload.game ? cardDealSoundForPayload(previousGame, payload) : false;
  const events = (payload.events || []).filter((event) => !seenEventIds.has(event.id));
  for (const event of events) seenEventIds.add(event.id);
  replayHandCards = replay && events.length && payload.game ? replayHandForPayload(previousGame, payload, events) : null;
  if (!replay) optimisticHandCards = null;
  state = payload;
  if (!replay && canPatchLobby(previousPayload, payload)) {
    patchLobby(previousPayload!, payload);
    return;
  }
  if (!replay || !events.length || !payload.game) {
    if (shouldPlayDealSound && !overlays.some((overlay) => overlay.kind === "deal")) playSound("cardDeal");
    if (overlays.length) await playFocusOverlays(overlays);
    replayHandCards = null;
    optimisticHandCards = null;
    render();
    void maybeStartEndGameFlow(payload);
    return;
  }
  replayBaseGame = previousGame;
  await replayEvents(events, overlays, shouldPlayDealSound);
  void maybeStartEndGameFlow(payload);
}


function cardDealSoundForPayload(previousGame: GamePayload | null, payload: AppPayload) {
  const viewer = payload.viewerSeat;
  const nextGame = payload.game;
  if (!viewer || !nextGame || nextGame.phase !== "TEAM_SWAPS") return false;
  const nextHand = nextGame.hands[viewer].cards || [];
  if (!nextHand.length) return false;
  if (!previousGame) return true;
  if (previousGame.phase !== "TEAM_SWAPS") return true;
  return previousGame.dealRoundIndex !== nextGame.dealRoundIndex;
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
      playSound("cardDeal");
      await delay(2000);
      activeOverlay = { ...overlay, rolling: false };
      render();
      playSound("diceRoll");
      await delay(700);
    } else {
      await delay(2000);
    }
  }
  activeOverlay = null;
}

async function replayEvents(events: TurnEvent[], overlays: FocusOverlay[] = [], playDealSoundAfterReplay = false) {
  replayInProgress = true;
  replayPawns = events[0].pawnsBefore;
  currentReplayEvent = null;
  render();
  await delay(260);
  for (const event of events) {
    currentReplayEvent = event;
    replayEndpointEventId = null;
    replaySettleEventId = null;
    replayPathEventId = isReplayPathEvent(event) ? event.id : null;
    replayPawns = event.pawnsBefore;
    render();
    if (event.card) playSound("playCard");
    await delay(replayAnticipationDelay(event));

    replayPathEventId = null;
    replayEndpointEventId = isReplayMovementEvent(event) ? event.id : null;
    replayPawns = event.pawnsAfter;
    render();
    await delay(replayMoveAnimationDelay(event));
    if (isReplayMovementEvent(event)) playSound("pawnMove");

    replayEndpointEventId = null;
    replaySettleEventId = isReplayMovementEvent(event) ? event.id : null;
    replayPawns = event.pawnsAfter;
    render();
    await delay(replaySettleDelay(event));
  }
  currentReplayEvent = null;
  replayEndpointEventId = null;
  replayPathEventId = null;
  replaySettleEventId = null;
  replayPawns = null;
  replayBaseGame = null;
  replayInProgress = false;
  if (playDealSoundAfterReplay && !overlays.some((overlay) => overlay.kind === "deal")) playSound("cardDeal");
  if (overlays.length) await playFocusOverlays(overlays);
  replayHandCards = null;
  optimisticHandCards = null;
  render();
}

async function maybeStartEndGameFlow(payload: AppPayload) {
  if (endGameFlowInProgress || !payload.viewerSeat || !payload.game?.winner || payload.game.phase !== "GAME_OVER") return;
  if (handledEndGameId === payload.session.game_id) return;
  const viewerTeam = payload.game.players.find((player) => player.id === payload.viewerSeat)?.team;
  if (!viewerTeam) return;
  handledEndGameId = payload.session.game_id;
  endGameFlowInProgress = true;
  endGameOverlay = { gameId: payload.session.game_id, outcome: viewerTeam === payload.game.winner ? "win" : "lose", phase: "splash" };
  render();
  await delay(1600);
  if (endGameOverlay?.gameId === payload.session.game_id && endGameOverlay.phase === "splash") {
    endGameOverlay = { ...endGameOverlay, phase: "prompt" };
    render();
  }
  endGameFlowInProgress = false;
}

function renderTurnNotice(game: GamePayload) {
  if (currentReplayEvent || replayInProgress || actionInFlight || endGameOverlay) return "";
  if (!state?.viewerSeat || game.phase !== "PLAY_LOOP" || game.activePlayer !== state.viewerSeat) return "";
  if (selectedCardId !== null || noCardAction(game)) return "";
  return `
    <div class="replay-banner turn-notice human">
      <div>
        <span>YOUR TURN</span>
        <strong>Pick a card to play</strong>
      </div>
    </div>
  `;
}

function renderReplayBanner() {
  if (!currentReplayEvent) return "";
  const actor = escapeHtml(currentReplayEvent.actorName);
  const card = currentReplayEvent.card ? `<img src="/cards/${currentReplayEvent.card.asset}" alt="${escapeHtml(currentReplayEvent.card.label)}" />` : "";
  return `
    <div class="replay-banner ${currentReplayEvent.isBot ? "bot" : "human"}">
      ${card}
      <div>
        <span>${currentReplayEvent.isBot ? "Bot move" : "Your move"}</span>
        <strong>${actor}</strong>
        ${renderEventLabel(currentReplayEvent)}
      </div>
    </div>
  `;
}

function renderEventLabel(event: TurnEvent) {
  const action = event.action;
  if (!action) return `<p>${renderLabelWithPawnBadges(event.label)}</p>`;
  if (action.type === "PlayEnterAction" && action.pawns[0]) {
    return `<p>Enter ${renderActionPawnBadge(action.pawns[0])}</p>`;
  }
  if (action.type === "PlayStepCardAction" && action.pawns[0]) {
    const sign = action.direction === "BACKWARD" ? "-" : "+";
    return `<p>Move ${renderActionPawnBadge(action.pawns[0])} ${sign}${action.steps}</p>`;
  }
  if (action.type === "PlayJackSwapAction" && action.pawns[0] && action.pawns[1]) {
    return `<p>Swap ${renderActionPawnBadge(action.pawns[0])} with ${renderActionPawnBadge(action.pawns[1])}</p>`;
  }
  if (action.type === "PlaySevenSplitAction") {
    const moves = action.moves.map((move) => `${renderActionPawnBadge(move.pawn)} +${move.steps}`).join(" ");
    return `<p>Split ${moves}</p>`;
  }
  return `<p>${renderLabelWithPawnBadges(event.label)}</p>`;
}

function renderLabelWithPawnBadges(label: string) {
  const pattern = /\b(A1|A2|B1|B2)\.([1-4])\b/g;
  let html = "";
  let cursor = 0;
  for (const match of label.matchAll(pattern)) {
    const index = match.index ?? 0;
    html += escapeHtml(label.slice(cursor, index));
    html += renderActionPawnBadge({ owner: match[1] as Seat, number: Number(match[2]) - 1 });
    cursor = index + match[0].length;
  }
  html += escapeHtml(label.slice(cursor));
  return html;
}

function renderActionPawnBadge(pawn: { owner: Seat; number: number }) {
  const color = state?.game?.players.find((player) => player.id === pawn.owner)?.color || "#143d2b";
  return `<span class="pawn-badge replay-pawn-badge" style="--pawn-color:${color}" title="${pawn.owner}.${pawn.number + 1}">${pawn.number + 1}</span>`;
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function renderSoundToggle() {
  const enabled = soundEnabled();
  return `
    <button type="button" class="ghost sound-toggle" id="sound-toggle" aria-pressed="${enabled}" aria-label="${enabled ? "Sound on" : "Sound off"}" title="${enabled ? "Sound on" : "Sound off"}">
      <span class="sound-icon" aria-hidden="true">${enabled ? soundOnIcon() : soundOffIcon()}</span>
    </button>
  `;
}

function bindSoundToggle() {
  document.querySelector<HTMLButtonElement>("#sound-toggle")?.addEventListener("click", () => {
    toggleSound();
    render();
  });
}

function soundOnIcon() {
  return `<svg viewBox="0 0 24 24" focusable="false"><path d="M4 9v6h4l5 4V5L8 9H4Z"></path><path d="M16 8.5c1 .9 1.5 2.1 1.5 3.5s-.5 2.6-1.5 3.5"></path><path d="M18.5 6c1.7 1.6 2.5 3.6 2.5 6s-.8 4.4-2.5 6"></path></svg>`;
}

function soundOffIcon() {
  return `<svg viewBox="0 0 24 24" focusable="false"><path d="M4 9v6h4l5 4V5L8 9H4Z"></path><path d="M19 9l-5 5"></path><path d="M14 9l5 5"></path></svg>`;
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

function renderEndGameOverlay() {
  if (!endGameOverlay) return "";
  const won = endGameOverlay.outcome === "win";
  const resultWord = won ? "WIN" : "LOSE";
  const button = endGameOverlay.phase === "prompt" ? `<button id="play-again" type="button">Play again</button>` : `<div class="endgame-button-placeholder" aria-hidden="true"></div>`;
  return `
    <div class="endgame-overlay ${endGameOverlay.phase}">
      <div class="endgame-dialog ${won ? "win" : "lose"}">
        <strong class="endgame-title"><span>YOU</span><span>${resultWord}</span></strong>
        ${button}
      </div>
    </div>
  `;
}

async function playAgain() {
  if (actionInFlight) return;
  actionInFlight = true;
  render();
  try {
    const playerName = state?.viewerSeat ? state.session.seats[state.viewerSeat].human_name || "Player" : "Player";
    const created = await createSession(playerName);
    saveIdentity(created.game_id, created.player_token, created.host_token);
    seenEventIds = new Set<string>();
    actionInFlight = false;
    await refresh();
  } catch (error) {
    actionInFlight = false;
    toast(error);
    render();
  } finally {
    actionInFlight = false;
  }
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
  const preview = replayInProgress ? replayPathPreview() : pathPreview(game, finalAction);
  const previewMode = replayPathEventId ? "sequence" : "steady";
  const replayPathTiming = replayPathEventId && currentReplayEvent ? replayPathTimingForEvent(currentReplayEvent) : null;
  const boardActivePlayer = currentReplayEvent?.actor || game.activePlayer;
  const slowMotion = isReplayMovementEvent(currentReplayEvent);
  const replayEndpointAnimations = replayEndpointEventId && currentReplayEvent ? replayAnimationsForEvent(currentReplayEvent) : [];
  const replayEndpointDuration = replayEndpointEventId && currentReplayEvent ? replayMoveAnimationDelay(currentReplayEvent) : null;
  const replaySettleDuration = replaySettleEventId && currentReplayEvent ? replaySettleDelay(currentReplayEvent) : null;
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
        <div class="header-actions">
          ${renderSoundToggle()}
          <button class="ghost exit-button" id="exit-game">Exit</button>
        </div>
      </header>
      <section class="table-area">
        ${renderReplayBanner()}
        ${renderTurnNotice(game)}
        ${renderBoard(displayedPawns, boardActivePlayer, boardSeatLabels(), boardSelectedPawnIds(game), replayInProgress ? [] : selectablePawnIds, currentReplayEvent?.affectedPawns || [], preview.positions, preview.capturePawnIds, slowMotion, replayEndpointAnimations, replayEndpointDuration, previewMode, replaySettleDuration, replayPathTiming)}
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
      ${renderEndGameOverlay()}
    </main>
  `;
  document.querySelector("#back-lobby")!.addEventListener("click", refresh);
  bindSoundToggle();
  document.querySelector("#exit-game")!.addEventListener("click", confirmExitGame);
  document.querySelector("#play-again")?.addEventListener("click", playAgain);
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
        selectedSevenMoves = [];
      }
      if (kind === "reset-rank") {
        selectedRank = null;
        selectedVariant = null;
        selectedPawnIds = [];
        selectedSevenActionId = null;
        selectedSevenMoves = [];
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

function pathPreview(game: GamePayload, finalAction: ActionInfo | null): PathPreview {
  if (isCustomSevenMode(game)) return customSevenPreview(game);
  const action = finalAction || singleSelectedPawnPreviewAction(game);
  return action?.preview?.valid ? action.preview : emptyPreview();
}


function replayPathPreview(): PathPreview {
  if (!currentReplayEvent || replayPathEventId !== currentReplayEvent.id || !isReplayPathEvent(currentReplayEvent)) return emptyPreview();
  const preview = currentReplayEvent.action?.preview;
  return preview?.valid ? preview : emptyPreview();
}

function replayPathTimingForEvent(event: TurnEvent) {
  const count = event.action?.preview?.positions.length || 0;
  if (count <= 1) return { stepDelayMs: 0, stepDurationMs: 300 };
  const available = Math.max(420, replayAnticipationDelay(event) - 360);
  const stepDelayMs = Math.round(available / (count - 1));
  const stepDurationMs = Math.round(Math.min(360, Math.max(160, stepDelayMs * 0.85)));
  return { stepDelayMs, stepDurationMs };
}

function emptyPreview(): PathPreview {
  return { positions: [], capturePawnIds: [], valid: true };
}

function singleSelectedPawnPreviewAction(game: GamePayload) {
  if (selectedPawnIds.length !== 1) return null;
  const pawnId = selectedPawnIds[0];
  const candidates = variantFilteredActions(game).filter(
    (action) =>
      (action.type === "PlayStepCardAction" || action.type === "PlayEnterAction") &&
      action.pawns.length === 1 &&
      action.pawns[0].id === pawnId,
  );
  return candidates.length === 1 ? candidates[0] : null;
}

function customSevenPreview(game: GamePayload): PathPreview {
  const payload = customSevenPreviewPayload(game);
  if (!payload) return emptyPreview();
  const key = sevenPreviewCacheKey(game, payload);
  const cached = sevenPreviewCache.get(key);
  if (cached) return cached.valid ? cached : emptyPreview();
  scheduleSevenPreview(key, gameId, token, payload);
  return emptyPreview();
}

function customSevenPreviewPayload(game: GamePayload) {
  if (!isCustomSevenMode(game) || selectedCardId === null || !token) return null;
  const moves = selectedSevenMoves
    .filter((move): move is { pawnId: string; steps: number } => move.steps !== null)
    .map((move) => ({ pawn_id: move.pawnId, steps: move.steps, prefer_safe_entry: true }));
  if (!moves.length) return null;
  const representedRank = variantFilteredActions(game).find((action) => action.type === "PlaySevenSplitAction")?.representedRank || "7";
  return { cardId: selectedCardId, representedRank, moves };
}

function sevenPreviewCacheKey(game: GamePayload, payload: NonNullable<ReturnType<typeof customSevenPreviewPayload>>) {
  const pawnState = game.pawns.map((pawn) => `${pawn.id}:${pawn.position.kind}:${pawn.position.index ?? ""}`).join(",");
  const moves = payload.moves.map((move) => `${move.pawn_id}:${move.steps}:${move.prefer_safe_entry !== false ? 1 : 0}`).join("|");
  return [gameId, game.dealRoundIndex, game.discardCount, game.drawCount, game.activePlayer, pawnState, payload.cardId, payload.representedRank, moves].join(";");
}

function scheduleSevenPreview(key: string, requestGameId: string, requestToken: string, payload: NonNullable<ReturnType<typeof customSevenPreviewPayload>>) {
  pendingSevenPreviewKey = key;
  if (sevenPreviewTimer !== null) window.clearTimeout(sevenPreviewTimer);
  sevenPreviewTimer = window.setTimeout(async () => {
    sevenPreviewTimer = null;
    try {
      const preview = await previewSevenSplit(requestGameId, requestToken, payload.cardId, payload.representedRank, payload.moves);
      rememberSevenPreview(key, preview);
      if (pendingSevenPreviewKey === key) render();
    } catch {
      rememberSevenPreview(key, { positions: [], capturePawnIds: [], valid: false });
      if (pendingSevenPreviewKey === key) render();
    }
  }, 180);
}

function rememberSevenPreview(key: string, preview: PathPreview) {
  sevenPreviewCache.set(key, preview);
  while (sevenPreviewCache.size > 40) {
    const oldest = sevenPreviewCache.keys().next().value;
    if (!oldest) break;
    sevenPreviewCache.delete(oldest);
  }
}

function resetSevenPreviewCache() {
  sevenPreviewCache.clear();
  pendingSevenPreviewKey = "";
  if (sevenPreviewTimer !== null) window.clearTimeout(sevenPreviewTimer);
  sevenPreviewTimer = null;
}

function replaySettleDelay(event: TurnEvent) {
  const replayMultiplier = isReplayMovementEvent(event) ? 1.3 : 1;
  const settleDelay = event.isBot ? (event.affectedPawns.length ? 1760 : 1460) : event.affectedPawns.length ? 760 : 460;
  return Math.round(settleDelay * replayMultiplier);
}

function replayAnticipationDelay(event: TurnEvent) {
  const replayMultiplier = isReplayMovementEvent(event) ? 1.3 : 1;
  return Math.round((event.isBot ? 1520 : 360) * replayMultiplier);
}

function replayMoveAnimationDelay(event: TurnEvent) {
  return isReplayMovementEvent(event) ? 410 : 0;
}

function replayAnimationsForEvent(event: TurnEvent): ReplayAnimationPawn[] {
  const before = new Map(event.pawnsBefore.map((pawn) => [pawn.id, pawn]));
  const after = new Map(event.pawnsAfter.map((pawn) => [pawn.id, pawn]));
  return event.affectedPawns.flatMap((id) => {
    const from = before.get(id);
    const to = after.get(id);
    if (!from || !to) return [];
    if (from.position.kind === to.position.kind && from.position.index === to.position.index) return [];
    return [{ id, from, to }];
  });
}

function isReplayMovementEvent(event: TurnEvent | null) {
  return Boolean(event && event.type !== "DiscardHandAction" && event.type !== "SkipTurnAction" && event.affectedPawns.length > 0);
}

function isReplayPathEvent(event: TurnEvent | null) {
  return Boolean(
    event &&
      (event.type === "PlayStepCardAction" || event.type === "PlaySevenSplitAction") &&
      event.action?.preview?.valid &&
      event.action.preview.positions.length > 0,
  );
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
    parts.push(renderJokerRankSelector(options.rankOptions));
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

function renderJokerRankSelector(values: string[]) {
  if (selectedRank) {
    return `
      <div class="joker-value-selected">
        <span>Joker value</span>
        <strong>${rankLabel(selectedRank)}</strong>
        <button type="button" class="choice-btn" data-kind="reset-rank">Change Joker value</button>
      </div>
    `;
  }
  return `
    <div class="joker-value-picker">
      <span>Choose Joker value</span>
      <div class="joker-rank-grid ${values.length > 7 ? "two-rows" : "one-row"}">
        ${values.map((value) => `<button type="button" class="step-btn joker-rank-btn" data-kind="rank" data-value="${value}">${rankLabel(value)}</button>`).join("")}
      </div>
    </div>
  `;
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

function botLevelLabel(level: BotLevel) {
  if (level === "Idiot") return "Idi(b)ot";
  if (level === "Cheater") return "Mista Gridi Chitar";
  return level;
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
