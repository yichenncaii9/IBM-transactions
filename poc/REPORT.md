# Preliminary proof of concept: HI/LI Medium

## Verdict

The proposed historical FX volatility X-factor fails its feasibility check on these files. Both datasets contain hundreds of thousands of currency-conversion transactions, but none are labelled as laundering. Their implied exchange rates are effectively constant across dates, and differ materially from actual historical ECB rates. An external rates join runs successfully, but that does not establish a valid market-behaviour analysis.

A temporal network analysis works as an exploratory computation. A better supported X-factor is measuring what a bank misses when it sees only its own transactions, including currency changes between successive transfers. The HI pattern annotations provide independent scheme membership for checking this claim. This is evidence of visibility differences, not an evaluated laundering detector or proof of recoverable funds.

## Actual files tested

- `/Applications/MAMP/htdocs/y3s1/IS459/HI-Medium_Trans.csv`
- `/Applications/MAMP/htdocs/y3s1/IS459/LI-Medium_Trans.csv`
- `/Applications/MAMP/htdocs/y3s1/IS459/HI-Medium_Patterns.txt`

Both complete CSV files were scanned twice using streaming pandas chunks. The second scan independently audited rates after excluding small amounts. LI's companion pattern file was not present; scheme-level validation below applies to HI only. No AWS deployment or cloud performance test was performed.

| Measure | HI Medium | LI Medium |
| --- | ---: | ---: |
| Transactions | 31,898,238 | 31,251,483 |
| Laundering-labelled transactions | 35,230 | 16,041 |
| Overall laundering rate | 0.110445% | 0.051329% |
| Payment currency differs from receiving currency | 485,144 | 467,879 |
| Laundering-labelled conversions | **0** | **0** |
| Same-currency laundering rate | 0.112151% | 0.052109% |
| Observed timestamp range | Sep 1–28, 2022 | Sep 1–27, 2022 |
| Nonpositive paid or received amounts | 0 | 0 |

The paper's approximate 16-day duration does not capture the tails in the actual files supplied. Use observed timestamps for partitioning and censoring. There are 15 currencies. Bank and account IDs were read as strings to preserve leading zeroes; the duplicate `Account` headers were renamed by position.

## FX X-factor: actual test

Definition: a conversion has `payment_currency != receiving_currency`; implied rate is `amount_received / amount_paid`, in receiving-currency units per payment-currency unit.

1. Count all conversions and their labels across the full files. Result: zero positive labels in both conversion subsets, so a conversion-pair laundering heatmap contains no positive off-diagonal cells. The same-currency diagonal remains meaningful descriptively.
2. Audit variation using conversions with both paid and received amounts at least 1,000 in their respective native units. This is a rounding diagnostic, not a common-currency value threshold. It retains 248,578 HI and 234,127 LI conversions.
3. For each pair, calculate daily median implied rates. Restrict variation comparisons to pairs observed on at least ten dates: 100 HI pairs and 97 LI pairs.
4. Fetch the official ECB historical reference archive and join dates/currency codes. Use the previous published business-day observation to avoid assigning an end-of-day reference rate to an earlier transaction. Reference rates remain a benchmark, not executable quotes.

| Diagnostic | HI Medium | LI Medium |
| --- | ---: | ---: |
| Median relative range of daily pair medians | 0.0000474% | 0.0000377% |
| Maximum relative range among pairs observed ≥10 days | 0.000449% | 0.000802% |
| Large conversions with an ECB benchmark | 226,495 | 215,045 |
| Median absolute deviation from ECB, across covered daily pair groups | 8.848% | 8.807% |
| Covered daily pair groups deviating by >5% | 1,107 / 1,550 | 1,026 / 1,430 |

The near-zero daily variation supports fixed synthetic rates rather than market-following rates. The ECB comparison is unweighted across pair/date groups. Bitcoin and Saudi Riyal are outside this reference archive; RUB has no contemporary rate because ECB suspended publication in March 2022. Rates coverage must remain explicit.

**Decision:** do not interpret synthetic-vs-ECB deviations as suspicious pricing, transaction profit/loss, or evidence that criminals exploit volatile markets. USD conversion using ECB data can illustrate external valuation, but it cannot validate the original volatility hypothesis. Avoid summing hop amounts as recovered money: repeated transfers double-count value, and mixed currencies require an explicit valuation convention.

## Q1: path tracing and endpoints

The HI pattern file contains 2,756 annotated attempts and 22,743 transaction occurrences. Every annotated occurrence matches a laundering-labelled transaction in the full HI CSV, with bank/account IDs, timestamps, amounts, currencies, format, and label matched together. Pattern annotations cover about 64.6% of HI's positive transactions; the remaining positives are outside this scheme-validation subset.

Temporal paths require strictly increasing timestamps and account identity `(bank, account)`. Events with the same minute timestamp are processed as a batch; their order is unresolved. A dynamic-programming traversal finds up to 13 strictly chronological hops in the annotated attempts.

