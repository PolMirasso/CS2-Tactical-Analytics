# Resultats empírics: Clef contra DeepSets

> Clef és el model de decisió de Cloudflare (27B, servit amb Ollama), la proposta de Jordi.
> Respon preguntes tancades amb una probabilitat per opció. **No s'entrena**: rep cada ronda com a
> text i hi contesta. **Tres tandes de 6675 rondes, totes preguntades**:
>
> | Tanda | Què rep | On | Temps |
> |---|---|---|---|
> | zero-shot (§1–§5) | només l'utility, amb callouts | CPU del portàtil, 2026-10-24 → 26 | 29 h |
> | + context (§6) | + el mateix context que els altres models | RTX 5080, 2026-10-28 | 2 h 13 min |
> | + context + 8 exemples (§6) | + 8 rondes etiquetades d'altres equips | RTX 5080, 2026-10-28 | 2 h 50 min |
>
> S'avaluen amb **les mateixes particions** que DeepSets, la GCN i el Set Transformer.
> Comprovat: els baselines surten idèntics (A/B 0.533, 3 classes 0.450, timing 0.583 al holdout;
> A/B 0.510 amb equips no vistos), o sigui que les rondes de test són les mateixes.
>
> Els JSON crus són a `data_store/sweep_clef/`, `sweep_clef_ctx/` i `sweep_clef_ctx_k8/`
> (`answers.jsonl` amb la resposta de cada ronda, `lto.json`, `holdout.json`); els de DeepSets, a
> `data_store/sweep_deepsets_2026-09-21/`.


---

## 0. Les tres tandes, de cop

Equips no vistos (5 folds, 3585 plants), llevat d'on diu holdout:

| | zero-shot | + context | + context + 8 exemples | DeepSets |
|---|---|---|---|---|
| A contra B, **equips no vistos** | 0.721 | 0.708 | **0.823** | **0.891 ±0.003** |
| A contra B, holdout | 0.721 ±0.007 | 0.710 ±0.008 | no es mesura (§6) | 0.899 ±0.005 |
| 3 classes, equips no vistos | 0.441 | 0.477 | 0.551 | 0.600 ±0.005 |
| 3 classes, holdout | 0.435 ±0.010 | 0.476 ±0.013 | no es mesura | 0.614 ±0.011 |
| Timing, totes les rondes amb plant | 0.731 | 0.737 | 0.772 | 0.880 ±0.006 (holdout) |
| AUC del site | 0.808 | 0.796 | 0.885 | |
| AUC del plant | 0.584 | 0.604 | 0.649 | |
| Rondes on diu «plant» | 99,8 % | 76 % | 77 % | (n'hi ha el 53,7 %) |
| ECE, totes les rondes | 0.229 | 0.222 | 0.215 | 0.045 → 0.035 (holdout) |
| Temps per ronda (mediana) | 13,2 s (CPU) | 0,79 s (GPU) | 1,20 s (GPU) | |

Baselines: A/B 0.510, 3 classes 0.463 (equips no vistos); timing, regla «última granada + 9 s» 0.868.

**Control sense LLM:** fer votar els mateixos 8 exemples (el site que més es repeteix) dona
**0.805** al site i 0.641 d'AUC al plant. Clef hi afegeix 1,8 i 0,8 punts (§6).

**Lectura per a la memòria.** Amb la mateixa informació que els altres models, Clef no millora
el site (0.708). Amb exemples puja 10 punts, però gairebé tot ho fa la tria dels exemples: Clef
copia la votació en el 89 % dels plants. Ni així arriba a DeepSets (−6,8 punts). **El senyal és a
les dades**, i quan l'LLM les rep, el que fa és sobretot reproduir-les.

---

## 1. La resposta curta (zero-shot)

**Clef perd de molt contra DeepSets.** Sap llegir alguna cosa de l'utility (21 punts per
sobre del baseline a site), però queda **17 punts per sota** d'un model de ~1.400 paràmetres
entrenat amb les nostres dades.

