# Problema de Roteamento de Veículos com Capacidade (CVRP)

## 1. Conjuntos e índices

| Símbolo | Descrição |
|---|---|
| $N = \{1,\dots,n\}$ | clientes |
| $V = \{0\} \cup N$ | nós (0 = depósito) |
| $A = \{(i,j) \in V \times V : i \neq j\}$ | arcos |
| $K = \{1,\dots,m\}$ | veículos (frota homogênea) |
| $S \subseteq N$ | subconjuntos de clientes (usado nos cortes) |

## 2. Parâmetros

| Símbolo | Descrição |
|---|---|
| $c_{ij}$ | custo/distância do arco $(i,j) \in A$ |
| $q_i$ | demanda do cliente $i \in N$, com $q_0 = 0$ |
| $Q$ | capacidade do veículo |
| $r(S) = \left\lceil \frac{\sum_{i \in S} q_i}{Q} \right\rceil$ | nº mínimo de veículos para atender $S$ |

---

## 3. Formulação de três índices (vehicle-flow)

É a forma "canônica de livro-texto", porque permite indexar atributos por veículo (frota heterogênea, janelas, motoristas).

**Variáveis**

$$x_{ijk} \in \{0,1\} \quad \text{1 se o veículo } k \text{ percorre o arco } (i,j)$$
$$y_{ik} \in \{0,1\} \quad \text{1 se o cliente } i \text{ é atendido pelo veículo } k$$

**Modelo**

$$\min \sum_{k \in K} \sum_{(i,j) \in A} c_{ij}\, x_{ijk}$$

sujeito a:

$$\sum_{k \in K} y_{ik} = 1 \qquad \forall i \in N \tag{1}$$

$$\sum_{k \in K} y_{0k} \le m \tag{2}$$

$$\sum_{j \in V \setminus \{i\}} x_{ijk} = y_{ik} \qquad \forall i \in V,\ \forall k \in K \tag{3}$$

$$\sum_{i \in V \setminus \{j\}} x_{ijk} = y_{jk} \qquad \forall j \in V,\ \forall k \in K \tag{4}$$

$$\sum_{i \in N} q_i\, y_{ik} \le Q \qquad \forall k \in K \tag{5}$$

$$\sum_{i \in S}\sum_{j \in S} x_{ijk} \le |S| - 1 \qquad \forall S \subseteq N,\ |S| \ge 2,\ \forall k \in K \tag{6}$$

$$x_{ijk} \in \{0,1\},\quad y_{ik} \in \{0,1\}$$

- (1) cada cliente é atendido exatamente uma vez
- (2) no máximo $m$ veículos saem do depósito
- (3)–(4) conservação de grau: se o veículo $k$ visita $i$, ele entra e sai exatamente uma vez
- (5) capacidade
- (6) eliminação de subrotas (DFJ) — **exponencial**, tipicamente separada por geração de cortes

---

## 4. Formulação de dois índices (a mais usada em branch-and-cut)

Elimina a simetria entre veículos idênticos. Assume frota homogênea.

$$x_{ij} \in \{0,1\}$$

$$\min \sum_{(i,j) \in A} c_{ij}\, x_{ij}$$

$$\sum_{i \in V \setminus \{j\}} x_{ij} = 1 \qquad \forall j \in N \tag{7}$$

$$\sum_{j \in V \setminus \{i\}} x_{ij} = 1 \qquad \forall i \in N \tag{8}$$

$$\sum_{j \in N} x_{0j} = m, \qquad \sum_{i \in N} x_{i0} = m \tag{9}$$

$$\sum_{i \notin S}\sum_{j \in S} x_{ij} \ \ge\ r(S) \qquad \forall S \subseteq N,\ S \neq \emptyset \tag{10}$$

A restrição (10) — *rounded capacity cut* — faz o trabalho duplo de eliminar subrotas **e** impor capacidade. É a base do branch-and-cut moderno para CVRP.

---

## 5. Versões compactas da eliminação de subrotas

Como (6) e (10) têm cardinalidade exponencial, existem duas alternativas polinomiais para quando você quer um modelo que entra inteiro no solver.

### 5.1 MTZ (Miller–Tucker–Zemlin) adaptado

$$u_i \in \mathbb{R},\qquad q_i \le u_i \le Q \quad \forall i \in N$$

$$u_i - u_j + Q\, x_{ij} \le Q - q_j \qquad \forall i,j \in N,\ i \neq j \tag{11}$$

$u_i$ representa a carga acumulada ao chegar em $i$. Tamanho $O(n^2)$, mas **relaxação linear fraca**.

### 5.2 Fluxo de uma commodity (Gavish–Graves) — recomendada

$$f_{ij} \ge 0 \quad \text{carga transportada no arco } (i,j)$$

$$\sum_{i \in V \setminus \{j\}} f_{ij} - \sum_{i \in V \setminus \{j\}} f_{ji} = q_j \qquad \forall j \in N \tag{12}$$

$$q_j\, x_{ij} \ \le\ f_{ij} \ \le\ (Q - q_i)\, x_{ij} \qquad \forall (i,j) \in A \tag{13}$$

Também $O(n^2)$, porém com bound de relaxação linear sensivelmente mais forte que MTZ. Na prática é a escolha padrão quando se quer um modelo compacto.

---

## 6. Extensão canônica: janelas de tempo (VRPTW)

Adicionando $t_{ij}$ (tempo de viagem), $s_i$ (serviço) e $[a_i, b_i]$ (janela):

$$w_i \ge 0 \quad \text{instante de início do serviço em } i$$

$$w_i + s_i + t_{ij} - M_{ij}(1 - x_{ij}) \le w_j \qquad \forall (i,j) \in A,\ j \neq 0 \tag{14}$$

$$a_i \le w_i \le b_i \qquad \forall i \in N \tag{15}$$

com $M_{ij} = \max\{0,\ b_i + s_i + t_{ij} - a_j\}$ — o big-M **apertado**, não um valor arbitrário.

Note que (14)–(15) já eliminam subrotas por si só (o tempo é estritamente crescente ao longo da rota), tornando (6)/(10)/(11) redundantes para esse fim.

---

## 7. Notas de modelagem

**Força da relaxação:** DFJ/capacity cuts $\succ$ fluxo de uma commodity $\succ$ MTZ. A diferença de gap na raiz entre MTZ e as capacity cuts costuma ser de uma ordem de grandeza.

**Dimensionamento:** a formulação de três índices tem $|K| \cdot |A| \approx m \cdot n^2$ variáveis binárias. Com $n = 200$ e $m = 20$ você já passa de 800 mil binárias — ou seja, escala de instância que exige criação em batch e conjunto esparso de arcos.

**Esparsidade de arcos:** raramente se constrói $A$ completo. O padrão é restringir a $k$-vizinhos mais próximos ($k \approx 10$–$20$), o que reduz $|A|$ de $O(n^2)$ para $O(kn)$. Isso conecta diretamente com o `valid_ijk: frozenset` da arquitetura discutida antes — o conjunto de arcos válidos é um dado da instância, não do modelo.

**Simetria:** na formulação de três índices, veículos idênticos geram $m!$ soluções equivalentes. Se precisar do índice $k$, adicione quebra de simetria (ex.: $y_{ik} \le \sum_{i' < i} y_{i',k-1}$) ou prefira a formulação de dois índices.

**Depósito e frota:** trocar (2) por $\sum_k y_{0k} \le m$ com custo fixo $F_k$ no objetivo transforma o problema em minimização conjunta de frota e distância — variante muito mais comum na prática do que a versão com $m$ fixo.