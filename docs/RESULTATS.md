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
marginalitza sobre 64 mostres dins d'aquell requadre; l'alçada hi va sempre **neutra**, perquè
l'usuari no dibuixa alçada. Per tant, en llegir qualsevol número d'aquest document:

- Són el **sostre**: el que dona el model amb l'entrada exacta.
- Com més gran sigui el requadre dibuixat, més repartida surt la predicció i més s'allunya
  d'aquestes xifres; amb un requadre petit i ben col·locat s'hi acosta.

### Quant costa dibuixar un requadre en comptes del punt exacte

Mesurat el **2026-09-12** (abans no ho estava). Es prenen **300 rondes reals amb plant** de les
324 demos i es **substitueix la posició exacta de cada granada per un requadre centrat en
ella**, que és el que fa l'usuari quan diu "aquesta utility caurà per aquí". El radar fa 1024
px, o sigui que 500 px és **mitja pantalla**:

| Requadre | Encert A/B | Desviació de la probabilitat | Senyal conservat |
|---|---|---|---|
| punt exacte | **0.843** | — | 100 % |
| 46 px (el clic mínim de l'eina) | 0.843 | 0.000 | 100 % |
| 120 px | 0.843 | 0.002 | 100 % |
| 240 px (¼ del mapa) | 0.840 | 0.009 | 99 % |
| 500 px (½ del mapa) | **0.823** | 0.037 | **95 %** |

El "senyal conservat" és quant s'allunya la predicció amb requadre de la del punt exacte,
mesurat contra la distància entre el punt exacte i **no dibuixar cap utility** (el 0 % seria
"la granada ja no compta per a res").

**La utility no deixa de comptar quan el requadre creix.** Amb mitja pantalla l'encert baixa
dos punts —dins del soroll de 300 rondes (±2)— i la predicció conserva el **95 %** del senyal.
El que sí que es perd és precisió en el **número**: la probabilitat es desplaça fins a 0.037.

> **Dues variants que semblaven millors i no ho són.** La sospita era que un requadre gran
> gasta les mostres en llocs on no hi cau mai res (parets, buits): el **62–88 %** de l'àrea
> d'un requadre no ha vist mai aquell tipus de granada en 35 758 esdeveniments reals de dust2.
> Provades totes dues amb el mateix nombre de mostres, mostrejar només on el radar dibuixa, o
> ponderar per la densitat empírica, **no milloren l'encert** (0.827 i 0.823 contra 0.827 del
> mostreig pla) i la densitat és la que **més desplaça** la resposta (0.057). O sigui que la
> dilució no ve de mostrejar el buit: ve que mitja pantalla **de debò** cobreix posicions
> tàcticament diferents, i promediar-les és el comportament correcte.

**El que sí calia arreglar era l'estimació.** Amb 4 granades el promig és una integral de 12
dimensions i es feia amb **24 tirades independents**, que s'apelotonen i deixen forats: el
resultat es movia fins a **0.033** només segons la llavor. Des del 2026-09-12 els punts surten
d'una **seqüència de baixa discrepància** (Sobol scrambled) i són **64**:

| Requadre | Error abans (24 uniformes) | Error ara (64 Sobol) |
|---|---|---|
| 120 px | 0.0018 | 0.0001 |
| 320 px | 0.0054 | 0.0003 |
| 500 px | 0.0094 | 0.0005 |
| 500 px + finestra de 30 s | 0.0126 | 0.0005 |

Sobre 150 rondes reals, el mostreig nou **clava el valor convergit** (el que dona promitjant
amb 1024 punts) i el vell hi ballava al voltant:

| Requadre | Convergit | Ara (64 Sobol) | Abans (24 uniformes, 5 llavors) |
|---|---|---|---|
| 240 px | 0.813 | **0.813** | 0.811 de mitjana, entre 0.793 i 0.820 |
| 500 px | 0.787 | **0.787** | 0.795 de mitjana, entre 0.787 i 0.813 |

O sigui que **l'encert no puja** —ni havia de pujar— i els números més alts que de vegades
donava el mostreig vell eren **sort de la llavor**: amb un requadre de mitja pantalla, **6 de
150 rondes canviaven de site predit** només canviant-la (4 amb 240 px, 1 amb 120 px). Ara això
no pot passar.

### Per què 64 punts fixos i no un nombre que creixi amb el requadre

