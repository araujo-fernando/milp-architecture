# Arquitetura Python para Otimização (LP/MIP) com CPLEX/docplex em Escala de 10 Milhões de Variáveis

## TL;DR
- **Separe rigidamente "modelo estático" de "dados da instância" (padrão AbstractModel/ConcreteModel do Pyomo) e organize o código como um pipeline ETL** — Extract (leitura crua) → Transform/Validate (validação na fronteira) → Build (construção do modelo) → Solve → Extract Solution → Report. Uma única classe `InstanceData` com `slots=True`/dataclass e dicts de variáveis indexados por tupla de inteiros resolve a grande maioria dos casos sem over-abstração.
- **Para chegar a 10M de variáveis, o gargalo NÃO é o solver CPLEX (que é C nativo) e sim a camada Python que cria objetos.** Use as regras oficiais da IBM (`binary_var_list`/`var_dict` em batch, `Model.sum`/`scal_prod`/`dotf`, `add_constraints` no plural, `ignore_names=True`, `checker='off'`) — isso reduz o tempo de build em ~3,9× em média (de ~35s para ~4s no benchmark oficial da IBM). Acima de ~1–5M de variáveis com edição incremental, considere migrar o hot loop para a **API de baixo nível `cplex` (matriz esparsa, `SparsePair`, índices inteiros)**, que a IBM recomenda explicitamente para modelos muito grandes.
- **Na ingestão, valide na fronteira e use estruturas cruas e rápidas internamente:** Polars/PyArrow para transformação (menos memória e mais rápido que pandas em milhões de linhas), msgspec para JSON (decodifica *e valida* mais rápido do que o orjson decodifica sozinho). Na saída, use **xlsxwriter em `constant_memory` mode** (RAM constante) e respeite o limite de 1.048.576 linhas por planilha.

## Key Findings

**1. O gargalo em escala é a construção do modelo em Python, não o solve.** A evidência mais concreta (relatada por Leo Singer e Prof. Paul Rubin em thread do fórum IBM Decision Optimization): criar 10.000.000 de variáveis binárias com `binary_var_list` leva ~17,5s; exportar para SAV leva ~1s; mas ler o SAV de volta via `ModelReader.read()` do docplex leva ~46s (modelo sintético) ou ~7 minutos (modelo real), enquanto o solve leva apenas 45s. O mesmo experimento em Java (API de baixo nível CPLEX 12.10) constrói em ~8s e lê o SAV em ~5s. O engenheiro da IBM Philippe Couronne confirma na íntegra: "criar 10 milhões de objetos Python 'var' leva tempo. Não há muito o que fazer... a única alternativa viável para modelos muito grandes é usar a API matricial em Python (ou C/C++)". O consultor de vendas técnicas da IBM Alex Fleischer reforça: "Se você quer que isso seja rápido, então, em vez do docplex, recomendo a API matricial do cplex".

**2. As "regras de ouro" da IBM para build rápido em docplex têm efeito medido.** O notebook oficial "Writing efficient DOcplex code" mostra a progressão de otimizações em um modelo O(N²): uso de `Model.sum()` em vez do `sum()` nativo (evita expressões intermediárias, tempo O(N²)); `Model.scal_prod`/`dotf` em vez de laços `for`; `add_constraints` em batch; `ignore_names=True`; e `checker='off'`. O resultado agregado, na plataforma da IBM, foi redução do tempo de build de ~35s para ~4s (ganho geométrico médio ~3,9× entre tamanhos). Além disso, a partir da versão 22.1, a própria IBM registra "melhoria média de 30–50% no tempo de execução de modelagem" no docplex.

**3. Estruturas de dados: dict-de-tupla é o padrão pragmático; index-mapping para inteiros é a otimização extrema.** Os métodos `*_var_dict` do docplex retornam dicionários indexados por tupla `X[i,j,k]`, e essa é a abordagem idiomática. Para conjuntos esparsos (nem toda combinação `(i,j,k)` existe), o dict é obrigatório — arrays densos multidimensionais desperdiçam memória proporcional ao produto cartesiano. Para acesso máximo em escala, faça label-encoding (strings → inteiros contíguos) e, se necessário, flattening `idx = i*n_j*n_k + j*n_k + k`. Na API de baixo nível, indexar por **índice inteiro** em vez de nome é decisivo: um usuário relatou que `linear_constraints.add` com 650k binárias + 200k contínuas + 1M de restrições levava ~1h30, e a recomendação da comunidade foi trocar nomes por índices.

