#!/usr/bin/env python3
"""Weekly RPA radar. Python stdlib only; Groq via OpenAI-compatible HTTP API."""
import datetime as dt
import email.utils
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent
TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()
STAMP = TODAY.isoformat()
SITE_URL = os.getenv('SITE_URL', 'https://maikonfcosta.github.io/radar-rpa-ia/').rstrip('/') + '/'
MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
FEEDS = [
    ('Python Insider', 'Python', 'https://blog.python.org/feeds/posts/default?alt=rss'),
    ('UiPath Blog', 'UiPath', 'https://www.uipath.com/blog/feed'),
    ('Power Automate Blog', 'Power Automate', 'https://www.microsoft.com/en-us/power-platform/blog/power-automate/feed/'),
    ('Automation Anywhere Blog', 'Automation Anywhere', 'https://www.automationanywhere.com/company/blog/rss.xml'),
    ('Microsoft Power Platform Blog', 'Power Automate', 'https://www.microsoft.com/en-us/power-platform/blog/feed/'),
    ('Google AI Blog', 'GenAI', 'https://blog.google/technology/ai/rss/'),
]

def fetch(url, timeout=18):
    req = urllib.request.Request(url, headers={'User-Agent': 'RadarRPAIA/1.0 (+GitHub Actions)', 'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*'})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read(1_500_000)

def node_text(node, names):
    for name in names:
        x = node.find(name)
        if x is not None and x.text:
            return x.text.strip()
    return ''

def parse_feed(raw, category, source):
    root = ET.fromstring(raw)
    entries = root.findall('.//item') or root.findall('{http://www.w3.org/2005/Atom}entry')
    out = []
    for e in entries[:15]:
        title = node_text(e, ['title', '{http://www.w3.org/2005/Atom}title'])
        link = node_text(e, ['link'])
        if not link:
            for l in e.findall('{http://www.w3.org/2005/Atom}link'):
                if l.attrib.get('rel', 'alternate') == 'alternate':
                    link = l.attrib.get('href', '')
                    break
        published = node_text(e, ['pubDate', '{http://www.w3.org/2005/Atom}published', '{http://www.w3.org/2005/Atom}updated'])
        date = None
        try:
            date = email.utils.parsedate_to_datetime(published).date()
        except Exception:
            try:
                date = dt.date.fromisoformat(published[:10])
            except Exception:
                pass
        if title and link and link.startswith('https://') and date and 0 <= (TODAY-date).days <= 14:
            out.append({'title': re.sub('<[^>]+>', '', title), 'url': link, 'date': date.isoformat(), 'category': category, 'source': source})
    return out

def collect():
    stories, seen = [], set()
    for name, category, url in FEEDS:
        try:
            items = parse_feed(fetch(url), category, name)
            print(f'{name}: {len(items)} recent articles')
            for item in items:
                if item['url'] not in seen:
                    seen.add(item['url'])
                    stories.append(item)
        except Exception as exc:
            print(f'Feed unavailable ({name}): {exc}', file=sys.stderr)
    return sorted(stories, key=lambda x: x['date'], reverse=True)[:35]

