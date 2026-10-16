# Resultats empírics: Set Transformer contra DeepSets

> El Set Transformer substitueix DeepSets (el model es descriu a
> [`TRANSFORMER.md`](TRANSFORMER.md)). **60 entrenaments**, el 2026-10-11: les 8 llavors
> aparellades amb equips no vistos i 4 configuracions al holdout. **160 més** el 2026-10-15:
> quatre variants per frenar l'atenció, a les mateixes 8 llavors (§5). Comprovat: la llavor 0 del
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

**Intents de millorar-ho (§5).** Frenant l'atenció de quatre maneres, la millor (un sol SAB)
puja a 0.888 i guanya el Transformer per defecte a les 8 llavors, però contra DeepSets només
empata (−0.003, t = −1,9, 2 de 8). Amb una porta que comença a 0, la xarxa la deixa gairebé
tancada. Tancat com a segon resultat negatiu.

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

### Intents de millorar-ho (2026-10-15)

Si el problema és sobreajust a combinacions de granades de cada equip, el remei és frenar
l'atenció, no donar-li més capacitat. Quatre variants, totes amb equips no vistos i les mateixes
8 llavors aparellades que DeepSets (**160 entrenaments**, 5 h 30 min):

| Config | Què canvia | Per què |
|---|---|---|
| `gate0` | la branca d'atenció passa per un `α` après que comença a 0 (`TRANSFORMER.md` §2) | el bloc arrenca sent DeepSets i només barreja granades si les dades ho demanen |
| `wd_1e-3` | weight decay 10 vegades més gran | regularitzar totes les matrius, l'atenció inclosa |
| `phi1` | un sol SAB en comptes de dos | menys interacció i la meitat de paràmetres al codificador |
| `narrow` | amplades 12/16 en comptes de 24/32 | menys capacitat a tot arreu |

**Cap arriba a DeepSets.** Les tres que frenen l'atenció milloren el Transformer per defecte;
la que només en treu mida, l'empitjora:

| llavor | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | mitjana |
|---|---|---|---|---|---|---|---|---|---|
| DeepSets | 0.8862 | 0.8868 | 0.8934 | 0.8895 | 0.8923 | 0.8929 | 0.8907 | 0.8943 | **0.8908 ±0.0030** |
| ST per defecte | 0.8854 | 0.8653 | 0.8809 | 0.8778 | 0.8695 | 0.8803 | 0.8876 | 0.8879 | 0.8793 ±0.0083 |
| `gate0` | 0.8809 | 0.8826 | 0.8826 | 0.8806 | 0.8820 | 0.8854 | 0.8854 | 0.8840 | 0.8829 ±0.0018 |
| `wd_1e-3` | 0.8845 | 0.8795 | 0.8840 | 0.8803 | 0.8817 | 0.8815 | 0.8895 | 0.8834 | 0.8831 ±0.0032 |
| **`phi1`** | 0.8884 | 0.8884 | 0.8881 | 0.8865 | 0.8817 | 0.8929 | 0.8881 | 0.8890 | **0.8879 ±0.0031** |
| `narrow` | 0.8834 | 0.8600 | 0.8672 | 0.8611 | 0.8672 | 0.8706 | 0.8633 | 0.8717 | 0.8681 ±0.0075 |

Aparellat (t amb 7 g.l.; el llindar de p = 0,05 és |t| = 2,36):

| Variant | − DeepSets | t | guanya | − ST per defecte | t | guanya | 3 classes (DS 0.600) |
|---|---|---|---|---|---|---|---|
| `gate0` | −0.0078 | −8,4 | 0 de 8 | +0.0036 | 1,3 | 5 de 8 | 0.598 · t = −1,7 |
| `wd_1e-3` | −0.0077 | −5,3 | 0 de 8 | +0.0037 | 1,7 | 6 de 8 | 0.598 · t = −0,7 |
| **`phi1`** | **−0.0029** | −1,9 | 2 de 8 | **+0.0086** | 3,2 | **8 de 8** | **0.602** · t = +0,7 |
| `narrow` | −0.0227 | −7,7 | 0 de 8 | −0.0113 | −4,0 | 0 de 8 | 0.591 · t = −3,7 |

