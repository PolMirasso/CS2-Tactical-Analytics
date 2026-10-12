# Resultats empírics: Set Transformer contra DeepSets

> El Set Transformer substitueix DeepSets (el model es descriu a
> [`TRANSFORMER.md`](TRANSFORMER.md)). **60 entrenaments**, el 2026-10-11: les 8 llavors
> aparellades amb equips no vistos i 4 configuracions al holdout. Comprovat: la llavor 0 del
> holdout dona exactament el mateix que la prova de fum aïllada, o sigui que la partició 80/20
> és la mateixa que la de DeepSets i la GCN.
>
> Els JSON crus són a `data_store/sweep_tf/`; els de DeepSets, a
> `data_store/sweep_deepsets_2026-09-21/`; els de la GCN, a `data_store/sweep/`.


---

## 1. La resposta curta

**El Set Transformer perd contra DeepSets.** És la primera arquitectura que queda clarament per
sota, no empatada.

| | Set Transformer | DeepSets | Diferència |
|---|---|---|---|
| A contra B, **equips no vistos** (8 llavors) | 0.879 ±0.008 | 0.891 ±0.003 | **−0.011 · t = −4,1 · 0 de 8** |
| A contra B, holdout (5 particions) | 0.893 ±0.008 | 0.899 ±0.005 | −0.006 |
| 3 classes, equips no vistos | 0.597 ±0.005 | 0.600 ±0.005 | −0.004 · t = −1,4 · 3 de 8 |
| 3 classes, holdout | 0.610 ±0.019 | 0.614 ±0.011 | −0.004 |
| Timing, holdout | 0.870 ±0.010 | 0.880 ±0.006 | −0.010 |
| ECE (abans → després) | 0.041 → **0.024** | 0.045 → 0.035 | millor calibrada |
| Un entrenament sencer | 2382 s | 673 s | **3,5 vegades més lent** |

La comparació d'equips no vistos és **aparellada**: cada llavor entrena tots dos models amb els
mateixos folds. De les 8 llavors, el Transformer no en guanya **cap** contra DeepSets ni contra
la GCN residual, i només una contra la GCN sense residual:

| Set Transformer − … | Δ mitjà | t (7 g.l.) | Llavors guanyades |
|---|---|---|---|
| DeepSets | −0.0114 ±0.0079 | −4,07 | 0 de 8 |
| GCN | −0.0094 ±0.0087 | −3,05 | 1 de 8 |
| GCN residual | −0.0118 ±0.0072 | −4,62 | 0 de 8 |

Tres coses que diu la bateria:

- **Al holdout gairebé empata; amb equips no vistos no.** La diferència es dobla quan els
  equips de test no s'han vist mai (§5).
- **És el més variable de tots** entre llavors (±0.008, més que la GCN sense residual), tot i
  portar la connexió residual de sèrie, que a la GCN era el que l'estabilitzava.
- **Calibra millor**, com la GCN: l'ECE després de la temperatura baixa a 0.024 (DeepSets
  0.035). No mou cap encert.

**Lectura per a la memòria.** El Transformer és el pas següent a la GCN: en lloc d'un graf fix
que decideixo jo, la xarxa aprèn quant mira cada granada a cada altra. Si la relació entre
granades portés senyal, aquí hauria de sortir. No surt, i la flexibilitat extra es paga amb
equips que no ha vist. Confirma el que deia la GCN: **la posició de cada granada ja porta el
senyal, i fer-les interactuar no hi afegeix res.**

---

## 2. El model per defecte

**settf[2×SAB · 4 caps + LN] 18→24/32 · atenció · ρ 32→2 · ReLU**, α = 1e-4, lr = 5e-3. Tota
la resta, igual que a `RESULTATS.md` §3. Cap hiperparàmetre està ajustat: són els del paper
(2 SAB, 4 caps, post-LN) amb les amplades de DeepSets.

### Holdout 80/20