def generate_briefing(items):
    key = os.getenv('GROQ_API_KEY')
    if not key:
        raise RuntimeError('GROQ_API_KEY não configurada')
    prompt = '''Você é um analista sênior de RPA e IA. Crie um briefing TÉCNICO em português brasileiro para um desenvolvedor de Automation Anywhere, UiPath, Power Automate, Python e GenAI. Use SOMENTE os títulos, URLs, datas e fontes fornecidos. NÃO invente versões, lançamentos, números, funcionalidades ou notícias. Se a lista for escassa, diga isso. Retorne APENAS JSON válido com as chaves: "executive_summary" (string, 2-4 frases), "highlights" (array de até 8 objetos com "title", "category", "impact", "technical_detail", "action", "url"), "next_actions" (array de exatamente 3 strings). Cada highlight deve corresponder a um item da lista, preservando exatamente a URL; diferencie notícia publicada de lançamento confirmado. Escreva de forma objetiva, útil e tecnicamente rigorosa. Não trate um título de blog como prova de lançamento de produto.''' 
    payload = {'model': MODEL, 'temperature': 0.2, 'response_format': {'type': 'json_object'}, 'messages': [{'role':'system','content':prompt},{'role':'user','content':json.dumps({'date': STAMP, 'items': items},ensure_ascii=False)}]}
    req = urllib.request.Request('https://api.groq.com/openai/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Authorization':f'Bearer {key}', 'Content-Type':'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=90) as response:
        obj = json.load(response)
    result = json.loads(obj['choices'][0]['message']['content'])
    valid = {i['url']: i for i in items}
    highlights = []
    for item in result.get('highlights', []):
        if isinstance(item, dict) and item.get('url') in valid:
            orig = valid[item['url']]
            highlights.append({**orig, 'impact':str(item.get('impact','')), 'technical_detail':str(item.get('technical_detail','')), 'action':str(item.get('action',''))})
    result['highlights'] = highlights[:8]
    result['next_actions'] = [str(x) for x in result.get('next_actions', [])][:3]
    return result

def render(data, count):
    esc = lambda v: html.escape(str(v), quote=True)
    highlights = data['highlights']
    cards = []
    for i in highlights:
        cards.append(f'''<article class="card" data-category="{esc(i['category'])}"><div class="meta"><span class="pill">{esc(i['category'])}</span><span>{esc(i['source'])} · {esc(i['date'])}</span></div><h3>{esc(i['title'])}</h3><p><b>Impacto:</b> {esc(i['impact'])}</p><details><summary>Detalhes técnicos e ação</summary><p>{esc(i['technical_detail'])}</p><p><b>Aplicação prática:</b> {esc(i['action'])}</p></details><a href="{esc(i['url'])}" target="_blank" rel="noopener noreferrer">Ler fonte original ↗</a></article>''')
    actions = ''.join(f'<li>{esc(x)}</li>' for x in data['next_actions'])
    empty = '<p class="empty">Nenhum destaque pôde ser confirmado nas fontes consultadas. Consulte os links oficiais antes de tomar decisões técnicas.</p>' if not cards else ''
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Radar técnico semanal de RPA e IA com fontes verificáveis"><title>Radar RPA & IA — {STAMP}</title><style>:root{{color-scheme:dark;--bg:#0a1020;--card:#172238;--line:#30435d;--text:#edf4ff;--muted:#b5c6de;--accent:#71f0ca}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:radial-gradient(circle at 85% 0%,#24456b,transparent 40%),var(--bg);font:16px/1.6 system-ui,sans-serif;color:var(--text)}}.wrap{{max-width:1100px;margin:auto;padding:26px}}header{{padding-top:55px}}h1{{font-size:clamp(2.3rem,6vw,4.5rem);letter-spacing:-.05em;line-height:1.1;margin:12px 0}}h2{{margin-top:34px}}p{{color:var(--muted)}}.eyebrow{{color:var(--accent);font-weight:700;letter-spacing:.15em;text-transform:uppercase;font-size:.75rem}}.lead{{font-size:1.15rem;max-width:800px}}.stats{{display:flex;flex-wrap:wrap;gap:10px;margin:26px 0}}.stat,.card,.panel{{border:1px solid var(--line);background:var(--card);border-radius:18px;padding:22px}}.stat{{min-width:160px}}.stat strong{{display:block;font-size:1.6rem}}.stat span,.meta{{color:var(--muted);font-size:.83rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:16px}}.card{{transition:transform .2s,border-color .2s;animation:up .45s both}}.card:hover{{transform:translateY(-3px);border-color:var(--accent)}}.card h3{{line-height:1.3}}.meta{{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}}.pill{{background:#174b49;color:#b6ffe6;border-radius:99px;padding:4px 10px}}a{{color:var(--accent)}}a:focus-visible,button:focus-visible{{outline:3px solid var(--accent);outline-offset:3px}}.filters{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}}button{{border:1px solid var(--line);background:#1a2b44;color:var(--text);padding:9px 15px;border-radius:30px;cursor:pointer}}button[aria-pressed=true]{{background:var(--accent);color:#082420;font-weight:700}}details{{margin:15px 0}}summary{{cursor:pointer;color:var(--accent)}}footer{{padding:38px 0;color:var(--muted);font-size:.85rem}}.empty{{padding:24px;border:1px dashed var(--line);border-radius:16px}}#progress{{position:fixed;top:0;left:0;height:4px;width:0;background:var(--accent);z-index:10}}@keyframes up{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:translateY(0)}}}}@media(prefers-reduced-motion:reduce){{*,*:before,*:after{{animation:none!important;transition:none!important;scroll-behavior:auto!important}}}}</style></head><body><div id="progress" aria-hidden="true"></div><header class="wrap"><div class="eyebrow">Inteligência aplicada à automação</div><h1>Radar RPA <span style="color:var(--accent)">& IA</span></h1><p class="lead">Briefing técnico semanal para quem constrói automações. Edição de {STAMP} · leitura estimada: 10–15 min.</p><div class="stats"><div class="stat"><strong>{len(highlights)}</strong><span>destaques com fonte</span></div><div class="stat"><strong>{count}</strong><span>itens recentes coletados</span></div><div class="stat"><strong>5</strong><span>áreas acompanhadas</span></div></div></header><main class="wrap"><section class="panel"><h2>Visão executiva</h2><p>{esc(data.get('executive_summary','Não foi possível sintetizar notícias suficientes.'))}</p></section><section><h2>Novidades e impactos</h2><div class="filters" role="group" aria-label="Filtrar tecnologia"><button aria-pressed="true" data-filter="Todos">Todos</button>{''.join(f'<button aria-pressed="false" data-filter="{esc(x)}">{esc(x)}</button>' for x in ['Automation Anywhere','UiPath','Power Automate','Python','GenAI'])}</div><div class="grid">{''.join(cards)}</div>{empty}</section><section class="panel" style="margin-top:28px"><h2>3 ações práticas</h2><ol>{actions}</ol></section><footer><p>Fontes: links originais nos cards. O conteúdo foi resumido por IA a partir de títulos de feeds públicos e pode conter erros; confirme detalhes e disponibilidade nas publicações oficiais.</p><p><a href="edicoes/{STAMP}.html">Link permanente desta edição</a> · <a href="https://github.com/maikonfcosta/radar-rpa-ia">Código no GitHub</a></p></footer></main><script>document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{{document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));document.querySelectorAll('[data-category]').forEach(c=>c.hidden=b.dataset.filter!=='Todos'&&c.dataset.category!==b.dataset.filter)}}));function progress(){{let d=document.documentElement;document.getElementById('progress').style.width=(100*scrollY/Math.max(1,d.scrollHeight-innerHeight))+'%'}}addEventListener('scroll',progress,{{passive:true}});progress();</script></body></html>'''

def main():
    items = collect()
    if not items:
        print('Nenhum item recente coletado; não publicar briefing vazio.', file=sys.stderr)
        sys.exit(2)
    data = generate_briefing(items)
    if not data['highlights']:
        print('A IA não retornou destaques com links válidos; não publicar.', file=sys.stderr)
        sys.exit(3)
    page = render(data, len(items))
    (ROOT / 'index.html').write_text(page, encoding='utf-8')
    archive = ROOT / 'edicoes' / f'{STAMP}.html'
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(page.replace(f'href="edicoes/{STAMP}.html"', f'href="{SITE_URL}edicoes/{STAMP}.html"'), encoding='utf-8')
    (ROOT / 'latest.json').write_text(json.dumps({'date':STAMP,'url':SITE_URL,'summary':data.get('executive_summary',''),'highlights':len(data['highlights'])},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Generated {archive} and index.html')

if __name__ == '__main__':
    main()
