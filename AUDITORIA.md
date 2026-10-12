# Auditoria — maikonfcosta/radar-rpa-ia

Análise em 12/10/2026, baseada na branch `main`, commit `a7359a19d0480fc9dc3263dfc571ae53beb66b44`.

## Resultado e limites

A integração lê o repositório, mas não conseguiu criar uma branch: recebeu **HTTP 403 — Resource not accessible by integration**. As alterações foram preparadas **somente no workspace**. Nenhuma branch, commit ou PR remoto foi criado; não foram alteradas permissões, secrets, proteção de branch, Pages ou configurações de segurança. Nenhum e-mail foi enviado.

## Evidências de acesso

| Verificação | Resultado |
| --- | --- |
| Metadados do repositório | Público, ativo, branch padrão main |
| Identidade retornada pelo conector | maikonfcosta |
| Permissões informadas nos metadados | admin, maintain e push verdadeiros |
| Árvore recursiva de main | Somente README.md, generate.py, send_email.py e index.html |
| Listagem de instalações pelo conector | Lista vazia; não comprova ausência de instalação nem suas permissões efetivas |
| Criar branch codex/weekly-radar-automation a partir do commit analisado | HTTP 403, Resource not accessible by integration; branch não criada |
| Consultar proteção de main | HTTP 403, Resource not accessible by integration |
| Listar rulesets do repositório | Lista vazia; não exclui proteção de branch clássica |
| Consultar configuração detalhada de Pages / Actions workflow permissions | O conector rejeita esses endpoints por sua própria lista de URLs permitidas; não foi uma confirmação de permissão GitHub |
| Git clone no executor | Falha de conexão com o proxy; snapshot local obtido por leitura dos arquivos via conector |

O erro de criação de uma branch nova demonstra que a escrita está bloqueada na autorização efetiva da integração, independentemente da configuração de `GITHUB_TOKEN`. A indicação `admin/push` do usuário nos metadados não concede esses poderes ao token usado pelo aplicativo. A causa específica entre permissão de Contents, escopo da instalação e restrição da conexão não pôde ser distinguida com os endpoints acessíveis.

Não foi necessário criar um arquivo em main para reproduzir o bloqueio. A tentativa de branch de trabalho foi suficiente e evitou alterações no dashboard publicado.

## Permissões a revisar pelo proprietário

| Operação | Permissão da conexão GitHub |
| --- | --- |
| Ler código | Contents: read |
| Criar/editar arquivos e branches | Contents: write e acesso a este repositório |
| Criar/editar arquivos em .github/workflows | Contents: write + Workflows: write |
| Abrir PR com a proposta | Pull requests: write |
| Consultar proteção clássica da branch | Administration: read |
| Consultar configurações de Actions | Administration: read, conforme endpoint |
| Consultar origem do Pages | Pages: read |
| Solicitar build do Pages existente | Pages: write |

Essas permissões pertencem à conexão/app. Não confundir com as permissões do token temporário de cada job. Administration não é necessária à automação proposta; serve apenas à inspeção de configurações restritas. Não é necessário conceder acesso geral à conta ou desabilitar proteções.

O proprietário deve revisar a instalação/conexão GitHub, a seleção deste repositório e eventuais permissões atualizadas pendentes de aceitação. Se o conector disponível não oferecer escrita/Workflows, os arquivos podem ser aplicados pelo próprio proprietário por GitHub/Git, sem contornar a restrição da integração.

## Pages e dashboard existente

O repositório retorna `has_pages: true`. Há duas execuções de **pages build and deployment** concluídas com sucesso:

