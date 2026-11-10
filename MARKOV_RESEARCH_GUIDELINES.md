# Markov research guidelines — Quant Markov Process

> Project-specific research guidance. The automated Kilo workflow is repository-agnostic; it does not contain or depend on the Markov-specific rules in this file. The repository handoff and `AGENTS.md` direct research agents to consult this guide.

**Mission:** discover, specify, and rigorously test whether Markov-process models can reveal persistent predictive structure in liquid cryptocurrency markets. The result must be mathematically coherent, reproducible, point-in-time valid, and economically meaningful after realistic trading frictions.

This is a research mandate, not permission to trade, deploy, access private accounts, or use credentials. Follow `AGENTS.md` and stop when `AGENT_STOP` exists.

## 1. Research question

Can the conditional distribution of future market states and returns, given a properly defined present state, provide information that is:
- out of sample and stable across time and market regimes;
- not explained by simple trend, volatility, liquidity, or market-beta baselines;
- robust to reasonable state definitions and parameter uncertainty;
- exploitable at a practical decision frequency after fees, spread, slippage, funding, borrow, turnover, and execution constraints?

A Markov model is not an edge by itself. A high estimated transition probability, a visually persuasive regime chart, or a high in-sample Sharpe ratio is not sufficient evidence.

## 2. Initial scope and assumptions

Start with liquid cryptocurrency spot and linear perpetual instruments using free, public, exchange-available data. Record the instrument, venue, contract type, quote currency, timestamp convention, candle-closure rule, and data source for every experiment.

Explore several economically plausible horizons rather than presuming one: for example 15-minute, 1-hour, 4-hour, and 24-hour observations/holding periods. These are research candidates, not predetermined optimal settings. Study directional and cross-sectional/market-neutral formulations separately; do not combine their results or risk assumptions.

Potential observable features, subject to source quality and timestamp availability:
- returns and lagged returns at multiple horizons;
- realized volatility, range, gaps, and volatility changes;
- trend, drawdown, and distance from rolling levels;
- volume, relative volume, spread, depth, and liquidity proxies;
- funding, basis, open-interest changes, and liquidation data where genuinely public and reliable;
- order-flow or trade-imbalance features only when their sampling and historical coverage are adequate.

Use point-in-time asset universes where possible. Today's market-cap ranking must not be projected backward into historical tests. Record delistings, listings, missing instruments, and venue coverage. Do not make an apparent cross-sectional edge out of survivorship bias.

## 3. Keep model families distinct

Investigate these as separate hypotheses. Explain why each model is appropriate before coding it.

### A. Finite-state Markov chains

Define a state vector or discrete state map (S_t), then estimate transition probabilities such as

[
P_{ij}(h)=P(S_{t+h}=jmid S_t=i).
]

Test whether the chosen state is close to Markov-sufficient. State discretization must be justified and fitted using training data only. Compare a small number of interpretable binning, quantile, clustering, or economically defined state schemes. Report sparse states and transition-count uncertainty.

### B. Higher-order and state-augmented chains

Test whether conditioning only on (S_t) leaves meaningful dependence on (S_{t-1}, S_{t-2}, ldots). Compare a compact higher-order state or explicit lag augmentation against the first-order model. Control state-space growth and avoid combinatorial grids with weak sample support.

### C. Hidden Markov models and latent regimes

For latent regime (Z_t), distinguish the transition model (P(Z_tmid Z_{t-1})) from the observation/emission model (P(X_tmid Z_t)). Investigate suitable emission distributions and initialization sensitivity. Use filtered, online-available state probabilities for trading simulations; smoothed probabilities that use future observations are descriptive only and must never drive historical trades.

### D. Markov-switching time-series models

Evaluate regime-dependent mean, autoregressive, and/or volatility dynamics. Determine whether regime switching improves genuinely out-of-sample conditional forecasts over simpler fixed-parameter models. Check label switching, regime collapse, unstable transition estimates, and excessive model complexity.

### E. Semi-Markov and duration-dependent models

Test whether state duration or sojourn-time distributions matter beyond a memoryless transition model. Compare duration-aware hazard/transition specifications and assess whether duration estimates are reliable at the available sample size.

### F. Markov decision processes (MDPs)

Use the term MDP only when the research explicitly defines states, available actions, transition dynamics, and a reward/cost function. A Markov chain with a trading rule attached is not automatically a well-specified MDP. If tested, compare the learned policy to simple fixed policies and account for transaction costs, constraints, risk, and policy instability.

Also consider continuous-state Markov transition models only when they offer a defensible advantage over discrete or latent-state approaches. Do not select a sophisticated family simply because it is sophisticated.

## 4. Mathematical and empirical specification

For each hypothesis, write down before implementation:
1. the stochastic process and state definition;
2. the Markov or conditional-independence assumption being tested;
3. the sampling interval, forecast horizon, and decision timestamp;
4. the estimator, regularization/prior, initialization, and re-estimation schedule;
5. the forecast target (state probability, return distribution, volatility, tail risk, or another precisely defined quantity);
6. the mapping from forecast to an action, including a no-trade region;
7. position sizing, leverage limits, exit rules, and risk constraints;
8. the baseline, null hypothesis, and explicit failure criteria.

Do not confuse forecasting the next state with forecasting the sign or magnitude of returns. Estimate the conditional return distribution or a clearly defined payoff conditional on state transitions. Quantify calibration as well as discrimination.

## 5. Data and point-in-time contract

