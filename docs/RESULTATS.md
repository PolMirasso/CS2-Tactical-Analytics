# Resultats empírics

> Mesurat sobre **324 demos**. Totes les xifres surten d'**una sola
> construcció del conjunt de dades** i del mateix codi, així que les files es poden comparar
> entre elles
>
> Es mesura sobre **la utility realment llançada a cada ronda**, no sobre requadres dibuixats
> a mà: vegeu el §2, que és el que diu com s'han de llegir tots els números d'aquí.


## 1. Sobre quines dades

**324 demos · 6675 rondes · 3585 plants · 55 equips · 9 mapes**

| Mapa | rondes | A | B | NoPlant | plants | granades/ronda |
|---|---|---|---|---|---|---|
| de_dust2 | 1573 | 469 | 410 | 694 | 879 | 12 |
| de_mirage | 1131 | 334 | 197 | 600 | 531 | 10 |
| de_nuke | 897 | 216 | 219 | 462 | 435 | 10 |
| de_ancient | 713 | 197 | 221 | 295 | 418 | 13 |
| de_inferno | 597 | 149 | 191 | 257 | 340 | 13 |
| de_anubis | 568 | 166 | 200 | 202 | 366 | 13 |
| de_train | 515 | 120 | 142 | 253 | 262 | 11 |
| de_overpass | 352 | 72 | 90 | 190 | 162 | 11 |
| de_cache | 329 | 104 | 88 | 137 | 192 | 12 |
| **Total** | **6675** | **1827** | **1758** | **3090** | **3585** | **12** |

**Els nou mapes passen tots del llindar de lectura**; el més petit (overpass) té 162 plants.

**La concentració, que és el que condiciona la validació, no és un problema:** cap mapa domina
(dust2 és el 23,6 % de les rondes) i cap equip domina (el més representat té el **16,6 %**, i
els tres primers el 47,3 %). Encara hi ha cua llarga: 20 dels 55 equips tenen menys de 30
rondes.

Etiquetes de timing (només rondes amb plant): **199 rush · 1250 default · 2136 late**. `rush`
és el 5,6 %, així que el seu encert individual no és fiable i el 0.79 global és sobretot encert
a `default` i `late`.

---

## 2. Com es mesura

### Sobre quina utility

Totes les xifres es mesuren sobre **la utility que es va llançar de debò a cada ronda**, tal com
surt de la demo: cada token és una granada real, amb la seva **posició exacta** al radar, el seu
**instant** i la seva **alçada**. No es mesura sobre res dibuixat a mà.

A l'eina, en canvi, l'usuari **dibuixa una àrea i una finestra de temps**, i el model
marginalitza sobre 24 mostres dins d'aquell requadre; l'alçada hi va sempre **neutra**, perquè
l'usuari no dibuixa alçada. Per tant, en llegir qualsevol número d'aquest document:

- Són el **sostre**: el que dona el model amb l'entrada exacta.
- Com més gran sigui el requadre dibuixat, més repartida surt la predicció i més s'allunya
  d'aquestes xifres; amb un requadre petit i ben col·locat s'hi acosta.
- **Quant se n'allunya no està mesurat.** Caldria simular requadres de mides diferents al
  voltant de cada granada real i tornar a avaluar.

### Dos protocols

Es fan servir dos, i **donen respostes diferents a propòsit**.

**Holdout 80/20.** Es reserva el 20 % de les rondes abans d'entrenar i totes les mètriques es
calculen només sobre aquest tros. És el número que ensenya la targeta del model a `/scouting`.
Cada configuració es mesura sobre **3 particions** i es reporta la mitjana ± la desviació:

| Partició | site (A/B) | 3 classes | timing | ECE (abans → després) |
|---|---|---|---|---|
| seed 0 | 0.876 | 0.625 | 0.775 | 0.055 → 0.013 |
| seed 1 | 0.865 | 0.609 | 0.804 | 0.052 → 0.027 |
| seed 2 | 0.892 | 0.625 | 0.797 | 0.038 → 0.033 |

> El soroll del holdout és de **±0.002–0.015** en `site`, o sigui que **ja distingeix**: una
> diferència de 3 punts amb desviacions d'un punt és real.

**Deixant equips fora (leave-teams-out).** Es parteixen els 55 equips en 5 grups i, per cada
grup, s'entrena amb els altres i es prova sobre els equips retirats, que el model **no ha vist
mai**. També s'exclouen de l'entrenament les rondes on l'equip retirat era el **rival**, per
evitar fuga. Respon a: *el model llegeix la tàctica o memoritza la taxa base de cada equip?*

