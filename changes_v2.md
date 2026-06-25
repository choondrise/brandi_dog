# Brändi Dog Agent Development Summary

This document summarizes the main engineering and modeling work done for the Brändi Dog project, with emphasis on the heuristic agent, Monte Carlo agent, supervised/imitation learning pipeline, encoders, and reinforcement learning fine-tuning. The purpose of this document is to provide material and structure for the master thesis write-up.

## 1. Baseline Agent Development

### Random Legal Agent

The simplest baseline agent is the random legal agent. It queries the engine for all legal actions in the current state and samples uniformly from them.

This agent is useful as:

- a sanity-check baseline,
- an opponent for early experiments,
- a fallback rollout policy,
- a way to verify that game execution itself is fast when no expensive decision logic is used.

Random play is not strategically strong, but it is useful for testing correctness and measuring the overhead of the engine independently from agent logic.

## 2. Heuristic Agent

### Motivation

The original heuristic agent was created as a deterministic or semi-deterministic expert policy that can play the game without learning. Its goal is to encode human-like priorities in a fixed rule/scoring system.

The heuristic agent evaluates legal actions and gives higher priority to strategically meaningful actions such as:

- moving pawns into the safe/home zone,
- entering a pawn from base,
- capturing opponent pawns,
- improving pawn progress,
- avoiding unnecessary discards,
- coordinating with the teammate when possible.

### How It Works Conceptually

At a decision point, the heuristic agent:

1. Determines the active player and team.
2. Gets legal actions from the engine or from its reduced action-generation policy.
3. Filters or simplifies excessive action sets when needed.
4. Analyzes each action using immediate tactical features.
5. Scores/ranks the candidate actions.
6. Selects the highest-scoring action.

The heuristic agent does not perform long-term simulation. It is primarily a one-step evaluator with domain-specific priorities.

### Action Scoring Features

The heuristic scoring logic uses features such as:

- whether the action enters the safe zone,
- whether it enters from base,
- whether it captures an opponent pawn,
- how much progress the moved pawn gains,
- whether the action helps the teammate,
- whether the action wastes a strong card,
- whether the action is a discard/no-op,
- whether the action uses a special card such as Jack, Seven, or Joker.

These features allow the heuristic agent to rank moves in a way that is much stronger than random play.

### Swap Phase Handling

The heuristic agent also handles the team card-swap phase. During the swap phase, it chooses a card to give to the teammate according to fixed rules. For example, it can prefer giving useful entry cards or fall back to a low-value card when no better rule applies.

A bug was fixed where the heuristic agent attempted to analyze swap actions as if they were normal play actions. Swap actions are now handled separately.

## 3. Engine-Side Action Generation Improvements

### Problem

The engine originally generated too many equivalent legal actions, especially for:

- entering from base with Ace/King/Joker,
- Seven-card split moves.

For base entry, different base pawns are often strategically identical. If a player has multiple pawns in base and an entry card, the engine could generate one action per pawn even though those actions represent the same conceptual move.

For Seven cards, the branching factor could become extremely large. In some states, Seven generated thousands of split-move combinations, many of which were practically redundant or too expensive for search-based agents.

### Changes

The action-generation logic was reduced to avoid unnecessary branching:

- base-entry cards no longer need to distinguish equivalent base pawns,
- Seven-card generation was reduced so that the engine exposes more meaningful split actions,
- Joker generation avoids duplicating actions already covered by real cards in hand.

This was important because the main bottleneck was not always the agent scoring itself, but the number of actions being generated and evaluated.

## 4. Advanced Heuristic Agent

### Motivation

The advanced heuristic agent was introduced as a stronger, more flexible heuristic policy. It keeps the general idea of ranking available engine actions, but adds a more intentional layer for choosing good candidate moves.

Unlike the earlier heuristic agent, the advanced heuristic agent is designed to:

- use engine-generated legal moves,
- reduce the action set when it is too large,
- generate high-level intentions from the board state,
- match those intentions against actual legal actions,
- fall back to full heuristic ranking only when intention matching fails.

### Strategic Styles

The advanced heuristic agent supports configurable heuristic styles such as balanced, aggressive, or defensive. These styles change the weights assigned to different action features.

For example:

- an aggressive style values captures more highly,
- a defensive style values safe-zone entry and pawn safety more highly,
- a balanced style uses a moderate mix of progress, safety, and captures.

### Intention-Based Candidate Search

