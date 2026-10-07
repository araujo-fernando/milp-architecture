# CVRP: pipeline de otimização com CPLEX e Docplex

Template executável que transforma JSON operacional em problema canônico,
valida dados, divide clientes, resolve duas prioridades, audita e melhora rotas
e publica JSONs/Excel com o mesmo conteúdo. Os dois backends estão em módulos
específicos: `builder_docplex.py` usa a API algébrica, e `builder_cplex.py` usa a
API matricial CPLEX. A formulação tem frota heterogênea, peso/volume, custos
fixo/variável, circulação e MTZ compacto.

A [revisão e plano](docs/review-and-plan.md) registra a auditoria histórica de
2026-10-07. O comportamento entregue está em [arquitetura](docs/architecture.md),
[modelo matemático](docs/model.md) e [saída](docs/output-data.md).

## Instalar

Requer Python 3.12+, uv e runtime/licença CPLEX compatíveis com `cplex==22.2.0.0`.
Na raiz do repositório:

```bash
uv sync --group dev
```

## Executar

Cada cenário contém `input.json`; o [contrato de entrada](docs/input-data.md)
descreve os dados operacionais. Para executar ambos os backends:

```bash
uv run cvrp caminho/do/cenario CD-BH01 --date 2026-08-07 --backend docplex
uv run cvrp caminho/do/cenario CD-BH01 --date 2026-08-07 --backend cplex
```

Se `--date` for omitido, usa a data de referência do JSON. A execução modular é
equivalente:

```bash
uv run python -m cvrp caminho/do/cenario CD-BH01 --backend docplex
```

Por padrão, são desejados quatro clusters, executados sequencialmente, com
30 s de solve por split, gap 1%, um thread e 5 s de pós-processamento. Use
`--clusters 1` para resolver o problema único. Exemplo paralelo com limites
explícitos e exportação das duas FOs em LP:

```bash
uv run cvrp caminho/do/cenario CD-BH01 --backend cplex --clusters 4 \
  --parallel --workers 2 --threads 1 --cpu-budget 4 --memory-budget-mb 4096 \
  --time-limit 30 --total-seconds 120 --mip-gap 0.01 \
  --abs-tol 0.000001 --rel-tol 0 --post-seconds 5 --seed 42 --export-lp
```

`--distance-mode provided_only` restringe o grafo aos arcos direcionais do JSON;
o padrão `complete_with_geography` completa distâncias com haversine.
`--cplex-log` exibe o log nativo. Todas as opções podem ser consultadas com:

```bash
uv run cvrp --help
```

O deadline é cooperativo, e o time limit por split cobre as duas FOs. Build,
clustering e escrita também consomem tempo; a execução sequencial pode somar
orçamentos de vários splits e tentativas. Paralelismo depende de CPUs, memória
e licença. Partições e resultados locais não certificam ótimo global.

## Artefatos

Cada execução publica `runs/RUN-<UTC>-<UUID>/` no diretório do cenário:

| Arquivo | Conteúdo |
| --- | --- |
| `resumo.json`, `rotas.json`, `paradas.json` | Execução, KPIs e atendimento |
| `objetivos.json`, `splits.json`, `diagnostico.json` | FOs, membros, histórico e avisos |
| `report.xlsx` | Seis abas com os mesmos registros |
| `output.json` | Envelope agregado compatível |
| `manifest.json` | Schema, contagens, arquivos e checksums SHA-256 |
| `solver/` | Cópias dos logs e LPs da computação, quando existentes |

`output.json` no diretório do cenário contém o agregado da última execução.
Conteúdos vazios conservam cabeçalhos no Excel. A publicação escreve temporários
e renomeia o diretório somente após conclusão; não sobrescreve execuções
anteriores. Limites do Excel produzem erro explícito, sem truncamento.

`feasible` significa solução completa auditada; `empty` não chama o solver.
Resultados parciais ou sem incumbente são publicados com diagnóstico e a CLI
retorna código 1. Entrada inválida gera relatório `invalid_input` e código 2.
Na biblioteca, erros de entrada continuam levantando `InputError`.

## Biblioteca

