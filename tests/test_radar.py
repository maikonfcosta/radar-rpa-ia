import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import pathlib
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import generate
import send_email

STORY = {'title': 'Atualização oficial', 'url': 'https://blog.python.org/2026/update.html',
         'date': generate.STAMP, 'category': 'Python', 'source': 'Python Insider',
         'excerpt': 'Mudança descrita pela fonte.'}
BRIEFING = {'executive_summary': 'Resumo com evidência.', 'highlights': [
    {'url': STORY['url'], 'title': 'Título inventado', 'category': 'Outra categoria',
     'impact': 'Avaliar compatibilidade.', 'technical_detail': 'Detalhe informado no excerto.',
     'action': 'Executar regressão.'}], 'next_actions': ['Testar CSV.', 'Revisar filas.', 'Revisar logs.']}

class Feeds(unittest.TestCase):
    def test_large_uipath_feed_keeps_only_complete_entries(self):
        entry = f'<item><title>Release</title><link>https://www.uipath.com/blog/release</link><pubDate>{generate.STAMP}</pubDate></item>'
        raw = ('<rss><channel>' + entry + '<item><description>' + 'x' * 1_500_000).encode()
        details = {}
        with patch.object(generate.urllib.request, 'urlopen') as http, \
             contextlib.redirect_stderr(io.StringIO()):
            response = http.return_value.__enter__.return_value
            response.geturl.return_value = 'https://www.uipath.com/blog/rss.xml'
            response.read.return_value = raw[:1_500_001]
            normalized = generate.fetch(response.geturl(), source='UiPath Blog', details=details)
        items = generate.parse_feed(normalized, 'UiPath', 'UiPath Blog')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Release')
        self.assertTrue(details['limited'])

    def test_oversized_non_uipath_response_stays_rejected(self):
        with patch.object(generate.urllib.request, 'urlopen') as http:
            response = http.return_value.__enter__.return_value
            response.geturl.return_value = 'https://blog.python.org/feed'
            response.read.return_value = b'x' * 1_500_001
            with self.assertRaisesRegex(ValueError, 'excede limite'):
                generate.fetch(response.geturl(), source='Python Insider')

    def test_official_article_uses_publication_date_not_modification(self):
        article = {'@type': 'Article', 'headline': 'Atualização oficial',
                   'datePublished': generate.STAMP + 'T08:00:00-0700',
                   'description': '<b>Excerto oficial</b>'}
        url = 'https://www.automationanywhere.com/company/blog/update'
        def page(data):
            return ('<script type="application/ld+json">' + json.dumps({'@graph': [data]}) + '</script>').encode()
        item = generate.parse_article(page(article), url, 'Automation Anywhere', 'Automation Anywhere Blog')
        self.assertEqual(item['date'], generate.STAMP)
        self.assertEqual(item['excerpt'], 'Excerto oficial')
        self.assertEqual(item['url'], url)
        article['datePublished'] = (generate.TODAY - dt.timedelta(days=15)).isoformat()
        article['dateModified'] = generate.STAMP
        self.assertIsNone(generate.parse_article(page(article), url, 'Automation Anywhere', 'Automation Anywhere Blog'))
        del article['datePublished']
        with self.assertRaises(ValueError):
            generate.parse_article(page(article), url, 'Automation Anywhere', 'Automation Anywhere Blog')
        article['datePublished'] = (generate.TODAY + dt.timedelta(days=1)).isoformat()
        self.assertIsNone(generate.parse_article(page(article), url, 'Automation Anywhere', 'Automation Anywhere Blog'))

    def test_blog_collection_ignores_external_and_duplicate_links(self):
        url = 'https://www.automationanywhere.com/company/blog'
        listing = b'<a href="/company/blog/browse">Browse</a><a href="/company/blog/author/example">Author</a><a href="/company/blog/update">A</a><a href="/company/blog/update">B</a><a href="https://evil.test/company/blog/injected">C</a>'
        article = ('<script type="application/ld+json">' + json.dumps({
            '@type': 'BlogPosting', 'headline': 'Atualização', 'datePublished': generate.STAMP,
            'description': 'Excerto'}) + '</script>').encode()
        with patch.object(generate, 'fetch', side_effect=[listing, article]) as fetch:
            items, failed = generate.collect_blog(url, 'Automation Anywhere', 'Automation Anywhere Blog')
        self.assertEqual(len(items), 1)
        self.assertEqual(failed, 0)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(items[0]['url'], url + '/update')

    def test_collection_records_unavailable_and_empty_sources_separately(self):
        sources = [('Python Insider', 'Python', 'https://blog.python.org/feed'),
                   ('UiPath Blog', 'UiPath', 'https://www.uipath.com/blog/rss.xml')]
        diagnostics = []
        with patch.object(generate, 'FEEDS', sources), \
             patch.object(generate, 'fetch', side_effect=[b'<rss><channel/></rss>', urllib.error.HTTPError(
                 sources[1][2], 404, 'not-found', {}, None)]), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(generate.collect(diagnostics), [])
        self.assertEqual([item['status'] for item in diagnostics], ['no_recent_articles', 'unavailable'])
        self.assertEqual(diagnostics[1]['error'], 'HTTP 404')

    def test_official_hosts(self):
        for url in ('https://python.org/release', 'https://blog.python.org/news'):
            self.assertTrue(generate.official_url(url, 'Python Insider'))
        for url in ('http://python.org/news', 'https://python.org.evil.test/news',
                    'https://evilpython.org/news', 'https://user@python.org/news',
                    'https://python.org:444/news', 'https://evil.test/news'):
            self.assertFalse(generate.official_url(url, 'Python Insider'))

    def test_rss_rejects_stale_future_missing_and_external(self):
        def entry(url, date):
            return f'<item><title>Release</title><link>{url}</link><pubDate>{date}</pubDate><description>&lt;b&gt;Fato&lt;/b&gt;</description></item>'
        today = generate.TODAY
        raw = '<rss><channel>' + ''.join([
            entry(STORY['url'], today.isoformat()),
            entry('https://python.org/old', (today - dt.timedelta(days=15)).isoformat()),
            entry('https://python.org/future', (today + dt.timedelta(days=1)).isoformat()),
            entry('https://python.org/undated', ''),
            entry('https://python.org.evil.test/news', today.isoformat()),
        ]) + '</channel></rss>'
        items = generate.parse_feed(raw.encode(), 'Python', 'Python Insider')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['excerpt'], 'Fato')

    def test_atom(self):
        raw = f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Notícia</title><link href="{STORY["url"]}"/><updated>{generate.STAMP}T10:00:00Z</updated><summary>Excerto oficial</summary></entry></feed>'
        item = generate.parse_feed(raw.encode(), 'Python', 'Python Insider')[0]
        self.assertEqual(item['url'], STORY['url'])
        self.assertEqual(item['excerpt'], 'Excerto oficial')

    def test_broad_microsoft_feed_keeps_only_relevant_and_deduplicates(self):
        other = {**STORY, 'title': 'Power Apps update', 'url': 'https://www.microsoft.com/power-apps', 'excerpt': ''}
        relevant = {**STORY, 'title': 'Power Automate update', 'url': 'https://www.microsoft.com/power-automate'}
        with patch.object(generate, 'FEEDS', [('Microsoft Power Platform Blog', 'Power Automate', 'https://www.microsoft.com/feed')]), \
             patch.object(generate, 'fetch', return_value=b'feed'), \
             patch.object(generate, 'parse_feed', return_value=[other, relevant, relevant]), \
             contextlib.redirect_stdout(io.StringIO()):
            items = generate.collect()
        self.assertEqual([x['url'] for x in items], [relevant['url']])