A key improvement was intention-based action selection.

Instead of always scanning every legal action, the advanced heuristic agent first asks what the board position suggests should be important. Examples:

- one pawn is close to entering safe zone,
- a pawn can be brought out of base,
- captures are available,
- a teammate pawn can be improved,
- a Seven card can perform a useful split.

The agent then searches the legal action list for actions matching the top intentions.

This helps avoid evaluating thousands of actions when only a few are strategically relevant.

### Seven Simplification

When the team controls many pawns and Seven generates too many legal actions, the advanced heuristic agent simplifies Seven handling. In large branching states, it can treat Seven more like a normal move or generate a smaller set of strategically meaningful Seven actions.

This was one of the most important speed improvements, because Seven-card branching was a major source of slowdowns.

### Fallback Tracking

Diagnostics were added to measure how often the advanced heuristic agent falls back from intention-based selection to broader/full heuristic ranking.

A high fallback rate means the intention system often fails to find matching actions and the agent must scan more actions. Lower fallback rates generally indicate faster decision-making, but too many intentions can reduce playing strength if the intentions are imperfect.

## 5. Monte Carlo Agent

### Motivation

The Monte Carlo agent was introduced to evaluate actions using short-term simulations instead of only immediate heuristic scoring.

The goal was not full MCTS. Instead, the agent performs limited-horizon Monte Carlo rollouts until the end of the current card round.

This makes it more computationally expensive than a heuristic agent, but potentially stronger because it can estimate the consequences of actions over several turns.

### Limited-Horizon Rollout Concept

At a decision point, the Monte Carlo agent:

1. Gets legal actions.
2. Reduces/ranks them using heuristic candidate selection.
3. Keeps the top `k` candidate actions.
4. For each candidate action, runs several rollouts.
5. Each rollout simulates only until the end of the current round.
6. At the end of the rollout, evaluates the resulting board state.
7. Selects the action with the best average rollout score.

The important design decision is that the rollout stops before future card deals dominate the result. This keeps the evaluation focused on the current round rather than trying to solve the entire game.

### Rollout Policies

During rollouts, future actions can be selected by different policies:

- random legal policy,
- heuristic policy,
- advanced heuristic policy.

The advanced heuristic rollout policy is stronger but slower. The random rollout policy is faster but noisier.

### Team-Based State Evaluation

At the end of each rollout, the board is scored from the active team perspective. The scoring considers:

- pawns in safe/home zones,
- progress around the board,
- pawns still in base,
- opponent progress,
- teammate progress.

This is important because Brändi Dog is a team game. The agent should not evaluate only the active player’s pawns.

### Rollouts Per Action

`rollouts_per_action` controls how many simulations are run for each candidate action.

More rollouts produce a more stable estimate but increase runtime. Fewer rollouts are faster but noisier.

The default was kept small for practical runtime, but values like 20 are conceptually stronger if compute is available.

### Parallel Rollouts

Rollout computation is independent across candidate actions and rollout indices, so it was parallelized.

The Monte Carlo agent now supports:

```python
MonteCarloAgent(..., rollout_workers=4)
```

Each rollout worker evaluates independent rollout jobs and returns scalar scores. The agent then averages them per candidate action.

The worker count is capped at 4 to avoid process explosion.

A key practical consideration is that simulation-level parallelism and Monte Carlo rollout-level parallelism multiply. For example:

```text
simulation workers * monte carlo agents * rollout workers
```

On an 8-core machine, it is safer to use either:

- simulation parallelism, or
- rollout parallelism,

but not high values for both.

## 6. Supervised / Imitation Learning Pipeline

### Motivation

The goal of the supervised learning pipeline was to train a neural action-ranking model to imitate expert decisions.

The expert policy initially came from `AdvancedHeuristicAgent`, and later from `MonteCarloAgent`.

Instead of treating action selection as simple classification over a fixed action space, the dataset is structured as a ranking problem:

```text
state + candidate actions -> choose expert action
```

This fits the game better because the legal action set changes from state to state.

### Raw Dataset Format

Each dataset sample represents one decision point, not one action row.

A sample contains:

- game id,
- turn index,
- active player,
- team,
- serialized game state,
- serialized candidate actions,
- expert action id,
- candidate action ids.

The dataset is stored as JSONL:

```text
one decision point per line
```

This format is easier to stream, merge, and build in parallel.

### Candidate Action Set

