# Comparativa d'arquitectures: DeepSets, GCN, Set Transformer i Clef

> Les tres arquitectures provades per al codificador de granades de `/scouting`, més Clef (un
> LLM que no s'entrena, en tres tandes: zero-shot, amb context i amb exemples), sobre **les mateixes dades** (324 demos · 6675 rondes · 3585 plants · 55
> equips · 9 mapes) i **les mateixes particions**: la llavor 0 del holdout dona exactament el
> mateix a totes les branques, i les 8 llavors d'equips no vistos són aparellades (mateixos folds
> per a tots els models). Clef no s'entrena: dona una sola xifra, la mateixa a totes les llavors.
>
> `main` serveix DeepSets. Cada alternativa viu a la seva branca amb els seus resultats
> complets: `RESULTATS-GCN.md` a `arch/gcn`, `RESULTATS-TRANSFORMER.md` a `arch/transformer` i
> `RESULTATS-CLEF.md` a `arch/clef`. Aquí només hi ha el que cal per comparar-les.

---

## 1. La resposta curta

**Cap arquitectura millora DeepSets.** La GCN hi empata, la GCN residual hi empata i és igual
d'estable, el Set Transformer perd i Clef queda per sota: 17 punts sense exemples i 6,8 amb 8
exemples.

| Model | Branca | Equips no vistos (8 llavors) | − DeepSets · t · llavors guanyades |
|---|---|---|---|
| **DeepSets** | `main` | **0.891 ±0.003** | - |
| GCN | `arch/gcn` | 0.889 ±0.007 | −0.002 · t = −0,9 · 4 de 8 |
| GCN residual | `arch/gcn` | 0.891 ±0.002 | +0.0003 · t = 0,25 · 4 de 8 |
| Set Transformer | `arch/transformer` | 0.879 ±0.008 | **−0.011 · t = −4,1 · 0 de 8** |
| Set Transformer, 1 SAB (`phi1`) | `arch/transformer` | 0.888 ±0.003 | −0.003 · t = −1,9 · 2 de 8 |
| Clef (zero-shot) | `arch/clef` | 0.721 (sense llavors) | **−0.170 · 0 de 8** |
| Clef + context | `arch/clef` | 0.708 (sense llavors) | **−0.183 · 0 de 8** |
| Clef + context + 8 exemples | `arch/clef` | 0.823 (sense llavors) | **−0.068 · 0 de 8** |

t aparellada amb 7 g.l.; el llindar de p = 0,05 és |t| = 2,36. Clef no té t perquè no varia
entre llavors: fins i tot amb exemples (0.823) queda 6,3 punts per sota de la pitjor llavor de
DeepSets (0.886). Baseline A contra B amb equips no vistos: 0.510.

**Lectura per a la memòria.** Les tres comparteixen tot menys una cosa: **com es relacionen les
granades d'una ronda abans del pooling**. DeepSets no les relaciona, la GCN les relaciona amb
un graf fix d'espai i temps, i el Transformer amb una atenció apresa. Que cap millori vol dir
que **la posició de cada granada ja porta el senyal i fer-les interactuar no hi afegeix res**.
Com més llibertat té la interacció, pitjor generalitza a equips nous.

Clef és la prova contrària: en lloc d'aprendre de les dades sense saber res del joc, sap del joc
però no ha vist les dades. Llegeix alguna cosa de l'utility (21 punts per sobre del baseline),
però no s'acosta a cap model entrenat. Amb el mateix context que els altres models no millora
(0.708). Amb 8 rondes semblants d'altres equips puja a 0.823, però fer votar aquestes 8 rondes,
sense LLM, ja dona 0.805: Clef segueix la votació al 89 % dels plants. **El senyal és a les dades,
no en saber què és un callout.**

---

## 2. Què canvia entre els quatre

