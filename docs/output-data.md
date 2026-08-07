# Saída da solução — JSON hierárquico + tabela flat

## 1. JSON de saída

Estrutura em três níveis: envelope de execução → KPIs agregados → rotas → paradas. O JSON é a fonte de verdade; a tabela flat é uma projeção dele.

```json
{
  "execucao": {
    "id_execucao": "RUN-20260807-0631-CDBH01",
    "instancia": "CD-BH01/2026-08-07",
    "gerado_em": "2026-08-07T06:31:44-03:00",
    "versao_modelo": "cvrp-3idx-1.4.0",
    "hash_instancia": "sha256:a41c9e7b0d2f8813",
    "moeda": "BRL"
  },

  "status_solver": {
    "status": "OPTIMAL_TOLERANCE",
    "objetivo": 2417.63,
    "bound_dual": 2401.55,
    "gap_relativo": 0.00665,
    "tempo_build_s": 3.82,
    "tempo_solve_s": 47.19,
    "nos_explorados": 1284,
    "iteracoes_simplex": 96412,
    "num_variaveis": 18420,
    "num_restricoes": 7315,
    "num_nao_zeros": 91307,
    "cortes_aplicados": { "rounded_capacity": 214, "clique": 12, "cover": 31 }
  },

  "instancia_resumo": {
    "clientes_elegiveis": 5,
    "clientes_atendidos": 5,
    "clientes_descartados": [
      { "codigo": "C-006", "motivo": "coordenada_ausente" },
      { "codigo": "C-999", "motivo": "cliente_nao_cadastrado" }
    ],
    "veiculos_disponiveis": 4,
    "veiculos_utilizados": 2,
    "demanda_total_kg": 3268.8,
    "capacidade_total_kg": 15000.0
  },

  "kpis_globais": {
    "custo_total": 2417.63,
    "custo_fixo": 360.00,
    "custo_variavel": 2057.63,
    "distancia_total_km": 428.17,
    "custo_por_km": 5.65,
    "custo_por_kg_entregue": 0.7396,
    "custo_por_parada": 483.53,
    "duracao_total_h": 15.62,
    "paradas_total": 5,
    "paradas_por_rota_media": 2.5,
    "carga_total_kg": 3268.8,
    "carga_media_por_rota_kg": 1634.4,
    "ocupacao_media_pct": 45.63,
    "ocupacao_minima_pct": 22.34,
    "ocupacao_maxima_pct": 68.92,
    "desvio_padrao_carga_kg": 1024.71,
    "indice_balanceamento": 0.627,
    "km_por_parada": 85.63,
    "km_vazio_retorno": 33.90,
    "pct_km_vazio": 7.92
  },

  "rotas": [
    {
      "id_rota": 1,
      "veiculo": { "id": "VUC-CDBH01-01", "tipo": "VUC", "capacidade_kg": 1500.0, "capacidade_m3": 6.5 },
      "kpis": {
        "distancia_km": 78.42,
        "duracao_h": 3.14,
        "custo_fixo": 180.00,
        "custo_variavel": 380.34,
        "custo_total": 560.34,
        "custo_por_km": 7.15,
        "carga_kg": 1033.92,
        "carga_m3": 1.52,
        "ocupacao_kg_pct": 68.92,
        "ocupacao_m3_pct": 23.38,
        "dimensao_restritiva": "kg",
        "folga_kg": 466.08,
        "num_paradas": 3,
        "km_por_parada": 26.14,
        "carga_media_por_parada_kg": 344.64,
        "custo_por_kg": 0.5419
      },
      "paradas": [
        { "seq": 0, "no": "CD-BH01", "tipo": "deposito", "chegada": "07:00", "saida": "07:00",
          "carga_a_bordo_kg": 1033.92, "distancia_acum_km": 0.00 },

        { "seq": 1, "no": "C-003", "tipo": "cliente", "razao_social": "Supermercado Norte",
          "chegada": "07:34", "servico_min": 127.5, "saida": "09:41",
          "demanda_kg": 1152.00, "carga_a_bordo_kg": 1033.92, "distancia_arco_km": 18.20,
          "distancia_acum_km": 18.20, "custo_arco": 88.27, "pedidos": ["PD-88124"] },

        { "seq": 2, "no": "C-001", "tipo": "cliente", "razao_social": "Mercearia Sul Ltda",
          "chegada": "10:02", "servico_min": 55.5, "saida": "10:58",
          "demanda_kg": 326.40, "carga_a_bordo_kg": 259.20, "distancia_arco_km": 11.30,
          "distancia_acum_km": 29.50, "custo_arco": 54.81, "pedidos": ["PD-88120", "PD-88121"] },

        { "seq": 3, "no": "C-004", "tipo": "cliente", "razao_social": "Conveniência Savassi",
          "chegada": "11:07", "servico_min": 37.5, "saida": "11:45",
          "demanda_kg": 180.00, "carga_a_bordo_kg": 0.00, "distancia_arco_km": 4.62,
          "distancia_acum_km": 34.12, "custo_arco": 22.41, "pedidos": ["PD-88126"] },

        { "seq": 4, "no": "CD-BH01", "tipo": "retorno", "chegada": "12:24",
          "carga_a_bordo_kg": 0.00, "distancia_arco_km": 44.30,
          "distancia_acum_km": 78.42, "custo_arco": 214.86 }
      ]
    },

    {
      "id_rota": 2,
      "veiculo": { "id": "TOCO-CDBH01-01", "tipo": "TOCO", "capacidade_kg": 6000.0, "capacidade_m3": 22.0 },
      "kpis": {
        "distancia_km": 349.75,
        "duracao_h": 12.48,
        "custo_fixo": 180.00,
        "custo_variavel": 1677.29,
        "custo_total": 1857.29,
        "custo_por_km": 5.31,
        "carga_kg": 2234.88,
        "carga_m3": 3.42,
        "ocupacao_kg_pct": 37.25,
        "ocupacao_m3_pct": 15.55,
        "dimensao_restritiva": "kg",
        "folga_kg": 3765.12,
        "num_paradas": 2,
        "km_por_parada": 174.88,
        "carga_media_por_parada_kg": 1117.44,
        "custo_por_kg": 0.8311
      },
      "paradas": [
        { "seq": 0, "no": "CD-BH01", "tipo": "deposito", "chegada": "06:00", "saida": "06:00",
          "carga_a_bordo_kg": 2234.88, "distancia_acum_km": 0.00 },

        { "seq": 1, "no": "C-005", "tipo": "cliente", "razao_social": "Atacado Betim",
          "chegada": "06:59", "servico_min": 270.0, "saida": "11:29",
          "demanda_kg": 2304.00, "carga_a_bordo_kg": 480.00, "distancia_arco_km": 31.40,
          "distancia_acum_km": 31.40, "custo_arco": 205.60, "pedidos": ["PD-88127"] },

        { "seq": 2, "no": "C-002", "tipo": "cliente", "razao_social": "Padaria Central ME",
          "chegada": "12:07", "servico_min": 60.0, "saida": "13:07",
          "demanda_kg": 480.00, "carga_a_bordo_kg": 0.00, "distancia_arco_km": 20.45,
          "distancia_acum_km": 51.85, "custo_arco": 133.89, "pedidos": ["PD-88122"] },

        { "seq": 3, "no": "CD-BH01", "tipo": "retorno", "chegada": "13:41",
          "carga_a_bordo_kg": 0.00, "distancia_arco_km": 297.90,
          "distancia_acum_km": 349.75, "custo_arco": 1337.80 }
      ]
    }
  ],

  "diagnostico": [
    { "nivel": "WARN", "codigo": "OCUPACAO_BAIXA", "rota": 2,
      "mensagem": "Ocupação de 37.25% sugere que um VUC atenderia a rota." },
    { "nivel": "INFO", "codigo": "CLIENTE_DESCARTADO", "entidade": "C-006",
      "mensagem": "Pedido PD-88128 (180kg) não roteirizado por ausência de coordenada." }
  ]
}
```