| Fold | equips fora | rondes per entrenar | rondes de test | plants | site (A/B) |
|---|---|---|---|---|---|
| 1 | 8 | 4264 | 1334 | 750 | 0.867 |
| 2 | 8 | 4173 | 1332 | 755 | 0.879 |
| 3 | 11 | 4216 | 1343 | 712 | 0.874 |
| 4 | 14 | 4172 | 1331 | 701 | 0.874 |
| 5 | 14 | 4086 | 1335 | 667 | 0.870 |
| **Conjunt** | 55 | — | 6675 | 3585 | **0.873** |

Els cinc folds diuen el mateix (0.867–0.879) i tots entrenen amb ~4100–4300 rondes. Repetint el
protocol sencer amb tres inicialitzacions: **0.873 / 0.869 / 0.869** (mitjana 0.870, desviació
0.002).

> **El resultat més important d'aquesta secció:** el holdout dona **0.878** i els equips no
> vistos **0.873**. Són el mateix número. Si el model memoritzés la taxa base de cada equip,
> retirar equips sencers l'hauria d'enfonsar, i no passa.

### Dos baselines, i per què no són intercanviables

Totes les taules porten el baseline **A contra B**: el site més freqüent d'aquell equip en
aquell mapa, calculat sobre les rondes d'entrenament i avaluat **només sobre els plants**, que
és el mateix conjunt sobre el qual es mesura `site`. Val **0.524** al holdout i **0.510**
deixant equips fora.

El baseline de **3 classes** es mesura sobre **totes** les rondes i val 0.431. Com que el 46 %
de les rondes són NoPlant, aquell baseline sobretot prediu NoPlant i **no és comparable** amb un
encert d'A contra B. Cada mètrica va amb el seu.

---

## 3. El model desplegat

**φ 18→32→24 · atenció · ρ 32→2 · ReLU**, α = 1e-4, lr = 5e-3, Adam amb early stopping i
calibratge de temperatura. Reentrenat el **2026-08-30** sobre les 6675 rondes i 55 equips (302 s).

| Mètrica | Model | Baseline | Protocol |
|---|---|---|---|
| Site (A contra B, donat un plant) | **0.876** | 0.532 | holdout 80/20, partició del model desplegat |
| Timing (rush/default/late) | **0.775** | 0.567 | ídem |
| 3 classes (A/B/NoPlant) | **0.625** | 0.440 | ídem |
| Site sobre **equips no vistos** | **0.873** | 0.510 | deixant equips fora, 5 folds |
| ECE (calibratge) | 0.055 → **0.013** | — | ídem holdout |

El desglossat per mapa és al §6, amb els dos protocols i molta més mostra per fila.

---

## 4. Configuracions de xarxa

Divuit configuracions, cadascuna canviant **un sol factor** respecte del defecte. La profunditat,
l'activació i les amplades són paràmetres (`TrainConfig` a `app/ml/model.py`).

Com que el backprop està escrit a mà, cada variant nova podria portar un gradient equivocat que
no donaria cap error, només resultats pitjors. La suite el comprova per **diferències finites**
en 15 combinacions — les 3 activacions × els 3 poolings, més sis variants de profunditat.

| Configuració | Què canvia | site — holdout (3 particions) | site — equips fora |
|---|---|---|---|
| `baseline` | — | 0.878 ±0.011 | **0.873** |
| `phi1` | φ sense capa oculta | 0.876 ±0.006 | 0.881 |
| `rho1` | ρ sense capa oculta | 0.885 ±0.007 | 0.876 |
| `phi1_rho1` | cap capa oculta enlloc | **0.685** ±0.004 | **0.660** |
| `phi3` | φ amb 2 capes ocultes | 0.879 ±0.005 | 0.864 |
| `rho3` | ρ amb 2 capes ocultes | 0.879 ±0.008 | 0.874 |
| `phi3_rho3` | les dues amb 2 ocultes | 0.882 ±0.005 | 0.864 |
| `narrow` | 16/12/16 | 0.873 ±0.005 | 0.877 |
| `wide` | 64/48/64 | 0.881 ±0.011 | 0.883 |
| `xwide` | 128/64/128 | 0.884 ±0.005 | 0.879 |
| `tanh` | activació tanh | 0.879 ±0.005 | 0.870 |
| `leaky_relu` | activació leaky ReLU | 0.886 ±0.009 | 0.871 |
| `pool_mean` | pooling per mitjana | **0.850** ±0.015 | **0.846** |
| `pool_sum` | pooling per suma | **0.834** ±0.007 | **0.832** |
| `lr_1e-3` | lr més baix | 0.877 ±0.002 | **0.819** |
| `lr_1e-2` | lr més alt | 0.881 ±0.007 | 0.873 |
| `wd_0` | sense weight decay | 0.874 ±0.006 | 0.879 |
| `wd_1e-3` | weight decay ×10 | 0.871 ±0.006 | 0.885 |

