# HeuristicAgent analysis

Ovaj dokument opisuje kako trenutno radi `brandi_dog/agents/heuristic_agent.py`, koje odluke donosi, po kojim pravilima rangira poteze i kako ga treba klasificirati: kao heuristicki agent, rule-based agent, ili nesto izmedu.

Dokument se odnosi na trenutno stanje koda nakon uvodenja `AgentActionGenerationPolicy` u `brandi_dog/agents/action_generation.py`.

## 1. Kratki zakljucak

`HeuristicAgent` je rule-based heuristicki agent.

Preciznije:

- On nije learning agent.
- On ne uci iz podataka.
- On ne procjenjuje vrijednost stanja pomocu naucenog modela.
- On ne pretrazuje duboko stablo igre kao minimax/MCTS agent.
- On ne optimizira eksplicitnu dugorocnu funkciju korisnosti.
- On koristi rucno definirana pravila, prioritete, tezine i pragove.

Zato je tehnicki ispravno reci da je agent rule-based.

Ali nije samo trivijalni if-else agent. On je heuristicki u smislu da:

- generira skup kandidata,
- izracunava semanticke znacajke poteza,
- rangira poteze po rucno definiranim kriterijima,
- koristi aproksimacije za vrijednost poteza,
- koristi stohasticko uzorkovanje kod sedmica,
- koristi skracivanje prostora akcija prema domeni igre.

Najbolja formulacija za diplomski rad bila bi:

> Agent je rucno projektirani rule-based heuristic agent. Ne koristi ucenje, ali koristi domenski specificne heuristike za filtriranje, evaluaciju i odabir akcija.

Drugim rijecima: da, semanticki je velikim dijelom skup if-else pravila i rucno postavljenih prioriteta, ali ta pravila implementiraju heuristicku funkciju odabira akcija. U literaturi se takav agent normalno moze opisati kao heuristicki agent ili rule-based heuristic agent.

## 2. Glavna struktura agenta

Glavna klasa je:

```python
class HeuristicAgent:
```

Konstruktor prima:

- `seed`
- `rng`
- `action_policy`

Ako se zada i `seed` i `rng`, baca se `ValueError`. Ako `rng` nije zadan, kreira se `random.Random(seed)`. To znaci da je agent deterministicki reproducibilan za isti seed, osim ako mu se eksplicitno ne proslijedi vanjski RNG.

Ako `action_policy` nije zadan, koristi se:

```python
AgentActionGenerationPolicy()
```

Trenutni default policy ima:

```python
suppress_redundant_joker_ranks=True
ignore_base_pawns_for_movement=True
seven_capture_only_when_available=True
```

To znaci da agent vec u fazi generiranja akcija smanjuje prostor razmatranja.

## 3. Glavna metoda `select_action`

Ulaz:

```python
select_action(self, engine: GameEngine, state: GameState) -> Action
```

Prvo se odreduje aktivni igrac:

- ako je faza `TEAM_SWAPS`, aktivni igrac je `active_swap_player(state)`
- inace je aktivni igrac `state.play_current`

Zatim agent razlikuje dvije velike situacije:

1. faza zamjene karata (`RoundStage.TEAM_SWAPS`)
2. faza igre (`RoundStage.PLAY_LOOP`)

U fazi zamjene agent koristi puni engine legal action generator:

```python
options = engine.legal_actions(state)
```

Zatim bira swap akciju preko `_select_swap_action(...)`.

U fazi igre agent ne koristi direktno puni `engine.legal_actions(state)`, nego:

```python
options = self._play_options_for_agent(engine, state)
filtered = self._preselect_play_options(options, state, actor, engine.cards_by_id)
return self._select_play_action(filtered, state, actor, engine.cards_by_id)
```

To je bitna arhitekturna razlika:

- `engine` zna sva legalna pravila igre
- `HeuristicAgent` generira agent-level podskup legalnih poteza
- zatim taj podskup deduplicira, filtrira i rangira

## 4. Pravila za fazu zamjene karata

Metoda:

```python
_select_swap_action(...)
```

Prvo uzima sve `SwapCardAction` akcije iz `options`.

Ako nema swap akcija, fallback je random izbor iz dostupnih opcija:

```python
return self.rng.choice(options)
```

Zatim agent gleda ruku aktivnog igraca i trazi entry karte:

```python
ENTRY_RANKS = {Rank.ACE, Rank.KING, Rank.JOKER}
```

### 4.1 Ako igrac ima vise entry karata

