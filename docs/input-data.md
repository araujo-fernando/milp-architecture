# JSON bruto de entrada — CVRP (formulação de três índices)

A ideia é que este arquivo seja o que um ERP/WMS realmente exportaria: vocabulário de negócio, entidades normalizadas em listas separadas, unidades inconsistentes e **nenhum** conjunto $V$, $A$, $K$ ou parâmetro $c_{ij}$ pronto. Todo o trabalho de virar modelo linear fica na camada Transform.

```json
{
  "metadata": {
    "origem": "WMS-EXPORT",
    "versao_schema": "2.3",
    "gerado_em": "2026-08-06T23:14:07-03:00",
    "data_referencia": "2026-08-07"
  },

  "parametros_operacionais": {
    "custo_por_km": 4.85,
    "custo_fixo_por_veiculo": 180.00,
    "velocidade_media_kmh": 32,
    "tempo_descarga_min_por_caixa": 1.5,
    "raio_maximo_atendimento_km": 45,
    "moeda": "BRL"
  },

  "centros_distribuicao": [
    {
      "codigo": "CD-BH01",
      "nome": "CD Contagem",
      "ativo": true,
      "latitude": -19.9317,
      "longitude": -44.0536,
      "janela_operacao": { "abertura": "06:00", "fechamento": "18:00" }
    },
    {
      "codigo": "CD-SP02",
      "nome": "CD Guarulhos",
      "ativo": true,
      "latitude": -23.4356,
      "longitude": -46.4731,
      "janela_operacao": { "abertura": "05:00", "fechamento": "20:00" }
    }
  ],

  "catalogo_produtos": [
    { "sku": "SKU-1001", "descricao": "Refrigerante 2L",  "peso_kg_caixa": 14.4, "volume_m3_caixa": 0.021 },
    { "sku": "SKU-1002", "descricao": "Água 500ml",       "peso_kg_caixa": 12.0, "volume_m3_caixa": 0.018 },
    { "sku": "SKU-2050", "descricao": "Suco 1L",          "peso_kg_caixa": 9.6,  "volume_m3_caixa": 0.015 },
    { "sku": "SKU-3300", "descricao": "Energético 269ml", "peso_kg_caixa": 7.2,  "volume_m3_caixa": 0.011 }
  ],

  "clientes": [
    { "codigo": "C-001", "razao_social": "Mercearia Sul Ltda",   "cd_atendimento": "CD-BH01", "latitude": -19.9245, "longitude": -43.9352, "janela_recebimento": { "inicio": "08:00", "fim": "12:00" } },
    { "codigo": "C-002", "razao_social": "Padaria Central ME",   "cd_atendimento": "CD-BH01", "latitude": -19.8891, "longitude": -43.9711, "janela_recebimento": null },
    { "codigo": "C-003", "razao_social": "Supermercado Norte",   "cd_atendimento": "CD-BH01", "latitude": -19.8402, "longitude": -43.9198, "janela_recebimento": { "inicio": "07:00", "fim": "16:00" } },
    { "codigo": "C-004", "razao_social": "Conveniência Savassi", "cd_atendimento": "CD-BH01", "latitude": -19.9386, "longitude": -43.9345, "janela_recebimento": { "inicio": "09:00", "fim": "17:00" } },
    { "codigo": "C-005", "razao_social": "Atacado Betim",        "cd_atendimento": "CD-BH01", "latitude": -19.9678, "longitude": -44.1982, "janela_recebimento": { "inicio": "06:00", "fim": "14:00" } },
    { "codigo": "C-006", "razao_social": "Bar do Zé",            "cd_atendimento": "CD-BH01", "latitude": null,     "longitude": null,     "janela_recebimento": null },
    { "codigo": "C-007", "razao_social": "Empório Vila Nova",    "cd_atendimento": "CD-SP02", "latitude": -23.5501, "longitude": -46.6339, "janela_recebimento": null }
  ],

  "pedidos": [
    { "numero": "PD-88120", "cliente": "C-001", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1001", "quantidade_caixas": 18 }, { "sku": "SKU-2050", "quantidade_caixas": 7 } ] },

    { "numero": "PD-88121", "cliente": "C-001", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-3300", "quantidade_caixas": 12 } ] },

    { "numero": "PD-88122", "cliente": "C-002", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1002", "quantidade_caixas": 40 } ] },

    { "numero": "PD-88123", "cliente": "C-003", "status": "CANCELADO",  "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1001", "quantidade_caixas": 200 } ] },

    { "numero": "PD-88124", "cliente": "C-003", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1001", "quantidade_caixas": 55 }, { "sku": "SKU-1002", "quantidade_caixas": 30 } ] },

    { "numero": "PD-88125", "cliente": "C-004", "status": "CONFIRMADO", "data_entrega": "2026-08-08",
      "itens": [ { "sku": "SKU-2050", "quantidade_caixas": 9 } ] },

    { "numero": "PD-88126", "cliente": "C-004", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-3300", "quantidade_caixas": 25 } ] },

    { "numero": "PD-88127", "cliente": "C-005", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1001", "quantidade_caixas": 120 }, { "sku": "SKU-2050", "quantidade_caixas": 60 } ] },

    { "numero": "PD-88127", "cliente": "C-005", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1001", "quantidade_caixas": 120 }, { "sku": "SKU-2050", "quantidade_caixas": 60 } ] },

    { "numero": "PD-88128", "cliente": "C-006", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1002", "quantidade_caixas": 15 } ] },

    { "numero": "PD-88129", "cliente": "C-999", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1001", "quantidade_caixas": 10 } ] },

    { "numero": "PD-88130", "cliente": "C-007", "status": "CONFIRMADO", "data_entrega": "2026-08-07",
      "itens": [ { "sku": "SKU-1002", "quantidade_caixas": 22 } ] }
  ],

  "frota": {
    "tipos": [
      { "codigo": "VUC",  "capacidade_kg": 1500, "capacidade_m3": 6.5,  "custo_km_relativo": 1.00, "restricao_centro_urbano": false },
      { "codigo": "TOCO", "capacidade_kg": 6000, "capacidade_m3": 22.0, "custo_km_relativo": 1.35, "restricao_centro_urbano": true }
    ],
    "disponibilidade": [
      { "cd": "CD-BH01", "tipo": "VUC",  "quantidade": 3, "em_manutencao": 1 },
      { "cd": "CD-BH01", "tipo": "TOCO", "quantidade": 2, "em_manutencao": 0 },
      { "cd": "CD-SP02", "tipo": "VUC",  "quantidade": 4, "em_manutencao": 0 }
    ]
  },

  "restricoes_circulacao": [
    { "cd": "CD-BH01", "tipo_veiculo": "TOCO", "clientes_bloqueados": ["C-004"], "motivo": "rodizio_centro" }
  ],

  "distancias_conhecidas": [
    { "origem": "CD-BH01", "destino": "C-005", "distancia_km": 31.4 },
    { "origem": "C-005", "destino": "CD-BH01", "distancia_km": 33.9 }
  ]
}
```