**Què en surt:**

- **Cap configuració millora el defecte.** **Quinze de les divuit** cauen entre 0.871 i 0.886 al
  holdout, dins d'un soroll d'un punt. Les tres que en surten, en surten **per sota**.
- **Ni la profunditat ni l'amplada són el coll d'ampolla.** Afegir o treure una capa a φ o a ρ no
  canvia res mesurable, i de 16/12/16 a 128/64/128 hi ha un punt de diferència en els dos
  protocols: vuit vegades més paràmetres no compren res. L'única variant que cau de debò és
  `phi1_rho1`, que **deixa la xarxa sencera sense cap no-linealitat** — llavors deixa de ser un
  DeepSets i passa a ser un model lineal sobre la suma dels tokens. És el control que confirma
  que la no-linealitat cal, no que en calguin més capes.
- **L'activació és indiferent**: ReLU, tanh i leaky ReLU queden a menys d'un punt.
- **El pooling sí que importa, i és l'única decisió d'arquitectura que aguanta.** L'atenció guanya
  la mitjana i la suma en **tots dos protocols** (0.878 / 0.850 / 0.834 al holdout; 0.873 / 0.846
  / 0.832 amb equips fora), amb barres d'error d'un punt.
- **El learning rate baix fa mal on no es veia.** `lr_1e-3` sembla bo al holdout (0.877) i perd
  quatre punts amb equips fora (0.819): no convergeix prou i el que queda és memorització.

**La columna d'equips fora s'ha de repetir igualment.** `wd_1e-3` hi dona 0.885 i `wide`
0.883, tots dos per sobre del defecte, i seria temptador adoptar-ne un. Repetint el protocol
sencer tres vegades:

| Configuració | rep. 1 | rep. 2 | rep. 3 | mitjana | desviació |
|---|---|---|---|---|---|
| `baseline` | 0.873 | 0.869 | 0.869 | **0.870** | **0.002** |
| `rho3` | 0.874 | 0.867 | 0.869 | 0.870 | 0.003 |
| `narrow` | 0.877 | 0.811 | 0.874 | 0.854 | **0.031** |
| `pool_sum` | 0.832 | 0.828 | 0.831 | **0.830** | 0.002 |
| `lr_1e-3` | 0.819 | 0.865 | 0.862 | 0.848 | 0.021 |

`rho3` **empata** exactament. `narrow`, que amb una sola mesura sortia per sobre del defecte
(0.877), té **quinze vegades més variabilitat** i de mitjana queda per sota: una de les tres
repeticions dona 0.811. No és una configuració millor, és una configuració **inestable**.
Aquesta taula és el motiu de no concloure res d'una sola mesura.

---

## 5. Ablacions: què llegeix realment el model

Mateix entrenador i mateixos protocols, però mutilant una entrada cada vegada. Diu **d'on surt
l'encert**, que és més informatiu que el número global.

| Ablació | Què es fa | site — holdout | site — equips fora |
|---|---|---|---|
| cap | referència | 0.878 ±0.011 | 0.873 |
| sense posició | x,y al centre del radar | **0.584** ±0.013 | **0.521** |
| posició barrejada | es permuten les x,y entre tokens del mateix mapa | **0.564** ±0.014 | **0.535** |
| sense one-hot de mapa | el token no diu de quin mapa és | 0.691 ±0.045 | 0.681 |
| sense temps | t01 = 0 | 0.844 ±0.014 | 0.827 |
| sense alçada | z_lvl neutre | 0.857 ±0.008 | 0.855 |

**Què en surt:**

- **La posició és el senyal, i és el resultat més important del projecte.** Sense ella, decidir A
  contra B cau a **0.521** amb equips fora, que és **exactament el baseline** (0.510): sense
  posició el model no aporta res per sobre de la taxa base. La barreja de posicions és el control
  net —conserva exactament la distribució de posicions del mapa i només trenca l'aparellament
  ronda→posició— i també s'ensorra (0.535). O sigui que el model no s'aprofita d'"on cau la
  utility en general", sinó **d'on cau en aquesta ronda concreta**.
- **El mapa al token val 19 punts** (0.873 → 0.681). Confirma amb una mesura el diagnòstic que va
  motivar el disseny: sense saber de quin mapa és, la relació posició→site apunta en direccions
  contràries segons el mapa i els gradients s'anul·len.
- **El temps val 4,6 punts** per al site (0.873 → 0.827) i és **imprescindible per al timing**:
  treure'l fa caure la cabeça de timing de 0.792 a **0.616**. Confirma que la cabeça llegeix de
  debò la línia de temps que es dibuixa.
