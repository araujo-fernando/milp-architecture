# Modelo executado: CVRP heterogêneo com duas prioridades

Os módulos `model/builder_docplex.py` e `model/builder_cplex.py` implementam a
mesma formulação, respectivamente nas APIs algébrica Docplex e matricial CPLEX.
Ambos usam nomes por família e índices, exportam LP e resolvem custo seguido de
equilíbrio de paradas. Este documento descreve o código entregue; a
[revisão de 2026-10-07](review-and-plan.md) registra a auditoria histórica e o plano.

## Dados e variáveis

Para cada split, sejam $I=\{1,\ldots,n\}$ os clientes, $V=\{0\}\cup I$
os nós e $K$ os veículos físicos reservados. O depósito tem índice zero.
$A_k$ contém somente os arcos direcionais autorizados para o veículo $k$.
Cada veículo possui capacidades $Q_k^{kg}$ e $Q_k^{m3}$ e custo por km $p_k$.
Cada cliente tem demandas $q_i^{kg}$ e $q_i^{m3}$. A distância $d_{ij}$ usa o
override direcional quando informado. O custo fixo $f$ é comum à frota.

As variáveis binárias são $x_{ijk}$, indicando um arco percorrido, e $y_{ik}$,
indicando a visita; $a_k=y_{0k}$ indica ativação do veículo. As variáveis
contínuas $u_i\in[1,n]$ ordenam clientes. $L,U\in[0,n]$ representam os
limites de quantidade de paradas das rotas usadas. Defina $s_k=\sum_{i\in I}y_{ik}$.

## Restrições e nomes

| Família | Equação | Interpretação |
| --- | --- | --- |
| `r1_i` | $\sum_k y_{ik}=1$ para $i\in I$ | Atendimento único |
| `r3_i_k` | $\sum_{j:(i,j)\in A_k}x_{ijk}=y_{ik}$ | Saída do nó |
| `r4_j_k` | $\sum_{i:(i,j)\in A_k}x_{ijk}=y_{jk}$ | Entrada do nó |
| `r5_k` | $\sum_i q_i^{kg}y_{ik}\le Q_k^{kg}$ | Capacidade de peso |
| `r6_k` | $\sum_i q_i^{m3}y_{ik}\le Q_k^{m3}$ | Capacidade de volume |
| `r7_i_j_k` | $u_i-u_j+n x_{ijk}\le n-1$ para arcos entre clientes | MTZ de ordenação |
| `r8_k` | $s_k\le U$ | Máximo de paradas |
| `r9_k` | $s_k\ge L-n(1-a_k)$ | Mínimo somente para usados |
| `r10_k` | $s_k\le n a_k$ | Atendimento implica ativação |
| `r11` | $L\le U$ | Consistência dos limites |

As somas de entrada/saída usam adjacências esparsas. Restrições de circulação
estão na seleção de $A_k$: não existe variável para arco proibido. A ligação com
o depósito é única por veículo. MTZ impede subrotas inclusive com demanda zero,
sem enumerar subconjuntos DFJ. O tamanho cresce com clientes e arcos válidos,
com ordem $O(|K|n^2)$ em um grafo completo.

Não há família `r2`: o limite de veículos pela frota disponível já decorre das
variáveis de ativação. Variáveis usam nomes `x_i_j_k`, `y_i_k`, `u_i`, `L` e `U`.
O LP da segunda etapa acrescenta `lex_cost_limit`.

## Execuções sucessivas

FO1 minimiza

$$F_1=\sum_{k\in K}\sum_{(i,j)\in A_k}p_k d_{ij}x_{ijk}+f\sum_k a_k.$$

Dado o custo do incumbente $F_1^*$, a FO2 acrescenta

$$F_1\le F_1^*+\varepsilon_{abs}+\varepsilon_{rel}|F_1^*|$$

e minimiza $F_2=U-L$. Na solução concreta, FO2 é recalculada como a diferença
entre o maior e o menor número de paradas das rotas usadas. Veículos ociosos
ficam fora desse mínimo. Há MIP start com o incumbente da FO1. Se FO2 não
produzir incumbente aceitável, a solução da FO1 é conservada.

Por padrão, 70% do orçamento de 30 segundos por split é reservado à FO1; a FO2
usa o tempo restante. O relatório preserva valor, bound, gap, tempo, status e
indicador de ótimo de cada etapa. Um incumbente da FO1 com gap positivo não
certifica ótimo lexicográfico. FO2 tem unidades de paradas, e seu valor não é o
custo total publicado nos KPIs.

## Alcance das garantias

Frota exclusiva torna o custo aditivo para a partição escolhida. A partição
restringe o espaço de soluções; resultados ótimos por split não certificam o
ótimo do problema global. O equilíbrio local também não garante equilíbrio
global. Se a partição falhar, o pipeline pode tentar o problema único dentro do
orçamento restante. O histórico de tentativas permanece no relatório.

Depois da consolidação, relocate, swap e 2-opt avaliam arcos direcionais no
problema global e preservam capacidades, atendimento e o teto de custo original.
A auditoria independente recalcula custos, cargas, distâncias e paradas.
Bounds/gaps publicados pertencem às etapas originais, não à solução alterada
pela busca local. Não estão modelados janelas de tempo, duração, split delivery
ou frota adicional fictícia.