**4. Validação: msgspec/Polars-Pandera na fronteira, dataclasses cruas internamente.** Segundo a documentação oficial do msgspec, "em benchmarks, o msgspec decodifica e valida JSON mais rápido do que o orjson consegue decodificar sozinho", e "codificar/decodificar uma mensagem com msgspec pode ser ~10–80× mais rápido que bibliotecas alternativas". As `Struct` do msgspec são, segundo o site oficial, "5–60× mais rápidas em operações comuns" que dataclasses/attrs, e em benchmark de criação "~4× mais rápidas que classes padrão/attrs/dataclasses e 17× mais rápidas que pydantic". Pandera valida DataFrames muito mais rápido que validação linha-a-linha com Pydantic. A regra consolidada: validar na fronteira (boundary validation), estruturas rápidas dentro.

**5. Saída em Excel: xlsxwriter constant_memory para grande escala.** Conforme a documentação oficial do XlsxWriter, no modo `constant_memory` "a maior quantidade de dados mantida em memória para uma planilha é a necessária para armazenar uma única linha... o uso de memória permanece pequeno e constante". O autor do XlsxWriter, John McNamara, afirma que "para arquivos grandes é ~10× mais rápido que o OpenPyXL mantendo uso de memória baixo e constante" (benchmark de 1M de linhas: openpyxl 469,1s vs xlsxwriter 186,2s). Um caso de produção relatado ("Mass Software Solutions") reduziu a geração de 52 colunas × 200.000 linhas de "aproximadamente 9 minutos" (openpyxl) para "apenas 3 minutos" (xlsxwriter). Limite absoluto do formato XLSX: 1.048.576 linhas por planilha.

## Details

### Arquitetura de diretórios (src layout)

```
optmodel/
├── pyproject.toml
├── README.md
├── src/
│   └── optmodel/
│       ├── __init__.py
│       ├── config.py            # dataclasses de config / pydantic-settings + TOML
│       ├── io/                  # camada "Extract" e "Load/Report"
│       │   ├── readers.py       # JSON (msgspec), CSV/Parquet (polars), Excel (calamine), DB
│       │   └── writers.py       # Excel (xlsxwriter constant_memory)
│       ├── domain/
│       │   ├── sets.py          # conjuntos/índices + IndexMap (label encoding)
│       │   └── instance.py      # InstanceData (dataclass com slots) — DTO validado
│       ├── validation/
│       │   └── schemas.py       # msgspec.Struct / Pandera schemas (boundary validation)
│       ├── transform/
│       │   └── build_instance.py# raw -> InstanceData (o "T" do ETL)
│       ├── model/
│       │   ├── builder.py       # ModelBuilder (docplex) — construção estática
│       │   └── lowlevel.py      # (opcional) builder via API cplex matricial
│       ├── solve/
│       │   └── solver.py        # configura Model.parameters, resolve, retorna Solution
│       ├── report/
│       │   └── extract.py       # SolveSolution -> DataFrames (solution extraction)
│       └── pipeline.py          # orquestra Extract->Transform->Build->Solve->Report
└── tests/
    ├── test_small_instances.py  # instâncias pequenas com solução conhecida
    ├── test_invariants.py       # invariantes de restrições
    └── test_build_perf.py
```

O src layout é a recomendação oficial do Python Packaging Guide e do pyOpenSci porque "garante que os testes rodem contra a versão instalada do pacote" e evita imports acidentais do diretório de trabalho.