class Briefing(unittest.TestCase):
    def test_source_metadata_wins_and_duplicates_removed(self):
        data = copy.deepcopy(BRIEFING)
        data['highlights'] *= 2
        output = generate.validate_briefing(data, [STORY])
        self.assertEqual(len(output['highlights']), 1)
        self.assertEqual(output['highlights'][0]['title'], STORY['title'])
        self.assertEqual(output['highlights'][0]['category'], STORY['category'])

    def test_invented_source_fails(self):
        data = copy.deepcopy(BRIEFING)
        data['highlights'][0]['url'] = 'https://python.org/invented'
        with self.assertRaises(ValueError):
            generate.validate_briefing(data, [STORY])

    def test_incomplete_response_fails(self):
        for field, value in [('next_actions', []), ('next_actions', 'abc'),
                             ('executive_summary', {}), ('highlights', 'abc')]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(BRIEFING)
                data[field] = value
                with self.assertRaises(ValueError):
                    generate.validate_briefing(data, [STORY])

    def test_html_escaped(self):
        data = generate.validate_briefing(copy.deepcopy(BRIEFING), [STORY])
        data['executive_summary'] = '<script>alert(1)</script>'
        data['highlights'][0]['impact'] = '<img src=x onerror=alert(1)>'
        page = generate.render(data, 1)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('&lt;img', page)

    def test_source_coverage_visible_in_report(self):
        data = generate.validate_briefing(copy.deepcopy(BRIEFING), [STORY])
        page = generate.render(data, 1, [{'source': 'UiPath Blog', 'status': 'unavailable', 'articles': 0}])
        self.assertIn('Cobertura das fontes', page)
        self.assertIn('UiPath Blog', page)
        self.assertIn('Indisponível', page)