Ako igrac ima barem dvije entry karte, agent zeli jednu dati suigracu.

Rangiranje entry karata za davanje suigracu:

```python
ENTRY_SWAP_GIVE_PRIORITY = {
    Rank.JOKER: 1,
    Rank.KING: 2,
    Rank.ACE: 3,
}
```

Koristi se `_choose_max`, dakle vece je bolje. To znaci da ce agent preferirati dati:

1. `ACE`
2. zatim `KING`
3. zatim `JOKER`

Komentar u kodu kaze: ako vec imamo vise entry karata, jednu proslijedi teammateu.

Prakticna interpretacija:

- agent smatra da je dobro da tim ima vise mogucnosti ulaska iz baze
- ako aktivni igrac ima visak entry karata, timski je korisno dati jednu suigracu

### 4.2 Ako igrac nema entry kartu i nema figuru u igri

Agent provjerava ima li vlastitu figuru izvan baze:

```python
has_pawn_in_play = any(position != BASE for pawn in player_pawns(actor))
```

Ako nema entry karti i nema figuru u igri, onda sam trenutno ne moze napraviti mnogo korisnog. U tom slucaju agent suigracu daje najjacu non-entry kartu prema tablici:

```python
NO_ENTRY_SWAP_STRENGTH = {
    Rank.SEVEN: 11,
    Rank.FOUR: 10,
    Rank.JACK: 9,
    Rank.QUEEN: 8,
    Rank.TEN: 7,
    Rank.NINE: 6,
    Rank.EIGHT: 5,
    Rank.SIX: 4,
    Rank.FIVE: 3,
    Rank.THREE: 2,
    Rank.TWO: 1,
}
```

Ovo preferira dati suigracu sedmicu, zatim cetvorku, zatim jacka, itd.

Interpretacija:

- ako igrac ne moze uci iz baze i nema figuru na ploci, vjerojatno je korisnije da jacu kartu iskoristi suigrac
- sedmica je posebno jaka jer omogucuje split movement i capture preko prolaska

### 4.3 Default swap strategija

Ako nije niti jedan od prethodnih posebnih slucajeva, agent pokusava zadrzati jace karte, a dati slabiju.

Za to koristi:

```python
FALLBACK_KEEP_STRENGTH = {
    Rank.JOKER: 100,
    Rank.ACE: 95,
    Rank.KING: 90,
    Rank.SEVEN: 80,
    Rank.FOUR: 70,
    Rank.JACK: 60,
    Rank.QUEEN: 50,
    Rank.TEN: 45,
    Rank.NINE: 40,
    Rank.EIGHT: 35,
    Rank.SIX: 30,
    Rank.FIVE: 25,
    Rank.THREE: 20,
    Rank.TWO: 10,
}
```

Koristi se `_choose_min`, sto znaci da se za swap bira karta s najmanjom vrijednoscu u ovoj tablici. To efektivno znaci: zadrzi jake karte, daj slabiju.

## 5. Generiranje play opcija

Metoda:

```python
_play_options_for_agent(engine, state)
```

Ako stanje nije `PLAY_LOOP`, agent koristi engine legal actions.

Ako je ruka prazna, vraca:

```python
SkipTurnAction(player=player)
```

Ako ruka nije prazna:

1. racuna skup ne-joker rankova u ruci
2. za svaku kartu u ruci generira opcije preko `_card_options_for_agent(...)`
3. ako postoji barem jedna opcija, vraca ih
4. ako nema opcija, fallback je `engine.legal_actions(state)`
5. ako ni engine nema opcija, vraca `DiscardHandAction`

Ovaj fallback je vazan jer agent-level generator moze biti restriktivniji od enginea. Engine ostaje zadnja sigurnosna mreza za legalnost.

## 6. Generiranje opcija po karti

Metoda:

```python
_card_options_for_agent(...)
```

Prvo se odreduju rankovi koje karta predstavlja.

Za obicnu kartu to je samo njen stvarni rank.

Za jokera se koriste joker pravila iz policyja.

Zatim se generiraju akcije ovisno o `represented` ranku.

### 6.1 Ace

Za `Rank.ACE` agent generira:

- entry akcije iz baze
- step akcije za 1 naprijed
- step akcije za 11 naprijed

Dakle ace se tretira kao karta koja moze uvesti figuru u igru ili pomaknuti figuru 1/11 koraka naprijed.

### 6.2 King

Za `Rank.KING` agent generira:

- entry akcije iz baze
- step akcije za 13 naprijed

### 6.3 Four