```python
import json
from pathlib import Path

from cvrp import CVRPPipeline, PipelineConfig
from cvrp.io.writer import ReportWriter

scenario = Path("caminho/do/cenario")
raw = json.loads((scenario / "input.json").read_text(encoding="utf-8"))
config = PipelineConfig(backend="docplex", clusters=4, output_dir=scenario)
pipeline = CVRPPipeline(raw, "CD-BH01", "2026-08-07", config=config)
solution = pipeline.solve()  # RoutingSolution tipado
assert pipeline.problem is not None
published = ReportWriter.write(pipeline.problem, solution, config)
```

`CVRPPipeline(...).run()` executa o pipeline e retorna o `dict` agregado.
`InstanceTransformer(raw, cd, date).prepare()` retorna `ProblemData` sem chamar
solver. Modelos e soluções nativas ficam nas camadas de modelagem/resolução;
rotas, diagnósticos e resultados são dataclasses serializáveis.
`CVRPBuilderCplex.model` expõe o `Cplex` nativo; a antiga fachada `Solver` e o
atributo `.solver` foram removidos. `CVRPPipeline.run()` mantém o agregado em
dict, e `solve()` disponibiliza os objetos de resultado.

## Estrutura e qualidade

```text
src/cvrp/
├── domain/         # entrada, problema, instância e resultados tipados
├── io/             # fronteiras JSON e publicação JSON/Excel
├── validation/     # entrada, elegibilidade e auditoria das rotas
├── transform/      # filtros, unidades, agregação e materialização
├── preprocess/     # clustering e frota exclusiva
├── model/          # módulos específicos Docplex e CPLEX
├── solve/          # FOs sucessivas e executores de splits
├── postprocess/    # relocate, swap e 2-opt direcionais
├── report/         # extração limitada e conteúdos tipados
├── config.py       # políticas e orçamentos
├── pipeline.py     # fluxo explícito entre contratos
└── __main__.py     # interface de cenário
```

Não há DataFrames nem objetos por coeficiente no fluxo. Dataclasses usam slots;
mapas internos seguem ownership e não devem ser alterados por consumidores.

```bash
uv run ruff check .
uv run mypy src/cvrp
PYTHONPATH=. uv run pytest
```

C901 limita complexidade a 9. Os testes verificam os dois backends, formulação,
validações, FOs, splits, pós, status e paridade JSON/Excel usando XML do XLSX,
sem dependência extra de leitura Excel.

## Benchmark

Cada amostra executa em processo independente, alternando a ordem dos backends.
Por padrão, são três repetições nos modos de build e pipeline, com um cluster:

```bash
uv run python benchmark.py 20 4 --mode both --repetitions 3 --clusters 1 \
  --threads 1 --time-limit 30 --post-seconds 5 --output data/benchmark
```

Para medir somente construção, sem resolver nem dividir clientes:

```bash
uv run python benchmark.py 100 10 --mode build --repetitions 3 --output data/benchmark-build
```

Para medir o pipeline com decomposição e processos:

```bash
uv run python benchmark.py 20 4 --mode pipeline --repetitions 3 --clusters 4 \
  --parallel --workers 2 --threads 1 --time-limit 30 --post-seconds 5 \
  --output data/benchmark-parallel
```

As pastas `build-cplex-1`, `build-docplex-1`, `pipeline-cplex-1` e
`pipeline-docplex-1` identificam modo, backend e repetição. Cada amostra conserva
`input.json` e `metrics.json`; amostras de pipeline também publicam `runs/` com
relatórios JSON/Excel. `benchmark-summary.json` reúne amostras, medianas, mínimos,
máximos e status. Consulte opções com `uv run python benchmark.py --help`.

As medições incluem tempos por etapa/FO/escrita, qualidade, variáveis,
restrições, não zeros, pico de RSS do processo da amostra e o maior pico dos
filhos encerrados. Esses picos não representam a memória simultânea total do
conjunto de processos. Build usa o problema único; pipeline usa os clusters
configurados. Compare orçamento e qualidade junto aos tempos. Não há benchmark
controlado com Java que demonstre superioridade deste template.