- **L'alçada val 1,8 punts** amb equips fora (0.873 → 0.855) i 2,1 al holdout, amb desviacions de
  0.008–0.011: està fora del soroll. És informativa només a nuke, que és l'**11,9 %** dels tokens
  (8687 de 72 917); dins de nuke, el 90,5 % de la utility va al nivell alt, o sigui que la feature
  segueix sent esbiaixada — però amb prou volum ja paga.

---

## 6. Precisió per mapa

Aquesta és la taula que respon a "el 0.86 es manté fora de dust2?". **Llegiu primer la columna de
plants**: és el nombre de decisions A-contra-B sobre les quals es calcula l'encert.

### Deixant equips fora (agregat sobre els 5 folds)

| Mapa | plants | site (A/B) | baseline A/B | Supera el baseline |
|---|---|---|---|---|
| de_dust2 | 879 | **0.906** | 0.534 | +37,2 |
| de_mirage | 531 | **0.887** | 0.629 | +25,8 |
| de_nuke | 435 | **0.789** | 0.497 | +29,2 |
| de_ancient | 418 | **0.880** | 0.471 | +40,9 |
| de_anubis | 366 | **0.888** | 0.454 | +43,4 |
| de_inferno | 340 | **0.906** | 0.438 | +46,8 |
| de_train | 262 | **0.763** | 0.458 | +30,5 |
| de_cache | 192 | **0.885** | 0.542 | +34,3 |
| de_overpass | 162 | **0.914** | 0.444 | +47,0 |

**Els nou mapes superen el seu baseline, i tots per més de 25 punts.** Set dels nou van de 0.88 a
0.91 amb equips que el model no ha vist mai. És la resposta afirmativa a si el 0.86 de dust2 era
un miratge d'un sol mapa: **no ho era**, i fora de dust2 el número fins i tot puja.

**Els dos mapes més fluixos són nuke (0.789) i train (0.763)**, els únics per sota de 0.88. No és
falta de mostra —tenen 435 i 262 plants—, així que aquí caldria mirar què els diferencia.

### Holdout 80/20 (mitjana de 3 particions)

| Mapa | plants al holdout | site (A/B) | baseline A/B |
|---|---|---|---|
| de_dust2 | 175 | 0.919 | 0.530 |
| de_mirage | 99 | 0.892 | 0.572 |
| de_ancient | 91 | 0.878 | 0.520 |
| de_nuke | 89 | 0.786 | 0.521 |
| de_anubis | 72 | 0.874 | 0.558 |
| de_inferno | 67 | 0.906 | 0.496 |
| de_train | 52 | 0.815 | 0.438 |
| de_cache | 35 | 0.927 | 0.589 |
| de_overpass | 33 | 0.862 | 0.401 |

> **Les dues taules diuen el mateix**, mapa a mapa: nuke i train baixos als dos, la resta per
> sobre de 0.86. Que dos protocols diferents coincideixin és més informatiu que qualsevol dels
> dos per separat.

### Corba d'aprenentatge

Es reserva el 20 % de sempre i es va variant **només la quantitat de dades d'entrenament**, amb
el conjunt de test fix.

| Rondes d'entrenament | site (A/B) | 3 classes | timing |
|---|---|---|---|
| 1068 (20 %) | 0.852 ±0.012 | 0.606 ±0.008 | 0.771 ±0.006 |
| 2136 (40 %) | 0.864 ±0.007 | 0.604 ±0.003 | 0.780 ±0.003 |
| 3204 (60 %) | 0.878 ±0.007 | 0.604 ±0.006 | 0.788 ±0.007 |
| 4272 (80 %) | 0.870 ±0.007 | 0.613 ±0.004 | 0.788 ±0.007 |
| 5340 (100 %) | 0.878 ±0.011 | 0.619 ±0.007 | 0.792 ±0.012 |

**La corba fa pla a partir d'unes 3200 rondes.** De 3204 a 5340 el guany està dins del soroll, o
sigui que el volum global ha deixat de ser el coll d'ampolla. El que queda obert és una altra
cosa: **nuke i train** (no és mostra), la **diversitat d'equips** (20 dels 55 tenen menys de 30
rondes) i **de_vertigo**, que segueix a zero demos.

---

## 7. Com reproduir-ho

Les taules es regeneren dels JSON, i els JSON de la base de dades, amb els dos scripts de
`backend/scripts/`: **`sweep.py`** fa les bateries (`--stage configs | ablations | lto |
lto_ablations | curve`) i **`sweep_report.py`** en treu les taules en markdown. Els resultats
crus queden a `data_store/sweep/*.json`.

Comprovació del backprop, que és escrit a mà:

```bash
cd backend && PYTHONPATH=. ./.venv/bin/python -m pytest tests/test_ml.py -q
```