Za `Rank.FOUR` agent generira:

- step akcije za 4 naprijed
- step akcije za 4 nazad

### 6.4 Seven

Za `Rank.SEVEN` agent generira sampled split-7 akcije preko:

```python
_sampled_seven_actions(...)
```

Ovo je najkompleksniji dio agenta.

### 6.5 Jack

Za `Rank.JACK` agent generira jack swap akcije preko engine helpera:

```python
engine_rules._legal_jack_actions(...)
```

### 6.6 Numeric forward ranks

Ako je rank u `NUMERIC_FORWARD_VALUES`, agent generira step akcije za odgovarajuci broj koraka naprijed.

To ukljucuje:

- 2
- 3
- 5
- 6
- 8
- 9
- 10
- Queen kao 12
- King kao 13 u mapi, iako King ima posebnu granu ranije

## 7. Joker pravila

Joker redoslijed preferiranih reprezentacija definiran je kao:

```python
JOKER_REPRESENT_ORDER = (
    Rank.ACE,
    Rank.KING,
    Rank.SEVEN,
    Rank.JACK,
    Rank.FOUR,
    Rank.QUEEN,
    Rank.TEN,
    Rank.NINE,
    Rank.EIGHT,
    Rank.SIX,
    Rank.FIVE,
    Rank.THREE,
    Rank.TWO,
)
```

U novom helper modulu postoji isti semanticki redoslijed kao `DEFAULT_JOKER_REPRESENT_ORDER`.

Aktualna metoda u agentu delegira na:

```python
represented_ranks_for_card(card.rank, non_joker_ranks_in_hand, self.action_policy)
```

Ako `suppress_redundant_joker_ranks=True`, joker ne generira rankove koje igrac vec ima kao obicne karte.

Primjer:

- ruka ima `SEVEN`
- ruka ima `JOKER`
- za jokera se ne generira `represented_rank=Rank.SEVEN`

Ako bi filtriranje uklonilo sve rankove, fallback vraca puni joker redoslijed.

Dodatno postoji i kasniji redundant-joker filter:

```python
_is_redundant_joker_action(...)
```

On odbacuje akcije u kojima joker predstavlja rank koji vec postoji u ruci kao ne-joker karta.

To znaci da agent ima dvostruku zastitu:

1. u fazi generiranja rankova
2. u fazi preselect filtriranja akcija

## 8. Movement pruning za figure u bazi

Za obicne step akcije agent koristi:

```python
_legal_step_actions_for_agent(...)
```

Ova metoda:

1. odredi ownera kojeg igrac trenutno kontrolira preko engine helpera `_controlled_owner_for_turn`
2. uzme figure preko `movement_pawns_for_owner(...)`
3. ako policy kaze `ignore_base_pawns_for_movement=True`, preskace figure koje su u `PositionKind.BASE`
4. za svaku preostalu figuru koristi engine helper `_step_path_candidates(...)`
5. ako je karta joker, provjerava safe-entry joker ogranicenje
6. kreira `PlayStepCardAction`

Ovo je vazno jer engine moze provjeravati sve figure, ali agent ne mora trositi vrijeme na figure koje se standardnim movement kartama ionako ne mogu pomaknuti iz baze.

## 9. Sedmica: osnovni princip

Sedmica se ne generira punim DFS-om kroz engine `_legal_seven_actions`. Umjesto toga, agent koristi sampled generator.

Konstante:

```python
SEVEN_OPTION_SAMPLE_LIMIT = 24
SEVEN_PLAN_BUILD_ATTEMPTS = 16
SEVEN_PRIORITY_FRACTION = 0.6
```

Znacenje:

- agent ne pokusava generirati sve moguce split-7 akcije
- generira ograniceni broj kandidata
- zadrzava prioritizirane i uzorkovane planove

To je jedan od najvaznijih razloga zasto agent nije samo legal-action enumerator, nego koristi heuristicku aproksimaciju.

## 10. Sedmica: koje figure smije micati

Metoda:

```python
_sampled_seven_actions(...)
```

Prvo odredi koji owneri su dopusteni za sedmicu:

```python
owners = engine_rules._seven_allowed_owners(state, player)
```

Zatim uzima movement figure:

```python
pawns = movement_pawns_for_owners(state, owners, self.action_policy)
```

Ako policy ignorira figure u bazi, sedmica razmatra samo figure koje su vec aktivne na ploci ili u safe zoni.

Ako nema takvih figura, vraca praznu listu.

## 11. Sedmica: capture-first shortcut