---

## Mapeamento bruto → modelo

| Elemento do modelo | Origem no JSON | Transformação necessária |
|---|---|---|
| $V$, nó 0 | `centros_distribuicao` | filtrar por `codigo` do CD-alvo; uma instância **por CD** |
| $N$ | `clientes` ∩ `pedidos` | join + filtro por `cd_atendimento`, `status`, `data_entrega` |
| $K$ | `frota.disponibilidade` | expandir `quantidade - em_manutencao` em veículos individuais |
| $q_i$ | `pedidos.itens` × `catalogo_produtos` | agregar por cliente: $q_i = \sum_{\text{itens}} \text{caixas} \times \text{peso\_kg\_caixa}$ |
| $Q$ | `frota.tipos.capacidade_kg` | escolher a dimensão *binding* (kg vs m³) ou modelar as duas |
| $c_{ij}$ | `latitude`/`longitude` | haversine → km → × `custo_por_km` × `custo_km_relativo[tipo(k)]` |
| $A$ (esparso) | derivado | $k$-vizinhos + `raio_maximo_atendimento_km` + `restricoes_circulacao` |

Note que $c_{ij}$ na formulação de três índices vira, na prática, $c_{ijk}$ — o custo depende do tipo do veículo. Isso é comum e não muda a estrutura do modelo, só o parâmetro.

---

## Armadilhas plantadas (o que a validação precisa pegar)

1. **Dois CDs** — o JSON contém duas instâncias sobrepostas; a transformação particiona, não mistura.
2. **Múltiplos pedidos por cliente** (C-001, C-003, C-004) — exige agregação; um erro aqui gera $q_i$ subestimado silenciosamente.
3. **Pedido duplicado** (`PD-88127` aparece duas vezes) — deduplicar por `numero` antes de somar, senão C-005 dobra de demanda.
4. **Filtros de status e data** — `PD-88123` é cancelado, `PD-88125` é de outro dia. C-004 tem um pedido válido e um inválido.
5. **Integridade referencial** — `C-999` aparece em pedido mas não no cadastro. Erro fatal ou warning com descarte? Decisão de política, não de código.
6. **Coordenada nula** — C-006 tem pedido válido mas não pode entrar no grafo. Bloqueia a instância inteira ou exclui o cliente?
7. **Unidades** — demanda em caixas, capacidade em kg. Conversão obrigatória via catálogo; SKU ausente no catálogo é falha de validação.
8. **Duas capacidades** (kg e m³) — o modelo canônico tem um único $Q$. Ou você escolhe a restritiva, ou duplica a restrição (5). Decisão de modelagem que o dado força.
9. **Frota efetiva ≠ declarada** — `quantidade - em_manutencao` define $|K|$; ignorar isso torna o modelo otimista.
10. **Arcos bloqueados** — `restricoes_circulacao` remove combinações $(i,j,k)$ específicas. É exatamente o `valid_ijk` esparso: o TOCO não pode chegar em C-004, então $x_{i,\text{C-004},k}$ nem existe para $k$ do tipo TOCO.
11. **Override de distância** — `distancias_conhecidas` sobrescreve o haversine e é **assimétrico** (31.4 vs 33.9). Se sua estrutura assume simetria, quebra aqui.
12. **Viabilidade** — vale checar $\sum_i q_i \le \sum_k Q_k$ e $\max_i q_i \le \max_k Q_k$ antes de construir o modelo. Detectar inviabilidade na validação custa microssegundos; descobrir pelo solver custa minutos.

O ponto 10 é o que torna este JSON interessante para a arquitetura: `valid_ijk` deixa de ser um produto cartesiano e passa a ser um dado derivado de três fontes independentes (raio, vizinhança, restrição regulatória) — que é exatamente o cenário em que o `frozenset` de tuplas se paga contra a matriz densa.