Responsabilidades por camada:
- **io/**: só entrada/saída bruta. Não conhece o modelo matemático. Adapters/Ports (padrão Repository) isolam a fonte (JSON/CSV/Excel/DB) do resto — é aqui que a troca de fonte de dados fica encapsulada.
- **validation/ + transform/**: o "E" e "T" do ETL. Validam na fronteira e montam a `InstanceData`.
- **domain/instance.py**: DTO único, validado, imutável — a "instância concreta" (análoga ao `ConcreteModel` do Pyomo, que é "um AbstractModel preenchido com dados reais").
- **model/builder.py**: o modelo estático/declarativo. Recebe `InstanceData`, devolve `Model` docplex. É aqui que vivem as decisões de performance.
- **solve/ + report/**: solve e extração. Separam "solution extraction" (dados crus) de "report rendering" (formatação Excel). Essa separação é o que permite trocar o formato de saída sem tocar na lógica de otimização.

Referência de estrutura mínima e madura em produção: o repositório `ekhoda/optimization-tutorial` encapsula o modelo numa classe `OptimizationModel` cujo `__init__` chama `_create_decision_variables`, `_create_main_constraints`, `_set_objective_function` separadamente e cria variáveis com `continuous_var_dict` sobre um índice — exatamente o padrão Builder recomendado aqui.

### Lição arquitetural do Pyomo (o que adaptar, o que evitar)

O Pyomo distingue `AbstractModel` (índices simbólicos, dados carregados depois via `DataPortal` + `create_instance()`) de `ConcreteModel` (dados instanciados na criação). A lição a adaptar: **o modelo é um template; a instância é o template + dados**. A documentação do próprio Pyomo, porém, adverte que a diferença prática entre os dois é pequena e "é largamente uma questão de gosto". Traduzido para docplex: você **não** precisa de uma máquina de "modelo abstrato" — basta um `ModelBuilder` estático que recebe uma `InstanceData` concreta. Reproduzir um sistema de `Set`/`Param`/`DataPortal` completo em cima do docplex seria over-abstração clássica; o dataclass + dict de tuplas é suficiente.

### Conjuntos, índices e o padrão IndexMap

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class IndexMap:
    """Label encoding: mapeia labels (str) para inteiros contíguos [0..n)."""
    labels: tuple[str, ...]
    _pos: dict[str, int]

    @classmethod
    def from_iterable(cls, it) -> "IndexMap":
        labels = tuple(dict.fromkeys(it))  # remove duplicatas preservando ordem
        return cls(labels, {lab: i for i, lab in enumerate(labels)})

    def idx(self, label: str) -> int:
        return self._pos[label]

    def __len__(self) -> int:
        return len(self.labels)
```

### Classe de dados da instância (DTO com slots)

```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class InstanceData:
    plants: IndexMap
    products: IndexMap
    periods: IndexMap
    demand: dict[tuple[int, int], float]         # d[j, n] indexado por inteiros
    unit_cost: dict[tuple[int, int, int], float]
    capacity: dict[int, float]
    valid_ijk: frozenset[tuple[int, int, int]]   # conjunto ESPARSO de combinações válidas
```

`slots=True` elimina o `__dict__` por instância (menos memória, atributos mais rápidos) — relevante quando há milhões de entradas em torno. `frozen=True` garante imutabilidade: a instância não muda depois de montada. Usar `dict` com chave-tupla de **inteiros** (não strings) e um `frozenset` `valid_ijk` para índices esparsos é a decisão-chave: iterar sobre combinações válidas evita criar milhões de variáveis inexistentes. Se a maioria das combinações existir e a memória permitir, o dict pode ser trocado por arrays NumPy indexados via IndexMap — mas para conjuntos esparsos o dict é obrigatório.

### Builder do modelo (docplex, caminho de alta performance)

```python
from docplex.mp.model import Model

class ModelBuilder:
    """Modelo ESTÁTICO. Só a InstanceData muda entre execuções."""

    def __init__(self, data: InstanceData):
        self.data = data
        # DECISÕES DE PERFORMANCE CRÍTICAS:
        # ignore_names=True  -> não gera strings de nome (custo alto em Python)
        # checker='off'      -> desativa checagem de tipos (só após testar!)
        self.m = Model(name="prod", ignore_names=True, checker="off")
        self.x = {}

    def build(self) -> Model:
        self._create_vars()
        self._create_constraints()
        self._set_objective()
        return self.m

    def _create_vars(self):
        d = self.data
        # Batch: variáveis criadas em UMA chamada sobre o conjunto esparso
        self.x = self.m.continuous_var_dict(d.valid_ijk, lb=0, name=None)

    def _create_constraints(self):
        d, x, m = self.data, self.x, self.m
        # add_constraints (plural) + generator, NÃO add_constraint em laço
        m.add_constraints(
            m.sum(x[i, j, k] for i in range(len(d.plants))
                  if (i, j, k) in x) <= d.capacity[k]
            for k in range(len(d.periods))
            for j in range(len(d.products))
        )

    def _set_objective(self):
        d, x, m = self.data, self.x, self.m
        # scal_prod evita construir expressões intermediárias
        keys = list(x.keys())
        coefs = [d.unit_cost[key] for key in keys]
        m.minimize(m.scal_prod([x[k] for k in keys], coefs))
```

A documentação da IBM explica por que `Model.sum` importa: o `sum` nativo do Python avalia `((x+y)+z)+t`, criando N expressões intermediárias que são copiadas a cada passo — tempo total O(N²); `Model.sum()` "cria apenas *uma* expressão e adiciona cada argumento incrementalmente". No benchmark, o modelo com `sum()` nativo levou ~2× mais tempo que com `Model.sum()`.

**Anti-padrões que degradam performance em docplex (evite):**
- `sum(...)` nativo do Python em expressões — use `Model.sum` (ou `scal_prod`/`dotf`).
- `add_constraint` (singular) em laço `for` — use `add_constraints` no plural com generator (a própria IBM recomendou isso a um usuário cujo modelo de column generation ficou "proibitivamente mais lento").
- Criar variáveis uma a uma (`m.continuous_var(...)` em loop) — use `*_var_dict`/`*_var_list`. A IBM: "para grande número de variáveis (digamos, acima de 1000) prefira criar variáveis em lotes".
- Nomes gerados por f-string para milhões de elementos — use `ignore_names=True` ("gerar grandes números de strings pode ter custo significativo em Python").
- Indexar variáveis/restrições por **nome** na API de baixo nível — use índices inteiros.
- Acessar `solution.get_value(var)` var-a-var em laço — use `get_values`/`get_value_dict` em batch.
- `checker='off'` combinado com `Model.sum_vars`/`sum_vars_all_different` recebendo não-variáveis — pode gerar erro silencioso; prefira `Model.sum` como default seguro.

### Quando descer para a API de baixo nível `cplex`

A IBM confirma que `cplex` é "um wrapper leve sobre a API C (CPLEX Callable Library)... variáveis e restrições são identificadas por seus índices na matriz". Para modelos com edição incremental (ex.: column generation, branch-and-price) ou acima de ~1–5M de variáveis onde o tempo de build domina, a construção matricial com `SparsePair` e índices inteiros mantém a velocidade do C:

```python
import cplex

c = cplex.Cplex()
c.variables.add(obj=obj_coefs, lb=lbs, ub=ubs)          # batch, por índice
c.linear_constraints.add(
    lin_expr=[cplex.SparsePair(ind=row_idx, val=row_val) for ...],
    senses=senses, rhs=rhs)                              # batch, por índice
```

A IBM oferece três padrões canônicos de população de modelo (exemplo `lpex1`): `populatebyrow` (`linear_constraints.add`), `populatebycolumn` (`variables.add(columns=...)`) e `populatebynonzero` (cria linhas/colunas vazias e depois `set_coefficients`). A documentação C++ observa que, embora rowwise seja mais natural em exemplos simples, "há modelos onde uma abordagem columnwise é mais natural, ou mais eficiente, para uma aplicação de produção".

Limites hard do CPLEX, segundo Tobias Achterberg (IBM), no fórum de Decision Optimization: "há um limite de 2,1 bilhões de variáveis e 2,1 bilhões de restrições (que é 2³¹...). O número de não-zeros na matriz de restrições no CPLEX 12 é limitado por 2⁶³. Assim, você tipicamente atingirá suas limitações de memória antes de bater nossos limites codificados". Ou seja: **RAM é a parede prática, não os limites do solver.**

### Formatos de arquivo: SAV vs LP/MPS

SAV é o formato binário do CPLEX: a documentação oficial diz que é "numericamente preciso... eficiente em tempo de leitura e escrita" e contém metadados de tamanho que permitem ao CPLEX alocar memória de uma vez, enquanto "ao ler arquivos LP ou MPS, o CPLEX realoca memória automaticamente conforme lê". docplex expõe `Model.export_as_lp`, `export_as_mps` e `export_as_sav` (inclusive `.sav.gz` comprimido). **Ressalva crítica:** escrever SAV via docplex é rápido (~1s para 10M vars), mas ler SAV de volta *para dentro do docplex* é lento (reconstrução de objetos Python — ~46s a 7min); ler via `cplex.Cplex().read()` de baixo nível permanece em velocidade C.

### Camada de ingestão e transformação

- **JSON grande:** msgspec (schema via type hints, core compilado) — decodifica+valida mais rápido que orjson decodifica sozinho, e permite declarar schema apenas para os campos usados, reduzindo alocações. Para streaming de arquivos que não cabem em RAM, use ijson. orjson é a alternativa se não precisar de schema.
- **CSV/Parquet/transformação:** Polars (Rust, Arrow, multithread, avaliação lazy). Benchmark reproduzível de Itamar Turner-Trauring (pythonspeed.com) mostra Polars lazy usando 152MB de RAM máx vs 909MB do pandas naive (via PyArrow), terminando em 0,11s vs 0,44s — "Polars usa menos memória, termina mais rápido e usa menos CPU". Ganhos de 3–10× são consistentes em ETL de 10M+ linhas. pandas continua útil por integração de ecossistema.
- **Excel (leitura):** python-calamine (Rust) ou openpyxl em read-only mode (que "abre um workbook quase imediatamente... reduzindo o uso de memória significativamente").
- **DB:** connectorx ou SQLAlchemy Core (evite o ORM para volume alto).

Padrão DTO vs Domain Model: leia para structs msgspec crus (DTO), valide na fronteira, e transforme em `InstanceData` (domain model). Cacheie a `InstanceData` processada em Parquet/msgpack/pickle para evitar re-processamento — política de "validate once, reuse".

### Extração de solução e relatório

```python
def extract_solution(sol, x: dict):
    import polars as pl
    # get_value_dict em batch; keep_zeros=False -> só não-zeros (esparso)
    values = sol.get_value_dict(x, keep_zeros=False)
    rows = [(*k, v) for k, v in values.items()]
    return pl.DataFrame(rows, schema=["i", "j", "k", "value"])
```

`SolveSolution` do docplex oferece `get_values` (sequência, batch), `get_value_dict` (dict de variáveis → valores, "com as mesmas chaves e como valores os valores da solução"), `iter_var_values` (itera só sobre variáveis mencionadas na solução), `get_value_df` e `as_df()`. Nota importante da documentação: `get_values` funciona só para *sequências*, não para dicts multidimensionais — por isso `get_value_dict` é o método correto para variáveis criadas com `*_var_dict`. **Filtre por não-zeros** (`keep_zeros=False`) em soluções esparsas: 10M de variáveis podem ter só uma fração não-nula.

```python
import xlsxwriter

def write_report(df, path: str):
    wb = xlsxwriter.Workbook(path, {"constant_memory": True})
    ws = wb.add_worksheet("solucao")
    # constant_memory EXIGE escrita em ordem: linha por linha, coluna a coluna
    for r, row in enumerate(df.iter_rows(), start=1):
        for cidx, val in enumerate(row):
            ws.write(r, cidx, val)
    wb.close()
```

O modo `constant_memory` faz flush de cada linha assim que a próxima é escrita, portanto **exige escrita em ordem de linha** (row-by-column); escrever fora de ordem só grava a primeira coluna. Se a saída exceder 1.048.576 linhas, particione em múltiplas planilhas/arquivos ou troque para Parquet/CSV.

### Configuração, logging, testes

- **Config:** dataclass de config ou pydantic-settings lendo TOML. Parâmetros CPLEX relevantes via `Model.parameters` (ou `context.cplex_parameters`): `threads`, `mip.tolerances.mipgap`, `timelimit`, `workmem` e `mip.strategy.file` (node file storage).
- **Logging/profiling:** um context manager que cronometra cada etapa do pipeline — exatamente o `ContextTimer` que a própria IBM usa no notebook de eficiência. Instrumente Extract/Transform/Build/Solve/Report separadamente para saber onde está o gargalo.
- **Testes:** (1) instâncias pequenas com solução ótima conhecida (assert no valor objetivo e no status "optimal"); (2) invariantes de restrições (toda solução viável satisfaz capacidade/demanda — verificar a posteriori); (3) property-based testing (Hypothesis) gerando dados aleatórios e checando invariantes que devem sempre valer, em vez de valores exatos.

## Recommendations

**Estágio 1 — Comece simples (KISS), até ~1M de variáveis.** Use docplex puro com: `*_var_dict` para variáveis (indexadas por tupla de inteiros via IndexMap), `add_constraints` em batch, `Model.sum`/`scal_prod`, e uma `InstanceData` dataclass com `slots=True`. Ingestão com Polars + msgspec, saída com xlsxwriter constant_memory. **Não** crie abstrações de "solver strategy" nem "repository" genéricos ainda — só as camadas do ETL. Isso já entrega clean code + SOLID sem over-engineering.

**Estágio 2 — Ative as flags de performance quando o build passar de alguns segundos.** Adicione `ignore_names=True` e, só depois de a suíte de testes estar verde, `checker='off'`. Meça cada etapa com o context manager. Threshold de referência: se o build está muito acima de ~4s para um modelo ~5k×5k, você está caindo em algum anti-padrão (provavelmente `sum()` nativo ou `add_constraint` em laço).

**Estágio 3 — Migre o hot path para a API `cplex` matricial acima de ~1–5M de variáveis OU quando houver edição incremental.** Mantenha o docplex como default e isole o builder de baixo nível atrás da mesma interface (`ModelBuilder`), usando `SparsePair` e índices inteiros (nunca nomes). Este é o único ponto onde o padrão Strategy (docplex vs cplex-matricial) se justifica — não antes. Se precisar persistir/recarregar o modelo, escreva SAV via docplex mas leia via `cplex.Cplex().read()`.

**Estágio 4 — Controle memória no solve, não só no build.** Configure `workmem` e `mip.strategy.file=2/3` (node file storage em disco/comprimido) para MIPs que geram muitos nós — o CPLEX começa a mover nós da árvore "viva" para disco quando o tamanho atinge `workmem` (default 2GB). Use `emphasis memory` para LPs grandes (reduz RAM ao custo de alguma performance). Monitore MaxRSS. Provisione RAM generosamente: modelos de dezenas de milhões de variáveis/restrições atingem o limite de memória antes do limite hard do CPLEX.

**Benchmarks/thresholds que mudam a decisão:**
- Build > 1–2 min em docplex → verifique anti-padrões; se limpo, migre para API matricial.
- Leitura de SAV via docplex dominando o tempo → leia via `cplex.Cplex().read()` de baixo nível.
- Transformação de dados > dezenas de segundos em pandas → migre para Polars.
- Relatório Excel estourando RAM → xlsxwriter constant_memory; se > 1.048.576 linhas, particione ou use Parquet/CSV.
- Solução com >90% de zeros → extraia só não-zeros (`keep_zeros=False`).

## Caveats
- Vários números de tempo (10M vars em ~17,5s; leitura SAV em ~46s/7min; equivalente Java em ~5–8s) vêm de posts do fórum IBM Decision Optimization por indivíduos nomeados (staff IBM como Philippe Couronne e Alex Fleischer, e acadêmicos como Prof. Paul Rubin), não de benchmarks controlados publicados — são confiáveis mas dependentes de hardware e versão (era CPLEX 12.10–22.1). Meça no seu ambiente.
- Não há tabela oficial da IBM quantificando "índices X% mais rápidos que nomes"; a afirmação é bem-suportada arquiteturalmente (nomes = overhead de criação de string em Python) e pelo efeito medido de `ignore_names=True` no notebook oficial, mas é inferência, não um único número citado.
- `checker='off'` desativa toda checagem de tipo — a documentação avisa que "deve ser feito apenas com extrema cautela" e só depois de o modelo ter sido "exaustivamente testado e os dados numéricos serem confiáveis".
- Benchmarks Polars vs pandas e msgspec vs Pydantic/orjson são sintéticos e dependem da forma dos dados (proporção de strings, aninhamento, floats); a vantagem é consistente mas a magnitude varia — o próprio autor do msgspec adverte que "benchmarks são difíceis" e a estrutura das mensagens importa.
- 10M de variáveis é viável em termos de *construção*, mas a *solubilidade* (tempo de solve) de um MIP desse porte não é garantida — depende inteiramente da estrutura do problema. Considere decomposição (Benders, column generation) como parte da arquitetura desde o início se o solve for o gargalo real; nesse caso a API de baixo nível `cplex` (edição incremental barata) passa a ser praticamente obrigatória.
- Este relatório trata da modelagem LP/MIP (docplex.mp / cplex). Para problemas de programação por restrições (CP Optimizer via docplex.cp) várias das APIs citadas (`scal_prod`, `SparsePair`) não se aplicam da mesma forma.