| Partició | site ST | site DS | 3 classes ST | 3 classes DS | timing ST | timing DS | ECE ST | ECE DS |
|---|---|---|---|---|---|---|---|---|
| seed 0 | 0.906 | 0.907 | 0.634 | 0.631 | 0.868 | 0.881 | 0.057 → 0.047 | 0.039 → 0.033 |
| seed 1 | 0.884 | 0.897 | 0.596 | 0.600 | 0.876 | 0.877 | 0.044 → 0.018 | 0.033 → 0.026 |
| seed 2 | 0.895 | 0.894 | 0.617 | 0.610 | 0.854 | 0.870 | 0.036 → 0.019 | 0.032 → 0.028 |
| seed 3 | 0.894 | 0.897 | 0.587 | 0.621 | 0.875 | 0.884 | 0.036 → 0.012 | 0.069 → 0.053 |
| seed 4 | 0.888 | 0.899 | 0.617 | 0.605 | 0.879 | 0.887 | 0.033 → 0.023 | 0.053 → 0.037 |
| **mitjana** | **0.893 ±0.008** | 0.899 ±0.005 | **0.610 ±0.019** | 0.614 ±0.011 | **0.870 ±0.010** | 0.880 ±0.006 | **0.041 → 0.024** | 0.045 → 0.035 |

Baselines: A contra B 0.533, 3 classes 0.450, timing 0.583.

**El timing** perd un punt sencer i queda a 0.870, pràcticament a la regla "última granada +
9 s" (0.868, `RESULTATS.md` §8). El cap de timing gairebé no hi afegeix res.

### Deixant equips fora (llavor 0)

| Fold | equips fora | rondes per entrenar | plants de test | site ST | site DS |
|---|---|---|---|---|---|
| 1 | 8 | 4264 | 750 | 0.892 | 0.899 |
| 2 | 8 | 4173 | 755 | 0.890 | 0.894 |
| 3 | 11 | 4216 | 712 | 0.865 | 0.865 |
| 4 | 14 | 4172 | 701 | 0.887 | 0.882 |
| 5 | 14 | 4086 | 667 | 0.892 | 0.891 |
| **Conjunt** | 55 | — | 3585 | **0.885** | 0.886 |

La llavor 0 és la que més afavoreix el Transformer (gairebé empat). Les altres set queden totes
per sota:

| llavor | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | mitjana |
|---|---|---|---|---|---|---|---|---|---|
| DeepSets | 0.8862 | 0.8868 | 0.8934 | 0.8895 | 0.8923 | 0.8929 | 0.8907 | 0.8943 | 0.8908 ±0.0030 |
| GCN | 0.8923 | 0.8745 | 0.8862 | 0.8890 | 0.8971 | 0.8934 | 0.8909 | 0.8862 | 0.8887 ±0.0068 |
| GCN residual | 0.8943 | 0.8876 | 0.8890 | 0.8898 | 0.8921 | 0.8918 | 0.8909 | 0.8932 | 0.8911 ±0.0022 |
| **Set Transformer** | 0.8854 | 0.8653 | 0.8809 | 0.8778 | 0.8695 | 0.8803 | 0.8876 | 0.8879 | **0.8793 ±0.0083** |

Rang entre llavors: 2,3 punts (0.8653–0.8879), igual que la GCN sense residual i el triple que
DeepSets. Prova de Levene contra DeepSets: p = 0,08.

---

## 3. Caps d'atenció i LayerNorm

Les dues decisions pròpies del Transformer. Holdout, 5 particions:

| Configuració | site | 3 classes | timing | ECE (abans → després) |
|---|---|---|---|---|
| **`baseline`** (4 caps de 6 dim + LN) | 0.893 ±0.008 | 0.610 | 0.870 | 0.041 → 0.024 |
| `heads_1` (1 cap de 24 dim) | 0.896 ±0.015 | 0.608 | 0.868 | 0.035 → 0.025 |
| `heads_2` (2 caps de 12 dim) | 0.897 ±0.011 | 0.607 | 0.868 | 0.041 → 0.022 |
| `no_ln` (sense LayerNorm) | 0.894 ±0.010 | 0.609 | 0.869 | 0.038 → 0.019 |

