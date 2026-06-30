export type SoundName = "cardDeal" | "pawnMove" | "diceRoll" | "playCard" | "skipTurn" | "selectionTick" | "turnWhoosh";

const SOUND_STORAGE_KEY = "brandi.soundEnabled";
const soundFiles: Record<SoundName, string> = {
  cardDeal: "/sounds/card_shuffle.mp3",
  pawnMove: "/sounds/pawn_movement.mp3",
  diceRoll: "/sounds/dice_roll.mp3",
  playCard: "/sounds/play_card.mp3",
  skipTurn: "/sounds/skip_turn.mp3",
  selectionTick: "/sounds/tick.mp3",
  turnWhoosh: "/sounds/whoosh.mp3",
};

const audioCache = new Map<SoundName, HTMLAudioElement>();
let enabled = localStorage.getItem(SOUND_STORAGE_KEY) === "1";

function audioFor(name: SoundName) {
  let audio = audioCache.get(name);
  if (!audio) {
    audio = new Audio(soundFiles[name]);
    audio.preload = "auto";
    audio.volume = 0.82;
    audioCache.set(name, audio);
  }
  return audio;
}

export function soundEnabled() {
  return enabled;
}

export function setSoundEnabled(nextEnabled: boolean) {
  enabled = nextEnabled;
  localStorage.setItem(SOUND_STORAGE_KEY, enabled ? "1" : "0");
  if (enabled) preloadSounds();
}

export function toggleSound() {
  setSoundEnabled(!enabled);
  return enabled;
}

export function preloadSounds() {
  (Object.keys(soundFiles) as SoundName[]).forEach((name) => audioFor(name).load());
}

export function playSound(name: SoundName, volumeScale = 1) {
  if (!enabled) return;
  const source = audioFor(name);
  const audio = source.cloneNode(true) as HTMLAudioElement;
  audio.volume = Math.max(0, Math.min(1, source.volume * volumeScale));
  audio.play().catch(() => {
    // Browsers can reject playback until the user interacts with the page.
  });
}