Ako je ukljuceno:

```python
seven_capture_only_when_available=True
```

agent prvo generira kandidate za pocetni segment sedmice s `remaining=7`.

Zatim filtrira:

```python
capture_openers = [candidate for candidate in initial_candidates if candidate.capture_count > 0]
```

Ako postoji barem jedan capture opener, agent ne ide u standardno sampled generiranje, nego odmah zove:

```python
_seven_actions_from_capture_openers(...)
```

To znaci da ce u toj situaciji generirati samo planove sedmice koji pocinju jedenjem protivnicke figure.

Capture openeri se rangiraju po tupleu:

1. `capture_count`
2. `safe_gain`
3. `unblocks_entry`
4. `pawn_progress`
5. `move.steps`

Za svaki opener pokusavaju se dvije varijante dovrsavanja:

- deterministicka
- stohasticka

Rezultati se dedupliciraju preko `_seven_action_key(...)`.

Ovo je izrazito rule-based odluka: ako mogu jesti sa sedmicom odmah, razmatram samo takve poteze. Ali je istovremeno heuristicka aproksimacija jer smanjuje prostor pretrage na poteze koji su takticki obecavajuci.

## 12. Sedmica: gradnja sampled plana

Postoje dvije slicne metode:

- `_build_sampled_seven_plan(...)`
- `_complete_sampled_seven_plan(...)`

Prva gradi plan od pocetka.

Druga dovrsava plan nakon sto je vec odabran capture opener.

Obje rade slicno:

1. dok `remaining > 0`
2. generiraju kandidate za trenutni segment sedmice preko `_seven_move_candidates(...)`
3. ako nema kandidata, plan nije moguc
4. ako policy dozvoljava, rezu kandidate na capture kandidate kad su dostupni
5. prioritiziraju kandidate preko `_prioritize_seven_candidates(...)`
6. biraju kandidata deterministicki ili stohasticki
7. dodaju segment u `raw_moves`
8. azuriraju simulirano stanje
9. smanjuju `remaining`
10. kada je remaining 0, vracaju `PlaySevenSplitAction`

## 13. Sedmica: kandidati segmenta

Metoda:

```python
_seven_move_candidates(...)
```

Za svaki pawn:

- ako je pawn u `BASE`, preskace se
- za svaki `step_count` od 1 do `remaining`
- za svaki path candidate iz engine helpera `_step_path_candidates(...)`
- ako je joker i safe-entry violation vrijedi, kandidat se preskace
- simulira se pomak preko engine helpera `_apply_move_path(...)`
- racunaju se znacajke kandidata:
  - `capture_count`
  - `safe_gain`
  - `unblocks_entry`
  - `pawn_progress`

Kandidat je `_SevenMoveCandidate`, koji sadrzi:

- `move`
- `path`
- `next_state`
- `safe_gain`
- `capture_count`
- `unblocks_entry`
- `pawn_progress`

Capture se detektira usporedbom stanja prije i poslije poteza:

- ako je protivnicka figura prije bila izvan baze
- a poslije je u bazi
- to se broji kao capture

## 14. Sedmica: prioritizacija kandidata

Metoda:

```python
_prioritize_seven_candidates(...)
```

Pravila su redom:

1. Ako je `force_four_capture=True` i `remaining == 7`, trazi kandidate gdje je `move.steps == 4` i `capture_count > 0`.
   - ako ih ima, vraca samo njih

2. Ako postoje potezi koji donose `safe_gain > 0`, vraca samo njih.

3. Ako postoje potezi s `capture_count > 0`, vraca samo njih.

4. Ako postoje potezi koji odblokiraju entry polje (`unblocks_entry`), vraca samo njih.

5. Inace uzima poteze koji imaju maksimalni `pawn_progress`.

Ovo je jasna leksikografska heuristika:

- prvo zavrsi ili napreduj u safe zoni
- zatim jedi protivnika
- zatim odblokiraj entry
- zatim guraj najnapredniju figuru

## 15. Sedmica: deterministicki izbor kandidata

Metoda:

```python
_choose_seven_candidate_deterministic(...)
```

Koristi `max` s tuple keyem:

1. `safe_gain`
2. `capture_count`
3. `unblocks_entry`
4. bonus ako je `remaining == 7`, `steps == 4`, i postoji capture
5. `pawn_progress`
6. `move.steps`

To znaci da deterministicki izbor kod sedmice preferira:

- veci safe gain
- vise capturea
- odblokiranje entryja
- posebnu 4+3 capture ideju
- veci progres figure
- dulji segment

