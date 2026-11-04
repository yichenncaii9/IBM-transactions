# Financial Crime Intelligence: Unified Data Methodology (Plan Overhaul)

This document outlines the standardized data engineering, modeling, dual-scope evaluation, and triage protocol designed to detect illicit network structures within financial transaction networks.

---

## 1. Data Partitioning & Temporal Validation Strategy

To prevent data leakage and evaluate the models under real-world conditions of concept drift and temporal evolution, the transaction ledger is partitioned chronologically without any initial row filtering.

- **Chronological Train Set (60%):** Used for initial structural feature extraction and model weight optimization.
- **Chronological Validation Set (20%):** Used for hyperparameter tuning and early stopping execution.
- **Chronological Held-Out Test Set (20%):** Preserved strictly for final performance benchmarking.

### 1.1 Stratification Constraint & Minority-Class Coverage

A temporal split cannot be stratified. Stratification shuffles rows to balance class ratios across folds, which breaks the chronological ordering the split exists to protect. Class prevalence in each fold is therefore whatever the timeline produces.

If the illicit accounts fall entirely (or almost entirely) into a single fold, the other folds cannot be trained on or evaluated meaningfully. In that case, as approved by the course professor:

- Illicit accounts are **bootstrapped or oversampled** into the deficient folds so that every fold (train, validation, test) contains illicit examples.
- Resampling is applied **after** the chronological split is fixed, so the split boundaries themselves are not altered.
- The number of resampled records per fold is logged, and the resulting positive prevalence in each fold is reported, since the test-fold prevalence sets the random-ranking baseline for Average Precision (Section 5).

---

## 2. The Unfiltered Data Mandate (Eliminating Selection Bias)

To prevent selection bias and ensure the system captures sophisticated adversaries who intentionally evade standard heuristic models, no transactions are pre-filtered out of the baseline population (preserving the full 1.2 million transaction distribution).

- **The Heuristic Transformation:** Features like fan-in cycles, loops, and scatter-gather structures are engineered as continuous or ordinal columns for every entity rather than being used to reduce the row count down to a pilot subset.
- **Data Preservation:** The full background noise of legitimate corporate hubs and high-volume commercial traffic is intentionally left in the dataset. This ensures that the models learn to distinguish true anomalies from heavy normal traffic.

---

## 3. Feature Engineering & Rule Equations

The system maps graph topology and financial activity into a structured feature matrix. Every account $u$ in the transaction graph $G = (V, E)$ receives a calculated value for each of the following metrics.

### Rule A: Fan-In / Fan-Out Ordinality Ratio

Tracks the structural profile of an account's connections to distinguish pass-through pipes from standard merchant hubs or source accounts.

- **In-Degree** $d_{in}(u)$: total number of unique accounts sending money to account $u$.
- **Out-Degree** $d_{out}(u)$: total number of unique accounts receiving money from account $u$.

$$
\text{Fan Ratio}(u) = \frac{\min\big(d_{in}(u),\, d_{out}(u)\big)}{\max\big(d_{in}(u),\, d_{out}(u)\big) + \epsilon}
$$

Where $\epsilon = 10^{-6}$ prevents division by zero. A ratio close to 1 flags a strict one-in-one-out pipe.

### Rule B: Time-Windowed Volume Flow Continuity

Aggregates directional cash flow within a localized rolling lookback window ($\Delta t = 72$ hours) to capture rapid pass-through behavior while neutralizing the masking effects of structured or split transactions.

- $V_{in}(u, \Delta t)$: sum of all incoming USD amounts to account $u$ within window $\Delta t$.
- $V_{out}(u, \Delta t)$: sum of all outgoing USD amounts from account $u$ within window $\Delta t$.

$$
\text{Continuity}(u) = 100 \times \frac{\min\big(V_{in}(u,\Delta t),\, V_{out}(u,\Delta t)\big)}{\max\big(V_{in}(u,\Delta t),\, V_{out}(u,\Delta t)\big) + \epsilon}
$$

### Rule C: Network Taint Propagation

Quantifies the exposure of an account to known high-risk or labeled illicit nodes by measuring the proportion of contaminated volume entering its ledger.

$$
\text{Taint}(u) = \frac{\sum_{e \in E_{in}(u)} \text{Volume}(e) \times \text{Taint}\big(\text{Source}(e)\big)}{\sum_{e \in E_{in}(u)} \text{Volume}(e) + \epsilon}
$$

Laundering source nodes are initialized with a baseline $\text{Taint} = 1.0$. Unlabeled source nodes begin at $0.0$.

### Rule D: Weighted Chain Score

