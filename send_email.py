#!/usr/bin/env python3
"""Send only after deployed GitHub Pages matches latest.json date."""
import datetime as dt
import email.message
import json
import os
import pathlib
import smtplib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
latest = json.loads((ROOT / 'latest.json').read_text(encoding='utf-8'))
url = latest['url']
# GitHub Pages may take a few minutes to deploy after git push.
for attempt in range(20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'RadarRPAIA/1.0'}), timeout=20) as response:
            html = response.read().decode('utf-8', errors='replace')
        if f'Radar RPA & IA — {latest["date"]}' in html:
            break
    except Exception as exc:
        print(f'Pages not ready: {exc}')
    print(f'Waiting for Pages deploy ({attempt+1}/20)')
    time.sleep(30)
else:
    raise RuntimeError('Pages ainda não mostra a edição atual; e-mail não enviado')

sender = os.environ['GMAIL_ADDRESS']
password = os.environ['GMAIL_APP_PASSWORD']
recipient = os.getenv('REPORT_RECIPIENT', sender)
msg = email.message.EmailMessage()
msg['Subject'] = f'Radar RPA & IA | Edição {latest["date"]}'
msg['From'] = sender
msg['To'] = recipient
msg.set_content(f'''Olá!\n\nA nova edição do Radar RPA & IA está publicada.\n\nResumo executivo:\n{latest['summary']}\n\nLeia o relatório completo: {url}\n\nBoa leitura!\n''')
with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
    smtp.login(sender, password)
    smtp.send_message(msg)
print('E-mail enviado após confirmação da publicação no Pages.')