---

## 2. Tabela flat (uma linha por parada)

O grão é **parada**, não rota. Isso permite reconstruir tudo por agregação e é o formato que sobrevive a pivot no Excel. Colunas de nível superior são desnormalizadas (repetidas).

| Coluna | Grão | Exemplo |
|---|---|---|
| `id_execucao` | execução | RUN-20260807-0631-CDBH01 |
| `instancia` | execução | CD-BH01/2026-08-07 |
| `gerado_em` | execução | 2026-08-07T06:31:44 |
| `status_solver` | execução | OPTIMAL_TOLERANCE |
| `gap_pct` | execução | 0.665 |
| `objetivo_total` | execução | 2417.63 |
| `dist_total_km` | execução | 428.17 |
| `veiculos_utilizados` | execução | 2 |
| `ocupacao_media_pct` | execução | 45.63 |
| `id_rota` | rota | 1 |
| `veiculo_id` | rota | VUC-CDBH01-01 |
| `veiculo_tipo` | rota | VUC |
| `capacidade_kg` | rota | 1500.0 |
| `rota_dist_km` | rota | 78.42 |
| `rota_duracao_h` | rota | 3.14 |
| `rota_custo_total` | rota | 560.34 |
| `rota_custo_fixo` | rota | 180.00 |
| `rota_custo_variavel` | rota | 380.34 |
| `rota_carga_kg` | rota | 1033.92 |
| `rota_ocupacao_pct` | rota | 68.92 |
| `rota_num_paradas` | rota | 3 |
| `rota_km_por_parada` | rota | 26.14 |
| `rota_custo_por_kg` | rota | 0.5419 |
| `seq` | parada | 1 |
| `no` | parada | C-003 |
| `tipo_no` | parada | cliente |
| `razao_social` | parada | Supermercado Norte |
| `pedidos` | parada | PD-88124 |
| `demanda_kg` | parada | 1152.00 |
| `carga_a_bordo_kg` | parada | 1033.92 |
| `chegada` | parada | 07:34 |
| `saida` | parada | 09:41 |
| `servico_min` | parada | 127.5 |
| `dist_arco_km` | parada | 18.20 |
| `dist_acum_km` | parada | 18.20 |
| `custo_arco` | parada | 88.27 |
| `pct_rota_percorrido` | parada | 23.21 |