Before any economic backtest:
- use completed observations only; define how partial candles are excluded;
- validate monotonic timestamps, timezone, duplicates, OHLCV consistency, missing bars, gaps, outliers, and instrument continuity;
- preserve source, endpoint, retrieval time, query parameters, coverage, row counts, and content hashes/manifests;
- distinguish genuinely observed zero values from missing values;
- verify that every feature was available at the simulated decision time;
- fit normalization, imputation, feature selection, clustering, and discretization on training data only;
- do not silently switch providers or fall back to synthetic or current-only data;
- estimate availability of funding, open interest, spread, and microstructure history before promising to evaluate them.

Prefer reproducible public exchange endpoints and free datasets. If provider access fails, record the exact error and pursue independent work or an alternative public provider; do not weaken the data contract.

## 6. Validation protocol

Use chronological research splits. A preferred structure is development/training, validation/model selection, and a separately locked final holdout, with a walk-forward or rolling-origin design inside development. Specify dates and boundaries before running the experiment.

- No random row shuffling for time-series evaluation.
- Apply purging and embargo when labels, positions, or target horizons overlap.
- Use expanding or rolling re-estimation exactly as a live research process could have done.
- Never use future-fitted scalers, clusters, bins, regime labels, smoothed HMM probabilities, or revised point-in-time universes.
- Do not choose hyperparameters or state counts by repeated inspection of a final holdout.
- Do not call a run confirmatory unless the candidate, protocol, costs, and analysis plan were frozen before that evaluation and the holdout remained independent.
- If there is no valid holdout or preregistration design yet, design and document it first; leave confirmatory results `NOT_RUN`.

## 7. Baselines, costs, and metrics

At minimum, compare against relevant simple baselines:
- unconditional historical transition/return distribution;
- buy-and-hold or market exposure when directional;
- simple momentum/trend and volatility-state rules;
- a no-signal/no-trade control;
- randomized or label-shuffled negative controls where methodologically valid.

Model all material frictions for the intended venue and product: maker/taker fees, spread, realistic slippage/market impact, funding cashflows, borrow/short availability, turnover, minimum notional, precision, and delayed execution. Show gross and net performance separately. Stress costs conservatively and test capacity/liquidity sensitivity.

Report, as applicable:
- net CAGR/annualized return, volatility, Sharpe, Sortino, Calmar, and maximum drawdown;
- hit rate, payoff ratio, profit factor, tail loss, exposure, leverage, turnover, trade count, holding time, and time in market;
- long and short legs separately for market-neutral tests;
- state occupancy, transition counts, transition-matrix confidence intervals, regime duration, forecast calibration, and state stability;
- bootstrap or other dependence-aware uncertainty intervals, effective sample size, and sensitivity to market periods/assets;
- multiple-testing awareness and the total number of model/hypothesis variants tried.

A strategy is not successful because its hit rate is above 50%. The relevant question is whether its expected net payoff is positive and robust after all costs and uncertainty.

## 8. Discovery priorities

Proceed in this order unless evidence justifies a different sequence:

1. **Literature and theory.** Review primary papers and credible quantitative-finance literature on Markov chains, HMMs, regime switching, duration dependence, and financial-market applications. Extract assumptions, methods, and known failure modes.
2. **Testable research plan.** Specify a small number of hypotheses, candidate state representations, decision horizons, data feasibility, baselines, and validation gates.
3. **Data feasibility.** Audit whether free public sources actually provide the required historical data, point-in-time universe, timestamps, and coverage.
4. **Minimal reference implementation.** Build transparent estimators and unit tests only after the model and data contract are written.
5. **Forecast validation.** Test transition/return calibration and state stability before converting forecasts into trades.
6. **Economic simulation.** Add the pre-specified execution and cost model only after forecast validity is measured.
7. **Red-team and robustness.** Attempt to falsify the apparent edge across periods, assets, costs, state definitions, and negative controls.

If a Markov family is exhausted or repeatedly fails its predeclared tests, do not keep varying bins, lookbacks, or thresholds to rescue it. Record the negative result, explain the failure mechanism, and generate genuinely new model families or state representations with distinct mathematical rationales. This is a mandatory discovery behavior, not an optional final step.

## 9. Session operating protocol

Every research-agent session must:
1. read `AGENTS.md`, this prompt, and `research_state/agent_handoff.md`;
2. verify the current `main` state and review relevant prior artifacts;
3. select one bounded task with the highest expected information gain;
4. state the hypothesis or engineering objective and what evidence could falsify it;
5. implement only what is justified, with focused tests and reproducible commands;
6. save durable outputs, preserving prior results rather than overwriting them;
7. update the handoff with exact file paths, findings, sources, test outcomes, uncertainty, blockers, and one next task.

Do not repeat a failed command indefinitely. Classify failures as methodology, implementation, data/provider, permissions, or environment issues and choose a materially different next action. When claims depend on external facts, cite stable primary sources and record access dates.

## 10. Deliverables and decision gates

The project should eventually produce:
- a sourced literature review;
- a falsifiable research plan and data contract;
- tested, transparent model implementations;
- immutable experiment manifests and reproducible run instructions;
- walk-forward forecasting and economic evaluation reports;
- a red-team report with negative results and uncertainty;
- a final decision: `REJECT`, `RESEARCH_MORE`, or `CANDIDATE_FOR_INDEPENDENT_CONFIRMATION`.

The last status is not permission to trade and does not authorize access to a locked holdout. No live-trading or deployment path may be added under this mandate.

## 11. Completion and stop conditions

Stop the current research cycle when:
- the predeclared hypotheses have been evaluated and the evidence supports a decision;
- no eligible, high-value task remains;
- required external permissions/data are unavailable and no independent research task remains; or
- the method is falsified and all sensible bounded extensions have been evaluated.

At completion, write a concise final report, update the handoff, create `AGENT_STOP` with the reason, and do not start another session. If one avenue is blocked but other independent theory, methodology, or data-feasibility work remains, record the blocker and continue only with that useful work.
