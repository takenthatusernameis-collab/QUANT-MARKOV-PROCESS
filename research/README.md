# Research workspace

Use this directory for durable literature reviews, model specifications, experiments, data contracts, and result reports.

Suggested structure:

- `literature/`: sourced academic and practitioner literature reviews.
- `specifications/`: hypotheses, mathematical definitions, state construction, transition models, and preregistered experiment plans.
- `data_contracts/`: provider, timestamp, universe, validation, and provenance requirements.
- `experiments/`: immutable experiment manifests, configurations, and reproducible run instructions.
- `results/`: results, diagnostics, robustness checks, and rejected hypotheses.

Every artifact must state its status and date. Keep raw datasets out of Git; commit small manifests and reproducible retrieval instructions instead. Do not overwrite earlier experiment results when a new run changes the conclusion.