| | Clef | DeepSets | Diferència |
|---|---|---|---|
| A contra B, **equips no vistos** | 0.721 | 0.891 ±0.003 | **−0.170 · perd a les 8 llavors** |
| A contra B, holdout (5 particions) | 0.721 ±0.007 | 0.899 ±0.005 | −0.178 |
| 3 classes, equips no vistos | 0.441 | 0.600 ±0.005 | −0.159 · **per sota del baseline (0.463)** |
| 3 classes, holdout | 0.435 ±0.010 | 0.614 ±0.011 | −0.179 · per sota del baseline (0.450) |
| Timing, holdout | 0.730 ±0.019 | 0.880 ±0.006 | −0.150 · per sota de la regla (0.868) |
| ECE | 0.224 (sense temperatura) | 0.045 → 0.035 | molt mal calibrat |
| Cost | 13,2 s per ronda, sense entrenar | 673 s un entrenament sencer | |

Clef dona **una sola xifra** amb equips no vistos: no s'entrena, així que no té llavors. La
comparació aparellada no té sentit; n'hi ha prou amb veure que la xifra queda 16 punts per sota
de la pitjor llavor de DeepSets (0.886).

Tres coses que diu la bateria:

- **El site sí que el llegeix**: AUC 0.81, i quan està molt segur (≥ 0.9, el 56 % de les
  rondes) encerta el 84 %. Però el 44 % restant és gairebé a l'atzar (§3).
- **No sap si plantaran**: diu que sí al 99,8 % de les rondes (AUC 0.58). Per això les 3 classes
  queden per sota del baseline, que almenys sap quins equips i mapes acaben més sovint en no-plant.
- **No perd res amb equips nous** (0.721 al holdout i amb equips no vistos), perquè no aprèn res
  d'ells. És l'altre extrem del Set Transformer.

**Lectura per a la memòria.** Clef és la prova contrària a les tres arquitectures anteriors:
en lloc d'aprendre de les dades sense saber res del joc, sap del joc però no ha vist les dades.
El coneixement general de CS2 que porta un LLM de 27B no substitueix 3585 plants amb la posició
de cada granada. **El senyal és a les dades, no en saber què és un callout.**

---

## 2. El model

**clef:latest** (27B, Q4_K_M, 20 GB) a Ollama 0.40.10, amb `num_ctx 2048` (§6). Una crida a
`/v1/systemone` per ronda, amb l'estat i tres preguntes. Clef respon amb probabilitats per opció
sense generar text (0 tokens de sortida; ~614 d'entrada de mediana, 484–712 entre el p10 i el
p90).

**Què rep** (`app/ml/clef.py`, `clef_state`): l'utility T fins al plant, igual que DeepSets,
però cada granada amb el **nom del callout** on cau (les zones de `/maps/edit`) en lloc de la
posició, i el segon de la ronda. Res més: ni economia, ni equip, ni marcador. Una ronda real:

```json
{"game": "Counter-Strike 2", "map": "Mirage", "side": "T (attackers)",
 "utility_thrown_by_T_so_far": [
  {"type": "smoke", "callout": "Mid", "time_s": 0},
  {"type": "smoke", "callout": "Sniper's Nest", "time_s": 0},
  {"type": "flash", "callout": "Mid", "time_s": 6},
  {"type": "flash", "callout": "Stairs", "time_s": 15},
  {"type": "smoke", "callout": "Stairs", "time_s": 40}]}
```

Totes les 70.204 granades van caure en una zona amb nom: cap no va sense callout.

**Les preguntes** (de tipus *choice*):

| Pregunta | Opcions |
|---|---|
| `site` · a quin site executen? | A · B |
| `plant` · plantaran la bomba? | plant · no_plant (save, eco o un execute que falla) |
| `timing` · si planten, quan? | rush (< 35 s) · default (35–70 s) · late (> 70 s) |

Les 3 classes es componen igual que a DeepSets: P(A) = P(plant)·P(A|plant),
P(B) = P(plant)·P(B|plant), P(NoPlant) = 1 − P(plant). Sense calibratge de temperatura: no hi
ha train per ajustar-la.

### Holdout 80/20