**Cap de les dues importa.** Les quatre variants queden a ±0.004 entre elles, molt per sota de
la desviació entre particions (0.008–0.015), i cap arriba a DeepSets (0.899). Treure la
LayerNorm, que el codi oficial del paper porta desactivada per defecte, tampoc canvia res. No és
un problema d'haver triat malament un hiperparàmetre del Transformer.

---

## 4. Precisió per mapa

Deixant equips fora, **mitjana de les 8 llavors** a totes les columnes (comparable amb
`RESULTATS-GCN.md` §6):

| Mapa | plants | site ST | site DS | site GCN residual | baseline A/B |
|---|---|---|---|---|---|
| de_dust2 | 879 | 0.925 | 0.923 | 0.924 | 0.534 |
| de_mirage | 531 | 0.913 | 0.919 | 0.919 | 0.629 |
| de_nuke | 435 | **0.772** | 0.782 | 0.786 | 0.497 |
| de_ancient | 418 | 0.888 | 0.896 | 0.890 | 0.471 |
| de_anubis | 366 | **0.861** | 0.890 | 0.893 | 0.454 |
| de_inferno | 340 | 0.906 | 0.913 | 0.915 | 0.438 |
| de_train | 262 | **0.806** | 0.828 | 0.830 | 0.458 |
| de_cache | 192 | 0.914 | 0.917 | 0.920 | 0.542 |
| de_overpass | 162 | **0.845** | 0.927 | 0.912 | 0.444 |

- **Al mapa amb més dades (dust2) empata**: 0.925 contra 0.923.
- **On més perd és als mapes amb menys plants**: overpass −8,2 punts (162 plants), train
  −2,2 (262), anubis −2,9 (366). Cache (192) és l'excepció.

---

## 5. Per què perd

**No és falta de capacitat.** El codificador té uns **8.600 paràmetres**, contra uns 1.400 de
la φ de DeepSets. Però `xwide` ja en tenia uns 10.700 a la φ i quedava a
0.890 amb equips fora, al nivell del defecte. La mida sola no fa perdre.

**El que canvia és que les granades s'influeixen entre elles i que la xarxa decideix com.**
La caiguda de holdout a equips no vistos:

| | holdout | equips no vistos | caiguda |
|---|---|---|---|
| DeepSets | 0.899 | 0.891 | 0.008 |
| GCN | 0.896 | 0.889 | 0.007 |
| GCN residual | 0.902 | 0.891 | 0.011 |
| **Set Transformer** | 0.893 | 0.879 | **0.014** |

Al holdout els equips de test ja s'han vist entrenant (altres rondes seves), i el Transformer
gairebé empata. Amb equips nous perd el doble que DeepSets. Encaixa amb que l'atenció aprengui
**combinacions de granades pròpies de cada equip**, que no es repeteixen en un altre. També
encaixa amb el §4: perd sobretot on hi ha menys rondes per aprendre-les.

Comparat amb la GCN: allà els pesos entre granades els fixava un kernel d'espai i temps, i en
el pitjor cas podia aprendre a ignorar-los (la residual). Aquí la xarxa els pot ajustar a les
dades lliurement, i amb unes 3.600 rondes amb plant ho fa massa.

**Estic mirant com millorar-ho** 


---

## 6. Com reproduir-ho

A la branca `arch/transformer`, copiant `sweep.py` al contenidor com a
`data_store/sweep_tf.py` (`/app` no és escrivible). El runner és `data_store/run_tf.sh`
(només dins el contenidor), amb `SWEEP_OUT=/app/data_store/sweep_tf` i `PYTHONPATH=/app`:

| Etapa | Ordre | Entrenaments |
|---|---|---|
| holdout | `--stage configs --seeds 5 --only baseline,heads_1,heads_2,no_ln` | 20 |
| equips no vistos | `--stage lto --folds 5 --seed N --only baseline`, N = 0…7 | 40 |
| **Total** | | **60** |

Unes 4 h 40 min amb ~15 workers. La comparació aparellada amb DeepSets i la GCN:

```bash
docker exec -e PYTHONPATH=/app cs2-backend-dev python3 /app/data_store/compare_tf.py
```
