"""Streaming proof of concept; never loads the full transaction files into memory."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

COLS = ['timestamp', 'from_bank', 'from_account', 'to_bank', 'to_account',
        'received', 'receiving_currency', 'paid', 'payment_currency', 'format', 'label']
DTYPES = {c: 'str' for c in COLS}
DTYPES.update(received='float64', paid='float64', label='int8')


def patterns(path):
    groups = []
    if not path.exists():
        return groups
    current = None
    for line in path.read_text().splitlines():
        if line.startswith('BEGIN'):
            current = {'type': line.split(' - ')[1].split(':')[0], 'edges': []}
        elif line.startswith('END'):
            groups.append(current)
            current = None
        elif current and line.strip():
            current['edges'].append(next(csv.reader([line])))
    return groups


def pattern_analysis(groups):
    summaries, endpoints = [], set()
    for i, group in enumerate(groups):
        edges = sorted(group['edges'], key=lambda e: e[0])
        senders = {(e[1], e[2]) for e in edges}
        receivers = {(e[3], e[4]) for e in edges}
        sinks = receivers - senders
        # Strict temporal DP; equal-minute events are processed as a batch.
        best = {}
        incoming_currencies = defaultdict(set)
        switches = 0
        grouped = defaultdict(list)
        for e in edges:
            grouped[e[0]].append(e)
        max_hops = 0
        for ts, batch in sorted(grouped.items()):
            updates = []
            for e in batch:
                src, dst = (e[1], e[2]), (e[3], e[4])
                hops = best.get(src, 0) + 1
                max_hops = max(max_hops, hops)
                updates.append((dst, hops, e[6]))
                if incoming_currencies[src] and any(c != e[8] for c in incoming_currencies[src]):
                    switches += 1
            for dst, hops, currency in updates:
                best[dst] = max(best.get(dst, 0), hops)
                incoming_currencies[dst].add(currency)
        for bank, account in sinks:
            endpoints.add((bank, account))
        summaries.append({'scheme': i, 'type': group['type'], 'edges': len(edges),
                          'max_temporal_hops': max_hops, 'sinks': len(sinks),
                          'currency_switch_edges': switches,
                          'currencies': len({e[8] for e in edges} | {e[6] for e in edges})})
    return summaries, endpoints


def scan(path, output, groups, chunk_size):
    name = path.stem.split('_')[0]
    ps, endpoints = pattern_analysis(groups)
    endpoint_accounts = {a for _, a in endpoints}
    last_outgoing = {}
    totals = Counter()
    currency = Counter()
    agg = []
    positive = []
    daily = []
    start, end = None, None
    for n, df in enumerate(pd.read_csv(path, names=COLS, header=0, dtype=DTYPES,
                                      chunksize=chunk_size), 1):
        date = df.timestamp.str[:10]
        conversion = df.payment_currency != df.receiving_currency
        illicit = df.label == 1
        totals['rows'] += len(df)
        totals['laundering'] += int(illicit.sum())
        totals['conversion'] += int(conversion.sum())
        totals['conversion_laundering'] += int((conversion & illicit).sum())
        totals['invalid_amount'] += int(((df.paid <= 0) | (df.received <= 0)).sum())
        totals['self_transfers'] += int(((df.from_bank == df.to_bank) & (df.from_account == df.to_account)).sum())
        lo, hi = df.timestamp.min(), df.timestamp.max()
        start, end = min(start or lo, lo), max(end or hi, hi)
        currency.update(df.payment_currency.value_counts().to_dict())
        positive.append(df.loc[illicit].copy())
        by_pair = df.groupby(['payment_currency', 'receiving_currency', 'format'], observed=True).label.agg(['count', 'sum']).reset_index()
        agg.append(by_pair)
        fx = df.loc[conversion].copy()
        if len(fx):
            fx['date'] = fx.timestamp.str[:10]
            fx['rate'] = fx.received / fx.paid
            fx['rate_squared'] = fx.rate ** 2
            daily.append(fx.groupby(['date', 'payment_currency', 'receiving_currency', 'label']).agg(
                count=('rate', 'size'), rate_sum=('rate', 'sum'), rate_squared_sum=('rate_squared', 'sum'),
                rate_min=('rate', 'min'), rate_max=('rate', 'max'), paid_sum=('paid', 'sum')).reset_index())
        if endpoint_accounts:
            relevant = df[df.from_account.isin(endpoint_accounts)]
            outgoing = relevant.groupby(['from_bank', 'from_account']).timestamp.max()
            for key, value in outgoing.items():
                last_outgoing[key] = max(last_outgoing.get(key, value), value)
        if n % 5 == 0:
            print(f'{name}: {totals["rows"]:,} rows scanned', flush=True)
    pairs = pd.concat(agg).groupby(['payment_currency', 'receiving_currency', 'format'])[['count', 'sum']].sum().reset_index()
    pairs.rename(columns={'count': 'transactions', 'sum': 'laundering'}, inplace=True)
    pairs['laundering_rate'] = pairs.laundering / pairs.transactions
    pairs.to_csv(output / f'{name}_pairs.csv', index=False)
    pos = pd.concat(positive, ignore_index=True)
    pos.to_csv(output / f'{name}_laundering.csv', index=False)
    if daily:
        fx = pd.concat(daily).groupby(['date', 'payment_currency', 'receiving_currency', 'label']).agg(
            count=('count', 'sum'), rate_sum=('rate_sum', 'sum'), rate_squared_sum=('rate_squared_sum', 'sum'),
            rate_min=('rate_min', 'min'), rate_max=('rate_max', 'max'), paid_sum=('paid_sum', 'sum')).reset_index()
        fx['rate_mean'] = fx.rate_sum / fx['count']
        fx['rate_std'] = np.sqrt(np.maximum(0, fx.rate_squared_sum / fx['count'] - fx.rate_mean ** 2))
        fx.to_csv(output / f'{name}_fx_daily.csv', index=False)
    else:
        fx = pd.DataFrame()
    a, b = totals['conversion_laundering'], totals['conversion'] - totals['conversion_laundering']
    c, d = totals['laundering'] - a, totals['rows'] - totals['conversion'] - (totals['laundering'] - a)
    odds, p = fisher_exact([[a, b], [c, d]])
    # Currency changes between adjacent labelled edges are candidate links, not fund attribution.
    incoming = pos[['to_bank', 'to_account', 'timestamp', 'receiving_currency']].rename(columns={
        'to_bank': 'bank', 'to_account': 'account', 'timestamp': 'in_time', 'receiving_currency': 'in_currency'})
    outgoing = pos[['from_bank', 'from_account', 'timestamp', 'payment_currency']].rename(columns={
        'from_bank': 'bank', 'from_account': 'account', 'timestamp': 'out_time', 'payment_currency': 'out_currency'})
    links = incoming.merge(outgoing, on=['bank', 'account'])
    links = links[links.out_time > links.in_time].copy()
    links['hours'] = (pd.to_datetime(links.out_time) - pd.to_datetime(links.in_time)).dt.total_seconds() / 3600
    links = links[links.hours <= 48]
    links['currency_change'] = links.in_currency != links.out_currency
    link_summary = {'candidate_links_within_48h': len(links), 'currency_change_links': int(links.currency_change.sum())}
    by_link = links.groupby(['in_currency', 'out_currency']).size().reset_index(name='candidate_links')
    by_link.to_csv(output / f'{name}_candidate_currency_links.csv', index=False)
    endpoint_rows = []
    for i, g in enumerate(groups):
        sources = {(e[1], e[2]) for e in g['edges']}
        terminal = {(e[3], e[4]) for e in g['edges']} - sources
        for key in terminal:
            arrival = max(e[0] for e in g['edges'] if (e[3], e[4]) == key)
            last = last_outgoing.get(key)
            endpoint_rows.append({'scheme': i, 'type': g['type'], 'bank': key[0], 'account': key[1],
                                  'arrival': arrival, 'last_outgoing': last,
                                  'later_outgoing': bool(last and last > arrival)})
    pd.DataFrame(ps).to_csv(output / f'{name}_pattern_metrics.csv', index=False)
    pd.DataFrame(endpoint_rows).to_csv(output / f'{name}_pattern_endpoints.csv', index=False)
    report = {'dataset': name, **dict(totals), 'start': start, 'end': end, 'currencies': dict(currency),
              'conversion_rate': totals['conversion'] / totals['rows'],
              'conversion_laundering_rate': a / (a + b) if a + b else None,
              'same_currency_laundering_rate': c / (c + d), 'fisher_odds_ratio': float(odds), 'fisher_p': float(p),
              'patterns': len(groups), 'pattern_types': dict(Counter(g['type'] for g in groups)),
              'multicurrency_patterns': sum(s['currencies'] > 1 for s in ps),
              'patterns_with_currency_switch': sum(s['currency_switch_edges'] > 0 for s in ps),
              'max_pattern_hops': max((s['max_temporal_hops'] for s in ps), default=None),
              'endpoint_instances': len(endpoint_rows),
              'endpoint_instances_with_later_outgoing': sum(e['later_outgoing'] for e in endpoint_rows),
              **link_summary}
    (output / f'{name}_summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    return fx


def fx_test(daily, archive, output):
    mapping = {'US Dollar': 'USD', 'Euro': 'EUR', 'Yen': 'JPY', 'Yuan': 'CNY',
               'UK Pound': 'GBP', 'Canadian Dollar': 'CAD', 'Australian Dollar': 'AUD',
               'Swiss Franc': 'CHF', 'Rupee': 'INR', 'Shekel': 'ILS', 'Ruble': 'RUB',
               'Brazil Real': 'BRL', 'Mexican Peso': 'MXN', 'Saudi Riyal': 'SAR', 'Bitcoin': 'BTC'}
    with zipfile.ZipFile(archive) as z:
        ecb = pd.read_csv(z.open('eurofxref-hist.csv'))
    ecb['Date'] = pd.to_datetime(ecb.Date)
    ecb = ecb.set_index('Date').sort_index().apply(pd.to_numeric, errors='coerce')
    ecb['EUR'] = 1.0
    # Previous business day only: avoid using end-of-day rates for earlier events.
    joined = []
    for name, df in daily.items():
        for _, row in df.iterrows():
            pay, rec = mapping.get(row.payment_currency), mapping.get(row.receiving_currency)
            day = pd.Timestamp(row.date.replace('/', '-'))
            previous = ecb[ecb.index < day]
            if pay not in ecb.columns or rec not in ecb.columns or previous.empty:
                market = np.nan
            else:
                latest = previous.iloc[-1]
                market = latest[rec] / latest[pay]
            r = row.to_dict()
            r.update(dataset=name, ecb_rate=market,
                     relative_deviation=row.rate_mean / market - 1 if pd.notna(market) else np.nan)
            joined.append(r)
    result = pd.DataFrame(joined)
    result.to_csv(output / 'ecb_comparison.csv', index=False)
    ecb.loc['2022-08-01':'2022-10-01'].to_csv(output / 'ecb_reference_window.csv')
    print('ECB joined records:', len(result), 'covered transactions:',
          int(result.loc[result.ecb_rate.notna(), 'count'].sum()) if len(result) else 0, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('poc/results'))
    parser.add_argument('--ecb', type=Path)
    parser.add_argument('--chunk-size', type=int, default=500000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    daily = {}
    for name in ['HI-Medium', 'LI-Medium']:
        daily[name] = scan(args.data_dir / f'{name}_Trans.csv', args.output,
                           patterns(args.data_dir / f'{name}_Patterns.txt'), args.chunk_size)
    if args.ecb:
        fx_test(daily, args.ecb, args.output)


if __name__ == '__main__':
    main()