El 20 % de test de cada partició són exactament les mateixes rondes que les de DeepSets. Com
que Clef no s'entrena, la variació entre particions només ve de quines rondes cauen a test.

| Partició | site Clef | site DS | 3 classes Clef | 3 classes DS | timing Clef | timing DS | ECE Clef | ECE DS |
|---|---|---|---|---|---|---|---|---|
| seed 0 | 0.728 | 0.907 | 0.434 | 0.631 | 0.750 | 0.881 | 0.215 | 0.039 → 0.033 |
| seed 1 | 0.711 | 0.897 | 0.425 | 0.600 | 0.753 | 0.877 | 0.236 | 0.033 → 0.026 |
| seed 2 | 0.730 | 0.894 | 0.451 | 0.610 | 0.720 | 0.870 | 0.214 | 0.032 → 0.028 |
| seed 3 | 0.716 | 0.897 | 0.425 | 0.621 | 0.703 | 0.884 | 0.238 | 0.069 → 0.053 |
| seed 4 | 0.720 | 0.899 | 0.441 | 0.605 | 0.725 | 0.887 | 0.216 | 0.053 → 0.037 |
| **mitjana** | **0.721 ±0.007** | 0.899 ±0.005 | **0.435 ±0.010** | 0.614 ±0.011 | **0.730 ±0.019** | 0.880 ±0.006 | **0.224** | 0.045 → 0.035 |

Baselines: A contra B 0.533, 3 classes 0.450, timing 0.583.

### Deixant equips fora

Els mateixos 5 folds que DeepSets (llavor 0). A Clef el train només serveix per als baselines:

| Fold | equips fora | rondes per entrenar | plants de test | site Clef | site DS | baseline A/B |
|---|---|---|---|---|---|---|
| 1 | 8 | 4264 | 750 | 0.741 | 0.899 | 0.492 |
| 2 | 8 | 4173 | 755 | 0.738 | 0.894 | 0.530 |
| 3 | 11 | 4216 | 712 | 0.695 | 0.865 | 0.492 |
| 4 | 14 | 4172 | 701 | 0.696 | 0.882 | 0.515 |
| 5 | 14 | 4086 | 667 | 0.735 | 0.891 | 0.520 |
| **Conjunt** | 55 | — | 3585 | **0.721** | 0.886 | 0.510 |

**El fold 3 és el més difícil per a tots dos** (Clef 0.695, DeepSets 0.865): aquests equips són
menys llegibles per les granades en general, no només per a un model entrenat.

Per llavors, DeepSets contra la xifra única de Clef:

| llavor | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | mitjana |
|---|---|---|---|---|---|---|---|---|---|
| DeepSets | 0.8862 | 0.8868 | 0.8934 | 0.8895 | 0.8923 | 0.8929 | 0.8907 | 0.8943 | 0.8908 ±0.0030 |
| **Clef** | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 | 0.7213 | **0.7213** |

---

## 3. Què encerta i què no

Totes les 6675 rondes (3585 plants).

### Site: el llegeix, però està massa segur

AUC 0.808. Per confiança (la probabilitat del site triat):

| Confiança | rondes | encert | confiança mitjana |
|---|---|---|---|
| 0.5–0.6 | 686 | 0.520 | 0.543 |
| 0.6–0.7 | 280 | 0.593 | 0.643 |
| 0.7–0.8 | 233 | 0.567 | 0.752 |
| 0.8–0.9 | 394 | 0.675 | 0.859 |
| **0.9–1.0** | **1992** | **0.836** | 0.965 |

ECE només del site: 0.113. **A totes les franges diu més del que encerta**, i a la franja
0.7–0.8 encerta menys que a la 0.6–0.7. Quan està molt segur (més de la meitat de les rondes)
és útil; la resta és gairebé l'atzar. També **té biaix cap a A**: el tria al 56,6 % dels plants,
quan només el 51,0 % són a A.

**Amb més granades encerta més**:

| granades T | 0 | 1–2 | 3–5 | 6–9 | 10–14 | 15 o més |
|---|---|---|---|---|---|---|
| plants | 20 | 97 | 380 | 561 | 1420 | 1107 |
| site Clef | 0.500 | 0.660 | 0.682 | 0.658 | 0.714 | **0.786** |

Amb un execute complet (15 granades o més) arriba a 0.79. Amb poca utility no endevina.

### Plant: no ho sap

| | |
|---|---|
| Rondes on diu «plant» | **99,8 %** (n'hi ha el 53,7 %) |
| P(plant) mitjana, rondes amb plant | 0.790 |
| P(plant) mitjana, rondes sense plant | 0.757 |
| AUC | 0.584 |

Les dues mitjanes gairebé no se separen. Sense economia ni marcador, una ronda que acaba en save
no es distingeix d'una que planta. Per això, de les 3090 rondes sense plant, només en marca 656
com a NoPlant, i les 3 classes (0.441) queden per sota del baseline (0.463). A DeepSets, el cap
de gate llegeix sobretot el context.

### Timing: va massa d'hora

Rondes amb plant (files: real; columnes: predicció de Clef):

| | rush | default | late |
|---|---|---|---|
| **rush** (199) | **168** | 31 | 0 |
| **default** (1250) | 254 | **995** | 1 |
| **late** (2136) | 130 | 547 | **1459** |

Mai no s'equivoca cap a més tard, només cap a més d'hora: prediu 552 rush quan n'hi ha 199. No
sap quant triguen els equips professionals a executar després de l'última granada, que és
justament el que llegeix la regla «última granada + 9 s» (0.868). Encert 0.731, per sobre de la
moda (0.583) però lluny de la regla.

---

## 4. Precisió per mapa

Deixant equips fora; DeepSets és la mitjana de les 8 llavors:

| Mapa | plants | site Clef | site DS | Clef − DS | baseline A/B |
|---|---|---|---|---|---|
| de_dust2 | 879 | 0.833 | 0.923 | −9,0 | 0.534 |
| de_mirage | 531 | **0.638** | 0.919 | **−28,1** | 0.629 |
| de_nuke | 435 | **0.589** | 0.782 | −19,3 | 0.497 |
| de_ancient | 418 | 0.667 | 0.896 | −22,9 | 0.471 |
| de_anubis | 366 | 0.650 | 0.890 | −24,0 | 0.454 |
| de_inferno | 340 | 0.762 | 0.913 | −15,1 | 0.438 |
| de_train | 262 | 0.691 | 0.828 | −13,7 | 0.458 |
| de_cache | 192 | 0.833 | 0.917 | −8,4 | 0.542 |
| de_overpass | 162 | **0.877** | 0.927 | −5,0 | 0.444 |

- **A Mirage gairebé no supera el baseline** (0.638 contra 0.629). Al mapa més conegut del joc.
  Mirage té el baseline més alt: cada equip va molt a un site, i això Clef no ho pot saber. A més,
  part de l'utility d'un execute a A o a B passa pels mateixos callouts del mig.
- **Nuke continua sent el pitjor en absolut** (0.589), com a totes les arquitectures. Els dos
  sites són un a sobre de l'altre i el callout no diu l'alçada.
- **On menys perd és als mapes amb menys plants** (overpass −5,0, cache −8,4). És el contrari
  del Set Transformer: a DeepSets li costa més aprendre on té poques dades, mentre que Clef hi
  arriba igual de preparat que a qualsevol altre mapa.

---

## 5. Per què perd

**No ha vist les dades.** DeepSets aprèn de 3585 plants com executa cada mapa *aquest* pool
d'equips. Clef només en sap el que va aprendre en general del joc. On més es veu és a Mirage i
al plant.

**Rep menys informació.** Un callout cobreix una àrea gran, mentre que DeepSets rep la posició
exacta en píxels i l'alçada. Que la posició sigui el senyal ja ho deien les ablacions (86 % del
guany). Aquesta bateria **no separa** les dues causes: no es pot dir quanta pèrdua ve de passar
de posició a callout i quanta d'ésser zero-shot. Per separar-les caldria entrenar DeepSets amb
el callout en lloc de la posició.

