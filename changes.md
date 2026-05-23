# Changes from this session

Ovaj dokument biljezi promjene napravljene tijekom ove sesije kako bi se kasnije moglo lakse rekonstruirati odluke, motivaciju i implementacijske detalje za potrebe diplomskog rada.

## 1. Dodan novi simulacijski paket

Prvo je uveden novi paket za simulacije, bez mijenjanja postojeceg paketa `engine`.

Pocetno su dodane datoteke:

- `simulations/__init__.py`
- `simulations/config.py`
- `simulations/metrics.py`
- `simulations/runner.py`

U `config.py` je definirana osnovna konfiguracija eksperimenta kao dataclass:

- `experiment_name`
- `num_games`
- `seed`
- `agents_by_player`
- `output_path`

Cilj je bio odvojiti konfiguraciju simulacijskih eksperimenata od samog rule enginea. Paket `engine` je ostao odgovoran samo za pravila igre, generiranje legalnih poteza i primjenu poteza.

## 2. Implementirano pokretanje jedne automatske partije

U `simulations/runner.py` je implementirana funkcija `run_single_game(config)`.

Za inicijalizaciju partije koristen je isti obrazac kao u postojecim skriptama projekta, posebno u `brandi_dog/simulate_heuristic_vs_random.py`:

- kreira se `GameEngine(seed=config.seed)`
- pocetno stanje dobiva se pozivom `engine.reset()`
- igra se vrti dok `state.round_stage != RoundStage.GAME_OVER`
- aktivni igrac se odreduje pomocu:
  - `active_swap_player(state)` tijekom `RoundStage.TEAM_SWAPS`
  - `state.play_current` tijekom play loopa
- agent se dohaca iz `config.agents_by_player`
- agent se poziva preko `agent.select_action(engine, state)`
- potez se primjenjuje pomocu `engine.step(state, action)`
- broji se broj poteza

Rezultat jedne partije je pocetno bio `SingleGameResult`, s pobjednickim timom i brojem poteza.

## 3. Dodano prikupljanje metrika za jednu partiju

Runner je zatim nadograden tako da za jednu partiju skuplja sljedece metrike:

- `game_length`
- `winner`
- `captures`
- `discard_or_noop_actions`

Uveden je dataclass `GameResult`.

Capture se detektira usporedbom `pawn_positions` prije i poslije poteza:

- za svaku protivnicku figuru gleda se pozicija prije i poslije poteza
- ako je figura prije poteza bila izvan `PositionKind.BASE`, a nakon poteza je u `PositionKind.BASE`, to se broji kao capture

Discard/no-op akcije se detektiraju preko postojecih tipova akcija iz `engine.actions`:

- `DiscardHandAction`
- `SkipTurnAction`

Ovo je napravljeno bez mijenjanja `engine` paketa.

## 4. Implementirano pokretanje vise partija i agregacija rezultata

Dodana je funkcija `run_experiment(config)` koja pokrece vise partija prema `config.num_games`.

Za ponovljivost simulacija po partiji se koristi deterministicki seed:

```python
game_seed = config.seed + game_index
```

To znaci da je eksperiment reproducibilan za isti `config.seed`, a svaka partija ipak dobiva razlicit seed.

Dodane su agregirane metrike:

- `team_0_win_rate`
- `team_1_win_rate`
- `average_game_length`
- `captures_per_game`
- `discard_or_noop_actions_per_game`

U `metrics.py` su uvedeni:

- `GameResult`
- `ExperimentResult`
- `aggregate_game_results(...)`

Rezultati se spremaju u JSON. JSON sadrzi:

- agregirane rezultate eksperimenta pod kljucem `"experiment"`
- rezultate pojedinacnih partija pod kljucem `"games"`

## 5. Dodan primjer pokretanja eksperimenata

Dodan je primjer pokretanja u `simulations/run_experiment.py`.

Primjer CLI-ja koristi `RandomLegalAgent` za sva cetiri igraca i prima argumente:

- `--games`
- `--seed`
- `--output`

Primjer pokretanja:

```bash
python -m simulations.run_experiment --games 10 --seed 1 --output simulation_results.json
```

Kasnije je put promijenjen jer je paket premjesten unutar `brandi_dog`.

## 6. Premjesten simulacijski paket u `brandi_dog/`

Na zahtjev je top-level paket `simulations` premjesten u:

- `brandi_dog/simulations/__init__.py`
- `brandi_dog/simulations/config.py`
- `brandi_dog/simulations/metrics.py`
- `brandi_dog/simulations/runner.py`
- `brandi_dog/simulations/run_experiment.py`