### Amostra materializada

```
id_execucao          instancia          status_solver       gap_pct  objetivo_total  dist_total_km  veiculos_utilizados  id_rota  veiculo_id       veiculo_tipo  capacidade_kg  rota_dist_km  rota_custo_total  rota_carga_kg  rota_ocupacao_pct  rota_num_paradas  seq  no        tipo_no    razao_social            pedidos              demanda_kg  carga_a_bordo_kg  chegada  saida  servico_min  dist_arco_km  dist_acum_km  custo_arco  pct_rota_percorrido
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    1        VUC-CDBH01-01    VUC           1500.0         78.42         560.34            1033.92        68.92              3                 0    CD-BH01   deposito   CD Contagem             —                    0.00        1033.92           07:00    07:00  0.0          0.00          0.00          0.00        0.00
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    1        VUC-CDBH01-01    VUC           1500.0         78.42         560.34            1033.92        68.92              3                 1    C-003     cliente    Supermercado Norte      PD-88124             1152.00     1033.92           07:34    09:41  127.5        18.20         18.20         88.27       23.21
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    1        VUC-CDBH01-01    VUC           1500.0         78.42         560.34            1033.92        68.92              3                 2    C-001     cliente    Mercearia Sul Ltda      PD-88120;PD-88121    326.40      259.20            10:02    10:58  55.5         11.30         29.50         54.81       37.62
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    1        VUC-CDBH01-01    VUC           1500.0         78.42         560.34            1033.92        68.92              3                 3    C-004     cliente    Conveniência Savassi    PD-88126             180.00      0.00              11:07    11:45  37.5         4.62          34.12         22.41       43.51
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    1        VUC-CDBH01-01    VUC           1500.0         78.42         560.34            1033.92        68.92              3                 4    CD-BH01   retorno    CD Contagem             —                    0.00        0.00              12:24    —      0.0          44.30         78.42         214.86      100.00
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    2        TOCO-CDBH01-01   TOCO          6000.0         349.75        1857.29           2234.88        37.25              2                 0    CD-BH01   deposito   CD Contagem             —                    0.00        2234.88           06:00    06:00  0.0          0.00          0.00          0.00        0.00
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    2        TOCO-CDBH01-01   TOCO          6000.0         349.75        1857.29           2234.88        37.25              2                 1    C-005     cliente    Atacado Betim           PD-88127             2304.00     480.00            06:59    11:29  270.0        31.40         31.40         205.60      8.98
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    2        TOCO-CDBH01-01   TOCO          6000.0         349.75        1857.29           2234.88        37.25              2                 2    C-002     cliente    Padaria Central ME      PD-88122             480.00      0.00              12:07    13:07  60.0         20.45         51.85         133.89      14.82
RUN-20260807-0631…   CD-BH01/2026-08-07  OPTIMAL_TOLERANCE   0.665    2417.63         428.17         2                    2        TOCO-CDBH01-01   TOCO          6000.0         349.75        1857.29           2234.88        37.25              2                 3    CD-BH01   retorno    CD Contagem             —                    0.00        0.00              13:41    —      0.0          297.90        349.75        1337.80     100.00
```