- [Execução 38289843815](https://github.com/maikonfcosta/radar-rpa-ia/actions/runs/38289843815), commit analisado, concluída em 12/10/2026 às 18:17 UTC.
- [Execução 38284527433](https://github.com/maikonfcosta/radar-rpa-ia/actions/runs/38284527433), publicação anterior.

Isso confirma Pages habilitado e publicações recentes bem-sucedidas. Não confirma por si só a origem exata main / nem o conteúdo atualmente servido na URL pública. A consulta direta da página pública não pôde ser concluída pelas ferramentas disponíveis. A proposta verifica origem e URL antes de gerar qualquer edição.

A inspeção do HTML original encontrou uma edição estática de 12/10/2026: quatro cards, filtros por tecnologia, detalhes expansíveis, painel Microsoft, plano de ação e links oficiais. Há CSS responsivo e tratamento de movimento reduzido. O conteúdo é embutido no HTML; não existe atualização automática nem histórico navegável no snapshot analisado.

O HTML original foi preservado byte a byte na home e em `edicoes/2026-10-12-inicial.html`. Suas afirmações técnicas não foram revalidadas contra cada release note nesta análise. A renderização visual foi tentada, mas Chromium/Playwright falhou sob as restrições do executor; filtro e layout não foram verificados em navegador.

## Alterações locais preparadas

- `.github/workflows/weekly-radar.yml`: cron de segunda-feira às 11:00 UTC, execução manual com dry run por padrão, etapas isoladas de geração, commit, publicação e notificação; recuperação sem regenerar uma edição existente.
- `.github/workflows/check.yml`: testes em PRs e alterações relevantes em main, com token de leitura e sem secrets.
- `generate.py`: coleta RSS/Atom de fontes oficiais, validação de HTTPS/domínios/datas, excertos limitados, filtro do feed amplo da Microsoft, validação da resposta Groq, HTML escapado, metadados originais preservados, evidências JSON e histórico imutável.
- `send_email.py`: nenhum efeito ao importar; dry run padrão sem rede; publicação confirmada pelo SHA-256 exato antes de SMTP; validação de destinatário; sem logs de credenciais ou respostas SMTP.
- `edicoes/`: arquivo da edição original e índice inicial; futuras edições recebem HTML e JSON.
- `tests/test_radar.py`: 17 testes seguros.
- `README.md`: instalação, permissões mínimas, autorização do Gmail, recuperação e limitações.
- `.gitignore`: exclui outputs temporários, caches, configuração intermediária e .env.

## GITHUB_TOKEN e permissões dos workflows

No snapshot original não há workflow semanal; portanto não há declaração `contents: write` a confirmar nele. A configuração padrão do token no repositório não pôde ser lida pelo conector.

Na proposta:

| Job | Permissões |
| --- | --- |
| generate | contents: read; pages: read |
| commit | contents: write |
| publish | contents: read; pages: write |
| notify | contents: read |
| CI | contents: read |

Permissões globais vazias no workflow semanal, sem `write-all`, sem Administração, sem secrets write e sem `id-token: write`. Actions externas fixadas por SHAs, comparados às tags oficiais. Groq e Gmail recebem secrets somente nas suas etapas. O workflow não imprime tokens nem consulta valores de secrets.

Como commits do `GITHUB_TOKEN` não disparam o build automático de Pages, o job publish solicita um build pela API com `pages: write`. A proposta mantém publicação por branch e não altera Settings → Pages. O job commit usa push normal, sem force, e falha se main mudar durante a geração ou se a proteção impedir o push.

Não se recomenda ampliar permissões padrão de todos os workflows para resolver o 403 do ChatGPT. As permissões efetivas desta proposta devem ser conferidas nos logs **GITHUB_TOKEN Permissions** após sua aplicação e uma execução autorizada.

## Testes executados

| Verificação | Resultado |
| --- | --- |
| python -m unittest discover -s tests -v | **17/17 passaram** |
| Compilação Python de scripts e testes | Passou |
| Parsing YAML dos dois workflows | Passou |
| bash -n nos comandos dos workflows | Passou |
| git diff --check | Passou |
| Comparação dos bytes da home e arquivo da edição original | Passou |
| Comparação dos SHAs de checkout/setup-python/upload-artifact/download-artifact com tags oficiais | Passou |
| Consultas reais aos seis feeds usando HTTP herdado do ambiente | Todas falharam com URLError por conectividade do executor; disponibilidade em Actions permanece pendente |
| Browser original/gerado | Bloqueado pelo ambiente; não houve validação visual |
| Chamada real da Groq, execução remota dos workflows, publicação nova | Não executadas |
| Autenticação SMTP e envio Gmail | Não executados |

Os testes usam dados fictícios, mocks de HTTP/SMTP e diretórios temporários. Cobrem RSS/Atom, datas, URLs maliciosas, respostas incompletas, URLs inventadas, deduplicação, HTML escapado, persistência do histórico, preservação da home e impedimento de envio com publicação incorreta. As prévias de teste não são edições reais nem fazem parte do pacote.

## Pendências para operação real

1. Revisar autorização da integração ou aplicar a proposta manualmente; o 403 impede salvar a proposta/abrir PR pelo conector atual.
2. Confirmar origem real do Pages como main /; adaptar se diferente, com autorização do proprietário.
3. Confirmar existência/validade de GROQ_API_KEY e disponibilidade/cota do modelo. Não houve acesso aos valores nem confirmação da afirmação antiga do README de que a chave já estava configurada.
4. Confirmar políticas de Actions, token efetivo contents: write no job commit, pages: write no job publish e regras de branch. Não desabilitar proteção para permitir o bot.
5. Executar o workflow manual com dry_run=true, send_email=false e inspecionar os feeds/modelo/artefato; os endpoints UiPath e Automation Anywhere especialmente precisam de confirmação ao vivo.
6. Validar publicação real com dry_run=false, send_email=false, após aplicar/revisar a proposta.
7. Configurar os secrets Gmail e destinatário; obter autorização antes de um primeiro envio real. EMAIL_ENABLED só deve ser habilitado após essa autorização.

A execução agendada pode ser atrasada/desativada pelo GitHub; resumos por IA exigem revisão editorial. SMTP não garante exatamente uma entrega; recuperação manual pode duplicar mensagem já aceita pelo Gmail. Não há teste de envio ou repetição automática de SMTP.

## Referências oficiais

- [HTTP Resource not accessible](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#resource-not-accessible)
- [Criar/atualizar arquivos e workflows](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents)
- [Criar referências/branches](https://docs.github.com/en/rest/git/refs#create-a-reference)
- [Ler proteção de branch](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection)
- [GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
- [Solicitar build Pages](https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build)
