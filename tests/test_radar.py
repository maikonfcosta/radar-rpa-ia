import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import pathlib
import tempfile
import unittest
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

class Generation(unittest.TestCase):
    def test_generation_archives_evidence_and_preserves_home(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / 'index.html').write_text('existing dashboard')
            (root / 'edicoes').mkdir()
            (root / 'edicoes' / '2026-10-12-inicial.html').write_text('original')
            output = root / 'generated'
            with patch.multiple(generate, ROOT=root, OUTPUT=output), \
                 patch.object(generate, 'collect', return_value=[STORY]), \
                 patch.object(generate, 'generate_briefing', return_value=generate.validate_briefing(copy.deepcopy(BRIEFING), [STORY])), \
                 contextlib.redirect_stdout(io.StringIO()):
                generate.main()
            self.assertEqual((root / 'index.html').read_text(), 'existing dashboard')
            latest = send_email.load_latest(output)
            self.assertEqual(latest['sha256'], hashlib.sha256((output / 'index.html').read_bytes()).hexdigest())
            self.assertEqual((output / 'edicoes' / f'{generate.STAMP}.html').read_bytes(), (output / 'index.html').read_bytes())
            evidence = json.loads((output / 'edicoes' / f'{generate.STAMP}.json').read_text())
            self.assertEqual(evidence['items'][0]['url'], STORY['url'])
            self.assertIn('2026-10-12-inicial.html', (output / 'edicoes' / 'index.html').read_text())

    def test_empty_collection_does_not_replace_dashboard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / 'index.html').write_text('unchanged')
            with patch.multiple(generate, ROOT=root, OUTPUT=root), \
                 patch.object(generate, 'collect', return_value=[]), \
                 patch.object(generate, 'generate_briefing') as groq, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
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

class Notifications(unittest.TestCase):
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