Of 367 attempts annotated `CYCLE`, 339 form a directly verifiable closed chain when all their edges are sorted chronologically. The other 28 do not pass that exact check. Keep annotation and temporal reconstruction separate; do not silently force timestamp order to match a pattern label.

For acyclic scheme endpoints, the test identifies receiving nodes with no outgoing edge **inside that annotated scheme**. There are 8,918 endpoint instances across schemes. **4,533 (50.83%) have a later outgoing transaction elsewhere in the full HI dataset.** Consequently, scheme termination cannot establish final cash-out or funds retention.

Example candidate endpoint-bank ranking, by distinct annotated schemes:

| Synthetic bank ID | Schemes ending there | Distinct endpoint accounts |
| --- | ---: | ---: |
| `000` | 90 | 89 |
| `011` | 80 | 89 |
| `020` | 79 | 85 |
| `012` | 77 | 84 |
| `003` | 59 | 63 |

These are candidate scheme destinations, not identified real institutions or confirmed cash-out banks. Counts can overlap because one scheme can have several endpoints. Cycles have no graph sink and must be shown as returning paths.

The labelled-edge linkage test connects an incoming edge to later outgoing edges from the same account within 48 hours:

| Measure | HI Medium | LI Medium |
| --- | ---: | ---: |
| Candidate links | 11,710 | 1,343 |
| Links with a currency change between hops | 3,885 | 523 |
| Arrivals with candidate successors | 6,766 | 833 |
| Arrivals with multiple candidate successors | 1,982 | 99 |
| Maximum candidate successors for one arrival | 183 | 118 |

This proves the mechanics run on both datasets, while exposing ambiguity. Labelled edges provide retrospective evidence; they are not sufficient to establish that one specific incoming dollar funded a particular outgoing transfer. An endpoint needs a defined follow-up horizon and a censoring flag near the end of observation. A finite look-ahead or hop cap is a truncated search, not proof of final cash-out.

## Revised X-factor: bank visibility and currency changes between hops

For each known HI attempt, compare the full scheme graph with the edges visible to each participating bank. A bank sees an edge when it is the sending or receiving bank. This assumes visibility of both sides of transactions involving that bank; it is a simulation of restricted information.

- 1,452 / 2,756 attempts (52.69%) contain multiple currencies.
- 1,039 / 2,756 attempts (37.70%) contain at least one strictly chronological adjacent currency switch.
- 1,170 / 2,756 attempts (42.45%) cannot be completely seen by any single participating bank.
- 458 / 2,756 attempts (16.62%) have a longer observable temporal path in the shared view than in even the best single-bank view.

Concrete example: annotated scheme index 1 is a 12-hop cycle across 12 banks and four currencies, with eight changes between successive hop currencies. Every individual transaction has matching payment/receiving currencies. The shared graph reveals all 12 chronological hops; the best individual bank sees only a two-hop path. Its currency sequence is Yuan → USD → EUR → Yuan → EUR → EUR → Yuan → USD → USD → USD → EUR → JPY.

This supports an interactive dashboard with a bank selector, a local/shared visibility toggle, temporal path highlights, currency-switch markers, and a missing-hop count. It directly extends Q1 and tests the value of collaboration. It does not yet show a detection-rate improvement: that requires controls, a scoring rule that does not use labels as inputs, and evaluation on held-out data.

Suggested revised Q2: **Which currency changes between connected transfers are associated with laundering chains, and how much of those chains does a single bank miss?** The current PoC establishes occurrence and visibility; comparison against legitimate matched chains is still required to claim higher risk. LI confirms candidate currency-switch links, but LI scheme membership cannot be validated without its pattern file.

## Reproduce and inspect

Run from the repository root, with the official archive downloaded to the path supplied below:

```sh
python3 poc/validate.py --data-dir /Applications/MAMP/htdocs/y3s1/IS459 --ecb /private/tmp/ibm-aml-ecb-fx.zip
python3 poc/audit.py --data-dir /Applications/MAMP/htdocs/y3s1/IS459
```

Tested dependencies: pandas 2.3.3, numpy 2.4.1, scipy 1.17.1. Results are under `poc/results/`. `audit_summary.json` and the two dataset summary JSON files contain the headline metrics. Pair tables, daily rates, reference comparisons, pattern metrics, endpoint records, and bank visibility tables provide auditable detail. The audit also refreshes independently computed pattern metrics. Handcrafted assertions verified strict timestamp ordering and currency-switch detection, including unresolved same-minute transfers.

The PoC confirms local computation and data feasibility. Distributed Glue performance, Athena queries, and dashboard delivery have not been tested. For deployment, use one shared cleaned Parquet table partitioned by dataset and date, and bounded temporal expansion; a full unrestricted all-path enumeration would grow rapidly.

## Sources

- [IBM AML dataset description](https://github.com/IBM/AML-Data/blob/main/README.md)
- [IBM research paper](https://arxiv.org/abs/2306.16424)
- [ECB reference rates and publication limitations](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)
- [Official ECB historical reference-rate archive used by the test](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip)