## 16. Sedmica: stohasticki izbor kandidata

Metoda:

```python
_choose_seven_candidate_weighted(...)
```

Racuna tezine preko `_seven_candidate_weight(...)`.

Tezina pocinje od 1.0, zatim se dodaje:

- `safe_gain * 8.0`
- `capture_count * 6.0`
- `4.0` ako potez odblokira entry
- `3.0` ako je pocetni 4-step capture
- `pawn_progress / 25.0`
- `move.steps / 8.0`

Zatim se radi weighted random izbor.

Ovo znaci da agent nije potpuno deterministicki u svim situacijama. Ali stohastika je i dalje vodena rucno zadanim tezinama.

## 17. Preselect faza za play opcije

Nakon sto se generiraju opcije, agent ih filtrira u:

```python
_preselect_play_options(...)
```

Ova faza radi tri stvari:

1. odbacuje redundantne joker akcije
2. deduplicira semanticki iste akcije
3. dodatno ogranicava broj sedmica ako ih ima previse

### 17.1 Redundantni joker

Ako akcija dolazi od jokera i joker predstavlja rank koji igrac vec ima kao obicnu kartu, akcija se odbacuje.

To se odnosi na:

- `PlayEnterAction`
- `PlayStepCardAction`
- `PlaySevenSplitAction`
- `PlayJackSwapAction`

### 17.2 Semanticka deduplikacija

Za svaku akciju racuna se semantic key.

Primjeri:

- enter akcija: player, stvarni rank karte, represented rank, pawn
- step akcija: player, stvarni rank, represented rank, pawn, steps, direction, prefer_safe_entry
- jack akcija: player, stvarni rank, represented rank, source, target
- seven akcija: player, stvarni rank, represented rank, sekvenca moveova

Ako dvije akcije imaju isti key, zadrzava se ona s manjim `card_id`.

To je deterministicki tie-breaker.

### 17.3 Sampling viska sedmica

Ako broj `PlaySevenSplitAction` opcija prelazi `SEVEN_OPTION_SAMPLE_LIMIT`, agent:

- odvaja non-seven akcije
- samplea sedmice preko `_sample_seven_options(...)`
- vraca non-seven + sampled seven

## 18. Sampling sedmica u preselect fazi

Metoda:

```python
_sample_seven_options(...)
```

Ako ima manje sedmica od limita, vraca sve.

Ako ima previse, radi sljedece:

1. formira priority pool od sedmica koje imaju barem jedan hint:
   - safe hint
   - capture hint
   - unblock-entry hint

2. odredi koliko priority poteza zeli uzeti:

```python
priority_target = min(len(priority_pool), int(limit * SEVEN_PRIORITY_FRACTION))
```

3. dodaje anchor akcije:
   - split 4+3 ako postoji
   - furthest-progress akciju

4. weighted samplea iz priority poola

5. ako jos nije popunjen limit, weighted samplea iz ostatka

Ovdje se ponovno vidi heuristicki karakter: agent ne pretrazuje sve, nego cuva reprezentativan i takticki relevantan subset.

## 19. Feature analiza poteza

Metoda:

```python
_analyze_action(...)
```

Za svaku akciju agent simulira sljedece stanje:

```python
next_state = self._apply_action_unchecked(state, action, cards_by_id)
```

Zatim racuna `_ActionFeatures`:

- `safe_progress`
- `deepest_safe_index`
- `capture_count`
- `seven_capture`
- `entry_priority`
- `furthest_progress`
- `starts_new_circle`

### 19.1 Safe progress

Za svaku prijateljsku figuru gleda se pozicija prije i poslije poteza.

Ako figura zavrsi u safe zoni:

- ako prije nije bila u safe zoni, dobiva se `after.index + 1`
- ako je vec bila u safe zoni i ide dublje, dobiva se razlika indeksa

`deepest_safe_index` pamti najdublju safe poziciju dosegnutu potezom.

### 19.2 Capture count

Za sve neprijateljske figure:

- ako je prije bila izvan baze
- a poslije je u bazi
- broji se kao capture

### 19.3 Moved friendly pawns i furthest progress

Agent odredi koje prijateljske figure su pomaknute akcijom.

Zatim racuna najveci `_pawn_progress(...)` medu njima.

### 19.4 Entry priority

Ako je akcija `PlayEnterAction`:

- stvarni `ACE` ili `KING` dobiva `entry_priority = 2`
- stvarni `JOKER` dobiva `entry_priority = 1`
- ostalo je 0