---

## 3. Notas de design

**Por que grão de parada.** Uma linha por rota perderia a sequência (que é a informação central de um VRP), e uma linha por execução seria inútil para operação. Com grão de parada, `SUM(dist_arco_km)` agrupado por `id_rota` reproduz `rota_dist_km` — os campos desnormalizados são redundantes por construção, o que dá uma checagem de consistência gratuita.

**KPIs derivados vs armazenados.** `rota_custo_por_kg`, `ocupacao_pct` e `km_por_parada` são calculados na camada de report, não pelo solver. Mantê-los na saída evita que cada consumidor (Excel, BI, e-mail) recalcule com fórmula ligeiramente diferente.

**`indice_balanceamento`.** Definido como $1 - \frac{\sigma_{\text{carga}}}{\bar{q}}$; 1.0 = rotas perfeitamente equilibradas. Métrica útil porque o CVRP puro minimiza distância e frequentemente entrega rotas muito desiguais — o que é ótimo no papel e ruim para o motorista.

**`dimensao_restritiva`.** Explicita qual restrição de capacidade está ativa. Se todas as rotas mostram `kg` e a ocupação em m³ fica abaixo de 25%, a restrição volumétrica é redundante no modelo e pode ser removida — economia direta de restrições em escala.

**`km_vazio_retorno` / `pct_km_vazio`.** O arco de retorno ao depósito é percorrido com carga zero. Na rota 2 ele representa 85% da distância total — sinal claro de que o cliente C-002 está mal posicionado na sequência ou que faltam clientes a jusante. Anomalia que só aparece se você medir.

**Escrita em Excel.** O flat vai numa aba `paradas`; os KPIs por rota e globais viram abas `rotas` e `resumo` derivadas por agregação. Com xlsxwriter em `constant_memory`, escreva `paradas` linha a linha em ordem de `(id_rota, seq)` — as demais abas são pequenas e podem ser escritas normalmente. Para instâncias grandes (10M variáveis → possivelmente 10⁵–10⁶ paradas), a aba `paradas` pode estourar e deve ir para Parquet, mantendo no Excel só as agregações.