Scores continuous multi-hop paths ($A \to B \to C$) by evaluating the alignment of transaction values across the hops, heavily penalizing massive scale disparities. For an isolated edge pair $(e_1, e_2)$:

$$
\text{Chain Score}(e_1, e_2) = 100 \times \frac{\text{Amount}(e_2)}{\text{Amount}(e_1)}
$$

Where $e_1$ is the inbound transfer and $e_2$ is the outbound transfer, bounded such that $\text{Amount}(e_2) \le \text{Amount}(e_1)$.

### Compensating Interaction Logic

Rules A to D are processed in parallel. If a launderer evades the temporal rules (weakening the Weighted Chain Score), the model can still capture the entity via a high Fan Ratio or an elevated Taint score.

---

## 4. Controlled Model Benchmarking Architecture

To determine if machine learning offers a measurable advantage over static heuristics, the performance of three independent frameworks is compared on the unfiltered evaluation data.

### Model 1: LightGBM (Hybrid ML Engine)

An ensemble tree classifier that trains on all graph features, structural indicators, and baseline profile statistics simultaneously. It leverages histogram binning to handle extreme volume disparities and discovers non-linear feature interactions (e.g., flagging an account only if both its Fan Ratio and Continuity score are elevated) without overfitting to single rules.

### Model 2: Pure Rule-Based Engine (Static Heuristic Expert System)

A rigid baseline framework evaluating deterministic rules based on strict mathematical limits. It counts the raw frequencies of structural motifs, specifically the number of:

- simple linear chains ($A \to B \to C$)
- closed loops ($A \to B \to A$)
- scatter patterns ($1 \to \text{Many}$)
- gather patterns ($\text{Many} \to 1$)

that an account participates in.

### Model 3: Uniform Random Ranking Baseline (Control Baseline)

Instead of a localized graph traversal, which can inadvertently track real transaction paths, Model 3 generates a completely un-enriched control benchmark. It assigns every account a random score drawn from a uniform distribution:

$$
\text{Score}(u) \sim \mathcal{U}(0, 1)
$$

This baseline establishes the exact random-ranking threshold. Comparing Model 1 and Model 2 against it isolates the statistical lift and predictive power gained from structural network patterns.

---

## 5. Two-Tier Evaluation & Triage Architecture

The framework balances financial crime analysis across two distinct tiers to resolve the inherent discrepancy between operational business targets and baseline data ground truths.

```
[ 1.2M Unfiltered Rows ] -> Map Weakly Connected Components (WCC) -> Complete Schemes Identified
                                              |
                 +----------------------------+----------------------------+
                 v                                                         v
 [ Tier 1: System Performance Evaluation ]             [ Tier 2: Operational Triage Delivery ]
 - Metric: Account-Level Average Precision (AP)        - Metric: Scheme-Level Decile Enrichment
 - Evaluates raw account scores across full list       - Groups accounts into unbroken schemes first
 - Measures global ranking quality, no thresholds      - Ranks and triages schemes by volume-weighted score
```

### Tier 1: System Performance Evaluation (Account Scope)

- **Objective:** Benchmark the raw predictive capacity of the models on the complete dataset.
- **Execution:** Every individual account receives a continuous risk score from the model. The entire account domain is ranked from highest to lowest score.
- **Headline Metric:** Account-Level Average Precision (AP). This evaluates the global quality of the ranking across all operating constraints without an arbitrary decision threshold. The random-ranking baseline equals the positive-account prevalence in the held-out test data (after any resampling in Section 1.1), and Model 3 should land at approximately this value.

### Tier 2: Operational Triage Delivery (Scheme Scope)

- **Objective:** Group and prioritize complete, unbroken fraudulent networks and laundering syndicates for investigation.
- **Execution:** Weakly Connected Components (WCC) or structural motifs are mapped across the full dataset first to isolate discrete networks (Schemes) before any scoring thresholds are applied.
- **Unified Scheme Scoring:** A single Scheme Risk Score is calculated for every component as the volume-weighted average of its account scores:

$$
\text{Scheme Risk Score} = \frac{\sum_{i \in \text{Scheme}} \text{Account Score}_i \times \text{Total Volume}_i}{\sum_{i \in \text{Scheme}} \text{Total Volume}_i}
$$

- **Triage Decile Partitioning:** All identified schemes are ranked by their unified risk scores and split into ten equal, ordered slices (Scheme Deciles 1 to 10). Scheme Decile 1 contains the highest-risk unbroken networks. Analysts evaluate whether the concentration of true illicit schemes rises sharply toward the top deciles, confirming the model's ability to surface complete laundering operations from topological patterns.