class Generation(unittest.TestCase):
    def test_generation_archives_evidence_and_preserves_home(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / 'index.html').write_text('existing dashboard')
            (root / 'edicoes').mkdir()
            (root / 'edicoes' / '2026-10-12-inicial.html').write_text('original')
            output = root / 'generated'
            coverage = [{'source': 'Python Insider', 'status': 'ok', 'articles': 1},
                        {'source': 'UiPath Blog', 'status': 'unavailable', 'articles': 0}]
            def collected(diagnostics):
                diagnostics.extend(coverage)
                return [STORY]
            with patch.multiple(generate, ROOT=root, OUTPUT=output), \
                 patch.object(generate, 'collect', side_effect=collected), \
                 patch.object(generate, 'generate_briefing', return_value=generate.validate_briefing(copy.deepcopy(BRIEFING), [STORY])), \
                 contextlib.redirect_stdout(io.StringIO()):
                generate.main()
            self.assertEqual((root / 'index.html').read_text(), 'existing dashboard')
            latest = send_email.load_latest(output)
            self.assertEqual(latest['sha256'], hashlib.sha256((output / 'index.html').read_bytes()).hexdigest())
            self.assertEqual((output / 'edicoes' / f'{generate.STAMP}.html').read_bytes(), (output / 'index.html').read_bytes())
            evidence = json.loads((output / 'edicoes' / f'{generate.STAMP}.json').read_text())
            self.assertEqual(evidence['items'][0]['url'], STORY['url'])
            self.assertEqual(evidence['coverage'], coverage)
            self.assertIn('Indisponível', (output / 'index.html').read_text(encoding='utf-8'))
            self.assertIn('2026-10-12-inicial.html', (output / 'edicoes' / 'index.html').read_text())

    def test_empty_collection_does_not_replace_dashboard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / 'index.html').write_text('unchanged')
            with patch.multiple(generate, ROOT=root, OUTPUT=root), \
                 patch.object(generate, 'collect', return_value=[]), \
                 patch.object(generate, 'generate_briefing') as groq, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'Nenhum artigo recente'):
                    generate.main()
                groq.assert_not_called()
            self.assertEqual((root / 'index.html').read_text(), 'unchanged')
            self.assertFalse((root / 'latest.json').exists())

    def test_existing_edition_is_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / 'edicoes').mkdir()
            archive = root / 'edicoes' / f'{generate.STAMP}.html'
            archive.write_text('original')
            with patch.multiple(generate, ROOT=root, OUTPUT=root), patch.object(generate, 'collect') as collect:
                with self.assertRaises(RuntimeError):
                    generate.main()
                collect.assert_not_called()
            self.assertEqual(archive.read_text(), 'original')