| Requadre | 16 punts | 32 | **64** | 128 | 256 |
|---|---|---|---|---|---|
| 120 px (d'1 a 14 granades) | ≤0.0009 | ≤0.0009 | **≤0.0010** | ≤0.0005 | ≤0.0004 |
| 500 px (d'1 a 14 granades) | 0.0015–0.0075 | 0.0003–0.0027 | **0.0001–0.0013** | 0.0001–0.0013 | 0.0001–0.0012 |

**A partir de 64 l'error ja no baixa**: 128 i 256 donen el mateix. I el que el mou és la
**mida del requadre**, no el nombre de granades — amb 120 px tant li fa que n'hi hagi una com
catorze, tot i que això multiplica per catorze les dimensions de la integral.

El motiu de fons és que **la superfície que es promitja és suau**. Avaluant P(A) en una
graella de 16×16 dins d'un requadre de 500 px a dust2 (un punt cada 31 px):

- P(A) va de **0.001 a 0.059** en tot el requadre: el recorrida sencer són 6 punts percentuals.
- Entre dos punts veïns a 31 px canvia **0.0017** de mitjana (màxim 0.0108).
- La mitjana real dels 256 punts és **0.0130**; amb 64 punts surt **0.0130**, i amb 16, 0.0129.

No hi ha cap detall fi que calgui resoldre posant-hi més punts: el que calia era que estiguessin
**ben repartits**, que és exactament el que fallava. Posats a comparar, l'error de 64 punts
(≤0.0013) és **vuit vegades més fi que el dígit més baix que pinta la interfície**, que ensenya
percentatges enters. Per això és una constant i no una heurística per mida.

És la mateixa integral —el promig no canvia, només s'estima bé—, així que **cap número
d'aquest document queda invalidat**. Costa entre 7 i 19 ms per predicció.

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

## 7. Les rondes que no van plantar

El **46 % de les rondes acaben sense plant**, i fins ara es feien servir només per al *gate*.
Però moltes no són "no volien plantar": són "anaven a B i els van matar abans". Això vol dir
que **la site head només ha après mai d'executes que van sortir bé**, i és un biaix de selecció
que valia la pena mirar.

### Llegir on anaven

La intenció es recupera del replay, sense tornar a obrir cap `.dem`. Dues lectures, preses a
**20 s i 12 s abans que acabi la ronda** i que han de **coincidir als dos instants** — un equip
que executa convergeix sobre un site i s'hi queda, un que fa control de mapa deriva:

| lectura | què mira |
|---|---|
| jugadors | regió majoritària dels T vius i fora de spawn, amb marge ≥2 |
| bomba | on és la bomba: a les mans de qui la porta, o allà on va caure |

Guanya la que decideixi. **Es calibra contra les rondes que SÍ van plantar**, on la resposta es
coneix:

| lectura | cobertura | precisió |
|---|---|---|
| jugadors | 74,3 % | 0,993 |
| bomba | 70,8 % | 0,983 |
| **unió** | **83,2 %** | **0,985** |

> Quan totes dues decideixen, **coincideixen 2128 de 2130 vegades (99,9 %)**. Per això no cal
> decidir quina mana: la unió només afegeix cobertura, no conflictes.

La bomba és el que fa viables les rondes que s'acaben per temps: allà els jugadors només
resolen el **16,6 %** i la bomba el **72,6 %**. Té sentit — amb el rellotge acabant-se l'equip
està escampat, però la bomba segueix sent en un lloc concret.

**Recuperades 2341 de les 3090 rondes sense plant (75,8 %)**:

| motiu del final de ronda | llegides | % |
|---|---|---|
| `t_killed` (els maten a tots) | 1806 / 2352 | 76,8 % |
| `ct_killed` (guanyen sense plantar) | 285 / 393 | 72,5 % |
| `time_ran_out` | 250 / 345 | 72,5 % |

> La lectura fa servir el **futur de la ronda**, així que és una **etiqueta i mai una feature** —
> el mateix estatus que té l'esdeveniment `bomb_planted` per decidir `target_site`. Les rondes
> recuperades només entren a l'**entrenament** de la site head; l'avaluació segueix sent sobre
> plants reals, o sigui que l'objectiu no canvia i els números segueixen sent comparables.

### Quant aporta

Mesurat aparellat: cada llavor entrena els dos braços amb la mateixa inicialització, i l'únic
que canvia és si la site head veu aquestes rondes (`TrainConfig.use_intent`).

**Deixant equips fora, 8 llavors:**

| | amb | sense |
|---|---|---|
| site (A contra B) | **0,8855 ± 0,0048** | 0,8775 ± 0,0037 |

**+0,0080 ± 0,0045 · t = 5,06 · 7 de 8 llavors positives · p = 0,0015**

**Holdout 80/20, 5 particions:**

| partició | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| delta | +0,0098 | −0,0057 | +0,0095 | +0,0014 | −0,0027 |

**+0,0025 ± 0,0071 · t = 0,79 · p = 0,48** — res.

**Què en surt:**

- **El guany apareix només amb equips que el model no ha vist mai.** Al holdout 80/20 els
  mateixos equips són a train i a test, així que pot recolzar-se en la seva taxa base i la
  posició li pesa menys. Amb equips nous aquella drecera desapareix i llegir la posició és
  l'únic que li queda — i aquestes rondes són posició pura. Encaixa amb el §5: sense posició,
  l'encert cau al baseline.
- **El calibratge no en surt perjudicat**: ECE 0,0251 amb contra 0,0279 sense.
- **El timing no es mou** (0,794 ± 0,014 als dos braços), com ha de ser: el canvi toca només la
  site head.
- **El braç `sense` dona 0,8775 i el número publicat al §6 és 0,873.** Que reprodueixi és el
  control que diu que aquesta bateria és comparable amb l'anterior.

> **Tres llavors no bastaven.** Amb les tres primeres el delta sortia **+0,0043 amb t=1,59**, que
> no demostra res; amb vuit és **+0,0080 amb t=5,06**. És la mateixa lliçó que la taula de
> repeticions del §4, on `narrow` semblava la millor configuració amb una sola mesura.

### El biaix de selecció, que resulta que no hi era

La hipòtesi de partida era que la site head, entrenada només amb executes reeixits, llegiria
pitjor els que van fallar. Es mesura entrenant **només amb plants** i preguntant pels executes
fallits d'equips no vistos.

Els fallits porten **8,8 granades de mitjana contra 12,5**, així que cal estratificar:

| granades a la ronda | plants | fallits |
|---|---|---|
| 1–4 | 0,7845 | 0,7811 |
| 5–8 | 0,8412 | **0,9067** |
| 9–12 | 0,8776 | **0,9013** |
| 13+ | 0,8991 | **0,9359** |
| **re-pesat a la mateixa distribució** | **0,8591** | **0,8909** |

**Amb utility comparable, el model llegeix un execute que van tallar igual de bé o millor que un
que va sortir: +0,032.** No hi ha biaix de selecció. Replicat amb dues mides de mostra (626 i
988 rondes) donant +0,034 i +0,032.

I un límit que val la pena tenir escrit: **el 9,1 % dels executes fallits no tenen ni una
granada**. Allà el model no té res a llegir i respon sempre el mateix — encerta el 46 %, una
moneda a l'aire. No és un error, és el sostre del que la utility pot dir.

> **Les taules dels §4, §5 i §6 es van mesurar sense aquestes rondes**, que és el comportament
> de `use_intent=False`. Descriuen el model tal com estava; el §7 és l'únic que mesura el canvi.

---

## 8. Com reproduir-ho

Les taules es regeneren dels JSON, i els JSON de la base de dades, amb els dos scripts de
`backend/scripts/`: **`sweep.py`** fa les bateries (`--stage configs | ablations | lto |
lto_ablations | curve`) i **`sweep_report.py`** en treu les taules en markdown. Els resultats
crus queden a `data_store/sweep/*.json`.

La comparació del §7 és la configuració `intent_off` contra el defecte, amb `--only` (que ara
filtra també a l'etapa `configs`, abans només a `lto`):

```bash
sweep.py --stage configs --seeds 5 --only baseline,intent_off --jobs 6
for s in 0 1 2 3 4 5 6 7; do
  sweep.py --stage lto --folds 5 --seed $s --out lto_seed$s --only baseline,intent_off --jobs 6
done
```

Comprovació del backprop, que és escrit a mà:

```bash
cd backend && PYTHONPATH=. ./.venv/bin/python -m pytest tests/test_ml.py -q
```
