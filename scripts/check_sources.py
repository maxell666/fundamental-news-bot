"""Diagnostic de collecte RSS en lecture seule, sans Telegram ni état du bot."""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sources


INVESTINGLIVE_PROBES = [
    ("PROBE InvestingLive News", "https://investinglive.com/feed/news/"),
    ("PROBE InvestingLive Central Banks", "https://investinglive.com/feed/centralbank/"),
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='audit/source_check.json')
    parser.add_argument('--max-items', type=int, default=sources.MAX_ITEMS_PER_SOURCE)
    parser.add_argument('--probe-investinglive', action='store_true',
                        help='Sonder deux candidats RSS sans les activer dans les sources de production')
    args = parser.parse_args(argv)
    if not 1 <= args.max_items <= 200:
        parser.error('--max-items doit être compris entre 1 et 200')
    specs = list(sources.RSS_SOURCES)
    if args.probe_investinglive:
        active_urls = {sources.canonicalize_url(url).rstrip('/') for _, url in specs}
        specs += [(name, url) for name, url in INVESTINGLIVE_PROBES
                  if sources.canonicalize_url(url).rstrip('/') not in active_urls]
    old_limit = sources.MAX_FEED_ITEMS
    try:
        sources.MAX_FEED_ITEMS = args.max_items
        try:
            articles, diagnostics = sources.collect_news(specs)
        except sources.SourceCollectionError as exc:
            articles, diagnostics = [], exc.diagnostics
    finally:
        sources.MAX_FEED_ITEMS = old_limit

    now = datetime.now(timezone.utc)

    def age_hours(value):
        if not isinstance(value, str):
            return None
        try:
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if date.tzinfo is None:
                return None
            return (now - date).total_seconds() / 3600
        except (ValueError, TypeError):
            return None

    source_names = {name for name, _ in sources.RSS_SOURCES}
    production_articles = [item for item in articles if item.get('source') in source_names]
    healthy = []
    for row in diagnostics:
        row['probe'] = row['source'] not in source_names
        if row['status'] in ('ok', 'warning') and not row['probe']:
            healthy.append(row)
        newest_age = age_hours(row.get('newest_at'))
        row['newest_age_hours'] = round(newest_age, 2) if newest_age is not None else None
        row['fresh_24h'] = newest_age is not None and -0.25 <= newest_age <= 24

    production_ages = [age_hours(item.get('published_at')) for item in production_articles]

    summary = {
        'source_count': len(diagnostics),
        'production_sources': len(source_names),
        'usable_production_sources': len(healthy),
        'usable_market_sources': sum(bool(row.get('primary')) for row in healthy),
        'fresh_market_sources': sum(bool(row.get('primary')) and row['fresh_24h'] for row in healthy),
        'fresh_articles_24h': sum(age is not None and -0.25 <= age <= 24 for age in production_ages),
        'article_count': len(articles),
        'production_articles': len(production_articles),
        'status_counts': dict(Counter(row['status'] for row in diagnostics)),
        'dated_articles': sum(bool(item.get('published_at')) for item in articles),
        'undated_articles': sum(not item.get('published_at') for item in articles),
    }
    document = {
        'generated_at': now.isoformat().replace('+00:00', 'Z'),
        'read_only': True,
        'probe_investinglive': args.probe_investinglive,
        'max_items_per_source': args.max_items,
        'summary': summary,
        'sources': diagnostics,
        'articles': articles,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    print('AUDIT_SUMMARY ' + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    for row in diagnostics:
        print('AUDIT_SOURCE ' + json.dumps(row, ensure_ascii=False, sort_keys=True))
    for item in articles:
        print('AUDIT_ITEM ' + json.dumps(item, ensure_ascii=False, sort_keys=True))
    print('Audit écrit : ' + str(output))
    if not production_articles:
        print('Échec : aucune source de production ne fournit d’article exploitable.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