For each decision point, the dataset contains up to 21 candidate actions:

```text
1 expert action
up to 10 hard negatives
up to 10 random negatives
```

The expert action is always included.

If fewer legal actions exist, fewer candidates are stored.

For advanced heuristic datasets, hard negatives are selected using the heuristic ranking logic.

For Monte Carlo datasets, the expert label comes from Monte Carlo, but hard negatives are ranked by `AdvancedHeuristicAgent`. This is a practical compromise: Monte Carlo is expensive, while the advanced heuristic provides strong hard negatives cheaply.

### Serializer

Explicit serializers were created instead of using `str(obj)`.

The state serializer stores fields such as:

- round stage,
- deal round index,
- round starter,
- current player,
- swap cursor,
- swap selections,
- active deal size,
- hands,
- pawn positions,
- safe-entry flags,
- draw pile,
- discard pile,
- winner.

The action serializer stores structured action information such as:

- action id,
- action type,
- card id,
- card rank,
- involved pawns,
- movement steps,
- from/to positions when available,
- flags such as capture, discard, no-op, base entry, safe-zone entry,
- raw dataclass fields as fallback.

This keeps the raw dataset useful for future experiments, even if the first encoder does not use every field.

## 7. Encoders

### Why Encoding Is Needed

The raw JSONL dataset is useful for storage and debugging, but neural models need numeric feature vectors.

The encoder converts each sample into grouped ranking data:

```text
candidate_features: [num_candidates, feature_dim]
target_index: index of expert action
metadata: debugging information
```

The candidates remain grouped by decision point. They are not flattened into independent binary rows, because training uses softmax over candidate scores.

### Encoder V1

The first encoder used partial-information features, but it still contained more absolute player/team information than ideal.

It encoded things like:

- active player information,
- active player hand cards,
- pawn positions,
- card counts,
- action type,
- action flags,
- progress features.

However, models trained with V1 showed signs of seat/team bias. Performance could depend strongly on which seat/team the model played from.

### Encoder V2: Perspective-Normalized Encoder

Encoder V2 was introduced to reduce seat and team bias.

The key idea is to encode everything from the active player’s perspective.

Instead of absolute players:

```text
player 0, player 1, player 2, player 3
```

V2 uses relative roles:

```text
self
partner
opponent_1
opponent_2
```

The relative mapping is:

```text
self = active player
partner = (active player + 2) % 4
opponent_1 = (active player + 1) % 4
opponent_2 = (active player + 3) % 4
```

This makes the feature representation seat-agnostic.

### V2 State Features

V2 includes richer state features, such as:

- number of self pawns in base/track/safe,
- number of partner pawns in base/track/safe,
- number of opponent pawns in base/track/safe,
- team progress,
- opponent progress,
- pawn progress statistics,
- hand size,
- own concrete hand cards,
- partner/opponent card counts but not concrete hidden cards.

The encoder follows partial-information rules:

- it uses the active player’s concrete hand,
- it does not use concrete partner/opponent cards,
- it does not use full draw pile order.

### V2 Action Features

V2 action features include:

- card rank,
- action type,
- capture flag,
- discard/no-op flag,
- base-entry flag,
- safe-zone entry flag,
- whether the action moves self/partner/opponent pawns,
- total movement steps,
- number of pawns involved,
- progress delta,
- team progress delta,
- opponent progress delta,
- whether the action uses Joker or Seven,
- whether the action is a Seven split.

Some of these are computed by applying the action to a copied state and comparing before/after state. This gives useful consequence features such as progress delta and capture detection.

### JSONL to PT Conversion

Encoded JSONL files are converted into `.pt` files for training.

The `.pt` format stores grouped samples:

```text
candidate_features: tensor[num_candidates, feature_dim]
target_index: tensor
metadata: dict
```

Candidate lists remain variable-length. The dataset is not globally padded.

## 8. Datasets Built

Two dataset scales were built for both encoder versions:

- approximately 20k samples,
- approximately 200k samples.

Both V1 and V2 encoders were used during experimentation.

Although larger datasets can improve coverage, the 200k dataset may encourage stronger imitation of the expert distribution and can overfit to the expert policy. The 20k V2 dataset was selected for the main model because it is likely less overtrained and because V2 reduces seat/team bias.

The selected supervised model was therefore trained from:

```text
20k samples + Encoder V2
```

This model became the base deep learning/ranking model used for later reinforcement learning.

