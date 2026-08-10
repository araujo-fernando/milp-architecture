# CVRP

Exemplo executável de arquitetura para resolver o **Problema de Roteamento de Veículos Capacitado** (CVRP) com CPLEX. O projeto transforma dados operacionais em JSON em uma instância imutável e esparsa, constrói uma formulação *vehicle-flow* de três índices, resolve o modelo e gera a solução em JSON.

## O que o projeto faz

O pipeline segue o fluxo `Transform → Build → Solve → Extract`:

- valida o CD selecionado e filtra pedidos confirmados para a data de entrega;
- deduplica pedidos, converte caixas para kg e m³ e descarta clientes sem coordenadas ou sem cadastro;
- expande a frota efetivamente disponível e respeita restrições de circulação por tipo de veículo;
- usa distâncias direcionais informadas quando disponíveis e calcula as demais a partir das coordenadas;
- cria somente os arcos válidos por veículo (`valid_ijk`), evitando um produto cartesiano desnecessário;
- produz rotas, indicadores, informações do solver e os itens descartados.

A formulação inclui atendimento único, fluxo de entrada e saída, capacidades de peso e volume, custo fixo de ativação e cortes DFJ para eliminar subrotas. Como os cortes DFJ são exponenciais, este exemplo é indicado para instâncias pequenas.

## Requisitos e instalação

- Python 3.12 ou superior;
- [uv](https://docs.astral.sh/uv/);
- runtime CPLEX compatível, necessário para resolver os modelos.

Na raiz do projeto, instale as dependências com:

```bash
uv sync --group dev
```

## Executar um cenário

Cada cenário é um diretório contendo `input.json`. Informe o diretório e o código do centro de distribuição:

```bash
uv run cvrp caminho/do/cenario CD-BH01 --date 2026-08-07
```

Também é possível executar o módulo diretamente:

```bash
uv run python -m cvrp caminho/do/cenario CD-BH01
```

Se `--date` for omitido, a data de referência presente no JSON é usada. A execução cria ou atualiza os artefatos no próprio diretório do cenário:

| Arquivo | Conteúdo |
| --- | --- |
| `input.json` | entrada operacional bruta |
| `output.json` | solução, KPIs, rotas e diagnósticos |
| `execution.log` | tempos e logs da execução |

Use `--cplex-log` para exibir o log do CPLEX no terminal.

O contrato de entrada e o de saída estão detalhados em [docs/input-data.md](docs/input-data.md) e [docs/output-data.md](docs/output-data.md).

## Uso como biblioteca

```python
import json

from cvrp import CVRPPipeline, InstanceTransformer

raw = json.loads(open("caminho/do/cenario/input.json", encoding="utf-8").read())

# Somente transforma e valida a entrada.
data = InstanceTransformer(raw, "CD-BH01", "2026-08-07").transform()

# Executa o pipeline completo com o builder Docplex (padrão).
result = CVRPPipeline(raw, "CD-BH01", "2026-08-07").run()
```

Há dois builders com a mesma formulação:

- `CVRPBuilderDocplex`, a implementação de alto nível com Docplex;
- `CVRPBuilderCplex`, que usa a API matricial do CPLEX por meio da fachada `Solver`.

Para usar o builder de baixo nível no pipeline, passe `builder="cplex"`:

```python
result = CVRPPipeline(raw, "CD-BH01", builder="cplex").run()
```

## Estrutura

```text
src/cvrp/
├── domain/        # contratos imutáveis da instância
├── transform/     # JSON operacional → InstanceData
├── model/         # builders Docplex e CPLEX
├── solve/         # fachada para a API matricial do CPLEX
├── report/        # solução → JSON de saída
├── pipeline.py    # orquestra as camadas
└── __main__.py    # interface de linha de comando
```

Para a formulação matemática e as decisões de arquitetura, consulte [docs/model.md](docs/model.md) e [docs/architecture.md](docs/architecture.md).

## Qualidade

```bash
uv run ruff check .
PYTHONPATH=. uv run pytest
```

`PYTHONPATH=.` permite que a suíte importe o gerador sintético `benchmark.py`, usado pelos testes. Os testes cobrem transformação e validações, esparsidade de arcos, os dois builders, formulação com cortes DFJ, pipeline, CLI e instrumentação. A cobertura mínima configurada é de 80%.

## Benchmark

O script gera uma instância sintética e compara o tempo do pipeline usando os builders CPLEX e Docplex:

```bash
uv run python benchmark.py 20 4
```

Os argumentos são, respectivamente, a quantidade de clientes e de veículos. O benchmark grava os arquivos em `data/<clientes>c-<veículos>v`:

- `input.json`;
- `output_cplex.json`;
- `output_docplex.json`;
- `execution.log`.

Use `--cplex-log` para exibir o log do solver. O benchmark também requer um runtime CPLEX compatível.
