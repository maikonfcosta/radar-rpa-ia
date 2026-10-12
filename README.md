# Radar RPA & IA — automação semanal com Groq

Automação de briefing técnico semanal em português, com dashboard HTML no GitHub Pages, histórico de edições e e-mail após publicação.

## Instalação

1. Copie `generate.py`, `send_email.py` e a pasta `.github` (com sua estrutura) para a raiz do repositório `maikonfcosta/radar-rpa-ia`. **Não substitua o `index.html` atual**; a automação o atualizará na primeira execução bem-sucedida.
2. Em **Settings → Secrets and variables → Actions**, configure os secrets:
   - `GROQ_API_KEY` — chave Groq (já configurada pelo usuário).
   - `GMAIL_ADDRESS` — endereço da conta Gmail que enviará os e-mails.
   - `GMAIL_APP_PASSWORD` — **senha de app do Google**, não a senha normal do Gmail. Requer verificação em duas etapas; disponibilidade depende da conta. Crie em https://myaccount.google.com/apppasswords. Não coloque essa senha em arquivos, commits ou mensagens.
3. Em **Settings → Actions → General → Workflow permissions**, permita **Read and write permissions** para `GITHUB_TOKEN` se a organização/conta permitir.
4. Em **Settings → Pages**, mantenha `Deploy from a branch`, `main`, `/ (root)`.
5. Em **Actions → Radar RPA e IA semanal → Run workflow**, faça um teste manual. Confira o commit, a página e o recebimento do e-mail.

## Agendamento

O workflow roda às **11:00 UTC de segunda-feira**, equivalentes a **08:00 em São Paulo** enquanto o fuso for UTC-3. O GitHub pode atrasar execuções agendadas; não há garantia de minuto exato. Se o Brasil voltar a adotar horário de verão, ajuste o cron.

## Segurança e limites

- Groq **não pesquisa notícias por conta própria**: o script primeiro consulta feeds públicos. Só URLs coletadas são aceitas nos destaques. Os feeds podem mudar ou ficar indisponíveis; valide-os nos logs.
- Se nenhum item recente ou nenhum destaque com fonte for encontrado, a execução falha **sem publicar ou enviar e-mail**.
- O conteúdo da IA é um resumo de títulos de feeds, **não uma auditoria de release notes**. Confirme afirmações técnicas nos links originais.
- O e-mail é enviado somente depois que o HTML publicado contém a data da edição nova.
- A chave Groq e a senha de app Gmail ficam apenas nos GitHub Secrets.
- A execução manual pode enviar e-mail; evite rodar repetidamente sem necessidade.
- `GROQ_MODEL` pode ser alterado no workflow se o modelo padrão não estiver disponível para sua conta.

## Diagnóstico

Se aparecer `403` no `git push`, verifique as permissões do `GITHUB_TOKEN` e proteção da branch. Se aparecer `401` na Groq, verifique `GROQ_API_KEY`. Se SMTP falhar, verifique a senha de app e a autenticação em duas etapas. Se o Pages não atualizar dentro de dez minutos, o e-mail não será enviado.
