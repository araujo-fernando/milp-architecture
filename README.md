# Architecture Example — CVRP

Implementação pragmática do problema de roteamento de veículos capacitado (CVRP), na formulação *vehicle-flow* de três índices da seção 3 de [model.md](docs/model.md).

O pipeline separa a transformação dos dados de negócio da construção do modelo Docplex: JSON bruto → `InstanceData` imutável e esparsa → modelo → solução JSON. As camadas estão em `domain/`, `transform/`, `model/`, `solve/`, `report/` e `pipeline.py`, seguindo a arquitetura proposta. A transformação deduplica pedidos, filtra status/data/CD, converte caixas para kg e m³, expande a frota disponível, aplica restrições de circulação e preserva distâncias direcionais conhecidas.

## Uso

```bash
uv run python -m architecture_example caminho/do/cenario CD-BH01
```

O diretório de cenário contém todos os artefatos da execução: a entrada deve estar
em `input.json`; a solução é gravada em `output.json`; e os logs em `execution.log`.
Use `--cplex-log` para exibir a saída do CPLEX durante a resolução; por padrão ela fica desativada.

É necessário um runtime CPLEX compatível para resolver. A construção do modelo pode ser usada independentemente:

```python
from architecture_example import CVRPBuilder, InstanceTransformer

data = InstanceTransformer(raw_json, "CD-BH01").transform()
model = CVRPBuilder(data).build()
```

O modelo cria `x[i, j, k]` apenas para arcos válidos e `y[i, k]` para atendimento. Ele inclui atendimento único, ativação/fluxo no depósito, conservação de grau, capacidades em kg e m³ e os cortes DFJ para eliminar subrotas. Como DFJ é exponencial, esta versão é apropriada para instâncias pequenas; em escala, a própria documentação recomenda separação de cortes ou uma formulação compacta.

## Qualidade

```bash
uv run ruff check .
uv run pytest
```

Os testes verificam transformação, validações, esparsidade e construção da formulação de três índices, com cobertura mínima configurada em 80%.

## Benchmark

O script na raiz gera uma entrada sintética, a grava no caminho informado e executa o pipeline completo, exibindo os tempos de escrita, pipeline e total:

```bash
uv run python benchmark.py 20 4
```

Os argumentos são, nesta ordem: quantidade de clientes e quantidade de veículos. O benchmark grava `input.json`, `output.json` e `execution.log` em `data/<clientes>c-<veículos>v`; por exemplo, `data/20c-4v`. Use `--cplex-log` para exibir a saída do CPLEX. A execução requer runtime CPLEX compatível.
