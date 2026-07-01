export type Language = "en" | "de" | "fr" | "hr";

export const LANGUAGE_STORAGE_KEY = "brandi.language";

export const languages: { code: Language; label: string; shortLabel: string; flag: string }[] = [
  { code: "en", label: "English", shortLabel: "EN", flag: "🇬🇧" },
  { code: "de", label: "Deutsch", shortLabel: "DE", flag: "🇩🇪" },
  { code: "fr", label: "Français", shortLabel: "FR", flag: "🇫🇷" },
  { code: "hr", label: "Hrvatski", shortLabel: "HR", flag: "🇭🇷" },
];

type Vars = Record<string, string | number>;
type TranslationValue = string | ((vars?: Vars) => string);
type TranslationMap = Record<string, TranslationValue>;

const dictionaries: Record<Language, TranslationMap> = {
  en: {
    "language.label": "Language",
    "home.subtitle.1": "Start a table",
    "home.subtitle.2": "share the game ID",
    "home.subtitle.3": "fill empty seats with bots",
    "home.subtitle.4": "and play from phone or desktop.",
    "home.name": "Your name",
    "home.namePlaceholder": "Player",
    "home.create": "Create game",
    "home.gameIdPlaceholder": "GAME ID",
    "home.join": "Join",
    "home.howToPlay": "How to play",
    "home.tutorial": "Tutorial (Beta)",
    "rules.back": "Go back",
    "rules.eyebrow": "Rules",
    "rules.title": "How to play Brandi Dog",
    "lobby.gameId": "Game ID",
    "lobby.leave": "Leave",
    "lobby.start": "Start game",
    "lobby.hostHint": "Empty seats will use their selected bot.",
    "lobby.guestHint": "Waiting for host to start.",
    "lobby.team": ({ team } = {}) => `Team ${team}`,
    "lobby.bot": "Bot",
    "lobby.botOccupant": ({ bot } = {}) => `${bot} bot`,
    "lobby.yourSeat": "Your seat",
    "lobby.takeSeat": "Take seat",
    "toast.savedGameGone": "That saved game is no longer available.",
    "toast.enterGameId": "Enter a game ID",
    "error.seatTaken": "Seat is already taken",
    "error.needHumanSeat": "At least one human must take a seat before starting",
    "error.gameOver": "Game is over",
    "error.notYourTurn": "It is not your turn",
    "error.invalidAction": "Invalid action",
    "error.moveNoLongerLegal": "Selected move is no longer legal. Refresh and choose again.",
    "error.lobbyClosed": "Session is no longer in the lobby",
    "error.notStarted": "Game has not started",
    "error.hostOnly": "Only the host can do that",
    "error.unknownToken": "Unknown player token",
    "error.invalidSeat": "Seat must be A1, B1, A2, or B2",
    "confirm.exit": "Exit this game and return to a new lobby?",
    "game.soundOn": "Sound on",
    "game.soundOff": "Sound off",
    "game.skipAnimations": "Always skip animations",
    "game.playAnimations": "Play animations",
    "game.botMove": "Bot move",
    "game.yourMove": "Your move",
    "game.enter": "Enter",
    "game.move": "Move",
    "game.swap": "Swap",
    "game.with": "with",
    "game.split": "Split",
    "game.yourTurn": "YOUR TURN",
    "game.pickCard": "Pick a card to play",
    "game.teamWins": ({ team } = {}) => `Team ${team} wins`,
    "game.toMove": ({ player } = {}) => `${player} to move`,
    "game.over": "Game over",
    "game.firstToPlay": ({ player, count } = {}) => `First to play: ${player} - ${count} cards`,
    "game.exit": "Exit",
    "game.yourHand": "Your hand",
    "game.cardCount": ({ count } = {}) => `${count} cards`,
    "game.noVisibleCards": "No visible cards",
    "game.resolving": "Resolving moves before the next hand is dealt.",
    "game.clear": "Clear",
    "game.fastForward": "Fast forward",
    "game.playing": "Playing...",
    "game.skip": "Skip",
    "game.discardHand": "Discard hand",
    "game.play": "Play",
    "game.swapCard": "Swap card",
    "game.cardReceived": "Card received",
    "game.receivedCard": ({ card } = {}) => `You received ${card} from your teammate.`,
    "game.newHand": "New hand",
    "game.dealText": ({ count, player } = {}) => `${count} cards dealt. ${player} plays first.`,
    "game.you": "YOU",
    "game.win": "WIN",
    "game.lose": "LOSE",
    "game.playAgain": "Play again",
    "selection.selectCard": "Select a card to begin.",
    "selection.noCard": "No card play is available. Confirm to continue.",
    "selection.chooseHow": "Choose how to play it",
    "selection.involvedFigures": ({ plural } = {}) => `Select the involved figure${plural ? "s" : ""} on the board.`,
    "selection.selectFiguresOrder": "Select figures in move order",
    "selection.tapFiguresOrder": "Tap the figures on the board in the order they should move.",
    "selection.splitExact": "The split must total exactly 7.",
    "selection.stepsRemaining": ({ count } = {}) => `${count} step${count === 1 ? "" : "s"} remaining.`,
    "selection.splitReady": "Ready to play this split.",
    "selection.routeChoice": "Route",
    "selection.routeSafe": "Safe zone",
    "selection.routeTrack": "On track",
    "selection.jokerValue": "Joker value",
    "selection.changeJoker": "Change Joker value",
    "selection.chooseJoker": "Choose Joker value",
    "variant.enter": "Enter pawn",
    "variant.jack": "Jack swap",
    "variant.seven": "Split 7",
    "variant.swap": "Swap with teammate",
    "variant.moveBackward": ({ steps } = {}) => `Move -${steps}`,
    "variant.moveForwardTrack": ({ steps } = {}) => `Move +${steps} on track`,
    "variant.moveForward": ({ steps } = {}) => `Move +${steps}`,
    "rank.joker": "Joker",
    "rank.ace": "A",
    "tutorial.back": "Go back",
    "tutorial.hand": "Your hand",
    "tutorial.cards": ({ count } = {}) => `${count} cards`,
    "tutorial.backButton": "Back",
    "tutorial.finish": "Finish",
    "tutorial.done": "Done",
    "tutorial.next": "Next",
    "tutorial.play": "Play",
    "tutorial.swapCard": "Swap card",
    "tutorial.reveals": "The game reveals only the choices that matter right now.",
    "tutorial.chooseDirection": "Choose direction",
    "tutorial.chooseJoker": "Choose joker value",
    "tutorial.firstPawn": "First pawn",
    "tutorial.secondPawn": "Second pawn",
    "tutorial.split7": "Split the 7",
    "tutorial.tapPawn": "Now tap the highlighted pawn on the board.",
    "tutorial.selectCard": "Select the highlighted card to continue.",
    "tutorial.partner": "Partner",
    "tutorial.opponent": "Opponent",
    "tutorial.you": "You",
  },
  de: {
    "language.label": "Sprache",
    "home.subtitle.1": "Tisch erstellen",
    "home.subtitle.2": "Spielcode teilen",
    "home.subtitle.3": "freie Plätze mit Bots füllen",
    "home.subtitle.4": "und am Handy oder Desktop spielen.",
    "home.name": "Dein Name",
    "home.namePlaceholder": "Spieler",
    "home.create": "Spiel erstellen",
    "home.gameIdPlaceholder": "SPIELCODE",
    "home.join": "Beitreten",
    "home.howToPlay": "Spielregeln",
    "home.tutorial": "Tutorial (Beta)",
    "rules.back": "Zurück",
    "rules.eyebrow": "Regeln",
    "rules.title": "So spielt man Brandi Dog",
    "lobby.gameId": "Spielcode",
    "lobby.leave": "Verlassen",
    "lobby.start": "Spiel starten",
    "lobby.hostHint": "Freie Plätze nutzen den ausgewählten Bot.",
    "lobby.guestHint": "Warten auf den Host.",
    "lobby.team": ({ team } = {}) => `Team ${team}`,
    "lobby.bot": "Bot",
    "lobby.botOccupant": ({ bot } = {}) => `${bot} Bot`,
    "lobby.yourSeat": "Dein Platz",
    "lobby.takeSeat": "Platz nehmen",
    "toast.savedGameGone": "Dieses gespeicherte Spiel ist nicht mehr verfügbar.",
    "toast.enterGameId": "Spielcode eingeben",
    "error.seatTaken": "Dieser Platz ist bereits belegt",
    "error.needHumanSeat": "Mindestens ein Mensch muss vor dem Start einen Platz nehmen",
    "error.gameOver": "Das Spiel ist vorbei",
    "error.notYourTurn": "Du bist nicht am Zug",
    "error.invalidAction": "Ungültiger Zug",
    "error.moveNoLongerLegal": "Der gewählte Zug ist nicht mehr legal. Aktualisiere und wähle erneut.",
    "error.lobbyClosed": "Diese Sitzung ist nicht mehr in der Lobby",
    "error.notStarted": "Das Spiel hat noch nicht begonnen",
    "error.hostOnly": "Nur der Host darf das tun",
    "error.unknownToken": "Unbekanntes Spieler-Token",
    "error.invalidSeat": "Der Platz muss A1, B1, A2 oder B2 sein",
    "confirm.exit": "Dieses Spiel verlassen und in eine neue Lobby wechseln?",
    "game.soundOn": "Ton an",
    "game.soundOff": "Ton aus",
    "game.skipAnimations": "Animationen immer überspringen",
    "game.playAnimations": "Animationen abspielen",
    "game.botMove": "Bot-Zug",
    "game.yourMove": "Dein Zug",
    "game.enter": "Einsetzen",
    "game.move": "Ziehen",
    "game.swap": "Tauschen",
    "game.with": "mit",
    "game.split": "Aufteilen",
    "game.yourTurn": "DU BIST DRAN",
    "game.pickCard": "Wähle eine Karte zum Spielen",
    "game.teamWins": ({ team } = {}) => `Team ${team} gewinnt`,
    "game.toMove": ({ player } = {}) => `${player} ist dran`,
    "game.over": "Spiel vorbei",
    "game.firstToPlay": ({ player, count } = {}) => `Startspieler: ${player} - ${count} Karten`,
    "game.exit": "Verlassen",
    "game.yourHand": "Deine Hand",
    "game.cardCount": ({ count } = {}) => `${count} Karten`,
    "game.noVisibleCards": "Keine sichtbaren Karten",
    "game.resolving": "Züge werden vor der nächsten Hand ausgespielt.",
    "game.clear": "Löschen",
    "game.fastForward": "Vorspulen",
    "game.playing": "Spielt...",
    "game.skip": "Passen",
    "game.discardHand": "Hand abwerfen",
    "game.play": "Spielen",
    "game.swapCard": "Karte tauschen",
    "game.cardReceived": "Karte erhalten",
    "game.receivedCard": ({ card } = {}) => `Du hast ${card} von deinem Partner erhalten.`,
    "game.newHand": "Neue Hand",
    "game.dealText": ({ count, player } = {}) => `${count} Karten ausgeteilt. ${player} beginnt.`,
    "game.you": "DU",
    "game.win": "GEWINNST",
    "game.lose": "VERLIERST",
    "game.playAgain": "Nochmal spielen",
    "selection.selectCard": "Wähle zuerst eine Karte.",
    "selection.noCard": "Kein Kartenzug verfügbar. Bestätige zum Fortfahren.",
    "selection.chooseHow": "Wähle die Spielweise",
    "selection.involvedFigures": ({ plural } = {}) => `Wähle die beteiligte${plural ? "n" : ""} Figur${plural ? "en" : ""} auf dem Brett.`,
    "selection.selectFiguresOrder": "Figuren in Zugreihenfolge wählen",
    "selection.tapFiguresOrder": "Tippe die Figuren in der Reihenfolge an, in der sie ziehen sollen.",
    "selection.splitExact": "Die Aufteilung muss genau 7 ergeben.",
    "selection.stepsRemaining": ({ count } = {}) => `${count} Schritt${count === 1 ? "" : "e"} übrig.`,
    "selection.splitReady": "Diese Aufteilung ist spielbereit.",
    "selection.routeChoice": "Route",
    "selection.routeSafe": "Zielbereich",
    "selection.routeTrack": "Auf dem Feld",
    "selection.jokerValue": "Jokerwert",
    "selection.changeJoker": "Jokerwert ändern",
    "selection.chooseJoker": "Jokerwert wählen",
    "variant.enter": "Figur einsetzen",
    "variant.jack": "Bube tauscht",
    "variant.seven": "7 aufteilen",
    "variant.swap": "Mit Partner tauschen",
    "variant.moveBackward": ({ steps } = {}) => `-${steps} ziehen`,
    "variant.moveForwardTrack": ({ steps } = {}) => `+${steps} auf der Bahn ziehen`,
    "variant.moveForward": ({ steps } = {}) => `+${steps} ziehen`,
    "rank.joker": "Joker",
    "rank.ace": "A",
    "tutorial.back": "Zurück",
    "tutorial.hand": "Deine Hand",
    "tutorial.cards": ({ count } = {}) => `${count} Karten`,
    "tutorial.backButton": "Zurück",
    "tutorial.finish": "Fertig",
    "tutorial.done": "Fertig",
    "tutorial.next": "Weiter",
    "tutorial.play": "Spielen",
    "tutorial.swapCard": "Karte tauschen",
    "tutorial.reveals": "Das Spiel zeigt nur die Auswahl, die gerade wichtig ist.",
    "tutorial.chooseDirection": "Richtung wählen",
    "tutorial.chooseJoker": "Jokerwert wählen",
    "tutorial.firstPawn": "Erste Figur",
    "tutorial.secondPawn": "Zweite Figur",
    "tutorial.split7": "Die 7 aufteilen",
    "tutorial.tapPawn": "Tippe jetzt die markierte Figur auf dem Brett an.",
    "tutorial.selectCard": "Wähle die markierte Karte, um fortzufahren.",
    "tutorial.partner": "Partner",
    "tutorial.opponent": "Gegner",
    "tutorial.you": "Du",
  },
  fr: {
    "language.label": "Langue",
    "home.subtitle.1": "Crée une table",
    "home.subtitle.2": "partage le code",
    "home.subtitle.3": "remplis les places libres avec des bots",
    "home.subtitle.4": "et joue sur téléphone ou ordinateur.",
    "home.name": "Ton nom",
    "home.namePlaceholder": "Joueur",
    "home.create": "Créer une partie",
    "home.gameIdPlaceholder": "CODE",
    "home.join": "Rejoindre",
    "home.howToPlay": "Règles",
    "home.tutorial": "Tutoriel (Beta)",
    "rules.back": "Retour",
    "rules.eyebrow": "Règles",
    "rules.title": "Comment jouer à Brandi Dog",
    "lobby.gameId": "Code",
    "lobby.leave": "Quitter",
    "lobby.start": "Lancer",
    "lobby.hostHint": "Les places libres utiliseront le bot choisi.",
    "lobby.guestHint": "En attente du lancement par l'hôte.",
    "lobby.team": ({ team } = {}) => `Équipe ${team}`,
    "lobby.bot": "Bot",
    "lobby.botOccupant": ({ bot } = {}) => `${bot} bot`,
    "lobby.yourSeat": "Ta place",
    "lobby.takeSeat": "Prendre place",
    "toast.savedGameGone": "Cette partie enregistrée n'est plus disponible.",
    "toast.enterGameId": "Entre un code de partie",
    "error.seatTaken": "Cette place est déjà prise",
    "error.needHumanSeat": "Au moins un joueur humain doit prendre une place avant de lancer",
    "error.gameOver": "La partie est terminée",
    "error.notYourTurn": "Ce n'est pas ton tour",
    "error.invalidAction": "Coup invalide",
    "error.moveNoLongerLegal": "Le coup choisi n'est plus légal. Actualise et choisis à nouveau.",
    "error.lobbyClosed": "Cette session n'est plus dans le lobby",
    "error.notStarted": "La partie n'a pas encore commencé",
    "error.hostOnly": "Seul l'hôte peut faire cela",
    "error.unknownToken": "Jeton joueur inconnu",
    "error.invalidSeat": "La place doit être A1, B1, A2 ou B2",
    "confirm.exit": "Quitter cette partie et revenir dans un nouveau salon ?",
    "game.soundOn": "Son activé",
    "game.soundOff": "Son coupé",
    "game.skipAnimations": "Toujours passer les animations",
    "game.playAnimations": "Jouer les animations",
    "game.botMove": "Coup du bot",
    "game.yourMove": "Ton coup",
    "game.enter": "Entrer",
    "game.move": "Avancer",
    "game.swap": "Échanger",
    "game.with": "avec",
    "game.split": "Partager",
    "game.yourTurn": "À TOI",
    "game.pickCard": "Choisis une carte à jouer",
    "game.teamWins": ({ team } = {}) => `L'équipe ${team} gagne`,
    "game.toMove": ({ player } = {}) => `À ${player} de jouer`,
    "game.over": "Partie terminée",
    "game.firstToPlay": ({ player, count } = {}) => `Premier à jouer : ${player} - ${count} cartes`,
    "game.exit": "Quitter",
    "game.yourHand": "Ta main",
    "game.cardCount": ({ count } = {}) => `${count} cartes`,
    "game.noVisibleCards": "Aucune carte visible",
    "game.resolving": "Les coups sont joués avant la prochaine main.",
    "game.clear": "Effacer",
    "game.fastForward": "Accélérer",
    "game.playing": "En cours...",
    "game.skip": "Passer",
    "game.discardHand": "Défausser la main",
    "game.play": "Jouer",
    "game.swapCard": "Échanger la carte",
    "game.cardReceived": "Carte reçue",
    "game.receivedCard": ({ card } = {}) => `Tu as reçu ${card} de ton partenaire.`,
    "game.newHand": "Nouvelle main",
    "game.dealText": ({ count, player } = {}) => `${count} cartes distribuées. ${player} commence.`,
    "game.you": "TU",
    "game.win": "GAGNES",
    "game.lose": "PERDS",
    "game.playAgain": "Rejouer",
    "selection.selectCard": "Choisis d'abord une carte.",
    "selection.noCard": "Aucun coup avec carte disponible. Confirme pour continuer.",
    "selection.chooseHow": "Choisis comment la jouer",
    "selection.involvedFigures": ({ plural } = {}) => `Choisis ${plural ? "les pions concernés" : "le pion concerné"} sur le plateau.`,
    "selection.selectFiguresOrder": "Choisis les pions dans l'ordre",
    "selection.tapFiguresOrder": "Tape les pions dans l'ordre où ils doivent avancer.",
    "selection.splitExact": "Le partage doit faire exactement 7.",
    "selection.stepsRemaining": ({ count } = {}) => `${count} pas restant${count === 1 ? "" : "s"}.`,
    "selection.splitReady": "Ce partage est prêt.",
    "selection.routeChoice": "Trajet",
    "selection.routeSafe": "Zone sûre",
    "selection.routeTrack": "Sur la piste",
    "selection.jokerValue": "Valeur du Joker",
    "selection.changeJoker": "Changer la valeur du Joker",
    "selection.chooseJoker": "Choisir la valeur du Joker",
    "variant.enter": "Entrer un pion",
    "variant.jack": "Échange du valet",
    "variant.seven": "Partager le 7",
    "variant.swap": "Échanger avec le partenaire",
    "variant.moveBackward": ({ steps } = {}) => `Reculer de ${steps}`,
    "variant.moveForwardTrack": ({ steps } = {}) => `Avancer de ${steps} sur la piste`,
    "variant.moveForward": ({ steps } = {}) => `Avancer de ${steps}`,
    "rank.joker": "Joker",
    "rank.ace": "A",
    "tutorial.back": "Retour",
    "tutorial.hand": "Ta main",
    "tutorial.cards": ({ count } = {}) => `${count} cartes`,
    "tutorial.backButton": "Retour",
    "tutorial.finish": "Terminer",
    "tutorial.done": "Terminé",
    "tutorial.next": "Suivant",
    "tutorial.play": "Jouer",
    "tutorial.swapCard": "Échanger la carte",
    "tutorial.reveals": "Le jeu montre seulement les choix importants à ce moment.",
    "tutorial.chooseDirection": "Choisir la direction",
    "tutorial.chooseJoker": "Choisir la valeur du joker",
    "tutorial.firstPawn": "Premier pion",
    "tutorial.secondPawn": "Deuxième pion",
    "tutorial.split7": "Partager le 7",
    "tutorial.tapPawn": "Tape maintenant le pion surligné sur le plateau.",
    "tutorial.selectCard": "Choisis la carte surlignée pour continuer.",
    "tutorial.partner": "Partenaire",
    "tutorial.opponent": "Adversaire",
    "tutorial.you": "Toi",
  },
  hr: {
    "language.label": "Jezik",
    "home.subtitle.1": "Pokreni stol",
    "home.subtitle.2": "podijeli kod igre",
    "home.subtitle.3": "popuni prazna mjesta botovima",
    "home.subtitle.4": "i igraj na mobitelu ili računalu.",
    "home.name": "Tvoje ime",
    "home.namePlaceholder": "Igrač",
    "home.create": "Stvori igru",
    "home.gameIdPlaceholder": "KOD IGRE",
    "home.join": "Pridruži se",
    "home.howToPlay": "Kako igrati",
    "home.tutorial": "Tutorial (Beta)",
    "rules.back": "Natrag",
    "rules.eyebrow": "Pravila",
    "rules.title": "Kako igrati Brandi Dog",
    "lobby.gameId": "Kod igre",
    "lobby.leave": "Izađi",
    "lobby.start": "Pokreni igru",
    "lobby.hostHint": "Prazna mjesta koristit će odabranog bota.",
    "lobby.guestHint": "Čeka se da host pokrene igru.",
    "lobby.team": ({ team } = {}) => `Tim ${team}`,
    "lobby.bot": "Bot",
    "lobby.botOccupant": ({ bot } = {}) => `${bot} bot`,
    "lobby.yourSeat": "Tvoje mjesto",
    "lobby.takeSeat": "Sjedni",
    "toast.savedGameGone": "Ta spremljena igra više nije dostupna.",
    "toast.enterGameId": "Unesi kod igre",
    "error.seatTaken": "To mjesto je već zauzeto",
    "error.needHumanSeat": "Najmanje jedan čovjek mora zauzeti mjesto prije početka",
    "error.gameOver": "Igra je završila",
    "error.notYourTurn": "Nisi na potezu",
    "error.invalidAction": "Neispravan potez",
    "error.moveNoLongerLegal": "Odabrani potez više nije legalan. Osvježi i odaberi ponovno.",
    "error.lobbyClosed": "Sesija više nije u lobbyju",
    "error.notStarted": "Igra još nije počela",
    "error.hostOnly": "Samo host to može napraviti",
    "error.unknownToken": "Nepoznat token igrača",
    "error.invalidSeat": "Mjesto mora biti A1, B1, A2 ili B2",
    "confirm.exit": "Izaći iz igre i vratiti se u novi lobby?",
    "game.soundOn": "Zvuk uključen",
    "game.soundOff": "Zvuk isključen",
    "game.skipAnimations": "Uvijek preskoči animacije",
    "game.playAnimations": "Prikaži animacije",
    "game.botMove": "Bot igra",
    "game.yourMove": "Tvoj potez",
    "game.enter": "Uđi",
    "game.move": "Pomakni",
    "game.swap": "Zamijeni",
    "game.with": "s",
    "game.split": "Podijeli",
    "game.yourTurn": "TI SI NA POTEZU",
    "game.pickCard": "Odaberi kartu za igranje",
    "game.teamWins": ({ team } = {}) => `Tim ${team} pobjeđuje`,
    "game.toMove": ({ player } = {}) => `${player} je na potezu`,
    "game.over": "Igra je završila",
    "game.firstToPlay": ({ player, count } = {}) => `Prvi igra: ${player} - ${count} karata`,
    "game.exit": "Izađi",
    "game.yourHand": "Tvoja ruka",
    "game.cardCount": ({ count } = {}) => `${count} karata`,
    "game.noVisibleCards": "Nema vidljivih karata",
    "game.resolving": "Potezi se odigravaju prije sljedeće ruke.",
    "game.clear": "Očisti",
    "game.fastForward": "Ubrzaj",
    "game.playing": "Igra se...",
    "game.skip": "Preskoči",
    "game.discardHand": "Odbaci ruku",
    "game.play": "Igraj",
    "game.swapCard": "Zamijeni kartu",
    "game.cardReceived": "Karta primljena",
    "game.receivedCard": ({ card } = {}) => `Primio si ${card} od suigrača.`,
    "game.newHand": "Nova ruka",
    "game.dealText": ({ count, player } = {}) => `Podijeljeno je ${count} karata. ${player} igra prvi.`,
    "game.you": "TI",
    "game.win": "POBJEĐUJEŠ",
    "game.lose": "GUBIŠ",
    "game.playAgain": "Igraj ponovno",
    "selection.selectCard": "Prvo odaberi kartu.",
    "selection.noCard": "Nema dostupnog poteza s kartom. Potvrdi za nastavak.",
    "selection.chooseHow": "Odaberi kako je igrati",
    "selection.involvedFigures": ({ plural } = {}) => `Odaberi uključenu figur${plural ? "e" : "u"} na ploči.`,
    "selection.selectFiguresOrder": "Odaberi figure redoslijedom pomicanja",
    "selection.tapFiguresOrder": "Dodirni figure redoslijedom kojim se trebaju pomaknuti.",
    "selection.splitExact": "Podjela mora imati točno 7.",
    "selection.stepsRemaining": ({ count } = {}) => `Preostalo koraka: ${count}.`,
    "selection.splitReady": "Ova podjela je spremna.",
    "selection.routeChoice": "Putanja",
    "selection.routeSafe": "Sigurna zona",
    "selection.routeTrack": "Po stazi",
    "selection.jokerValue": "Vrijednost jokera",
    "selection.changeJoker": "Promijeni vrijednost jokera",
    "selection.chooseJoker": "Odaberi vrijednost jokera",
    "variant.enter": "Uvedi figuru",
    "variant.jack": "Dečko zamjena",
    "variant.seven": "Podijeli 7",
    "variant.swap": "Zamijeni sa suigračem",
    "variant.moveBackward": ({ steps } = {}) => `Pomakni -${steps}`,
    "variant.moveForwardTrack": ({ steps } = {}) => `Pomakni +${steps} po stazi`,
    "variant.moveForward": ({ steps } = {}) => `Pomakni +${steps}`,
    "rank.joker": "Joker",
    "rank.ace": "A",
    "tutorial.back": "Natrag",
    "tutorial.hand": "Tvoja ruka",
    "tutorial.cards": ({ count } = {}) => `${count} karata`,
    "tutorial.backButton": "Natrag",
    "tutorial.finish": "Završi",
    "tutorial.done": "Gotovo",
    "tutorial.next": "Dalje",
    "tutorial.play": "Igraj",
    "tutorial.swapCard": "Zamijeni kartu",
    "tutorial.reveals": "Igra prikazuje samo izbore koji su trenutno bitni.",
    "tutorial.chooseDirection": "Odaberi smjer",
    "tutorial.chooseJoker": "Odaberi vrijednost jokera",
    "tutorial.firstPawn": "Prva figura",
    "tutorial.secondPawn": "Druga figura",
    "tutorial.split7": "Podijeli 7",
    "tutorial.tapPawn": "Sada dodirni označenu figuru na ploči.",
    "tutorial.selectCard": "Odaberi označenu kartu za nastavak.",
    "tutorial.partner": "Suigrač",
    "tutorial.opponent": "Protivnik",
    "tutorial.you": "Ti",
  },
};