**No té context.** Sense economia ni equips, la pregunta de plant és inútil (AUC 0.58). A
DeepSets el context és el que decideix el gate. Amb el context (§6) deixa de dir sempre que
plantaran, però l'AUC només puja a 0.60.

**No sobreajusta, però és perquè no s'ajusta.** La caiguda de holdout a equips no vistos:

| | holdout | equips no vistos | caiguda |
|---|---|---|---|
| DeepSets | 0.899 | 0.891 | 0.008 |
| GCN residual | 0.902 | 0.891 | 0.011 |
| Set Transformer | 0.893 | 0.879 | 0.014 |
| **Clef** | 0.721 | 0.721 | **0.000** |

Que DeepSets en perdi només 0,8 punts vol dir que **el que aprèn de les dades es transfereix
a equips nous**: no és memoritzar equips. Clef és el sostre d'un model sense dades, i DeepSets
el supera en 17 punts.

**Està molt mal calibrat** (ECE 0.224, DeepSets 0.035): les probabilitats que dona no es poden
fer servir com a tals a `/scouting` sense recalibrar-les.

### Veredicte

**Tercer resultat negatiu, tancat.** Es queda DeepSets. Un LLM amb coneixement del joc llegeix
la utility millor que l'atzar, però no s'acosta a un model petit entrenat amb les dades, i ho fa
sent molt més car: 13 s per ronda a la CPU (29 h per a tot el dataset), contra mil·lisegons.
Les dues tandes del §6 no ho canvien.

---

## 6. Amb context i amb exemples

Dues tandes més, per veure si la distància venia de **no tenir context** o de **no haver vist
les dades**. Es fan a l'RTX 5080 del PC de casa (16 GB; hi cap el 65 % del model, 12,9 de 19,8 GB),
amb `num_ctx 4096`. L'utility és la mateixa que a la tanda zero-shot.

### Què hi afegeix cada tanda

**+ context**: el mateix context que reben DeepSets, la GCN i el Set Transformer
(`round_context`): fase, equips, compra, valor de l'equip i armes de cada bàndol. **Ni marcador
ni número de ronda**, que els altres models no veuen. Una ronda real:

```json
"this_round": {"phase": "first half",
 "T":  {"team": "Natus Vincere", "buy": "full eco (saving)", "equipment_value": 2000,
        "weapons": "glock, deagle"},
 "CT": {"team": "Team Vitality", "buy": "full buy", "equipment_value": 22350,
        "weapons": "usp_s, p2000, dualies, famas, m4a4, m4a1_s"}}
```

**+ 8 exemples**: abans de la ronda, 8 rondes del mateix mapa amb com van acabar, en forma
compacta:

```json
{"utility": ["smoke Sniper's Nest 0s", "smoke Mid 0s", "flash Mid 8s", "smoke Stairs 59s",
             "molotov Stairs 62s", "flash Stairs 71s", "molotov B Short 77s"],
 "outcome": "planted A at 80 s", "buys": "T full buy, CT full buy"}
```

- **Sense fuites.** Surten dels equips d'entrenament del fold d'equips no vistos de la ronda
  (sense els equips del test ni les seves rondes com a rival). Per això aquesta tanda **només
  es puntua amb equips no vistos**: al holdout 80/20 els exemples podrien venir de rondes de test.
- **Els més semblants.** Els 8 amb més granades en comú (tipus + callout, Jaccard), amb el més
  semblant al final. Els empats es desfan per índex: és determinista.
- Mida: 1714 tokens d'entrada de mediana (1135–2024 entre el p10 i el p90, màxim 2340), contra
  742 de la tanda amb context.

### Resultats per fold

| Fold | plants | zero-shot | + context | + 8 exemples | DeepSets |
|---|---|---|---|---|---|
| 1 | 750 | 0.741 | 0.723 | 0.839 | 0.899 |
| 2 | 755 | 0.738 | 0.721 | 0.842 | 0.894 |
| 3 | 712 | 0.695 | 0.681 | 0.803 | 0.865 |
| 4 | 701 | 0.696 | 0.690 | 0.803 | 0.882 |
| 5 | 667 | 0.735 | 0.723 | 0.825 | 0.891 |
| **Conjunt** | 3585 | **0.721** | **0.708** | **0.823** | 0.886 (llavor 0) |