Nakon premjestanja, import putanja postala je:

```python
from brandi_dog.simulations.runner import run_experiment
```

Primjer pokretanja postao je:

```bash
python -m brandi_dog.simulations.run_experiment --games 10 --seed 1 --output simulation_results.json
```

Provjereno je da novi import radi preko smoke testa:

```python
from brandi_dog.simulations.runner import run_experiment
from brandi_dog.simulations.run_experiment import build_default_config
```

## 7. Rasprava o problemu performansi heuristickog agenta

Kasnije je identificiran problem da se `brandi_dog/simulate_heuristic_vs_random.py` za 10 igara vrti predugo.

Glavni uzroci koji su razmatrani:

1. Joker generira opcije koje su redundantne ako igrac vec ima standardnu kartu istog ranga.
   - Posebno je problem kada igrac ima kartu `7` i jokera.
   - Tada joker dodatno generira `represented_rank=Rank.SEVEN`, iako igrac vec ima stvarnu sedmicu.
   - To povecava broj mogucnosti i branch factor.

2. Sedmica ima velik branch factor.
   - Split-7 akcije mogu se razlagati na mnogo sekvenci segmenta.
   - Ako se jos ukljuci joker kao sedmica, broj opcija dodatno raste.

3. Agent-level generator nije trebao razmatrati pomicanje figura koje su jos u `BASE`.
   - Za obicne movement karte nema smisla gledati figure u bazi.
   - `engine` to moze legalno provjeriti i odbaciti, ali za heuristickog agenta je to nepotreban trosak.

Dogovoreno je da se `engine` ne dira, jer:

- `engine` treba ostati izvor istine za pravila igre
- `RandomLegalAgent` treba nastaviti koristiti puni `engine.legal_actions(state)`
- optimizacije se trebaju odnositi samo na specificne agente, posebno `HeuristicAgent` i buduce agente koji ce dijeliti slicne politike generiranja poteza

## 8. Dodan agent-level modul za generiranje i filtriranje akcija

Dodan je novi modul:

- `brandi_dog/agents/action_generation.py`

U njemu je uveden:

```python
@dataclass(frozen=True)
class AgentActionGenerationPolicy:
    suppress_redundant_joker_ranks: bool = True
    ignore_base_pawns_for_movement: bool = True
    seven_capture_only_when_available: bool = True
```

Ovaj policy definira ponasanje agent-level generatora:

- `suppress_redundant_joker_ranks`
  - ako igrac vec ima standardnu kartu nekog ranga, joker za specificnog agenta ne mora generirati taj isti rang
  - primjer: ako igrac ima `7`, joker ne generira sedmicu

- `ignore_base_pawns_for_movement`
  - movement akcije ne iteriraju po figurama koje su u `BASE`
  - to vrijedi za agent-level generator, ne za engine

- `seven_capture_only_when_available`
  - kod gradnje split-7 poteza, ako u trenutnom koraku postoji capture kandidat, zadrzavaju se samo capture kandidati
  - cilj je smanjiti branching i naglasiti heuristicku preferenciju jedenja protivnickih figura

Dodani helperi:

- `represented_ranks_for_card(...)`
- `movement_pawns_for_owner(...)`
- `movement_pawns_for_owners(...)`
- `prune_to_capture_candidates_when_available(...)`

Modul je dizajniran tako da ga mogu koristiti i buduci agenti, ne samo `HeuristicAgent`.

## 9. Nadograden `HeuristicAgent`

Datoteka:

- `brandi_dog/agents/heuristic_agent.py`

dobila je podrsku za `AgentActionGenerationPolicy`.

Konstruktor sada prima opcionalni argument:

```python
action_policy: Optional[AgentActionGenerationPolicy] = None
```

Ako se policy ne proslijedi, koristi se default:

```python
AgentActionGenerationPolicy()
```

Time se zadrzava kompatibilnost s postojecim koristenjem:

```python
HeuristicAgent(seed=...)
```

## 10. Joker rank pruning u heuristickom agentu

Postojeca metoda `_represented_ranks_for_card(...)` prebacena je na novi helper `represented_ranks_for_card(...)`.

Prakticni efekt:

- ako karta nije joker, vraca se samo njen stvarni rank
- ako je karta joker i `suppress_redundant_joker_ranks=True`, joker ne predstavlja rankove koje igrac vec ima kao ne-joker karte u ruci
- ako bi filtriranje uklonilo sve rankove, fallback i dalje vraca puni redoslijed mogucih joker rankova

