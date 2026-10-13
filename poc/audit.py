"""Independent FX-rate audit and known-scheme checks after validate.py."""
import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from validate import COLS, DTYPES, pattern_analysis, patterns


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('poc/results'))
    args = parser.parse_args()
    out = args.output
    findings = {}
    for name in ['HI-Medium', 'LI-Medium']:
        rates = []
        cols = ['timestamp', 'paid', 'received', 'payment_currency', 'receiving_currency']
        for i, df in enumerate(pd.read_csv(args.data_dir / f'{name}_Trans.csv', names=COLS,
                                           header=0, usecols=cols, dtype=DTYPES, chunksize=1000000), 1):
            # Exclude cent-scale transactions where rounding dominates implied rates.
            df = df[(df.payment_currency != df.receiving_currency) & (df.paid >= 1000) & (df.received >= 1000)].copy()
            df['date'] = df.timestamp.str[:10]
            df['rate'] = df.received / df.paid
            rates.append(df)
            if i % 10 == 0:
                print(f'{name}: rate audit {i} million rows', flush=True)
        rates = pd.concat(rates, ignore_index=True)
        daily = rates.groupby(['date', 'payment_currency', 'receiving_currency']).rate.agg(['size', 'median', 'min', 'max']).reset_index()
        daily.to_csv(out / f'{name}_large_fx_daily.csv', index=False)
        daily['within_day_relative_range'] = (daily['max'] - daily['min']) / daily['median']
        per_pair = daily.groupby(['payment_currency', 'receiving_currency']).agg(
            days=('date', 'nunique'), low=('median', 'min'), high=('median', 'max'),
            median_rate=('median', 'median'), transactions=('size', 'sum')).reset_index()
        per_pair['daily_relative_range'] = (per_pair.high - per_pair.low) / per_pair.median_rate
        per_pair.to_csv(out / f'{name}_large_fx_pair_variation.csv', index=False)
        stable = per_pair[per_pair.days >= 10]
        findings[name] = {'large_conversions': len(rates), 'pairs_with_at_least_10_days': len(stable),
                          'median_daily_relative_range': float(stable.daily_relative_range.median()),
                          'max_daily_relative_range': float(stable.daily_relative_range.max())}
    groups = patterns(args.data_dir / 'HI-Medium_Patterns.txt')
    metrics, _ = pattern_analysis(groups)
    pd.DataFrame(metrics).to_csv(out / 'HI-Medium_pattern_metrics.csv', index=False)
    summary_path = out / 'HI-Medium_summary.json'
    summary = json.loads(summary_path.read_text())
    summary['multicurrency_patterns'] = sum(m['currencies'] > 1 for m in metrics)
    summary['patterns_with_currency_switch'] = sum(m['currency_switch_edges'] > 0 for m in metrics)
    summary_path.write_text(json.dumps(summary, indent=2))
    positives = pd.read_csv(out / 'HI-Medium_laundering.csv', dtype=DTYPES)

    def canonical(row):
        return tuple(str(v) if j not in [5, 7, 10] else float(v) for j, v in enumerate(row))

    actual = Counter(canonical(row) for row in positives.itertuples(index=False, name=None))
    expected = Counter(canonical(e) for g in groups for e in g['edges'])
    present = sum((actual & expected).values())
    visibility = []
    for i, (group, m) in enumerate(zip(groups, metrics)):
        banks = {e[1] for e in group['edges']} | {e[3] for e in group['edges']}
        local_max = 0
        any_bank_complete = False
        for bank in banks:
            local = {'edges': [e for e in group['edges'] if bank in (e[1], e[3])], 'type': group['type']}
            lm, _ = pattern_analysis([local])
            local_max = max(local_max, lm[0]['max_temporal_hops'])
            any_bank_complete |= len(local['edges']) == len(group['edges'])
        visibility.append({'scheme': i, 'type': group['type'], 'banks': len(banks),
                           'shared_hops': m['max_temporal_hops'], 'best_local_hops': local_max,
                           'any_bank_sees_all_edges': any_bank_complete})
    vis = pd.DataFrame(visibility)
    vis.to_csv(out / 'HI-Medium_bank_visibility.csv', index=False)
    # Verify whether anonymous labelled-edge chaining creates branching ambiguity.
    ambiguity = {}
    for name in ['HI-Medium', 'LI-Medium']:
        p = pd.read_csv(out / f'{name}_laundering.csv', dtype=DTYPES)
        p['row_id'] = np.arange(len(p))
        incoming = p[['row_id', 'to_bank', 'to_account', 'timestamp']].rename(columns={
            'to_bank': 'bank', 'to_account': 'account', 'timestamp': 'arrival'})
        outgoing = p[['from_bank', 'from_account', 'timestamp']].rename(columns={
            'from_bank': 'bank', 'from_account': 'account', 'timestamp': 'departure'})
        links = incoming.merge(outgoing, on=['bank', 'account'])
        delta = (pd.to_datetime(links.departure) - pd.to_datetime(links.arrival)).dt.total_seconds() / 3600
        links = links[(delta > 0) & (delta <= 48)]
        counts = links.groupby('row_id').size()
        ambiguity[name] = {'arrivals_with_candidate_successors': len(counts),
                           'arrivals_with_multiple_candidates': int((counts > 1).sum()),
                           'max_candidate_successors': int(counts.max())}
    findings['known_pattern_validation'] = {'schemes': len(groups), 'expected_pattern_edges': sum(expected.values()),
                                            'edges_matched_in_full_csv': present,
                                            'multicurrency_schemes': summary['multicurrency_patterns'],
                                            'schemes_with_temporal_currency_switch': summary['patterns_with_currency_switch'],
                                            'schemes_without_complete_single_bank_visibility': int((~vis.any_bank_sees_all_edges).sum()),
                                            'schemes_with_more_hops_visible_globally': int((vis.shared_hops > vis.best_local_hops).sum())}
    findings['link_ambiguity'] = ambiguity
    # Compare robust daily medians with the already fetched ECB previous-day join.
    ecb = pd.read_csv(out / 'ecb_comparison.csv')
    comparisons = []
    for name in ['HI-Medium', 'LI-Medium']:
        d = pd.read_csv(out / f'{name}_large_fx_daily.csv')
        reference = ecb[ecb.dataset == name][['date', 'payment_currency', 'receiving_currency', 'ecb_rate']].drop_duplicates()
        d = d.merge(reference, on=['date', 'payment_currency', 'receiving_currency'])
        d['relative_deviation'] = d['median'] / d.ecb_rate - 1
        d['dataset'] = name
        comparisons.append(d)
        covered = d[d.ecb_rate.notna()]
        findings[name]['ecb_covered_large_conversions'] = int(covered['size'].sum())
        findings[name]['median_absolute_ecb_deviation'] = float(covered.relative_deviation.abs().median())
        findings[name]['daily_pair_groups_over_5pct_deviation'] = int((covered.relative_deviation.abs() > .05).sum())
        findings[name]['ecb_covered_daily_pair_groups'] = len(covered)
    pd.concat(comparisons).to_csv(out / 'robust_ecb_comparison.csv', index=False)
    (out / 'audit_summary.json').write_text(json.dumps(findings, indent=2))
    print(json.dumps(findings, indent=2), flush=True)


if __name__ == '__main__':
    main()
