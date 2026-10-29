import contextlib
import html
import io
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import sources


class FakeResponse:
    def __init__(self, body=b"", status=200):
        self.body = body
        self.status_code = status
        self.closed = False

    def iter_content(self, chunk_size):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start:start + chunk_size]

    def close(self):
        self.closed = True


def rss(items):
    return ('<?xml version="1.0"?><rss version="2.0"><channel>'
            '<title>News</title><link>https://example.test</link><description>News</description>'
            + ''.join(items) + '</channel></rss>').encode()


def item(title="Fed holds interest rates", link="https://example.test/news", date="Thu, 29 Oct 2026 14:00:00 +0200", summary="Policy decision", publisher=""):
    return ('<item><title>' + html.escape(title) + '</title><link>' + html.escape(link)
            + '</link><description>' + html.escape(summary) + '</description>'
            + ('<pubDate>' + date + '</pubDate>' if date else '')
            + publisher + '</item>')


class SourcesTests(unittest.TestCase):
    def test_publication_dates_are_utc_and_original_links_are_kept(self):
        link = 'https://example.test/news?id=42&utm_source=rss#section'
        response = FakeResponse(rss([item(link=link)]))
        with patch.object(sources.requests, 'get', return_value=response) as get:
            articles, health = sources._fetch_rss('Market source', 'https://example.test/rss')
        self.assertEqual(articles[0]['published_at'], '2026-10-29T12:00:00Z')
        self.assertEqual(articles[0]['url'], link)
        self.assertEqual(articles[0]['canonical_url'], 'https://example.test/news?id=42')
        self.assertEqual(health['newest_at'], '2026-10-29T12:00:00Z')
        self.assertTrue(response.closed)
        self.assertEqual(get.call_args.kwargs['timeout'], sources.REQUEST_TIMEOUT)

    def test_missing_dates_remain_unknown_instead_of_becoming_now(self):
        with patch.object(sources.requests, 'get', return_value=FakeResponse(rss([item(date='')]))):
            articles, health = sources._fetch_rss('BBC World', 'https://example.test/rss')
        self.assertIsNone(articles[0]['published_at'])
        self.assertEqual(health['undated_count'], 1)
        self.assertEqual(health['dated_count'], 0)
        self.assertIsNone(health['newest_at'])
        self.assertFalse(health['primary'])

    def test_atom_prefers_published_over_updated(self):
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Market</title>
        <entry><title>Rates held</title><link href="https://example.test/rates"/>
        <published>2026-10-27T10:00:00Z</published><updated>2026-10-29T12:00:00Z</updated>
        <summary>Policy</summary></entry></feed>'''
        with patch.object(sources.requests, 'get', return_value=FakeResponse(atom)):
            articles, _ = sources._fetch_rss('Market source', 'https://example.test/rss')
        self.assertEqual(articles[0]['published_at'], '2026-10-27T10:00:00Z')

    def test_partial_source_failure_does_not_discard_good_feed(self):
        def fetch(url, **kwargs):
            if 'bad' in url:
                raise requests.Timeout('https://bad.test/?private=not-for-logs')
            return FakeResponse(rss([item()]))
        with patch.object(sources.requests, 'get', side_effect=fetch):
            articles, health = sources.collect_news([
                ('Broken markets', 'https://bad.test/rss'), ('Good markets', 'https://good.test/rss'),
            ])
        self.assertEqual(len(articles), 1)
        self.assertEqual([row['status'] for row in health], ['error', 'ok'])
        self.assertNotIn('private', health[0]['detail'])
        self.assertTrue(health[1]['primary'])

    def test_total_failure_is_explicit_with_individual_diagnostics(self):
        with patch.object(sources.requests, 'get', return_value=FakeResponse(status=503)), \
                self.assertRaises(sources.SourceCollectionError) as error:
            sources.collect_news([('Market source', 'https://example.test/rss')])
        self.assertEqual(error.exception.diagnostics[0]['detail'], 'HTTP 503')

    def test_html_success_response_is_not_a_healthy_empty_feed(self):
        with patch.object(sources.requests, 'get', return_value=FakeResponse(b'<html><body>Access denied</body></html>')):
            articles, health = sources._fetch_rss('Market source', 'https://example.test/rss')
        self.assertEqual(articles, [])
        self.assertEqual(health['status'], 'error')
        self.assertIn('RSS/Atom', health['detail'])

    def test_valid_empty_feed_is_visible_and_all_empty_sources_fail(self):
        with patch.object(sources.requests, 'get', return_value=FakeResponse(rss([]))):
            articles, health = sources._fetch_rss('Market source', 'https://example.test/rss')
        self.assertEqual(articles, [])
        self.assertEqual(health['status'], 'empty')
        with patch.object(sources.requests, 'get', return_value=FakeResponse(rss([]))), \
                self.assertRaises(sources.SourceCollectionError):
            sources.collect_news([('Market source', 'https://example.test/rss')])

    def test_duplicates_keep_first_source_and_richer_summary(self):
        responses = {
            'https://first.test/rss': rss([item(link='https://example.test/a?utm_source=first', summary='Short')]),
            'https://second.test/rss': rss([item(link='https://example.test/a?utm_source=second', summary='Much richer summary')]),
        }
        with patch.object(sources.requests, 'get', side_effect=lambda url, **kw: FakeResponse(responses[url])):
            articles, health = sources.collect_news([
                ('First source', 'https://first.test/rss'), ('Second source', 'https://second.test/rss'),
            ])
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['source'], 'First source')
        self.assertEqual(articles[0]['desc'], 'Much richer summary')
        self.assertEqual(len(health), 2)

    def test_reuters_aggregation_requires_both_publisher_and_origin(self):
        entries = [
            item(title='Reuters original', link='https://news.google.com/rss/articles/one', publisher='<source url="https://www.reuters.com">Reuters</source>'),
            item(title='Other newspaper quotes Reuters', link='https://news.google.com/rss/articles/two', publisher='<source url="https://other.test">Other Newspaper</source>'),
            item(title='Wrong domain', link='https://news.google.com/rss/articles/three', publisher='<source url="https://reuters.com.attacker.test">Reuters</source>'),
            item(title='No publisher', link='https://news.google.com/rss/articles/four'),
        ]
        with patch.object(sources.requests, 'get', return_value=FakeResponse(rss(entries))):
            articles, health = sources._fetch_rss(sources.REUTERS_AGGREGATE_LABEL, sources.REUTERS_AGGREGATE_URL)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['original_source'], 'Reuters')
        self.assertEqual(articles[0]['source'], 'Reuters via Google News')
        self.assertEqual(articles[0]['source_kind'], 'aggregated')
        self.assertEqual(health['excluded_publishers'], 3)

    def test_feed_bytes_and_item_count_are_bounded(self):
        response = FakeResponse(b'x' * 100)
        with patch.object(sources.requests, 'get', return_value=response), patch.object(sources, 'MAX_FEED_BYTES', 10):
            articles, health = sources._fetch_rss('Market', 'https://example.test/rss')
        self.assertEqual(articles, [])
        self.assertIn('volumineux', health['detail'])
        self.assertTrue(response.closed)
        many = rss([item(link='https://example.test/' + str(i)) for i in range(101)])
        with patch.object(sources.requests, 'get', return_value=FakeResponse(many)):
            articles, _ = sources._fetch_rss('Market', 'https://example.test/rss')
        self.assertEqual(len(articles), sources.MAX_FEED_ITEMS)

    def test_invalid_links_are_not_published(self):
        invalid = rss([item(link='javascript:alert(1)'), item(link='file:///etc/passwd')])
        with patch.object(sources.requests, 'get', return_value=FakeResponse(invalid)):
            articles, health = sources._fetch_rss('Market', 'https://example.test/rss')
        self.assertEqual(articles, [])
        self.assertEqual(health['status'], 'empty')
        self.assertEqual(sources.canonicalize_url('https://['), '')
        self.assertEqual(sources.canonicalize_url(None), '')

    def test_newsapi_failure_never_logs_the_api_key(self):
        key = 'unit-test-private-news-key'
        with patch.object(sources.requests, 'get', side_effect=requests.ConnectionError('https://newsapi.org/?apiKey=' + key)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(sources.fetch_newsapi(key), [])
        self.assertNotIn(key, output.getvalue())

    def test_newsapi_key_is_in_header_and_dates_use_the_same_utc_contract(self):
        response = Mock(status_code=200)
        response.json.return_value = {"status": "ok", "articles": [{
            "title": "Fed holds rates", "url": "https://example.test/news",
            "source": {"name": "News agency"}, "publishedAt": "2026-10-29T14:00:00+02:00",
        }]}
        with patch.object(sources.requests, 'get', return_value=response) as get:
            articles = sources.fetch_newsapi('private-unit-test-key')
        self.assertNotIn('apiKey', get.call_args.kwargs['params'])
        self.assertEqual(get.call_args.kwargs['headers']['X-Api-Key'], 'private-unit-test-key')
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertEqual(articles[0]['published_at'], '2026-10-29T12:00:00Z')

    def test_empty_configuration_fails_instead_of_becoming_silent_success(self):
        with self.assertRaises(sources.SourceCollectionError):
            sources.collect_news([])


class SourceCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'scripts' / 'check_sources.py'
        spec = importlib.util.spec_from_file_location('source_check', path)
        cls.check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.check)

    def test_check_writes_audit_without_sending_or_modifying_source_configuration(self):
        original_specs = list(sources.RSS_SOURCES)
        article = {'title': 'Fed holds rates', 'url': 'https://example.test/a',
                   'source': original_specs[0][0], 'published_at': '2026-10-29T12:00:00Z'}
        health = {'source': original_specs[0][0], 'status': 'ok', 'primary': True,
                  'article_count': 1, 'newest_at': '2026-10-29T12:00:00Z'}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sources, 'collect_news', return_value=([article], [health])) as collect, \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            path = Path(directory) / 'audit.json'
            self.assertEqual(self.check.main(['--output', str(path), '--max-items', '20', '--probe-investinglive']), 0)
            data = json.loads(path.read_text())
        self.assertTrue(data['read_only'])
        self.assertEqual(data['max_items_per_source'], 20)
        self.assertEqual(len(collect.call_args.args[0]), len(original_specs))
        self.assertFalse(any(name.startswith('PROBE ') for name, _ in collect.call_args.args[0]))
        self.assertEqual(sources.RSS_SOURCES, original_specs)
        self.assertIn('AUDIT_ITEM ', stdout.getvalue())

    def test_freshness_summary_does_not_confuse_stale_or_future_data_with_live_news(self):
        names = [name for name, _ in sources.RSS_SOURCES[:4]]
        now = datetime.now(timezone.utc)
        dates = [(now - timedelta(hours=1)).isoformat(), (now - timedelta(hours=25)).isoformat(),
                 (now + timedelta(hours=2)).isoformat(), None]
        articles = [{'source': name, 'title': 'Test ' + str(index), 'published_at': date}
                    for index, (name, date) in enumerate(zip(names, dates))]
        health = [{'source': name, 'status': 'ok', 'primary': True, 'article_count': 1, 'newest_at': date}
                  for name, date in zip(names, dates)]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sources, 'collect_news', return_value=(articles, health)), \
                contextlib.redirect_stdout(io.StringIO()):
            path = Path(directory) / 'freshness.json'
            self.assertEqual(self.check.main(['--output', str(path)]), 0)
            data = json.loads(path.read_text())
        self.assertEqual(data['summary']['usable_market_sources'], 4)
        self.assertEqual(data['summary']['fresh_market_sources'], 1)
        self.assertEqual(data['summary']['fresh_articles_24h'], 1)

    def test_investinglive_probes_are_added_only_if_not_already_active(self):
        active = [(name, url) for name, url in sources.RSS_SOURCES if not name.startswith('InvestingLive ')]
        article = {'source': active[0][0], 'title': 'A news', 'published_at': None}
        row = {'source': active[0][0], 'status': 'ok', 'article_count': 1, 'newest_at': None}
        with tempfile.TemporaryDirectory() as directory, patch.object(sources, 'RSS_SOURCES', active), \
                patch.object(sources, 'collect_news', return_value=([article], [row])) as collect, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.check.main(['--output', str(Path(directory) / 'probe.json'),
                                             '--probe-investinglive']), 0)
        requested = collect.call_args.args[0]
        self.assertEqual(len(requested), len(active) + 2)
        self.assertEqual(len({url.rstrip('/') for _, url in requested}), len(requested))

    def test_total_failure_still_persists_source_diagnostics(self):
        diagnostic = {'source': 'Broken source', 'status': 'error', 'article_count': 0, 'newest_at': None}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sources, 'collect_news', side_effect=sources.SourceCollectionError([diagnostic])), \
                contextlib.redirect_stdout(io.StringIO()):
            path = Path(directory) / 'failed.json'
            self.assertEqual(self.check.main(['--output', str(path)]), 1)
            data = json.loads(path.read_text())
        self.assertEqual(data['sources'][0]['status'], 'error')
        self.assertEqual(data['articles'], [])

    def test_probe_success_alone_does_not_make_production_healthy(self):
        article = {'title': 'Rates held', 'source': 'PROBE InvestingLive News', 'published_at': None}
        diagnostic = {'source': article['source'], 'status': 'ok', 'article_count': 1,
                      'newest_at': None, 'primary': True}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sources, 'collect_news', return_value=([article], [diagnostic])), \
                contextlib.redirect_stdout(io.StringIO()):
            path = Path(directory) / 'probe.json'
            self.assertEqual(self.check.main(['--output', str(path), '--probe-investinglive']), 1)
            data = json.loads(path.read_text())
        self.assertTrue(data['sources'][0]['probe'])
        self.assertEqual(data['summary']['usable_market_sources'], 0)


if __name__ == '__main__':
    unittest.main()