class GroqIntegration(unittest.TestCase):
    def test_http_failure_explains_next_step_without_response_body(self):
        for code, expected in [(401, 'autenticação'), (429, 'limite'), (503, 'indisponível')]:
            with self.subTest(code=code), \
                 patch.dict(generate.os.environ, {'GROQ_API_KEY': 'synthetic-secret'}), \
                 patch.object(generate.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError(
                     'https://api.groq.com', code, 'synthetic-private-body', {}, None)), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, expected) as error:
                    generate.generate_briefing([STORY])
                self.assertIn(f'HTTP {code}', str(error.exception))
                self.assertNotIn('synthetic-private', str(error.exception))
                self.assertNotIn('synthetic-secret', str(error.exception))

    def test_network_failure_is_safe(self):
        with patch.dict(generate.os.environ, {'GROQ_API_KEY': 'synthetic-secret'}), \
             patch.object(generate.urllib.request, 'urlopen', side_effect=urllib.error.URLError('private-detail')), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'falha de rede') as error:
                generate.generate_briefing([STORY])
            self.assertNotIn('private-detail', str(error.exception))

    def test_invalid_http_json_and_model_json_are_rejected(self):
        for body, message in [(b'not-json', 'JSON HTTP inválido'),
                              (b'{"choices": []}', 'JSON ausente ou inválido'),
                              (b'{"choices": [{"message": {"content": "not-json"}}]}', 'JSON ausente ou inválido')]:
            with self.subTest(body=body), \
                 patch.dict(generate.os.environ, {'GROQ_API_KEY': 'synthetic-secret'}), \
                 patch.object(generate.urllib.request, 'urlopen') as http, \
                 contextlib.redirect_stdout(io.StringIO()):
                http.return_value.__enter__.return_value = io.BytesIO(body)
                with self.assertRaisesRegex(RuntimeError, message):
                    generate.generate_briefing([STORY])

    def test_valid_model_response_preserves_source_metadata(self):
        payload = json.dumps({'choices': [{'message': {'content': json.dumps(BRIEFING)}}]}).encode()
        with patch.dict(generate.os.environ, {'GROQ_API_KEY': 'synthetic-secret'}), \
             patch.object(generate.urllib.request, 'urlopen') as http, \
             contextlib.redirect_stdout(io.StringIO()):
            http.return_value.__enter__.return_value = io.BytesIO(payload)
            result = generate.generate_briefing([STORY])
        self.assertEqual(result['highlights'][0]['title'], STORY['title'])

    def test_invalid_briefing_blocks_generation(self):
        payload = json.dumps({'choices': [{'message': {'content': '{}'}}]}).encode()
        with patch.dict(generate.os.environ, {'GROQ_API_KEY': 'synthetic-secret'}), \
             patch.object(generate.urllib.request, 'urlopen') as http, \
             contextlib.redirect_stdout(io.StringIO()):
            http.return_value.__enter__.return_value = io.BytesIO(payload)
            with self.assertRaisesRegex(RuntimeError, 'Validação Groq'):
                generate.generate_briefing([STORY])

class Notifications(unittest.TestCase):
    def test_missing_edition_explains_initial_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'publish_current=false'):
                send_email.load_latest(pathlib.Path(temp))

    def setUp(self):
        self.page = b'<html>current edition</html>'
        self.latest = {'date': '2026-10-12', 'url': send_email.SITE_URL,
                       'summary': 'Resumo', 'sha256': hashlib.sha256(self.page).hexdigest()}

    def test_default_dry_run_uses_no_network(self):
        with patch.object(send_email, 'load_latest', return_value=self.latest), \
             patch.object(send_email.urllib.request, 'urlopen') as http, \
             patch.object(send_email.smtplib, 'SMTP_SSL') as smtp, \
             contextlib.redirect_stdout(io.StringIO()):
            send_email.main([])
            http.assert_not_called()
            smtp.assert_not_called()

    def test_stale_same_date_page_blocks_smtp(self):
        with patch.object(send_email.urllib.request, 'urlopen') as http, \
             patch.object(send_email.smtplib, 'SMTP_SSL') as smtp, \
             contextlib.redirect_stdout(io.StringIO()):
            response = http.return_value.__enter__.return_value
            response.read.return_value = b'Radar RPA & IA -- 2026-10-12 (old version)'
            response.geturl.return_value = send_email.SITE_URL
            with self.assertRaises(RuntimeError):
                send_email.wait_for_publication(self.latest, attempts=1, delay=0)
            smtp.assert_not_called()

    def test_publication_exact_hash_without_smtp(self):
        with patch.object(send_email.urllib.request, 'urlopen') as http, \
             patch.object(send_email.smtplib, 'SMTP_SSL') as smtp, \
             contextlib.redirect_stdout(io.StringIO()):
            response = http.return_value.__enter__.return_value
            response.read.return_value = self.page
            response.geturl.return_value = send_email.SITE_URL
            send_email.wait_for_publication(self.latest, attempts=1, delay=0)
            smtp.assert_not_called()

    def test_check_mode_cannot_send(self):
        with patch.object(send_email, 'load_latest', return_value=self.latest), \
             patch.object(send_email, 'wait_for_publication') as wait, \
             patch.object(send_email, 'send') as send:
            send_email.main(['--check-publication'])
            wait.assert_called_once()
            send.assert_not_called()

    def test_send_mode_publication_failure_blocks_send(self):
        with patch.object(send_email, 'load_latest', return_value=self.latest), \
             patch.object(send_email, 'wait_for_publication', side_effect=RuntimeError), \
             patch.object(send_email, 'send') as send:
            with self.assertRaises(RuntimeError):
                send_email.main(['--send'])
            send.assert_not_called()

    def test_header_injection_rejected(self):
        with self.assertRaises(ValueError):
            send_email.build_message(self.latest, 'test@example.com', 'test@example.com\nBcc: injected@example.com')

if __name__ == '__main__':
    unittest.main()