## 9. Supervised Ranking Model

### Model Architecture

The model is a small MLP scorer.

It receives one concatenated state-action feature vector and outputs one scalar score:

```text
(state, action) -> score
```

For a decision point, the model scores every candidate action. The scores are passed through a softmax, and the target is the expert action index.

Training uses cross-entropy loss over the candidate action scores.

### Why Ranking Instead of Classification

A fixed-class classifier would require a fixed action space, but Brändi Dog has a variable legal action set. The same card can generate different actions depending on board state.

A ranking model is more natural because it only compares currently legal/candidate actions.

## 10. Deep Learning Agent

The trained ranking model is used by `DeepLearningAgent`.

At runtime, the agent:

1. Gets candidate legal actions.
2. Encodes the current state and each candidate action with the selected encoder.
3. Scores each candidate using the trained MLP.
4. Chooses the highest-scoring action.

For phases not included in training, such as card swap, it falls back to heuristic behavior.

This allows the model to operate only where it was trained: the play loop.

## 11. Reinforcement Learning Agent

### Motivation

Supervised learning only teaches the model to imitate an expert. Reinforcement learning was introduced to improve the model through actual game outcomes.

The starting point was the trained V2 ranking model, not random initialization.

### RL Method Used

The reinforcement learning system uses a simple policy-gradient method, similar to REINFORCE.

The model already acts as a policy because it scores actions and softmax converts those scores into probabilities:

```text
scores -> softmax -> action probabilities
```

The RL update increases the probability of actions that lead to good returns and decreases the probability of actions that lead to bad returns.

The loss is conceptually:

```text
loss = -log_prob(action_taken) * return
```

### Why Policy Gradient

Policy gradient was chosen because:

- the model already represents a policy over legal actions,
- the action space is variable,
- it works naturally with softmax over candidate actions,
- it can fine-tune an imitation model directly,
- it does not require changing the engine,
- it is simpler than PPO or DQN.

DQN would require Q-learning machinery such as target networks, replay buffers, and bootstrapped next-state value estimates. PPO would be a stronger future method, but it requires a more complex clipped objective and usually a value function baseline.

### RL Training Details

The RL trainer supports:

- epsilon-greedy exploration,
- softmax temperature,
- entropy bonus,
- gamma discount factor,
- reward normalization,
- checkpointing,
- diagnostics such as gradient norm, entropy, selected action probability, and weight delta.

Reward shaping was added, including terms for:

- winning,
- losing,
- team progress,
- partner progress,
- opponent progress,
- safe-zone entry,
- captures,
- discards/no-ops,
- own/team pawns sent back to base.

### Exploration Parameters

Epsilon controls random exploration.

For example, epsilon can decay from 0.4 to 0.02 over 10k games using approximately:

```text
epsilon_decay = 0.9997004
```

Temperature controls how sharp or flat the policy distribution is:

- lower temperature makes the model more greedy,
- higher temperature makes it explore more among plausible actions.

Gamma controls how much future reward matters. Values around 0.95 to 0.99 are appropriate for this game.

## 12. RL Experiments and Model Selection

Several reinforcement learning versions were trained starting from the supervised V2 model.

The final selected RL agent was the one trained for approximately 10k games. It was selected because it evaluated best against itself and against previous checkpoints.

This model became the best checkpoint/champion used in later experiments.

Empirically, this RL agent performed better than the supervised Monte Carlo imitation model. The Monte Carlo imitation model beat the heuristic agent around 60% of the time, while the selected RL agent achieved about 67% against the heuristic agent. When the RL agent and Monte Carlo-imitation agent played against each other, the RL agent won around 55% of games.

This suggests that reinforcement learning improved the policy beyond pure imitation, even when the imitation expert was Monte Carlo-based.

## 13. Monte Carlo Imitation Dataset

A separate dataset was created using Monte Carlo decisions as expert labels.

This dataset contains approximately 40k Monte Carlo decision samples.

The goal was to train a model to imitate Monte Carlo search directly. However, the resulting model did not achieve strong accuracy and did not outperform the RL-trained model.

One reason may be that Monte Carlo decisions are harder to imitate from static state-action features. Monte Carlo evaluates short-term consequences through rollouts, and some of that information may not be fully captured by the encoder.

Another issue is that if negative examples are not sufficiently strong, the model may learn easier distinctions rather than the fine-grained decision boundary used by Monte Carlo.

