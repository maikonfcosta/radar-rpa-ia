#!/usr/bin/env python3
"""Gmail notification; no SMTP or HTTP unless explicitly requested via CLI."""
import argparse
import email.message
import email.utils
import hashlib
import json
import os
import pathlib
import re
import smtplib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
SITE_URL = 'https://maikonfcosta.github.io/radar-rpa-ia/'

def load_latest(root=ROOT):
    if not (root / 'latest.json').is_file():
        raise RuntimeError('Nenhuma edição automática registrada (latest.json ausente); '
                           'execute primeiro com publish_current=false e send_email=false')
    latest = json.loads((root / 'latest.json').read_text(encoding='utf-8'))
    if latest.get('url') != SITE_URL:
        raise ValueError('URL de publicação inesperada')
    if not isinstance(latest.get('date'), str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', latest['date']):
        raise ValueError('Data de edição inválida')
    if not isinstance(latest.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', latest['sha256']):
        raise ValueError('Hash de edição inválido')
    if not isinstance(latest.get('summary'), str):
        raise ValueError('Resumo inválido')
    if hashlib.sha256((root / 'index.html').read_bytes()).hexdigest() != latest['sha256']:
        raise ValueError('HTML local não corresponde à edição esperada')
    return latest

def wait_for_publication(latest, attempts=20, delay=30):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                latest['url'] + '?edition=' + latest['sha256'],
                headers={'User-Agent': 'RadarRPAIA/1.0', 'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.geturl().split('?')[0] != latest['url']:
                    raise ValueError('Redirecionamento de publicação inesperado')
                published = response.read(2_000_001)
            if hashlib.sha256(published).hexdigest() == latest['sha256']:
                print('Publicação confirmada pelo SHA-256 da edição.')
                return
        except (OSError, ValueError):
            pass
        print(f'Aguardando publicação ({attempt + 1}/{attempts})')
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise RuntimeError('Pages não contém o HTML esperado; e-mail não enviado')

def address(value):
    if '\r' in value or '\n' in value:
        raise ValueError('Endereço de e-mail inválido')
    _, parsed = email.utils.parseaddr(value)
    if parsed != value or not re.fullmatch(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+', value):
        raise ValueError('Informe um único endereço de e-mail válido')
    return value

def build_message(latest, sender, recipient):
    msg = email.message.EmailMessage()
    msg['Subject'] = f'Radar RPA & IA | Edição {latest["date"]}'
    msg['From'] = address(sender)
    msg['To'] = address(recipient)
    msg.set_content(f'Olá!\n\nA nova edição do Radar RPA & IA está publicada.\n\n'
                    f'Resumo executivo:\n{latest["summary"]}\n\n'
                    f'Leia o relatório completo: {latest["url"]}\n\nBoa leitura!\n')
    return msg

def send(latest):
    sender = os.environ.get('GMAIL_ADDRESS')
    password = os.environ.get('GMAIL_APP_PASSWORD')
    if not sender or not password:
        raise RuntimeError('Configure GMAIL_ADDRESS e GMAIL_APP_PASSWORD em Actions Secrets')
    recipient = os.getenv('REPORT_RECIPIENT') or sender
    msg = build_message(latest, sender, recipient)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print('E-mail enviado após confirmação da publicação.')

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--send', action='store_true', help='Confirmar publicação e enviar por Gmail')
    mode.add_argument('--check-publication', action='store_true', help='Consultar Pages sem usar SMTP')
    mode.add_argument('--dry-run', action='store_true', help='Validar arquivos locais sem rede (padrão)')
    args = parser.parse_args(argv)
    latest = load_latest()
    if not args.send and not args.check_publication:
        print('Dry run: edição local válida; nenhuma conexão HTTP ou SMTP realizada.')
        return
    wait_for_publication(latest)
    if args.send:
        send(latest)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # RuntimeError contém apenas orientações locais; erros SMTP permanecem sem detalhes.
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f'Falha: {detail}; nenhuma informação de credencial registrada.', file=sys.stderr)
        sys.exit(1)