- **`phi1` és la millor i la més propera a DeepSets**: guanya el Transformer per defecte a les
  8 llavors i queda 0,3 punts per sota de DeepSets, sense diferència significativa
  (p ≈ 0,10). A 3 classes fins i tot el supera per poc (0.602 contra 0.600, no significatiu). Però
  només guanya DeepSets a 2 llavors de 8: en el millor dels casos **empata, no millora**.
- **`gate0` i `wd_1e-3` treuen la variància** (±0.002–0.003, com DeepSets) però es queden a
  −0,8 punts, i aquí la diferència sí que és clara (0 de 8).
- **`narrow` confirma que no és la mida**: treu més paràmetres que `phi1` i perd encara més
  (−2,3 punts), mentre que treure només un SAB millora. El que fa mal és la segona capa
  d'interacció, no els paràmetres.

**Per mapa** (mitjana de les 8 llavors), on el Transformer per defecte més perdia:

| Mapa | plants | DeepSets | ST per defecte | `gate0` | `wd_1e-3` | `phi1` | `narrow` |
|---|---|---|---|---|---|---|---|
| de_overpass | 162 | 0.927 | 0.845 | 0.906 | 0.896 | **0.915** | 0.887 |
| de_train | 262 | 0.828 | 0.806 | 0.804 | 0.789 | **0.838** | 0.749 |
| de_anubis | 366 | 0.890 | 0.861 | 0.879 | 0.876 | 0.875 | 0.856 |
| de_nuke | 435 | 0.782 | 0.772 | 0.781 | 0.782 | 0.783 | 0.764 |
| de_dust2 | 879 | 0.923 | 0.925 | 0.918 | 0.925 | 0.924 | 0.915 |

`phi1` recupera gairebé tot overpass (de 0.845 a 0.915) i supera DeepSets a train. Anubis
continua 1,5 punts per sota. Als altres mapes (ancient, cache, inferno, mirage) totes les
variants queden a ±1 punt de DeepSets.

**La porta `α` de `gate0`** (mitjana de 5 folds × 8 llavors; 0 vol dir que la capa és DeepSets):

| Cap | SAB 1 | SAB 2 | \|α\| màxim |
|---|---|---|---|
| gate (planta o no) | −0.003 ±0.018 | +0.001 ±0.016 | 0.05 |
| timing | +0.012 ±0.058 | −0.017 ±0.106 | 0.20 |
| site (A o B) | +0.029 ±0.179 | −0.104 ±0.116 | 0.35 |

**La mateixa xarxa decideix no fer servir l'atenció.** Als caps de gate i timing la porta no es
mou de 0. Només el cap de site l'obre una mica, sobretot al segon SAB, amb un signe que canvia
d'un fold a un altre. I quan l'obre, perd 0,8 punts contra DeepSets: el que aprèn de la
interacció entre granades no es transfereix a equips nous.

### Veredicte

**Segon resultat negatiu, tancat.** Cap de les quatre variants arriba a DeepSets. La millor
(`phi1`) només hi empata, i ho fa traient interacció: com menys atenció, més s'acosta a
DeepSets, que n'és el cas límit (atenció zero). La porta après ho diu directament, quedant a
prop de 0. Coincideix amb la GCN: **la posició de cada granada ja porta el senyal, i fer-les
interactuar no hi afegeix res**. Amb aquesta tendència, el dropout a l'atenció (l'última
candidata) com a molt acostaria el model a DeepSets, no el passaria. No s'ha provat.

JSON a `sweep_tf/ltoV_seed*.json`; runner `data_store/run_tf2.sh`; comparació
`data_store/compare_tf2.py`.


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

Les variants del §5 amb `data_store/run_tf2.sh`: `--stage lto --folds 5 --seed N --only
gate0,wd_1e-3,phi1,narrow --jobs 6`, N = 0…7, tres llavors en paral·lel (160 entrenaments,
5 h 30 min amb la CPU limitada a ~900 MHz). La comparació:

```bash
docker exec cs2-backend-dev python3 /app/data_store/compare_tf2.py
```