export function detectInitialLanguage(): Language {
  const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (isLanguage(stored)) return stored;
  const browser = navigator.language.slice(0, 2).toLowerCase();
  if (isLanguage(browser)) return browser;
  return "en";
}

let currentLanguage: Language = detectInitialLanguage();

export function getLanguage() {
  return currentLanguage;
}

export function setLanguage(language: Language) {
  currentLanguage = language;
  localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
}

export function isLanguage(value: string | null): value is Language {
  return value === "en" || value === "de" || value === "fr" || value === "hr";
}

export function t(key: string, vars?: Vars): string {
  const value = dictionaries[currentLanguage][key] ?? dictionaries.en[key] ?? key;
  return typeof value === "function" ? value(vars) : value;
}

export function rulesMarkdown(): string {
  return rulesByLanguage[currentLanguage] || rulesByLanguage.en;
}

export function tutorialStepText(index: number) {
  return tutorialStepsByLanguage[currentLanguage][index] || tutorialStepsByLanguage.en[index];
}

const rulesByLanguage: Record<Language, string> = {
  en: `# Brändi Dog Game Rules

## 1. Players and Teams
- The game has 4 players.
- Players are split into 2 teams of 2.
- Teammates sit opposite each other.
- Each player controls 4 pawns.

## 2. Objective
- A team wins when all 8 pawns belonging to that team are in their safe zones.
- A player cannot finish the game using a Joker.
- A Joker may be used to bring the first 3 pawns into the safe zone, but not the 4th/final pawn.

## 3. Board Structure
- The board has a circular main track.
- Each player has a start area, an entry field, a section of the main track, and a safe zone.

## 4. Card Dealing
- Card rounds follow the 6, 5, 4, 3, 2 card cycle.
- After the normal cycle, the game continues with dice-based rounds.

## 5. Card Exchange
- Before playing a hand, each player exchanges exactly 1 card with their teammate.
- Other communication between teammates is not allowed.

## 6. Hidden Information
- Players can see the board state.
- Players cannot see other players' cards.

## 7. Movement
- Pawns move according to the played card.
- A move is legal only if the full path is legal.
- Passing over an entry field is not allowed.
- An occupied entry field blocks movement for all players.

## 8. Capturing
- Landing on an opponent pawn captures it and sends it back to start.

## 9. Card 4
- A 4 may move either +4 forward or -4 backward.

## 10. Card 7
- A 7 must use exactly 7 total steps.
- It may be split across own pawns and teammate pawns when legal.
- Pawns passed over or landed on during a 7 are captured.

## 11. Jack
- Jack swaps two pawns on the main track.
- It cannot swap pawns in start areas, safe zones, or finish fields.

## 12. Joker
- Joker copies the selected card.
- Joker inherits that card's rules.
- Joker cannot be used to finish the game.`,
  de: `# Brändi Dog Spielregeln

## 1. Spieler und Teams
- Das Spiel hat 4 Spieler.
- Es gibt 2 Teams mit je 2 Spielern.
- Partner sitzen sich gegenüber.
- Jeder Spieler kontrolliert 4 Figuren.

## 2. Ziel
- Ein Team gewinnt, wenn alle 8 Team-Figuren in den Zielfeldern sind.
- Mit einem Joker darf das Spiel nicht beendet werden.
- Ein Joker darf die ersten 3 Figuren ins Ziel bringen, aber nicht die 4. letzte Figur.

## 3. Brett
- Das Brett hat eine Hauptbahn.
- Jeder Spieler hat Startfelder, ein Einstiegsfeld, einen Bahnabschnitt und eine Zielspur.

## 4. Karten
- Die Kartenrunden folgen dem Zyklus 6, 5, 4, 3, 2 Karten.
- Danach wird die Kartenzahl per Würfel bestimmt.

## 5. Kartentausch
- Vor jeder Hand tauscht jeder Spieler genau 1 Karte mit seinem Partner.
- Weitere Kommunikation zwischen Partnern ist nicht erlaubt.

## 6. Verdeckte Information
- Alle sehen das Brett.
- Niemand sieht die Karten der anderen Spieler.

## 7. Bewegung
- Figuren ziehen nach der gespielten Karte.
- Ein Zug ist nur legal, wenn der ganze Weg legal ist.
- Über Einstiegsfelder darf nicht gezogen werden.
- Ein besetztes Einstiegsfeld blockiert alle Spieler.

## 8. Schlagen
- Wer auf einer gegnerischen Figur landet, schlägt sie zurück zum Start.

## 9. Karte 4
- Eine 4 kann +4 vorwärts oder -4 rückwärts ziehen.

## 10. Karte 7
- Eine 7 muss genau 7 Schritte verbrauchen.
- Sie darf legal auf eigene Figuren und Partnerfiguren aufgeteilt werden.
- Figuren, die während der 7 überlaufen oder erreicht werden, werden geschlagen.

## 11. Bube
- Der Bube tauscht zwei Figuren auf der Hauptbahn.
- Figuren im Start, Ziel oder auf Zielfeldern können nicht getauscht werden.

## 12. Joker
- Der Joker kopiert die gewählte Karte.
- Es gelten alle Regeln dieser Karte.
- Mit einem Joker darf das Spiel nicht beendet werden.`,
  fr: `# Règles de Brändi Dog

## 1. Joueurs et équipes
- La partie se joue à 4 joueurs.
- Les joueurs forment 2 équipes de 2.
- Les partenaires sont assis l'un en face de l'autre.
- Chaque joueur contrôle 4 pions.

## 2. But
- Une équipe gagne quand ses 8 pions sont dans les zones d'arrivée.
- Un joueur ne peut pas terminer la partie avec un Joker.
- Un Joker peut faire entrer les 3 premiers pions dans l'arrivée, mais pas le 4e pion final.

## 3. Plateau
- Le plateau possède une piste principale.
- Chaque joueur a une zone de départ, une case d'entrée, une section de piste et une zone d'arrivée.

## 4. Distribution
- Les manches suivent le cycle 6, 5, 4, 3, 2 cartes.
- Ensuite, le nombre de cartes est déterminé par le dé.

## 5. Échange de carte
- Avant de jouer une main, chaque joueur échange exactement 1 carte avec son partenaire.
- Aucune autre communication entre partenaires n'est autorisée.

## 6. Information cachée
- Tous les joueurs voient le plateau.
- Les cartes des autres joueurs restent cachées.

## 7. Mouvement
- Les pions avancent selon la carte jouée.
- Un coup est légal seulement si tout le chemin est légal.
- Il est interdit de passer par-dessus une case d'entrée.
- Une case d'entrée occupée bloque tous les joueurs.

## 8. Capture
- Arriver sur un pion adverse le capture et le renvoie au départ.

## 9. Carte 4
- Un 4 peut avancer de +4 ou reculer de -4.

## 10. Carte 7
- Un 7 doit utiliser exactement 7 pas.
- Il peut être partagé entre ses pions et ceux du partenaire si c'est légal.
- Les pions traversés ou atteints pendant un 7 sont capturés.

## 11. Valet
- Le valet échange deux pions sur la piste principale.
- Il ne peut pas échanger des pions au départ, dans l'arrivée ou sur les cases finales.

## 12. Joker
- Le Joker copie la carte choisie.
- Toutes les règles de cette carte s'appliquent.
- Un Joker ne peut pas terminer la partie.`,
  hr: `# Pravila Brändi Dog

## 1. Igrači i timovi
- Igra ima 4 igrača.
- Igrači su podijeljeni u 2 tima po 2 igrača.
- Suigrači sjede jedan nasuprot drugome.
- Svaki igrač kontrolira 4 figure.

## 2. Cilj
- Tim pobjeđuje kada je svih 8 timskih figura u sigurnim zonama.
- Igra se ne smije završiti Jokerom.
- Joker može uvesti prve 3 figure u sigurnu zonu, ali ne i 4. završnu figuru.

## 3. Ploča
- Ploča ima glavnu stazu.
- Svaki igrač ima bazu, ulazno polje, dio glavne staze i sigurnu zonu.

## 4. Dijeljenje karata
- Ruke idu ciklusom 6, 5, 4, 3, 2 karte.
- Nakon toga se broj karata određuje bacanjem kocke.

## 5. Zamjena karte
- Prije igranja ruke svaki igrač mora zamijeniti točno 1 kartu sa suigračem.
- Druga komunikacija između suigrača nije dopuštena.

## 6. Skrivene informacije
- Svi igrači vide stanje ploče.
- Karte drugih igrača nisu vidljive.

## 7. Kretanje
- Figure se kreću prema odigranoj karti.
- Potez je legalan samo ako je cijeli put legalan.
- Prelazak preko ulaznog polja nije dopušten.
- Zauzeto ulazno polje blokira kretanje za sve igrače.

## 8. Rušenje
- Ako figura stane na protivničku figuru, protivnička figura se vraća u bazu.

## 9. Karta 4
- Četvorka se može igrati kao +4 naprijed ili -4 nazad.

## 10. Karta 7
- Sedmica mora potrošiti točno 7 koraka.
- Može se podijeliti na vlastite figure i figure suigrača ako je legalno.
- Figure preko kojih se prijeđe ili na koje se stane tijekom sedmice se ruše.

## 11. Dečko
- Dečko mijenja dvije figure na glavnoj stazi.
- Ne može mijenjati figure u bazi, sigurnoj zoni ili završnim poljima.

## 12. Joker
- Joker kopira odabranu kartu.
- Vrijede sva pravila kopirane karte.
- Jokerom se ne smije završiti igra.`,
};