To improve this, the dataset pipeline was adjusted so Monte Carlo remains the expert label, but hard negatives are selected using `AdvancedHeuristicAgent.rank_actions`. This gives the model stronger alternatives to compare against.

## 14. Fine-Tuning on Monte Carlo Dataset

The supervised trainer was extended so it can fine-tune from an existing checkpoint using:

```text
--initial-model-path
```

This allows the best RL checkpoint to be fine-tuned on the Monte Carlo decision dataset.

A small L2 anchor penalty was also added:

```text
--l2-anchor-weight
```

This discourages the model from moving too far from the RL checkpoint and helps reduce catastrophic forgetting.

The intended use is conservative fine-tuning:

- low learning rate,
- few epochs,
- optional L2 anchor penalty.

This should nudge the RL policy toward Monte Carlo decisions without deleting the useful behavior learned through reinforcement learning.

## 15. Self-Play / League Training

A separate self-play training script was created for league-style reinforcement learning.

The goal is to avoid training only against the latest version of the agent. Instead, the agent trains against a mixed opponent pool:

- current champion,
- older RL checkpoints,
- heuristic agent,
- ranking_model_v2 agent,
- optional Monte Carlo evaluation only.

The opponent pool uses weighted sampling. A typical mix is:

```text
50% current champion
25% older checkpoints
15% heuristic
10% ranking_model_v2
```

The training loop works in chunks:

1. Start from current champion.
2. Train for a configurable number of games.
3. Save candidate checkpoint.
4. Evaluate candidate against heuristic, ranking model, old champion, and optionally Monte Carlo.
5. Promote candidate only if it passes the gate.

The champion gate checks:

- candidate win rate against old champion,
- no major regression against heuristic.

Promoted champions are saved separately and added to the opponent pool.

This creates a league-like training process where the agent must improve against a diverse set of opponents rather than overfitting to one latest policy.

## 16. Parallelization

Several parts of the system were parallelized.

### Simulation Parallelism

`run_experiment.py` supports `--workers`, allowing multiple games to be evaluated in parallel.

This is useful because independent games do not share state.

### Dataset Parallelism

The dataset builder supports parallel workers. Each worker generates a shard, and shards are merged into one JSONL dataset.

This was used to generate larger imitation datasets efficiently.

### Monte Carlo Rollout Parallelism

Monte Carlo rollouts are independent, so they were parallelized inside `MonteCarloAgent` with `rollout_workers`.

However, rollout parallelism and simulation parallelism multiply. For example:

```text
simulation workers * Monte Carlo agents * rollout workers
```

Therefore, care is needed to avoid overloading the machine.

## 17. Main Lessons for Thesis Discussion

The project demonstrates several important ideas:

1. Reducing the action space is critical before applying search or learning.
2. Strong heuristic agents are useful both as baselines and as data generators.
3. A ranking model is more appropriate than fixed-class classification for variable legal action spaces.
4. Perspective-normalized encoding improves generalization and reduces seat/team bias.
5. Supervised imitation can produce strong agents, but it is limited by the expert and the feature representation.
6. Reinforcement learning can improve beyond imitation by optimizing actual game outcomes.
7. Monte Carlo search can be useful as an expert, but imitating it is difficult because rollout value is not always visible from static features.
8. League/self-play training is a promising next step because it reduces overfitting to a single opponent.
9. Evaluation against multiple baselines is necessary; training accuracy alone is not enough.

## 18. Suggested Thesis Structure

A possible thesis chapter structure based on this work:

1. Game rules and computational challenges of Brändi Dog.
2. Engine and legal action generation.
3. Rule-based and heuristic agents.
4. Advanced heuristic agent and action-space reduction.
5. Limited-horizon Monte Carlo search.
6. Imitation learning dataset construction.
7. State/action serialization and feature encoding.
8. Perspective-normalized V2 encoder.
9. Supervised ranking model.
10. Reinforcement learning fine-tuning.
11. Experimental evaluation.
12. Discussion of results, limitations, and future work.

## 19. Future Work

Potential future improvements include:

- implementing PPO with a value baseline,
- adding batched parallel RL rollouts,
- improving Monte Carlo hard-negative generation,
- training on larger and more diverse league data,
- adding stronger validation splits by seed and opponent type,
- improving reward shaping,
- learning from hidden-information constraints more explicitly,
- using self-play leagues for long-term policy improvement.