Ovo je vazno za situaciju:

- igrac ima `7`
- igrac ima `JOKER`
- heuristicki agent vise ne generira dodatne joker-as-seven opcije koje dupliciraju stvarnu sedmicu

`RandomLegalAgent` nije promijenjen i dalje dobiva sve legalne joker mogucnosti iz enginea.

## 11. Movement pruning za figure u `BASE`

Za heuristickog agenta uveden je novi helper:

```python
_legal_step_actions_for_agent(...)
```

Umjesto da se za step akcije zove direktno `engine_rules._legal_step_actions(...)`, heuristicki agent sada koristi agent-level generator koji:

- odredi kontroliranog vlasnika preko `engine_rules._controlled_owner_for_turn(...)`
- uzme samo figure koje su relevantne za movement preko `movement_pawns_for_owner(...)`
- ako je policy aktivan, preskace figure u `PositionKind.BASE`
- i dalje koristi engine helper `_step_path_candidates(...)`
- i dalje postuje joker safe-entry ogranicenje preko `_joker_last_pawn_safe_entry_violation(...)`
- i dalje proizvodi iste tipove akcija (`PlayStepCardAction`)

Ovo smanjuje nepotrebnu iteraciju nad figurama koje ne mogu biti pomicane standardnim movement kartama.

## 12. Sedmica: aktivne figure i capture pruning

Kod generiranja sampled sedmica u `HeuristicAgent` promijenjeno je:

- lista figura za sedmicu sada se gradi preko `movement_pawns_for_owners(...)`
- ako je ukljucen `ignore_base_pawns_for_movement`, figure u `BASE` se ne koriste kao kandidati za split-7 movement
- u `_seven_move_candidates(...)` dodatno postoji zastita koja preskace figuru ako je trenutno u `BASE`

Dodano je capture pruning ponasanje:

- za svaki trenutni korak sedmice generiraju se kandidati
- ako postoji barem jedan kandidat s `capture_count > 0`, lista se reze samo na capture kandidate
- ako capture kandidat ne postoji, zadrzavaju se svi kandidati

To je implementirano preko:

```python
prune_to_capture_candidates_when_available(candidates, self.action_policy)
```

Ovo se primjenjuje tijekom dovrsavanja split-7 plana.

## 13. Sedmica: capture-first shortcut

Dodan je dodatni brzi put za slucaj kada na pocetku sedmice postoji capture.

U `_sampled_seven_actions(...)` se prvo generiraju pocetni kandidati za sedmicu s `remaining=7`.

Ako postoje `capture_openers`, agent odmah ulazi u:

```python
_seven_actions_from_capture_openers(...)
```

To znaci:

- ne generira se standardni set od mnogo sampled planova
- uzimaju se samo planovi koji pocinju capture segmentom
- capture openeri se rangiraju po:
  - `capture_count`
  - `safe_gain`
  - `unblocks_entry`
  - `pawn_progress`
  - `move.steps`
- svaki capture opener se pokusava dovrsiti deterministicki i stohasticki
- rezultati se dedupliciraju preko postojeceg `_seven_action_key(...)`

Cilj ove promjene je smanjiti najskuplji dio heuristickog generiranja poteza kada je sedmica takticki ocita zbog mogucnosti capturea.

## 14. Smanjeni heuristicki sampling limiti za sedmicu

U `HeuristicAgent` su smanjene konstante:

```python
SEVEN_OPTION_SAMPLE_LIMIT = 24
SEVEN_PLAN_BUILD_ATTEMPTS = 16
```

Prije su vrijednosti bile:

```python
SEVEN_OPTION_SAMPLE_LIMIT = 96
SEVEN_PLAN_BUILD_ATTEMPTS = 64
```

Ovo je agent-level aproksimacija i ne mijenja legalnost poteza u engineu.

Motivacija:

- heuristika ne mora analizirati sve moguce split-7 planove
- vec ima prioritizaciju prema safe progressu, captureu, unblockingu i progresu figura
- manji sample daje znatno manji runtime

## 15. Export policyja iz `brandi_dog.agents`

U `brandi_dog/agents/__init__.py` je dodan export:

```python
from .action_generation import AgentActionGenerationPolicy
```

`__all__` sada ukljucuje:

```python
["AgentActionGenerationPolicy", "HeuristicAgent", "RandomLegalAgent"]
```

Time buduci agenti mogu uvoziti policy jednostavno:

```python
from brandi_dog.agents import AgentActionGenerationPolicy
```

## 16. Sto nije mijenjano

Tijekom ovih promjena namjerno nije mijenjan `engine` paket.

Nisu mijenjani:

- `brandi_dog/engine/actions.py`
- `brandi_dog/engine/board.py`
- `brandi_dog/engine/cards.py`
- `brandi_dog/engine/dealing.py`
- `brandi_dog/engine/engine.py`
- `brandi_dog/engine/rules.py`
- `brandi_dog/engine/state.py`

Napomena: radno stablo je vec sadrzavalo neke postojece lokalne izmjene i `__pycache__` promjene u `engine` prije ovog dijela rada. U ovoj sesiji za opisane optimizacije nije diran `engine`.

Takoder nije mijenjan `RandomLegalAgent`.

`RandomLegalAgent` i dalje radi po starom principu:

```python
legal = engine.legal_actions(state)
return self.rng.choice(legal)
```

## 17. Provjere koje su pokretane

Pokretane su sintaksne provjere:

```bash
python -m py_compile brandi_dog/agents/action_generation.py brandi_dog/agents/heuristic_agent.py brandi_dog/agents/random_legal_agent.py
```

Nakon exporta policyja:

```bash
python -m py_compile brandi_dog/agents/__init__.py brandi_dog/agents/action_generation.py brandi_dog/agents/heuristic_agent.py brandi_dog/agents/random_legal_agent.py
```

Pokrenut je import smoke test:

```python
from brandi_dog.agents import AgentActionGenerationPolicy, HeuristicAgent, RandomLegalAgent
```

Pokrenuti su ciljani testovi:

```bash
pytest tests/test_heuristic_agent.py tests/test_decision_actions_and_safe_entry.py
```

Rezultat:

```text
11 passed
```

Pokrenut je i kratki runtime smoke test simulacije:

```bash
/usr/bin/time -f 'elapsed=%e' python -m brandi_dog.simulate_heuristic_vs_random --games 1 --seed 1 --max-turns 200
```

Nakon optimizacija test je zavrsio bez greske.

Zabiljezeno vrijeme:

```text
elapsed=14.38
```

Rezultat te kratke capped igre bio je:

```text
Game 1: 3-3
Totals
Team A safe pawns total: 3
Team B safe pawns total: 3
```

Prije dodatnog capture-first shortcuta i smanjenja sampling limita, slican smoke test s capom 200 trajao je dulje od 25 sekundi i zavrsio s rezultatom `2-2`.

## 18. Trenutno stanje i posljedice dizajna

Sadasnja arhitektura ima jasnu podjelu:

- `engine` ostaje izvor istine za legalnost poteza
- `RandomLegalAgent` koristi puni legalni prostor akcija
- `HeuristicAgent` koristi policy-pruned podskup legalnih akcija
- buduci agenti mogu koristiti isti policy/helper modul i po potrebi ukljucivati ili iskljucivati pojedine rezove

Vazna posljedica:

Heuristicki agent vise ne razmatra sve legalne poteze. On razmatra namjerno ogranicen podskup legalnih poteza, radi performansi i radi modeliranja heuristickog ponasanja.

To je prihvatljivo jer:

- `engine.step(...)` i dalje validira akciju prije primjene
- pravila igre nisu premjestena iz enginea u agenta
- agent samo bira sto ce uopce razmatrati

## 19. Moguci sljedeci koraci

Moguci nastavci:

1. Dodati mjerne logove za broj generiranih opcija po potezu.
   - posebno broj `PlaySevenSplitAction` opcija
   - posebno broj joker opcija

2. Dodati benchmark za `simulate_heuristic_vs_random.py`.
   - npr. vrijeme za 1, 5 i 10 igara
   - usporedba prije/poslije pruning politika

3. Dodati konfigurabilne sampling limite u `AgentActionGenerationPolicy`.
   - trenutno su `SEVEN_OPTION_SAMPLE_LIMIT` i `SEVEN_PLAN_BUILD_ATTEMPTS` konstante u `HeuristicAgent`
   - moglo bi se prebaciti u policy ako buduci agenti trebaju drugacije vrijednosti

4. Dodati jos jedan agent koji koristi isti `AgentActionGenerationPolicy`, ali drugaciju evaluaciju akcija.

5. Razmotriti zasebne testove za:
   - joker ne generira rank koji vec postoji u ruci
   - movement generator ne ukljucuje BASE figure
   - sedmica s dostupnim captureom generira samo capture-first planove

