# Resultats empírics: GCN contra DeepSets

> GCN substitueix DeepSets (el model es descriu a [`GCN.md`](GCN.md)). **488 entrenaments en 10,7 h** amb 12
> workers Comprovat: la llavor 0 del holdout dona **exactament** el mateix que una prova
> aïllada feta el dia abans, o sigui que la partició 80/20 és la mateixa que la de DeepSets.
>
> Els JSON crus són a `data_store/sweep/`; els de DeepSets, a
> `data_store/sweep_deepsets_2026-09-21/`.

## Índex

1. [La resposta curta](#1-la-resposta-curta)
2. [El model per defecte](#2-el-model-per-defecte)
3. [El graf: qui és veí de qui](#3-el-graf-qui-és-veí-de-qui)
4. [Configuracions de xarxa](#4-configuracions-de-xarxa)
5. [Ablacions](#5-ablacions)
6. [Precisió per mapa](#6-precisió-per-mapa)
7. [Corba d'aprenentatge](#7-corba-daprenentatge)
8. [Les rondes que no van plantar](#8-les-rondes-que-no-van-plantar)
9. [Què no s'ha refet](#9-què-no-sha-refet)
10. [Com reproduir-ho](#10-com-reproduir-ho)

---

## 1. La resposta curta

**La GCN empata amb DeepSets. No la millora.**

| | GCN | DeepSets | Diferència |
|---|---|---|---|
| A contra B, **equips no vistos** (8 llavors) | 0.889 ±0.007 | 0.891 ±0.003 | −0.002 · t = −0,9 · 4 de 8 |
| A contra B, holdout (5 particions) | 0.896 ±0.010 | 0.899 ±0.005 | −0.003 |
| 3 classes, holdout | 0.609 ±0.013 | 0.614 ±0.011 | −0.005 |
| Timing, holdout | 0.874 ±0.008 | 0.880 ±0.006 | −0.006 |
| ECE (abans → després) | 0.044 → **0.026** | 0.045 → 0.035 | millor calibrada |
| Un entrenament sencer | 565 s | 673 s | similar |

La comparació d'equips no vistos és **aparellada**: cada llavor entrena tots dos models amb
els mateixos folds. De les 8 llavors, la GCN en guanya 4 i en perd 4, i la diferència mitjana
(−0.002) és menor que la seva desviació (0.0065). És soroll.

Tres coses que sí que diu la bateria:

- **El graf importa, però en negatiu**: amb un graf mal definit la GCN perd fins a 7 punts
  (§3). Ben definit (espai **i** temps) només iguala.
- **La GCN és el doble de variable entre llavors** (±0.007 contra ±0.003 amb equips no vistos,
  ±0.010 contra ±0.005 al holdout). No ho compensa amb res.
- **Calibra millor**: l'ECE després de la temperatura baixa a 0.026 (DeepSets 0.035). És
  l'únic punt on guanya, i no mou cap encert.

**Lectura per a la memòria.** La GCN afegeix exactament el que DeepSets no té: que cada
granada es llegeixi amb les que cauen al costat i a la vegada. Que no millori vol dir que
**aquesta relació no porta senyal que la posició de cada granada no porti ja**. Encaixa amb
les ablacions (§5): la posició de cada granada explica el 84–86 % del que el model treu per
sobre del baseline, amb una arquitectura o amb l'altra.

---

## 2. El model per defecte

**gcn[space_time] 18→32→24 · atenció · ρ 32→2 · ReLU**, σ espacial 0,1 (≈ 100 px del radar),
σ temporal 6 s, α = 1e-4, lr = 5e-3. Tota la resta, igual que a `RESULTATS.md` §3.

### Holdout 80/20

| Partició | site GCN | site DS | 3 classes GCN | 3 classes DS | timing GCN | timing DS | ECE GCN | ECE DS |
|---|---|---|---|---|---|---|---|---|
| seed 0 | 0.912 | 0.907 | 0.632 | 0.631 | 0.874 | 0.881 | 0.050 → 0.038 | 0.039 → 0.033 |
| seed 1 | 0.886 | 0.897 | 0.596 | 0.600 | 0.860 | 0.877 | 0.038 → 0.022 | 0.033 → 0.026 |
| seed 2 | 0.889 | 0.894 | 0.599 | 0.610 | 0.880 | 0.870 | 0.041 → 0.020 | 0.032 → 0.028 |
| seed 3 | 0.904 | 0.897 | 0.603 | 0.621 | 0.875 | 0.884 | 0.047 → 0.016 | 0.069 → 0.053 |
| seed 4 | 0.892 | 0.899 | 0.613 | 0.605 | 0.881 | 0.887 | 0.042 → 0.037 | 0.053 → 0.037 |
| **mitjana** | **0.896 ±0.010** | 0.899 ±0.005 | **0.609 ±0.013** | 0.614 ±0.011 | **0.874 ±0.008** | 0.880 ±0.006 | **0.044 → 0.026** | 0.045 → 0.035 |

Baselines: A contra B 0.533, 3 classes 0.450, timing 0.583.

**El timing** perd mig punt, i contra la regla "última granada + 9 s" (0.868 a les mateixes
particions, `RESULTATS.md` §8) el cap ara hi afegeix **0,6 punts** en lloc d'1,2.

### Deixant equips fora

| Fold | equips fora | rondes per entrenar | plants de test | site GCN | site DS |
|---|---|---|---|---|---|
| 1 | 8 | 4264 | 750 | 0.907 | 0.899 |
| 2 | 8 | 4173 | 755 | 0.898 | 0.894 |
| 3 | 11 | 4216 | 712 | 0.888 | 0.865 |
| 4 | 14 | 4172 | 701 | 0.876 | 0.882 |
| 5 | 14 | 4086 | 667 | 0.892 | 0.891 |
| **Conjunt (llavor 0)** | 55 | — | 3585 | **0.892** | 0.886 |

Amb la llavor 0 la GCN surt sis mil·lèsimes per sobre, però **és la llavor que més l'afavoreix**:
repetint el protocol, les llavors 1 i 2 donen 0.874 i 0.886. Per això la xifra bona és la de
les vuit llavors aparellades del §1.

---

## 3. El graf: qui és veí de qui

És la decisió pròpia de la GCN, i la que la bateria contesta més clarament. Dues granades són
veïnes amb un pes gaussià segons la distància al radar i/o la diferència d'instant (`GCN.md`
§3).

| Graf | Veïnes si… | site holdout | site equips fora | timing holdout |
|---|---|---|---|---|
| **`space_time`** (defecte) | cauen a prop **i** alhora | **0.896** ±0.010 | **0.892** | 0.874 |
| `time` | es llancen alhora | 0.882 ±0.006 | 0.879 | 0.878 |
| `space` | cauen a prop | 0.872 ±0.010 | 0.870 | **0.819** |
| `full` (control) | sempre, totes amb totes | **0.822** ±0.012 | **0.814** | 0.788 |

**Què en surt:**

- **Totes connectades és el pitjor, amb diferència**: −7,4 punts al holdout, −7,8 amb equips
  fora, i repetit tres vegades dona 0.814 / 0.815 / 0.815. Amb totes connectades, després de la
  primera capa **tots els nodes valen el mateix** (la mitjana de la ronda) i el readout ja no
  pot triar cap granada. Queda fins i tot per sota del pooling per mitjana de DeepSets (0.847):
  aquí la mitjana es fa sobre els tokens crus, abans de cap no-linealitat.
- **Cal l'espai i el temps alhora.** Només temps perd 1,4 punts i només espai 2,4: connectar
  granades que cauen a prop però en moments diferents (o al revés) barreja coses que no van
  juntes.
- **Només espai enfonsa el timing** (0.819). En barrejar granades properes de moments
  diferents, s'emborrona justament l'instant de l'última, que és el que llegeix el cap de
  timing.
- **L'amplada del veïnatge és indiferent:**

| | σ espai 0,05 (50 px) | **0,1 (100 px)** | 0,2 (200 px) | σ temps 3 s | **6 s** | 12 s |
|---|---|---|---|---|---|---|
| site holdout | 0.898 | **0.896** | 0.895 | 0.898 | **0.896** | 0.896 |
| site equips fora | 0.895 | **0.892** | 0.889 | 0.895 | **0.892** | 0.890 |

  Tot dins d'un punt: el resultat no depèn d'haver encertat les σ.

O sigui: un graf dolent fa mal, un graf bo no ajuda. **El millor que pot fer la GCN és no
destorbar.**

---

## 4. Configuracions de xarxa

Les dinou de `RESULTATS.md` §4, ara totes amb el codificador GCN (`phi*` vol dir capes de
convolució de graf).

| Configuració | site holdout GCN | site holdout DS | site equips fora GCN | site equips fora DS |
|---|---|---|---|---|
| `baseline` | 0.896 ±0.010 | 0.899 ±0.005 | 0.892 | 0.886 |
| `phi1` | 0.897 ±0.009 | 0.900 ±0.006 | 0.894 | 0.896 |
| `rho1` | 0.899 ±0.008 | 0.900 ±0.004 | 0.890 | 0.892 |
| `phi1_rho1` | **0.696** ±0.021 | 0.698 ±0.018 | **0.682** | 0.684 |
| `phi3` | 0.893 ±0.008 | 0.898 ±0.009 | 0.885 | 0.888 |
| `rho3` | 0.895 ±0.007 | 0.898 ±0.010 | 0.891 | 0.895 |
| `phi3_rho3` | 0.893 ±0.010 | 0.894 ±0.011 | 0.880 | 0.884 |
| `narrow` | 0.897 ±0.007 | 0.897 ±0.010 | 0.891 | 0.891 |
| `wide` | 0.902 ±0.010 | 0.900 ±0.005 | 0.888 | 0.889 |
| `xwide` | 0.900 ±0.009 | 0.902 ±0.007 | 0.884 | 0.890 |
| `tanh` | 0.897 ±0.007 | 0.899 ±0.004 | 0.890 | 0.893 |
| `leaky_relu` | 0.897 ±0.010 | 0.901 ±0.007 | 0.893 | 0.892 |
| `pool_mean` | **0.847** ±0.007 | 0.847 ±0.006 | **0.839** | 0.841 |
| `pool_sum` | **0.839** ±0.011 | 0.834 ±0.013 | **0.825** | 0.831 |
| `lr_1e-3` | 0.901 ±0.008 | 0.892 ±0.007 | 0.882 | 0.882 |
| `lr_1e-2` | 0.897 ±0.008 | 0.900 ±0.005 | 0.891 | 0.893 |
| `wd_0` | 0.896 ±0.009 | 0.901 ±0.008 | 0.889 | 0.890 |
| `wd_1e-3` | 0.899 ±0.008 | 0.905 ±0.006 | 0.893 | 0.893 |
| `intent_off` | 0.889 ±0.008 | 0.893 ±0.014 | 0.886 | 0.885 |

**Fila a fila, les dues arquitectures donen el mateix**: la diferència més gran entre columnes
aparellades és de 9 mil·lèsimes (`lr_1e-3` al holdout), i la majoria és de 3 o menys. Totes
les conclusions de `RESULTATS.md` §4 es mantenen sense canviar-ne cap:

- **Cap configuració millora el defecte**; les mateixes tres en surten per sota.
- **Ni profunditat ni amplada** són el coll d'ampolla. En una GCN, més capes vol dir que cada
  granada veu veïns de veïns (`phi3`: dos salts), i tampoc hi guanya.
- **Sense no-linealitat** (`phi1_rho1`) s'enfonsa igual: 0.696.
- **El pooling per atenció segueix sent l'única decisió que aguanta** (0.896 contra 0.847 i
  0.839).
- **`lr_1e-3` torna a desestabilitzar el timing** en una partició (±0.100, com amb DeepSets).

### Repeticions amb equips fora

| Configuració | rep. 1 | rep. 2 | rep. 3 | mitjana GCN | mitjana DS |
|---|---|---|---|---|---|
| `baseline` | 0.892 | 0.874 | 0.886 | **0.884 ±0.007** | 0.889 ±0.003 |
| `intent_off` | 0.886 | 0.878 | 0.884 | 0.883 ±0.003 | 0.884 ±0.004 |
| `narrow` | 0.891 | 0.890 | 0.888 | 0.890 ±0.001 | 0.892 ±0.000 |
| `rho3` | 0.891 | 0.885 | 0.881 | 0.886 ±0.004 | 0.890 ±0.003 |
| `pool_sum` | 0.825 | 0.821 | 0.819 | 0.821 ±0.003 | 0.829 ±0.002 |
| `lr_1e-3` | 0.882 | 0.878 | 0.884 | 0.881 ±0.003 | 0.883 ±0.003 |
| `graph_full` | 0.814 | 0.815 | 0.815 | 0.815 ±0.000 | — |

La GCN per defecte és la més variable de la taula (una repetició a 0.874). Les altres
configuracions queden totes a menys de 8 mil·lèsimes de la seva parella de DeepSets.

---

## 5. Ablacions

Mateix protocol que `RESULTATS.md` §5.

| Ablació | holdout GCN | holdout DS | equips fora GCN | equips fora DS | timing GCN |
|---|---|---|---|---|---|
| cap | 0.896 ±0.011 | 0.899 ±0.006 | 0.892 | 0.886 | 0.871 |
| sense posició | **0.567** ±0.024 | 0.582 ±0.015 | **0.573** | 0.564 | 0.872 |
| posició barrejada | 0.574 ±0.010 | 0.574 ±0.017 | 0.566 | 0.571 | 0.868 |
| sense one-hot de mapa | 0.733 ±0.036 | 0.778 ±0.010 | 0.691 | 0.680 | 0.877 |
| sense temps | 0.838 ±0.015 | 0.845 ±0.012 | 0.829 | 0.826 | **0.612** |
| sense alçada | 0.872 ±0.007 | 0.875 ±0.013 | 0.864 | 0.871 | 0.875 |

**El mateix patró que amb DeepSets, xifra a xifra.**

- **La posició és el senyal.** Amb equips fora el model treu 38,2 punts al baseline (0.892
  contra 0.510), i sense posició en treu 6,3: la posició n'explica el **84 %** (DeepSets: 86 %).
  La posició barrejada també s'enfonsa (0.566).
- **El mapa val 20 punts** amb equips fora (DeepSets 21). Al holdout la GCN en perd més (16
  contra 12), però amb una desviació de 0.036: dues de les tres particions ho expliquen.
- **El temps val 6 punts per al site i és imprescindible per al timing** (0.612, al baseline).
- **L'alçada val 2,8 punts** amb equips fora (DeepSets 1,5).

> **A la GCN les ablacions toquen també el graf.** Sense posició, totes les granades cauen
> al centre del radar i el graf passa a ser **només de temps**; sense temps, **només d'espai**.
> Cada fila mesura alhora la pèrdua de la feature i la d'aquella dimensió del graf. Amb
> DeepSets no passava, i per això aquestes files no són del tot la mateixa mesura.

---

## 6. Precisió per mapa

Deixant equips fora, **mitjana de les 8 llavors** a totes dues columnes (a `RESULTATS.md` §6
la columna és d'una sola llavor, per això els números de DeepSets difereixen una mica):

| Mapa | plants | site GCN | site DS | baseline A/B |
|---|---|---|---|---|
| de_dust2 | 879 | 0.918 | 0.923 | 0.534 |
| de_mirage | 531 | 0.918 | 0.919 | 0.629 |
| de_nuke | 435 | **0.787** | 0.782 | 0.497 |
| de_ancient | 418 | 0.894 | 0.896 | 0.471 |
| de_anubis | 366 | 0.888 | 0.890 | 0.454 |
| de_inferno | 340 | 0.912 | 0.913 | 0.438 |
| de_train | 262 | **0.824** | 0.828 | 0.458 |
| de_cache | 192 | 0.922 | 0.917 | 0.542 |
| de_overpass | 162 | 0.910 | 0.927 | 0.444 |

**La GCN no arregla nuke ni train.** Era la hipòtesi més raonable per a aquesta arquitectura:
si els dos mapes fluixos fallaven perquè cal llegir la **composició** de l'execute (quines
granades cauen juntes), la GCN ho hauria d'haver notat. Queden igual (0.787 i 0.824). La
pregunta de `PENDENT.md` segueix oberta, però **ara sabem que no és això**.

Al holdout (llavor per llavor, mitjana de 5): nuke 0.770 i train 0.808, la resta de 0.891 a
0.955. Mateix patró.

---

## 7. Corba d'aprenentatge

| Rondes d'entrenament | site GCN | site DS | 3 classes GCN | timing GCN |
|---|---|---|---|---|
| 1068 (20 %) | 0.853 ±0.024 | 0.861 ±0.031 | 0.585 | 0.834 |
| 2136 (40 %) | 0.880 ±0.022 | 0.881 ±0.012 | 0.596 | 0.855 |
| 3204 (60 %) | 0.884 ±0.027 | 0.900 ±0.011 | 0.609 | 0.867 |
| 4272 (80 %) | 0.895 ±0.019 | 0.904 ±0.009 | 0.601 | 0.870 |
| 5340 (100 %) | 0.896 ±0.011 | 0.899 ±0.006 | 0.609 | 0.871 |

La GCN **no aprèn més de pressa amb poques dades** —era l'altre argument possible, que en
compartir informació entre granades aprofités millor una mostra petita— i té el doble de
desviació a cada punt. Fa pla a partir d'unes 4000 rondes.

---

## 8. Les rondes que no van plantar

### Quant aporten (`use_intent`, 8 llavors aparellades, equips fora)

| llavor | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| amb | 0.8923 | 0.8745 | 0.8862 | 0.8890 | 0.8971 | 0.8934 | 0.8909 | 0.8862 |
| sense | 0.8856 | 0.8784 | 0.8842 | 0.8789 | 0.8789 | 0.8862 | 0.8781 | 0.8697 |
| delta | +0.0067 | −0.0039 | +0.0020 | +0.0100 | +0.0181 | +0.0073 | +0.0128 | +0.0165 |

| | GCN | DeepSets |
|---|---|---|
| amb | 0.8887 ±0.0068 | 0.8908 ±0.0030 |
| sense | 0.8800 ±0.0054 | 0.8797 ±0.0054 |
| **delta** | **+0.0087 ±0.0074 · t = 3,34 · 7 de 8** | +0.0111 ±0.0060 · t = 5,20 · 8 de 8 |

**Segueixen ajudant**, amb la GCN també: +0,9 punts amb equips no vistos, 7 llavors de 8. El
guany és una mica menor i més sorollós, com tot a la GCN. Fixeu-vos que **sense** aquestes
rondes les dues arquitectures donen exactament el mateix (0.8800 i 0.8797).

### El biaix de selecció

Mateix arnès que a `RESULTATS.md` §7: la site head entrenada només amb plants, preguntada
pels 989 executes fallits d'equips no vistos, estratificant per nombre de granades.

| granades a la ronda | plants | fallits |
|---|---|---|
| 1–4 | 0.780 | 0.757 |
| 5–8 | 0.846 | **0.907** |
| 9–12 | 0.888 | **0.908** |
| 13+ | 0.914 | **0.951** |
| **re-pesat a la mateixa distribució** | **0.867** | **0.893** |

**+0.026** (DeepSets +0.030). **Tampoc hi ha biaix de selecció amb la GCN**: amb utility
comparable, llegeix un execute tallat igual de bé o millor que un que va sortir.

> El `delta net` que imprimeix el script (−0.0104) **està mal calculat**, com ja passava amb
> DeepSets (`PENDENT.md`): inclou els fallits sense cap granada. El bo és el de la taula.

---

## 9. Què no s'ha refet

- **El mostreig del requadre** (`RESULTATS.md` §2): mesura l'estimador (64 punts Sobol dins
  la caixa), no la xarxa. Amb la GCN hi ha un matís nou —cada mostra mou les granades i per
  tant **canvia el graf**—, i si mai la GCN passés a ser el model servit caldria remesurar-ho.
- **La fuga de la utility post-plant** (`RESULTATS.md` §8): és una propietat del conjunt de
  dades i ja està corregida a `build_dataset`, que és el mateix a les dues branques.

---

## 10. Com reproduir-ho

A la branca `arch/gcn`, copiant `sweep.py` i `sweep_report.py` al contenidor. El runner sencer
és `/app/run_gcn_battery.sh` (només dins el contenidor): les mateixes ordres de
`RESULTATS.md` §9 amb 26 configuracions (les 19 + `graph_*` + `sigma_*`), `graph_full` a les
repeticions, les 8 llavors aparellades i `bias_experiment_gcn.py` (el de DeepSets amb la
importació canviada).

Cost mesurat, 12 workers:

| Etapa | Entrenaments | Wall |
|---|---|---|
| `configs` (26 × 5) | 130 | 4,45 h |
| `ablations` (6 × 3) | 18 | 0,5 h |
| `lto` (26 × 5 folds) | 130 | 2,2 h |
| `lto_ablations`, `curve` | 45 | 0,6 h |
| repeticions (7 × 5 × 2) | 70 | 0,95 h |
| 8 llavors aparellades (2 × 5 × 8) | 80 | 1,2 h |
| biaix de selecció | 15 | 0,7 h |
| **Total** | **~488** | **10,7 h** |

Les taules es regeneren amb:

```bash
docker exec -w /app cs2-backend-dev /app/.venv/bin/python /app/sweep_report.py /app/data_store/sweep
```