To znaci da agent vise cijeni ulazak stvarnom entry kartom nego ulazak jokerom.

### 19.5 Seven capture

Ako je akcija `PlaySevenSplitAction` i ima capture, `seven_capture=True`.

### 19.6 Starts new circle

`starts_new_circle` pokusava kazniti poteze gdje figura koja vec moze uci u safe zonu nastavlja oko kruga umjesto da ude.

Za `PlayStepCardAction` provjerava:

- potez je forward
- pawn ima `pawn_safe_entry_ready`
- simulirani path prelazi vlastiti entry od iza
- zavrsava opet na tracku

Za `PlaySevenSplitAction` vraca true ako neki move ima:

- `prefer_safe_entry=False`
- pawn je safe-entry-ready

Interpretacija: agent ne voli poteze koji zapocinju novi krug umjesto da iskoriste ulaz u safe zonu.

## 20. Glavni odabir play akcije

Metoda:

```python
_select_play_action(...)
```

Za svaku opciju racuna featuree.

Zatim bira u strogoj hijerarhiji:

1. safe candidates
2. capture candidates
3. entry candidates
4. move candidates
5. fallback svi featurei

### 20.1 Ako postoji safe progress

Ako barem jedna akcija ima `safe_progress > 0`, agent bira samo medu njima.

Rangiranje:

1. `deepest_safe_index`
2. `safe_progress`
3. ne zapocinje novi krug
4. `capture_count`
5. `entry_priority`
6. `furthest_progress`
7. manji `card_id`

Zakljucak: ulazak ili napredak u safe zoni je najvisi prioritet.

### 20.2 Ako nema safe progressa, ali postoji capture

Ako barem jedna akcija ima `capture_count > 0`, agent bira medu capture akcijama.

Rangiranje:

1. `capture_count`
2. `seven_capture`
3. ne zapocinje novi krug
4. `furthest_progress`
5. `entry_priority`
6. manji `card_id`

Zakljucak: ako ne moze napredovati u safe zonu, agent preferira jesti protivnicke figure.

### 20.3 Ako nema capturea, ali postoji entry

Ako postoji `PlayEnterAction`, agent bira medu entry akcijama.

Rangiranje:

1. `entry_priority`
2. ne zapocinje novi krug
3. `furthest_progress`
4. manji `card_id`

Zakljucak: uvodenje figure u igru je prioritet nakon safe progressa i capturea.

### 20.4 Ako postoje movement akcije

Ako postoje `PlayStepCardAction`, `PlaySevenSplitAction` ili `PlayJackSwapAction`, agent bira medu njima.

Rangiranje:

1. ne zapocinje novi krug
2. `furthest_progress`
3. `capture_count`
4. `entry_priority`
5. manji `card_id`

Zakljucak: bez taktickih dobitaka, agent gura najnapredniju korisnu figuru i izbjegava novi krug.

### 20.5 Fallback

Ako nista od gore navedenog ne vrijedi, agent bira medu svim featureima slicnim kriterijem:

1. ne zapocinje novi krug
2. `furthest_progress`
3. `capture_count`
4. `entry_priority`
5. manji `card_id`

## 21. Tie-breaking i randomizacija

Metode:

- `_choose_feature(...)`
- `_choose_max(...)`
- `_choose_min(...)`

Sve rade slicno:

1. nadu najbolju vrijednost prema key funkciji
2. nadu sve kandidate koji imaju tu vrijednost
3. izaberu jednog pomocu `self.rng.choice(best)`

To znaci da agent nije potpuno deterministicki ako postoji vise jednako rangiranih poteza. Ali randomizacija se koristi samo za razbijanje izjednacenja ili weighted sampling, ne za osnovnu strategiju.

## 22. Pawn progress metrika

Metoda:

```python
_pawn_progress(state, pawn)
```

Vraca:

- `-1` za figure u bazi
- `1000 + index` za figure u safe zoni
- udaljenost od entry indexa za figure na tracku
- dodatnih `MAIN_TRACK_LENGTH` ako je figura `pawn_safe_entry_ready`

Interpretacija:

- safe zone je jako vrijedna jer dobiva vrijednosti iznad 1000
- track progress je kruzna udaljenost od vlastitog entryja
- ako je figura spremna za ulaz u safe zonu, smatra se naprednijom

Ovo je rucno definirana aproksimacija napretka figure.

## 23. Kako agent koristi engine

Agent koristi engine na tri nacina:

1. U swap fazi koristi `engine.legal_actions(state)`.

2. U play fazi koristi engine helper funkcije iz `engine.rules`, uglavnom privatne funkcije:
   - `_legal_entry_actions`
   - `_legal_jack_actions`
   - `_step_path_candidates`
   - `_apply_move_path`
   - `_apply_play_*`

3. Za konacnu primjenu akcije u simulaciji van agenta i dalje se koristi `engine.step(...)`.

Vazno: agent generira akcije koje bi trebale biti legalne, ali engine je i dalje zadnja validacija kada se akcija primijeni.

Arhitekturna napomena:

Agent trenutno ovisi o privatnim helperima iz `engine.rules` koji pocinju s `_`. To je prakticno, ali nije idealno kao javni API. Za diplomski se moze opisati kao pragmaticna odluka za izbjegavanje dupliciranja pravila, ali dugorocno bi se moglo izdvojiti javni API za agent-level generiranje akcija.

## 24. Sto agent ne radi

Agent ne radi sljedece:

- ne uci iz odigranih partija
- nema parametre koji se treniraju
- nema neuralnu mrezu
- nema tablicu vrijednosti
- nema reinforcement learning
- nema minimax pretragu
- nema Monte Carlo Tree Search
- ne procjenjuje protivnikove buduce poteze
- ne racuna vjerojatnosti karata u protivnickim rukama
- ne optimizira dugorocni expected value
- ne koristi dubinsku simulaciju vise poteza unaprijed, osim lokalne simulacije jedne akcije radi racunanja featurea

Zbog toga ga ne treba predstavljati kao AI agent u smislu ucenja ili planiranja. On je deterministicki/stohasticki rule-based evaluator akcija.

## 25. Je li ovo heuristika ili rule-based agent?

Odgovor: oboje, ali na razlicitim razinama opisa.

### 25.1 Zasto je rule-based

Agent je rule-based jer su sva njegova ponasanja zadana rucno:

- koje karte se smatraju jakima
- koje karte se daju suigracu
- kada se joker smatra redundantnim
- kada se preskacu figure u bazi
- kada se sedmica reze na capture poteze
- koji featurei imaju prednost
- kojim redoslijedom se usporeduju featurei
- koje tezine se koriste za weighted sampling

Sve su to eksplicitna pravila zapisana u kodu.

Glavna logika je zaista sastavljena od if-else odluka i tuple rankinga.

### 25.2 Zasto je ipak heuristicki

Agent je heuristicki jer ta pravila nisu samo tvrda pravila legalnosti igre. Ona su aproksimacije strategije.

Primjeri heuristika:

- safe progress je vazniji od capturea
- capture je vazniji od entryja
- entry je vazniji od obicnog pomaka
- stvarni Ace/King za entry je bolji od jokera
- sedmica koja jede protivnika je vrlo vrijedna
- kretanje u safe zonu je bolje od zapocinjanja novog kruga
- najnaprednija figura je cesto dobar kandidat za pomicanje
- ako postoji capture sa sedmicom, razmatraj samo capture-first sedmice

Ta pravila nisu matematski dokazana kao optimalna. Ona su domenski utemeljene procjene sto je vjerojatno dobro u igri. To je tocno ono sto se u praksi naziva heuristikom.

### 25.3 Najpreciznija klasifikacija

Najpreciznije:

> `HeuristicAgent` je rule-based heuristic agent s rucno dizajniranom evaluacijom akcija i agent-level pruningom prostora legalnih poteza.

Ako treba krace:

> To je heuristicki agent, ali ne learning-based. Njegova heuristika je implementirana kroz eksplicitna rule-based if-else pravila, featuree i prioritete.

Ako treba kriticki:

> Naziv `HeuristicAgent` je opravdan ako se heuristika shvati kao rucno zadana strategijska aproksimacija. Nije opravdan ako se pod heuristikom ocekuje naucena ili optimirana evaluacijska funkcija. U ovom kodu nema ucenja; inteligencija agenta dolazi iz rucno kodiranog domenskog znanja.

## 26. Kako ovo formulirati u diplomskom radu

Predlozena formulacija:

> Heuristicki agent implementiran u radu pripada skupini rule-based agenata. Agent ne koristi strojno ucenje, nego rucno definirane domenske heuristike za generiranje, filtriranje i rangiranje legalnih poteza. Svaki kandidat se lokalno simulira, nakon cega se racunaju znacajke poput napretka prema sigurnoj zoni, broja pojedenih protivnickih figura, mogucnosti ulaska iz baze i napretka najudaljenije figure. Akcije se zatim biraju leksikografskim prioritetima i, u slucaju izjednacenja ili uzorkovanja sedmice, kontroliranom stohastikom. Ovakav pristup ne garantira optimalnost, ali znatno smanjuje prostor pretrage i enkodira osnovne strategijske principe igre.

