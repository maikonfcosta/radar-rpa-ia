# Radar RPA & IA — automação semanal com Groq

O dashboard atual é preservado até a primeira edição gerada com sucesso. Os workflows geram HTML, preservam edições e evidências JSON, solicitam a publicação do Pages existente e permitem avisar por Gmail somente após confirmar o HTML publicado.

## Configuração e primeira execução

1. Mantenha os arquivos do repositório, incluindo a pasta oculta `.github/workflows`. Não substitua o dashboard por uma prévia de teste.
2. Confirme em **Settings → Pages** a origem **Deploy from a branch → main → / (root)**. O workflow apenas verifica essa configuração; não a modifica. Se a origem for diferente, adapte a proposta após revisão do proprietário.
3. Configure em **Actions Secrets**: `GROQ_API_KEY`, `GMAIL_ADDRESS` e `GMAIL_APP_PASSWORD`. Use uma senha de app do Google, nunca a senha normal da conta. A existência/validade desses secrets não foi confirmada nesta análise. Nunca cole valores em código ou logs.
4. Em **Actions → Radar RPA e IA semanal → Run workflow**, selecione a branch `main`, mantenha **dry_run=true**, **publish_current=false**, **send_email=false**. Isso chama Groq e gera um artefato revisável, sem commit, publicação nem SMTP.
5. Após revisar o artefato, execute com **dry_run=false** e **send_email=false** para validar a publicação real. Não desabilite proteção de branch se o push for recusado: revise o fluxo de publicação com o proprietário.
6. Habilite avisos semanais apenas após autorização, criando a variável Actions `EMAIL_ENABLED=true`. Sem essa variável, o agendamento publica sem enviar e-mail. Para uma execução manual, `send_email=true` autoriza um envio real; mantenha-o falso durante testes.

`REPORT_RECIPIENT` é uma variável Actions opcional com um único endereço; o padrão é a própria conta `GMAIL_ADDRESS`. `GROQ_MODEL` é opcional; padrão `llama-3.3-70b-versatile`.

## Agendamento e permissões

Segundas-feiras às **11:00 UTC / 08:00 em São Paulo (UTC−3)**. O GitHub pode atrasar o cron e desativá-lo após inatividade em repositórios públicos. Verifique o estado de Actions periodicamente.

O workflow usa `permissions: {}` global e concede somente por job:

| Job | GITHUB_TOKEN |
| --- | --- |
| generate | contents: read, pages: read |
| commit | contents: write |
| publish | contents: read, pages: write |
| notify | contents: read |
| CI de pull request | contents: read |

**Não é necessário ampliar por padrão todos os workflows em Settings para leitura/escrita.** A proposta declara `contents: write` apenas no job que salva a edição. Políticas da conta/organização e proteção de branch continuam valendo. Verifique as permissões efetivas no bloco **GITHUB_TOKEN Permissions** dos logs de inicialização de cada job após uma execução autorizada.

Commits feitos com `GITHUB_TOKEN` não disparam automaticamente um build do Pages. A proposta chama **POST /repos/{owner}/{repo}/pages/builds** com `pages: write`, mantendo a publicação por branch existente. Não usa `id-token: write`, tokens pessoais ou alteração da configuração de Pages.

## Coleta e histórico