Amb exemples guanya als 5 folds (+10 punts de mitjana), però queda per sota de DeepSets a tots.

### El context: arregla el plant, no el site

| | zero-shot | + context |
|---|---|---|
| Diu «plant» | 99,8 % | 76 % |
| P(plant) mitjana, rondes amb plant | 0.790 | 0.705 |
| P(plant) mitjana, rondes sense plant | 0.757 | 0.587 |
| AUC del plant | 0.584 | 0.604 |
| 3 classes, equips no vistos | 0.441 · per sota del baseline | **0.477 · per sobre (0.463)** |
| Site, equips no vistos | 0.721 | 0.708 |

Ara separa una mica les rondes sense plant i les 3 classes passen el baseline. Però l'AUC de 0.60 és molt lluny del que treu DeepSets del mateix context. Al site
no hi aporta res: hi perd 1,3 punts, dins del que varia d'un fold a un altre.

### Els exemples: el guany és de la tria, no de Clef

Mateixos 8 exemples, tres maneres de decidir el site:

| | site, equips no vistos |
|---|---|
| L'exemple més semblant | 0.755 |
| **Votació dels 8** (empats, 230 de 3585, compten com a mig encert) | **0.805** |
| Clef amb els 8 | 0.823 |
| DeepSets | 0.891 |

- **Clef tria el site de la votació al 89,4 % dels plants** (2999 de 3355 sense empat). Quan
  se n'aparta (356), encerta el 54,2 %: poc més que tirar una moneda.
- Al plant passa el mateix: la proporció dels 8 que van plantar ja dona 0.641 d'AUC; Clef, 0.649.
- La confiança millora: està segur (≥ 0.9) al 70 % dels plants i hi encerta el 88 %.
- El timing puja de 0.737 a 0.772, segurament perquè els exemples porten el segon del plant. Continua lluny
  de la regla (0.868).

Per mapa:

| Mapa | plants | zero-shot | + context | votació dels 8 | + 8 exemples | DeepSets |
|---|---|---|---|---|---|---|
| de_dust2 | 879 | 0.833 | 0.809 | 0.871 | 0.890 | 0.923 |
| de_mirage | 531 | 0.638 | 0.665 | **0.841** | **0.825** | 0.919 |
| de_nuke | 435 | 0.589 | 0.593 | 0.633 | 0.676 | 0.782 |
| de_ancient | 418 | 0.667 | 0.675 | 0.785 | 0.813 | 0.896 |
| de_anubis | 366 | 0.650 | 0.582 | 0.776 | 0.787 | 0.890 |
| de_inferno | 340 | 0.762 | 0.721 | 0.825 | 0.838 | 0.913 |
| de_train | 262 | 0.691 | 0.676 | 0.769 | 0.802 | 0.828 |
| de_cache | 192 | 0.833 | 0.839 | 0.872 | 0.885 | 0.917 |
| de_overpass | 162 | 0.877 | 0.846 | 0.849 | 0.883 | 0.927 |

- **Mirage passa de 0.638 a 0.825**, el salt més gran: el que li faltava era veure com hi
  executen aquests equips. Però és l'únic mapa on **Clef fa pitjor que la votació** (−1,6).
- **Nuke continua sent el pitjor** (0.676), ara també per a la votació (0.633): el callout no
  diu l'alçada, i les rondes semblants per callout poden anar a un site o a l'altre.
- **A train s'acosta a DeepSets** (−2,6), que també hi és fluix.

### Veredicte

**No canvia res: es queda DeepSets.** El context sol no ajuda al site. Els exemples sí, però el
que encerta és la tria de rondes semblants, que és un k-NN sobre callouts. Clef hi afegeix 1,8
punts i encara queda 6,8 punts per sota de DeepSets, que ho fa sense LLM i amb la posició
exacta. Per anar més enllà, amb 16 exemples, caldria `num_ctx 8192` i unes 3 h, i el que
milloraria més probablement seria la votació, no Clef.