| | DeepSets | GCN | Set Transformer | Clef |
|---|---|---|---|---|
| Abans del pooling | cada granada per separat (φ) | cada capa barreja cada granada amb les veïnes | 2 blocs SAB: cada granada mira totes les altres | no hi ha pooling: llegeix la llista de granades com a text |
| Pes entre granades | cap | fix: kernel gaussià, σ 100 px i 6 s | après (4 caps d'atenció) | el del LLM, sense entrenar amb les nostres dades |
| Paràmetres del codificador | ~1.400 | ~1.400 (+1.344 la residual) | **~8.600** | 27.000 milions (Q4_K_M, 20 GB), cap d'entrenat |
| Un entrenament sencer | 673 s | 565 s | **2382 s** (3,5×) | cap · 13,2 s per ronda a la CPU (29 h el dataset); 0,8–1,2 s a l'RTX 5080 |
| Entrenaments de la bateria | 313 | ~488 | 220 | 0 (6675 crides) |

Igual a les tres entrenades: tokens (posició, instant, alçada, tipus), context de mapa, les
tres caps (site, 3 classes, timing), pooling per atenció, calibratge de temperatura i mostreig
del requadre. Clef en comparteix l'utility tallada al plant i les tres preguntes, però rep el nom
del callout en lloc de la posició i no té calibratge. Zero-shot no rep context; amb context rep el
mateix que els altres (fase, equips, compra, valor de l'equip i armes), sense marcador; amb
exemples, a més, 8 rondes etiquetades dels equips d'entrenament del fold.

---

## 3. Equips no vistos, llavor a llavor

Site (A contra B), deixant equips fora, 5 folds per llavor:

| llavor | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | mitjana |
|---|---|---|---|---|---|---|---|---|---|
| **DeepSets** | 0.8862 | 0.8868 | 0.8934 | 0.8895 | 0.8923 | 0.8929 | 0.8907 | 0.8943 | **0.8908 ±0.0030** |
| GCN | 0.8923 | 0.8745 | 0.8862 | 0.8890 | 0.8971 | 0.8934 | 0.8909 | 0.8862 | 0.8887 ±0.0068 |
| GCN residual | 0.8943 | 0.8876 | 0.8890 | 0.8898 | 0.8921 | 0.8918 | 0.8909 | 0.8932 | 0.8911 ±0.0022 |
| Set Transformer | 0.8854 | 0.8653 | 0.8809 | 0.8778 | 0.8695 | 0.8803 | 0.8876 | 0.8879 | 0.8793 ±0.0083 |
| ST `phi1` | 0.8884 | 0.8884 | 0.8881 | 0.8865 | 0.8817 | 0.8929 | 0.8881 | 0.8890 | 0.8879 ±0.0031 |
| Clef | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 |
| Clef + context | 0.7077 | 0.7077 | 0.7077 | 0.7077 | 0.7077 | 0.7077 | 0.7077 | 0.7077 | 0.7077 |
| Clef + 8 exemples | 0.8229 | 0.8229 | 0.8229 | 0.8229 | 0.8229 | 0.8229 | 0.8229 | 0.8229 | 0.8229 |

Totes les variants del Transformer contra DeepSets (§5 de `RESULTATS-TRANSFORMER.md`):

| Variant | Què canvia | − DeepSets | t | guanya |
|---|---|---|---|---|
| per defecte | 2 SAB, 4 caps, 24/32 | −0.0114 | −4,1 | 0 de 8 |
| `gate0` | porta `α` que comença a 0 | −0.0078 | −8,4 | 0 de 8 |
| `wd_1e-3` | weight decay ×10 | −0.0077 | −5,3 | 0 de 8 |
| `phi1` | 1 SAB | −0.0029 | −1,9 | 2 de 8 |
| `narrow` | amplades 12/16 | −0.0227 | −7,7 | 0 de 8 |

Com menys atenció, més s'acosta a DeepSets, que n'és el cas límit. Amb `gate0` la mateixa
xarxa deixa la porta gairebé a 0 (|α| ≤ 0,05 a la cap de gate, ≤ 0,35 a la de site).

---

## 4. Holdout 80/20 (5 particions)

| | DeepSets | GCN | GCN residual | Set Transformer | ST `phi1` | Clef | Clef + context | Baseline |
|---|---|---|---|---|---|---|---|---|
| Site (A/B) | 0.899 ±0.005 | 0.896 ±0.010 | 0.902 ±0.012 | 0.893 ±0.008 | - | 0.721 ±0.007 | 0.710 ±0.008 | 0.533 |
| 3 classes (A/B/NoPlant) | 0.614 ±0.011 | 0.609 ±0.013 | 0.618 ±0.013 | 0.610 ±0.019 | - | **0.435 ±0.010** | 0.476 ±0.013 | 0.450 |
| Timing (rush/default/late) | 0.880 ±0.006 | 0.874 ±0.008 | 0.881 ±0.006 | 0.870 ±0.010 | - | 0.730 ±0.019 | 0.739 ±0.012 | 0.583 |
| ECE (abans → després) | 0.045 → 0.035 | 0.044 → 0.026 | 0.029 → **0.020** | 0.041 → 0.024 | - | **0.224** (sense temperatura) | 0.224 | - |

- = no mesurat. Les variants del Transformer només es van provar amb equips no vistos. Clef amb
exemples no es mesura al holdout: els exemples surten dels equips d'entrenament de cada fold
d'equips no vistos, i al holdout 80/20 podrien ser rondes de test.

Entre les tres entrenades, al holdout tot queda dins de la desviació entre particions. El timing
s'ha de llegir contra la regla "última granada + 9 s" (**0.868**): el Transformer (0.870)
gairebé no hi afegeix res. Les alternatives **calibren millor**, però no mouen cap encert.

Clef queda per sota de tot. Zero-shot, a 3 classes queda fins i tot per sota del baseline: diu
que plantaran al 99,8 % de les rondes, perquè sense context no distingeix un save d'un execute.
Amb context ho diu al 76 % i passa el baseline (0.476), però l'AUC del plant només és 0.60. Al
timing s'avança (zero-shot, prediu 552 rush quan n'hi ha 199), i està molt mal calibrat.

**La diferència és en passar a equips no vistos:**

| | holdout | equips no vistos | caiguda |
|---|---|---|---|
| DeepSets | 0.899 | 0.891 | 0.008 |
| GCN | 0.896 | 0.889 | 0.007 |
| GCN residual | 0.902 | 0.891 | 0.011 |
| **Set Transformer** | 0.893 | 0.879 | **0.014** |
| Clef | 0.721 | 0.721 | **0.000** |
| Clef + context | 0.710 | 0.708 | 0.002 |

El Transformer perd el doble que DeepSets: l'atenció aprèn combinacions de granades pròpies de
cada equip que no es repeteixen en un altre. Clef no perd res, perquè no aprèn res de cap
equip. Que DeepSets només en perdi 0,8 punts vol dir que el que aprèn es transfereix a equips
nous.

---

## 5. Per mapa

Equips no vistos, mitjana de les 8 llavors:

| Mapa | plants | DeepSets | GCN | GCN residual | Set Transformer | ST `phi1` | Clef | Clef + 8 ex. | Baseline |
|---|---|---|---|---|---|---|---|---|---|
| de_dust2 | 879 | 0.923 | 0.918 | 0.924 | 0.925 | 0.924 | 0.833 | 0.890 | 0.534 |
| de_mirage | 531 | 0.919 | 0.918 | 0.919 | 0.913 | - | **0.638** | 0.825 | 0.629 |
| de_nuke | 435 | **0.782** | 0.787 | 0.786 | 0.772 | 0.783 | **0.589** | **0.676** | 0.497 |
| de_ancient | 418 | 0.896 | 0.894 | 0.890 | 0.888 | - | 0.667 | 0.813 | 0.471 |
| de_anubis | 366 | 0.890 | 0.888 | 0.893 | **0.861** | 0.875 | 0.650 | 0.787 | 0.454 |
| de_inferno | 340 | 0.913 | 0.912 | 0.915 | 0.906 | - | 0.762 | 0.838 | 0.438 |
| de_train | 262 | **0.828** | 0.824 | 0.830 | 0.806 | 0.838 | 0.691 | 0.802 | 0.458 |
| de_cache | 192 | 0.917 | 0.922 | 0.920 | 0.914 | - | 0.833 | 0.885 | 0.542 |
| de_overpass | 162 | 0.927 | 0.910 | 0.912 | **0.845** | 0.915 | 0.877 | 0.883 | 0.444 |

- = no recollit. A `RESULTATS-TRANSFORMER.md` només consten els mapes on el Transformer per
defecte perdia més; als altres, `phi1` queda a ±1 punt de DeepSets.

- **Nuke i train són fluixos amb totes tres.** La GCN era la candidata a arreglar-los si
  calia llegir la composició de l'execute, i no ho fa: el problema d'aquests mapes no és aquest.
  Clef també té el pitjor encert a nuke (0.589).
- **El Transformer perd sobretot als mapes amb pocs plants** (overpass −8,2 punts, anubis
  −2,9, train −2,2) i empata al que en té més (dust2). `phi1` en recupera gran part (overpass
  0.915, train 0.838), però anubis segueix 1,5 punts per sota.
- **Clef fa el contrari: on menys perd és als mapes amb pocs plants** (overpass −5,0, cache
  −8,4), perquè no depèn de quantes rondes hi hagi per aprendre. **A mirage gairebé no supera
  el baseline** (0.638 contra 0.629): cada equip hi va molt a un site, i això Clef no ho pot
  saber. Amb 8 exemples hi puja a 0.825, el salt més gran, però hi fa pitjor que la simple
  votació dels mateixos exemples (0.841).

---

## 6. Què se'n treu

1. **La posició de cada granada és el senyal.** A les ablacions n'explica el 86 % del guany
   amb DeepSets i el 84 % amb la GCN. Relacionar-les no hi afegeix res.
2. **Un graf dolent fa mal, un de bo no ajuda.** La GCN amb totes les granades connectades
   cau a 0.814 (−7,8 punts); ben definida (espai **i** temps) només iguala.
3. **La inestabilitat de la GCN tenia causa**: cada capa promitjava la posició pròpia amb la
   de les veïnes. Amb una connexió residual que la conserva, la desviació baixa de ±0.007 a
   ±0.002 i l'encert no es mou.
4. **L'atenció apresa sobreajusta a cada equip.** Frenar-la la millora, però el límit
   d'aquesta millora és DeepSets.
5. **Saber del joc no substitueix les dades.** Clef, un LLM de 27.000 milions de paràmetres,
   llegeix el site per sobre de l'atzar (AUC 0.81) però queda 17 punts per sota d'un model de
   ~1.400 entrenat amb 3585 plants. El mateix context que els altres models no l'ajuda (0.708).
   Amb 8 rondes semblants puja a 0.823, però la votació d'aquestes rondes, sense LLM, ja fa
   0.805: el que hi guanya ve de les dades. No se sap quant de la resta de pèrdua ve de rebre
   el callout en lloc de la posició: caldria entrenar DeepSets amb callouts per separar-ho.
6. **Es queda DeepSets** a `main`: mateix encert que la millor alternativa, el menor nombre de
   paràmetres, el més estable (o empatat amb la GCN residual) i 3,5 vegades més ràpid que el
   Transformer. L'únic avantatge de les alternatives, el calibratge, no canvia cap predicció.

---

## 7. On és cada cosa

| Model | Branca | Codi | Resultats | JSON crus |
|---|---|---|---|---|
| DeepSets | `main` | `app/ml/deepsets.py` | `RESULTATS.md` | `data_store/sweep_deepsets_2026-09-21/` |
| GCN (+ residual) | `arch/gcn` | `app/ml/gcn.py` | `RESULTATS-GCN.md` | `data_store/sweep/` |
| Set Transformer | `arch/transformer` | `app/ml/transformer.py` | `RESULTATS-TRANSFORMER.md` | `data_store/sweep_tf/` |
| Clef | `arch/clef` | `app/ml/clef.py` | `RESULTATS-CLEF.md` | `data_store/sweep_clef/`, `sweep_clef_ctx/`, `sweep_clef_ctx_k8/` |