- RSS/Atom de domínios oficiais: Python, UiPath, Microsoft e Google AI. UiPath usa `https://www.uipath.com/blog/rss.xml`; como esse feed é extenso, a leitura limita-se a 1,5 MB e processa até 100 itens completos, ignorando o último item truncado.
- Automation Anywhere usa o [blog oficial](https://www.automationanywhere.com/company/blog) e consulta até 12 artigos com metadados JSON-LD. Usa `datePublished`, nunca `dateModified`, para evitar apresentar conteúdo antigo como notícia nova. HTTPS, domínios e datas são validados; itens sem data, futuros, com mais de 14 dias ou URLs externas são descartados.
- O feed geral da Microsoft é filtrado para Power Automate/Copilot Studio.
- Títulos e excertos são enviados à Groq. Os feeds são evidência parcial; os resumos não substituem a leitura das release notes. Não há garantia determinística de exatidão de todas as afirmações produzidas pelo modelo.
- URLs de destaques devem corresponder exatamente às coletadas; título/categoria vêm da fonte. JSON inválido, ausência de fontes recentes ou ausência de destaques válidos bloqueiam a publicação.
- Cada data gera `edicoes/AAAA-MM-DD.html` e `.json` com itens, excertos, modelo e briefing. `edicoes/index.html` lista as edições. A edição original é preservada em `edicoes/2026-10-12-inicial.html`.
- O HTML mostra a cobertura das fontes; o JSON registra estados distintos de fonte disponível, sem notícias recentes, parcial e indisponível. Uma coleta parcial pode gerar edição se houver destaques válidos; indisponibilidade não significa ausência de notícias.
- Uma edição existente não é sobrescrita. A home aponta para a última edição; Git mantém o histórico adicional.
- A confirmação do Pages compara SHA-256 do HTML com `latest.json`; uma página antiga com a mesma data não libera o SMTP.
- O HTML é escrito com os mesmos bytes UTF-8 usados no hash, evitando divergências de quebras de linha entre Windows e Linux.
- Secrets só entram nas etapas que precisam deles. Artefatos contêm somente conteúdo editorial público. Actions externas estão fixadas por SHA.

## Recuperação

Se o commit da edição concluir e o Pages ou Gmail falhar, execute manualmente com **publish_current=true**, **dry_run=false** e **send_email=false**. Isso republica a edição já registrada sem chamar Groq ou sobrescrever seu histórico. Só habilite envio manual após revisão do estado anterior.

A recuperação exige `latest.json` e HTML correspondente de uma edição automática já registrada. O dashboard inicial sozinho não permite recuperação. Para gerar a primeira edição, use **publish_current=false**; valide primeiro com **dry_run=true**.

O envio SMTP não oferece garantia de exatamente uma entrega: um erro após aceitação pelo Gmail ou uma repetição manual pode duplicar mensagens. Não há repetição automática de envio no script.

## Testes locais seguros

```sh
python -m unittest discover -s tests -v
python -m py_compile generate.py send_email.py
```

Os testes simulam APIs e SMTP, usam diretórios temporários e não enviam mensagens. `send_email.py` sem flags é um dry run sem rede, mas requer uma edição gerada válida em `latest.json`. `--check-publication` consulta HTTP sem SMTP; `--send` permite envio real.

O CI executa Python 3.12 em Ubuntu e Windows. Os testes cobrem geração, hash, coleta parcial, metadados oficiais e falhas de rede/JSON/HTTP da Groq. Os diagnósticos distinguem autenticação (401), acesso (403), limite de uso (429) e indisponibilidade (5xx), sem imprimir resposta HTTP nem credenciais. A validação com mocks não confirma chave, cota, publicação nova ou entrega SMTP; esses passos exigem execução real.

## HTTP 403 da integração ChatGPT

Permissões do usuário, token da integração ChatGPT e `GITHUB_TOKEN` são autorizações distintas. `contents: write` no YAML não concede escrita à integração ChatGPT.

Para criar arquivos/branches, a conexão GitHub precisa de acesso a este repositório e **Contents: read and write**. Para adicionar/alterar `.github/workflows/*`, precisa também de **Workflows: write**. Abrir PR exige **Pull requests: write**. Ler proteção de branch pode exigir **Administration: read**; isso não é necessário para gerar/publicar a edição.

A escrita da integração foi negada com HTTP 403 nesta análise. Nenhuma permissão, secret, proteção de branch ou configuração de segurança foi alterada. Veja `AUDITORIA.md` para evidências, testes e pendências.

Referências: [Contents API](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents), [permissões GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token), [Pages build API](https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build).