---

## 7. Com reproduir-ho

### Tanda zero-shot (portàtil)

A la branca `arch/clef`, des de `backend/`, amb la base de dades del Docker en marxa. El Clef de
la biblioteca d'Ollama porta `num_ctx 16384` al Modelfile, i a la RTX 3050 de 4 GB el buffer de
càlcul (5,3 GB) no hi cap (`cudaMalloc` OOM). Ni les opcions de la petició ni
`OLLAMA_CONTEXT_LENGTH` el sobreescriuen, i per això cal una variant amb 2048 (l'estat més llarg
en té 817). Va a la CPU (0 de 65 capes a la GPU), amb un Ollama propi al port 11435
i una còpia reflink del magatzem a `~/.ollama-clef`, sense tocar el servei del sistema:

```bash
OLLAMA_MODELS=~/.ollama-clef OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NUM_PARALLEL=1 \
  OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=-1 ollama serve
printf 'FROM clef\nPARAMETER num_ctx 2048\n' > Modelfile
OLLAMA_HOST=127.0.0.1:11435 ollama create clef-2k -f Modelfile

PYTHONPATH=. systemd-inhibit --what=idle:sleep python -u scripts/clef_eval.py --stage ask
PYTHONPATH=. python scripts/clef_eval.py --stage score
```

| Etapa | Què fa | Temps |
|---|---|---|
| `ask` | una crida per ronda; afegeix a `answers.jsonl` | 6675 crides · 13,2 s de mediana · 29 h |
| `score` | holdout de 5 particions i 5 folds d'equips fora | ~2 min |

`ask` es pot reprendre: salta les rondes que ja té, i si el dataset ha canviat s'atura (cada
fila porta un hash de l'estat). Pregunta en un ordre aleatori fix, de manera que una tirada a
mitges és una mostra a l'atzar: a 3735 rondes el site ja era 0.724.

Dues coses van alentir la tirada:
- **El perfil d'energia.** Amb `power-saver` la CPU queda a 1,4 GHz i passa a 21 s per ronda.
  Amb `balanced`, ~16 s.
- **La memòria.** El model (20 GB) no cap a la RAM (15 GB) i es llegeix del disc a mesura que
  calen les capes. Amb el navegador obert, va passar a 150–270 s per ronda. Tancar-lo no n'hi
  va haver prou: va caldre reiniciar el `llama-server` d'Ollama, que torna a 13 s.

### Tandes amb context i exemples (un altre PC)

La base de dades no té `ORDER BY`: retorna les rondes en l'ordre físic, i restaurada en un altre
PC en surt un altre, que canviaria les particions. Per això els prompts es construeixen al
portàtil, **l'altre PC només pregunta**, i es puntua al portàtil:

```bash
# portàtil: construir els prompts (amb els índexs d'aquí)
PYTHONPATH=. python scripts/clef_eval.py --stage export --context
PYTHONPATH=. python scripts/clef_eval.py --stage export --context --shots 8
```

A l'altre PC (Windows) només cal Ollama amb `clef`. `scripts/clef.ps1` llegeix
`prompts.jsonl` i `questions.json` de cada variant, crea `clef-4k` si no hi és, pregunta per
l'API d'Ollama i escriu `answers.jsonl` i `clef-log.txt` al costat. Es pot reprendre i s'atura si
una resposta guardada no correspon al seu prompt (hash). Mentre corre, el PC no se suspèn.

```powershell
powershell -ExecutionPolicy Bypass -File clef.ps1            # -Limit 5 per provar
```

```bash
# portàtil: puntuar
PYTHONPATH=. python scripts/clef_eval.py --stage score --context
PYTHONPATH=. python scripts/clef_eval.py --stage score --context --shots 8
```

El mateix es pot fer sense PowerShell amb `clef_eval.py --offline` (pregunta a partir de
l'exportació, sense base de dades). Amb `--shots`, `score` només fa equips no vistos.