Jos kraca formulacija:

> Agent je rule-based heuristicki agent: sva pravila odabira poteza definirana su rucno, ali pravila predstavljaju domenske heuristike, a ne samo provjeru legalnosti poteza.

## 27. Prednosti trenutnog pristupa

Prednosti:

- jednostavan za razumjeti i objasniti
- deterministicki reproducibilan uz seed
- ne zahtijeva skup podataka za treniranje
- lako se dodaju nova pravila
- lako se debugira pojedinacna odluka
- engine ostaje izvor legalnosti
- agent moze biti dobar baseline za usporedbu s buducim agentima
- performanse su bolje nego kod punog generiranja svih sedmica

## 28. Nedostaci trenutnog pristupa

Nedostaci:

- pravila su rucno podesena i subjektivna
- nema garancije optimalnosti
- ne uci iz pogresaka
- ne adaptira se protivniku
- ne planira vise poteza unaprijed
- moze propustiti dobar potez ako ga pruning izbaci
- jako ovisi o kvaliteti rucno dizajniranih prioriteta
- koristi privatne engine helper funkcije
- kompleksnost raste kako se dodaje jos if-else pravila

## 29. Sto bi ga ucinilo manje rule-based agentom

Ako bi se kasnije htjelo razviti napredniji agent, moguci smjerovi su:

1. Evaluacijska funkcija s podesivim tezinama.
   - npr. score = w1 * safe_progress + w2 * captures + w3 * entry + ...
   - tezine se mogu optimirati grid searchom ili self-playem

2. Monte Carlo evaluacija poteza.
   - za svaki kandidat odigrati nekoliko rollouta
   - odabrati potez s najboljim prosjecnim rezultatom

3. MCTS agent.
   - koristiti engine za simulacije
   - balansirati exploration/exploitation

4. Reinforcement learning agent.
   - uciti politiku ili vrijednosnu funkciju iz self-playa

5. Supervised learning iz ljudskih partija ili jakog agenta.

Trenutni `HeuristicAgent` moze posluziti kao baseline ili kao rollout policy za MCTS.

## 30. Sažetak pravila u jednoj listi

Agent u grubo radi ovako:

1. Ako je swap faza:
   - ako ima visak entry karata, jednu daje suigracu
   - ako nema entry i nema figuru u igri, daje suigracu najjacu non-entry kartu
   - inace daje najslabiju kartu prema keep-strength tablici

2. Ako je play faza:
   - generira agent-level skup akcija po kartama u ruci
   - joker ne duplicira rankove koje igrac vec ima
   - movement ne razmatra figure u bazi
   - sedmica se generira sampled pristupom
   - ako sedmica moze odmah jesti, generira samo capture-first planove
   - redundantne joker akcije se odbacuju
   - semanticki iste akcije se dedupliciraju
   - previse sedmica se uzorkuje prema hintovima

3. Za svaku akciju racuna:
   - napredak u safe zoni
   - koliko duboko ulazi u safe zonu
   - broj capturea
   - je li capture napravljen sedmicom
   - prioritet entryja
   - napredak pomaknute figure
   - zapocinje li nepotrebno novi krug

4. Odabir poteza:
   - prvo safe progress
   - zatim capture
   - zatim entry
   - zatim obicni movement
   - zatim fallback

5. Tie-break:
   - koristi rucno definirane tuple prioritete
   - ako vise poteza ima isti score, bira se random izmedu najboljih preko seeded RNG-a

## 31. Konacna ocjena naziva `HeuristicAgent`

Naziv `HeuristicAgent` je prihvatljiv, ali bi u tekstu diplomskog trebalo biti jasno objasnjeno sto se pod time misli.

Preporuka:

- ne predstavljati ga kao autonomnog inteligentnog agenta koji uci
- ne predstavljati ga kao optimalnog strategijskog igraca
- predstaviti ga kao rule-based heuristic baseline

Najtocnija recenica:

> `HeuristicAgent` koristi rucno dizajnirane domenske heuristike, implementirane kao skup pravila, prioriteta i feature-based rangiranja akcija; zbog toga je istovremeno rule-based agent i heuristicki agent, ali nije learning-based agent.
