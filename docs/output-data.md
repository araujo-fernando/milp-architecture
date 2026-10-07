# Saída: conteúdos canônicos JSON e Excel

`ReportProjector` recebe `ProblemData`, `RoutingSolution` e `PipelineConfig` e
produz um `ReportData` com registros concretos tipados. `ReportWriter` publica os
mesmos registros em seis JSONs e seis abas de `report.xlsx`. O Excel usa
XlsxWriter em `constant_memory`, escrito linha por linha, sem DataFrames.

## Diretório de execução

A CLI publica em `cenário/runs/RUN-<UTC>-<UUID>/` e conserva `cenário/output.json`
como cópia do agregado da última execução. Cada execução possui identidade
independente, inclusive quando ocorre no mesmo segundo.

| Arquivo | Aba Excel | Grão |
| --- | --- | --- |
| `resumo.json` | `resumo` | Uma linha com identidade, configuração, status e KPIs |
| `rotas.json` | `rotas` | Uma linha por rota efetivamente atendida |
| `paradas.json` | `paradas` | Depósito, clientes ordenados e retorno de cada rota |
| `objetivos.json` | `objetivos` | Uma linha por etapa e split, incluindo tentativas anteriores |
| `splits.json` | `splits` | Membros, frota reservada, status e tamanho de cada split |
| `diagnostico.json` | `diagnostico` | Código, mensagem, entidade, split e severidade |

Os JSONs são arrays de registros, inclusive `resumo.json`. Conteúdos sem linhas
são `[]`; suas abas conservam os cabeçalhos. O manifesto informa colunas e
contagens para cada conteúdo. Os nomes e a ordem de colunas vêm das dataclasses
em `report/data.py`, compartilhadas pelos writers.

Também são publicados `output.json`, `manifest.json` e, se existirem, os LPs e
logs copiados de `work/<RUN-ID>/` para `solver/`. O diretório `work` contém
artefatos da computação e pode permanecer após a publicação.

## Campos e interpretação

`resumo` inclui `id_execucao`, `gerado_em` em UTC, SHA-256 completo,
`versao_schema=2.0.0`, instância/CD/data, moeda, backend, status, clientes
elegíveis/atendidos, frota disponível/usada, demandas/capacidades em kg e m³,
custos fixo/variável/total, distância, cargas atendidas, paradas, equilíbrio,
tempos e tamanho dos modelos. Tempos de build/solve somam tentativas anteriores
e finais, uma vez por resultado. Contagens de variáveis, restrições e não zeros
somam somente a partição final; os registros de splits mantêm esses tamanhos por
tentativa para auditoria. `configuracao`, `tempos` e `pos_processamento`
são textos JSON canônicos nas duas representações.

`rotas` inclui veículo físico e tipo, capacidades, distância, carga nas duas
dimensões, custos, percentuais de ocupação e número de paradas. `paradas`
identifica `id_rota`, `veiculo_id`, sequência iniciada em zero, nó, tipo
(`deposito`, `cliente`, `retorno`), nome, demandas, pedidos, distância do arco
de chegada, distância acumulada e custo desse arco. Custo fixo fica na rota.

`objetivos` mantém `valor`, `bound`, `gap`, tempo, status, existência de
incumbente, ótimo comprovado, custo e equilíbrio recalculados e limite de custo.
Valor/bound/gap sem informação são `null`. `splits` conserva listas de clientes
e veículos mesmo se não houver solução. Os campos `tentativa` e
`resultado_final` distinguem histórico anterior e partição final: certificados
anteriores não certificam a solução publicada. Pós-processamento pode mudar a
rota de um cliente entre splits; os membros publicados descrevem a partição
resolvida, enquanto as rotas descrevem a solução final.

O atendimento e as cargas globais vêm das rotas publicadas. Uma execução
`partial` contabiliza apenas os clientes efetivamente atendidos. `no_incumbent`
não gera rotas. Uma entrada inválida gera `invalid_input`, diagnóstico, conteúdos
vazios e hash vazio, pois nenhum problema canônico foi construído. Contagens e
KPIs zerados nesse caso descrevem a ausência de solução publicada.

## Paridade e limites

Listas de pedidos, clientes e veículos são arrays no JSON e texto de array JSON
nas células Excel; decodificar esse texto recupera a lista sem perda de membros.
`null` corresponde à célula em branco, booleanos a células booleanas e números
a células numéricas. Comparações numéricas admitem a precisão decimal do Excel.
Textos são escritos como texto, inclusive quando começam com `=` ou parecem URL.

Uma aba admite 1.048.576 linhas, incluindo o cabeçalho, e 16.384 colunas. Células
admitem 32.767 unidades UTF-16. Se qualquer conteúdo ultrapassar um limite, a
publicação falha com mensagem explícita: não há truncamento ou particionamento
implícito. JSON não admite NaN/infinito.

## Publicação e identidade

O writer valida limites, escreve todos os arquivos num diretório temporário
irmão, fecha o Excel, calcula checksums e escreve o manifesto de conclusão.
Somente então renomeia o diretório para o nome definitivo. Uma falha remove o
temporário e preserva execuções já publicadas. Reutilizar um ID existente é erro.

`manifest.json` contém versão do schema, ID, timestamp, hash, `completed=true`,
contagens, mapeamento JSON/aba/colunas, regra de células e caminho/tamanho/SHA-256
de cada arquivo, incluindo artefatos do solver. O manifesto não inclui checksum
de si próprio. Leitores devem consumir diretórios finais com manifesto completo.

O hash usa JSON canônico ordenado do depósito, clientes, pedidos, frota,
geografia, overrides direcionais, circulação, custos, moeda e configuração
relevante. IDs e listas sem ordem semântica são ordenados. Caminho de saída,
exibição do log e opção de exportar LP são excluídos; backend, seed, políticas e
orçamentos entram no hash. Não se usa `repr` de objetos ou mapas.

## Agregado compatível

`output.json` conserva `execucao`, `status_solver`, `instancia_resumo`,
`kpis_globais`, `rotas` e `diagnostico`, e acrescenta `objetivos`, `splits`,
`pos_processamento` e `tempos`. Cada rota contém `veiculo`, `kpis` e `paradas`.
`status_solver.objetivo` é sempre o custo das rotas finais; bounds/gaps de cada
FO aparecem exclusivamente no histórico de objetivos. A API
`CVRPPipeline.run()` devolve esse envelope; `solve()` devolve `RoutingSolution`.