const tutorialStepsByLanguage: Record<Language, { title: string; body: string }[]> = {
  en: [
    { title: "The board is your map", body: "Your blue pawns start at the bottom. Move them around the track and into the blue finish lane. The lit edge shows whose turn is active." },
    { title: "Your hand drives every move", body: "Cards decide what you can do. Pick a card first, then pick the pawn or option that belongs to that card." },
    { title: "Controls appear when needed", body: "Some cards ask how you want to use them. A 4 can move forward or backward. A joker asks which card it should become." },
    { title: "Swap with your teammate", body: "At the start of a round, choose one card to pass to your teammate. Try swapping the 6." },
    { title: "Confirm the swap", body: "The button only matters after a valid choice. Press it to lock the selected card." },
    { title: "Enter a pawn with an Ace or King", body: "Select the Ace, then tap your first blue pawn in base. The entry field lights up before you commit." },
    { title: "Choose the pawn to enter", body: "Tap the highlighted blue pawn. Pawns in base do not jump over each other; entering means moving to the entry field." },
    { title: "Move on the track", body: "Select the 6, then move the pawn already on the track. The next six playable fields are previewed." },
    { title: "Preview before playing", body: "Tap the blue pawn on the track. If the path ends on another pawn, that pawn gets highlighted as a capture." },
    { title: "Fours can go backward", body: "Select the 4. Backward movement is often the fastest way to set up your finish lane later." },
    { title: "Pick the backward option", body: "Choose Move -4. The preview changes to show the backward path." },
    { title: "Jacks swap two pawns", body: "Select the Jack. Then select your pawn and the opponent pawn you want to swap with." },
    { title: "Select both swap targets", body: "Tap the blue pawn and then the green pawn. Jack swaps only pawns on the main track." },
    { title: "Complete the Jack pair", body: "Now tap the green pawn. Both selected pawns will be involved in the swap." },
    { title: "Seven is a split move", body: "Select the 7. You can divide seven steps across multiple friendly pawns, in the order you choose them." },
    { title: "Give the first pawn 3 steps", body: "Tap the first blue pawn, then choose 3. The remaining step buttons adapt to keep the total legal." },
    { title: "Finish the split with 4 steps", body: "Tap the second blue pawn and choose 4. Together, 3 plus 4 spends the full seven." },
    { title: "Jokers copy a missing card", body: "Select the Joker. In a real game you choose what it acts as, then play it like that card." },
    { title: "Choose a joker value", body: "Pick Ace. The joker can now enter a pawn or move like an Ace, depending on the board." },
    { title: "You are ready", body: "That is the core rhythm: card, option if needed, pawn or pawns, then Play. You can now jump into a real table." },
  ],
  de: [
    { title: "Das Brett ist deine Karte", body: "Deine blauen Figuren starten unten. Ziehe sie über die Bahn in die blaue Zielspur. Die leuchtende Kante zeigt, wer dran ist." },
    { title: "Deine Hand steuert jeden Zug", body: "Die Karten bestimmen deine Möglichkeiten. Wähle zuerst eine Karte, dann die passende Figur oder Option." },
    { title: "Optionen erscheinen bei Bedarf", body: "Manche Karten fragen nach der Spielweise. Eine 4 kann vorwärts oder rückwärts ziehen. Ein Joker fragt, welche Karte er wird." },
    { title: "Tausche mit deinem Partner", body: "Zu Beginn einer Runde gibst du deinem Partner eine Karte. Versuche, die 6 zu tauschen." },
    { title: "Tausch bestätigen", body: "Der Button wird erst wichtig, wenn deine Auswahl gültig ist. Drücke ihn, um die Karte zu fixieren." },
    { title: "Mit Ass oder König einsetzen", body: "Wähle das Ass und tippe dann deine erste blaue Figur im Start an. Das Einstiegsfeld leuchtet vor dem Bestätigen." },
    { title: "Figur zum Einsetzen wählen", body: "Tippe die markierte blaue Figur an. Figuren im Start überspringen sich nicht; Einsetzen bedeutet Bewegung auf das Einstiegsfeld." },
    { title: "Auf der Bahn ziehen", body: "Wähle die 6 und dann die Figur auf der Bahn. Die nächsten sechs spielbaren Felder werden angezeigt." },
    { title: "Vorschau vor dem Spielen", body: "Tippe die blaue Figur auf der Bahn an. Endet der Weg auf einer anderen Figur, wird sie als Schlagziel markiert." },
    { title: "Vieren können rückwärts", body: "Wähle die 4. Rückwärtszüge sind oft der schnellste Weg, die Zielspur vorzubereiten." },
    { title: "Rückwärtsoption wählen", body: "Wähle -4 ziehen. Die Vorschau zeigt nun den Rückwärtsweg." },
    { title: "Buben tauschen zwei Figuren", body: "Wähle den Buben. Dann wähle deine Figur und die gegnerische Figur, die du tauschen möchtest." },
    { title: "Beide Tauschziele wählen", body: "Tippe die blaue Figur und dann die grüne Figur an. Der Bube tauscht nur Figuren auf der Hauptbahn." },
    { title: "Bubenpaar abschließen", body: "Tippe jetzt die grüne Figur an. Beide gewählten Figuren werden getauscht." },
    { title: "Die Sieben ist ein Split", body: "Wähle die 7. Du kannst sieben Schritte auf mehrere befreundete Figuren in deiner Reihenfolge aufteilen." },
    { title: "Erste Figur 3 Schritte", body: "Tippe die erste blaue Figur an und wähle 3. Die übrigen Schrittbuttons passen sich an." },
    { title: "Split mit 4 Schritten beenden", body: "Tippe die zweite blaue Figur an und wähle 4. 3 plus 4 verbraucht die ganze Sieben." },
    { title: "Joker kopieren Karten", body: "Wähle den Joker. Im echten Spiel bestimmst du, welche Karte er ist, und spielst ihn dann so." },
    { title: "Jokerwert wählen", body: "Wähle Ass. Der Joker kann nun je nach Brett einsetzen oder wie ein Ass ziehen." },
    { title: "Du bist bereit", body: "Der Rhythmus ist: Karte, wenn nötig Option, Figur oder Figuren, dann Spielen. Jetzt kannst du an einen echten Tisch." },
  ],
  fr: [
    { title: "Le plateau est ta carte", body: "Tes pions bleus commencent en bas. Fais-les avancer sur la piste jusqu'à la zone d'arrivée bleue. Le bord lumineux indique qui joue." },
    { title: "Ta main guide chaque coup", body: "Les cartes décident de ce que tu peux faire. Choisis d'abord une carte, puis le pion ou l'option correspondante." },
    { title: "Les contrôles apparaissent au bon moment", body: "Certaines cartes demandent comment les utiliser. Un 4 avance ou recule. Un joker demande quelle carte il devient." },
    { title: "Échange avec ton partenaire", body: "Au début d'une manche, choisis une carte à passer à ton partenaire. Essaie d'échanger le 6." },
    { title: "Confirmer l'échange", body: "Le bouton sert après un choix valide. Appuie dessus pour verrouiller la carte sélectionnée." },
    { title: "Entrer avec un As ou un Roi", body: "Sélectionne l'As, puis tape ton premier pion bleu au départ. La case d'entrée s'allume avant la confirmation." },
    { title: "Choisir le pion à entrer", body: "Tape le pion bleu surligné. Les pions au départ ne se sautent pas; entrer signifie aller sur la case d'entrée." },
    { title: "Avancer sur la piste", body: "Sélectionne le 6, puis le pion déjà sur la piste. Les six prochaines cases jouables sont affichées." },
    { title: "Prévisualiser avant de jouer", body: "Tape le pion bleu sur la piste. Si le chemin finit sur un autre pion, il est marqué comme capture." },
    { title: "Les 4 peuvent reculer", body: "Sélectionne le 4. Reculer est souvent le chemin le plus rapide pour préparer l'arrivée." },
    { title: "Choisir l'option recul", body: "Choisis Reculer de 4. La prévisualisation montre le chemin en arrière." },
    { title: "Les valets échangent deux pions", body: "Sélectionne le Valet. Puis choisis ton pion et le pion adverse à échanger." },
    { title: "Choisir les deux cibles", body: "Tape le pion bleu puis le pion vert. Le Valet échange seulement des pions sur la piste principale." },
    { title: "Compléter la paire du Valet", body: "Tape maintenant le pion vert. Les deux pions sélectionnés seront échangés." },
    { title: "Le 7 est un coup partagé", body: "Sélectionne le 7. Tu peux diviser sept pas entre plusieurs pions alliés, dans l'ordre choisi." },
    { title: "Donner 3 pas au premier pion", body: "Tape le premier pion bleu, puis choisis 3. Les autres boutons s'adaptent pour rester légal." },
    { title: "Finir le partage avec 4 pas", body: "Tape le deuxième pion bleu et choisis 4. Ensemble, 3 plus 4 utilise tout le 7." },
    { title: "Les jokers copient une carte", body: "Sélectionne le Joker. En vraie partie, tu choisis ce qu'il devient, puis tu le joues comme cette carte." },
    { title: "Choisir une valeur de joker", body: "Choisis As. Le joker peut alors entrer un pion ou avancer comme un As selon le plateau." },
    { title: "Tu es prêt", body: "Le rythme est: carte, option si besoin, pion ou pions, puis Jouer. Tu peux rejoindre une vraie table." },
  ],
  hr: [
    { title: "Ploča je tvoja mapa", body: "Tvoje plave figure kreću s dna. Pomiči ih po stazi prema plavoj sigurnoj zoni. Osvijetljeni rub pokazuje tko je na potezu." },
    { title: "Tvoja ruka vodi svaki potez", body: "Karte određuju što možeš napraviti. Prvo odaberi kartu, zatim figuru ili opciju koja joj pripada." },
    { title: "Kontrole se pojave kad trebaju", body: "Neke karte pitaju kako ih želiš igrati. Četvorka može naprijed ili nazad. Joker pita koja karta postaje." },
    { title: "Zamijeni kartu sa suigračem", body: "Na početku runde odaberi jednu kartu koju daješ suigraču. Probaj zamijeniti 6." },
    { title: "Potvrdi zamjenu", body: "Gumb je bitan tek nakon ispravnog izbora. Pritisni ga za zaključavanje odabrane karte." },
    { title: "Uvedi figuru asom ili kraljem", body: "Odaberi asa, zatim dodirni prvu plavu figuru u bazi. Ulazno polje zasvijetli prije potvrde." },
    { title: "Odaberi figuru za ulazak", body: "Dodirni označenu plavu figuru. Figure u bazi se ne preskaču; ulazak znači pomak na ulazno polje." },
    { title: "Kretanje po stazi", body: "Odaberi 6, zatim figuru koja je već na stazi. Sljedećih šest mogućih polja bit će prikazano." },
    { title: "Pregled prije igranja", body: "Dodirni plavu figuru na stazi. Ako put završava na drugoj figuri, ta figura se označi kao rušenje." },
    { title: "Četvorke mogu unatrag", body: "Odaberi 4. Kretanje unatrag često je najbrži način za pripremu sigurne zone." },
    { title: "Odaberi opciju unatrag", body: "Odaberi pomak -4. Pregled se mijenja i pokazuje put unatrag." },
    { title: "Dečko mijenja dvije figure", body: "Odaberi dečka. Zatim odaberi svoju figuru i protivničku figuru koju želiš zamijeniti." },
    { title: "Odaberi obje mete zamjene", body: "Dodirni plavu figuru pa zelenu figuru. Dečko mijenja samo figure na glavnoj stazi." },
    { title: "Završi par za dečka", body: "Sada dodirni zelenu figuru. Obje odabrane figure sudjeluju u zamjeni." },
    { title: "Sedmica je podijeljeni potez", body: "Odaberi 7. Sedam koraka možeš podijeliti na više prijateljskih figura redoslijedom koji odabereš." },
    { title: "Prvoj figuri daj 3 koraka", body: "Dodirni prvu plavu figuru i odaberi 3. Preostali gumbi se prilagođavaju da zbroj ostane legalan." },
    { title: "Završi podjelu s 4 koraka", body: "Dodirni drugu plavu figuru i odaberi 4. Zajedno 3 plus 4 troši cijelu sedmicu." },
    { title: "Joker kopira kartu", body: "Odaberi Jokera. U pravoj igri biraš što Joker predstavlja, zatim ga igraš kao tu kartu." },
    { title: "Odaberi vrijednost jokera", body: "Odaberi Asa. Joker tada može uvesti figuru ili se kretati kao As, ovisno o ploči." },
    { title: "Spreman si", body: "Osnovni ritam je: karta, opcija ako treba, figura ili figure, pa Igraj. Sada možeš ući u pravu igru." },
  ],
};
