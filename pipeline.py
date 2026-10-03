#!/usr/bin/env python3
"""Screen YC or imported companies, prepare research packets, evaluate evidence cards."""
import argparse
import csv
import json
from pathlib import Path
import sys

from prospecting import PROFILE, blank_card, evaluate, research_packet, screen_all


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def export_rows(path, rows):
    fields = ['id', 'name', 'source', 'website', 'yc_url', 'batch', 'team_size', 'one_liner',
              'screen_state', 'lane', 'reasons', 'unknowns', 'stage', 'existing_tracker']
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            s = row['screen']
            out = {k: row.get(k, '') for k in fields}
            out.update(screen_state=s['state'], lane=s['lane'],
                       reasons='; '.join(s['reasons'] + s['holds']), unknowns='; '.join(s['unknowns']))
            # Prevent spreadsheet formula injection from untrusted directory data.
            writer.writerow({k: ("'" + str(v) if str(v).startswith(('=', '+', '-', '@')) else v)
                             for k, v in out.items()})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    s = sub.add_parser('screen', help='cheap directory screen before contact enrichment')
    s.add_argument('--input', help='JSON array from YC scraper or another directory')
    s.add_argument('--batches', nargs='+', help='YC batches; defaults to all batches since profile min year')
    s.add_argument('--profile', help='optional local JSON configuration')
    s.add_argument('--known', help='JSON array of existing tracker company names or canonical IDs')
    s.add_argument('--out', default='data/pipeline')
    s.add_argument('--packets', type=int, default=25, help='number of top research handoffs')
    e = sub.add_parser('evaluate', help='validate and rank completed research cards')
    e.add_argument('--input', required=True, help='JSON array of completed cards')
    e.add_argument('--out', default='data/evaluated.json')
    a = ap.parse_args(argv)
    try:
        if a.command == 'evaluate':
            cards = read_json(a.input)
            if not isinstance(cards, list):
                raise ValueError('Input must be a JSON array of research cards')
            out = [{'card': c, 'evaluation': evaluate(c)} for c in cards]
            out.sort(key=lambda x: -x['evaluation']['effective_priority'])
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            write_json(a.out, out)
            print(f'Evaluated {len(out)} cards. No outreach sent.')
            return
        profile = {**PROFILE, **(read_json(a.profile) if a.profile else {})}
        if a.input:
            raw = read_json(a.input)
        else:
            from api.yc import algolia, batches
            selected = a.batches or [b['batch'] for b in batches()
                                    if any(str(y) in b['batch'] for y in range(profile['min_batch_year'], profile['max_batch_year'] + 1))]
            if not selected:
                raise ValueError('No batches matched the discovery window')
            raw = []
            for batch in selected:
                page = 0
                while True:
                    response = algolia({'hitsPerPage': 1000, 'page': page,
                                        'facetFilters': json.dumps([[f'batch:{batch}']])})
                    raw.extend(response['hits'])
                    page += 1
                    if page >= response['nbPages']:
                        break
                print(f'Loaded {batch}', file=sys.stderr)
        if not isinstance(raw, list) or not all(isinstance(c, dict) and c.get('name') for c in raw):
            raise ValueError('Input must be a JSON array of companies with names')
        rows = screen_all(raw, profile)
        known = {str(x).casefold() for x in read_json(a.known)} if a.known else set()
        for row in rows:
            row['existing_tracker'] = row['id'].casefold() in known or row['name'].casefold() in known
        root = Path(a.out)
        root.mkdir(parents=True, exist_ok=True)
        write_json(root / 'companies.json', rows)
        export_rows(root / 'companies.csv', rows)
        selected = [c for c in rows if c['screen']['state'] == 'research' and not c['existing_tracker']][:max(0, a.packets)]
        packets = root / 'research'
        packets.mkdir(exist_ok=True)
        # Remove obsolete generated packets from a previous run, preserving other files.
        for old in packets.glob('[0-9][0-9][0-9]-*.md'):
            old.unlink()
        for i, c in enumerate(selected, 1):
            safe = ''.join(ch if ch.isalnum() else '-' for ch in c['name'])[:80]
            (packets / f'{i:03}-{safe}.md').write_text(research_packet(c, profile), encoding='utf-8')
        write_json(root / 'cards.json', [blank_card(c) for c in selected])
        counts = {state: sum(c['screen']['state'] == state for c in rows)
                  for state in ('research', 'review', 'hold', 'reject')}
        write_json(root / 'summary.json', {'raw': len(raw), 'deduplicated': len(rows),
                                         **counts, 'research_packets': len(selected),
                                         'already_in_tracker': sum(c['existing_tracker'] for c in rows),
                                         'note': 'Research candidates, not verified hiring opportunities'})
        print(json.dumps(counts), f'→ {root}. No outreach sent.')
    except (ValueError, OSError, RuntimeError) as err:
        ap.exit(1, f'Pipeline stopped: {err}\n')


if __name__ == '__main__':
    main()
