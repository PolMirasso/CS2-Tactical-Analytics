# Resultats empírics

> Mesurat sobre **324 demos**. Totes les xifres surten d'**una sola
> construcció del conjunt de dades** i del mateix codi, així que les files es poden comparar
> entre elles. La bateria sencera es va refer el **2026-09-21** (313 entrenaments, 6 h) després
> de treure la utility posterior al plant, que inflava el número de 3 classes: vegeu el §8.
>
> Es mesura sobre **la utility realment llançada a cada ronda**, no sobre requadres dibuixats
> a mà: vegeu el §2, que és el que diu com s'han de llegir tots els números d'aquí.


## 1. Sobre quines dades

**324 demos · 6675 rondes · 3585 plants · 55 equips · 9 mapes**

| Mapa | rondes | A | B | NoPlant | plants | granades/ronda |
|---|---|---|---|---|---|---|
| de_dust2 | 1573 | 469 | 410 | 694 | 879 | 10,7 |
| de_mirage | 1131 | 334 | 197 | 600 | 531 | 9,6 |
| de_nuke | 897 | 216 | 219 | 462 | 435 | 9,4 |
| de_ancient | 713 | 197 | 221 | 295 | 418 | 11,7 |
| de_inferno | 597 | 149 | 191 | 257 | 340 | 11,1 |
| de_anubis | 568 | 166 | 200 | 202 | 366 | 11,5 |
| de_train | 515 | 120 | 142 | 253 | 262 | 10,4 |
| de_overpass | 352 | 72 | 90 | 190 | 162 | 10,6 |
| de_cache | 329 | 104 | 88 | 137 | 192 | 10,7 |
| **Total** | **6675** | **1827** | **1758** | **3090** | **3585** | **10,5** |

"Granades/ronda" és la utility T que veu el model, ja sense la llançada després del plant:
**70 204 granades**. 265 rondes (4,0 %) no en tenen cap.

**Els nou mapes passen tots del llindar de lectura**; el més petit (overpass) té 162 plants.

**La concentració, que és el que condiciona la validació, no és un problema:** cap mapa domina
(dust2 és el 23,6 % de les rondes) i cap equip domina (el més representat té el **16,6 %**, i
els tres primers el 47,3 %). Encara hi ha cua llarga: 20 dels 55 equips tenen menys de 30
rondes.

Etiquetes de timing (només rondes amb plant): **199 rush · 1250 default · 2136 late**. `rush`
és el 5,6 %, així que el seu encert individual no és fiable i el 0.88 global és sobretot encert
a `default` i `late`.

---

## 2. Com es mesura

### Sobre quina utility

Totes les xifres es mesuren sobre **la utility que es va llançar de debò a cada ronda**, tal com
surt de la demo: cada token és una granada real, amb la seva **posició exacta** al radar, el seu
**instant** i la seva **alçada**. No es mesura sobre res dibuixat a mà.

Només compta la utility **fins al plant**. Les 2713 granades T llançades després (el 6 % de les
de rondes amb plant, repartides en 1525 de les 3585) són l'equip aguantant el site que ja ha
pres, i a l'eina no es dibuixen mai. Fins al 2026-09-20 s'hi incloïen, i inflaven el 3 classes
(§8).

A l'eina, en canvi, l'usuari **dibuixa una àrea i una finestra de temps**, i el model
marginalitza sobre 64 mostres dins d'aquell requadre; l'alçada hi va sempre **neutra**, perquè
l'usuari no dibuixa alçada. Per tant, en llegir qualsevol número d'aquest document:

- Són el **sostre**: el que dona el model amb l'entrada exacta.
- Com més gran sigui el requadre dibuixat, més repartida surt la predicció i més s'allunya
  d'aquestes xifres; amb un requadre petit i ben col·locat s'hi acosta.

### Quant costa dibuixar un requadre en comptes del punt exacte

Mesurat el **2026-09-12** amb el model servit (el del 30-08). Mesura l'**estimador** del
requadre, no l'entrenament, així que no s'ha refet amb la bateria nova. Es prenen **300 rondes
reals amb plant** i es **substitueix la posició exacta de cada granada per un requadre centrat
en ella**, que és el que fa l'usuari quan diu "aquesta utility caurà per aquí". El radar fa 1024
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
Cada configuració es mesura sobre **5 particions** i es reporta la mitjana ± la desviació:

| Partició | site (A/B) | 3 classes | timing | ECE (abans → després) |
|---|---|---|---|---|
| seed 0 | 0.907 | 0.632 | 0.881 | 0.039 → 0.033 |
| seed 1 | 0.897 | 0.600 | 0.877 | 0.033 → 0.026 |
| seed 2 | 0.894 | 0.611 | 0.870 | 0.032 → 0.028 |
| seed 3 | 0.897 | 0.621 | 0.884 | 0.069 → 0.053 |
| seed 4 | 0.899 | 0.605 | 0.887 | 0.053 → 0.037 |
| **mitjana** | **0.899 ±0.005** | **0.614 ±0.011** | **0.880 ±0.006** | **0.045 → 0.035** |

> El soroll del holdout és de **±0.004–0.014** en `site`, o sigui que **ja distingeix**: una
> diferència de 3 punts amb desviacions d'un punt és real. En 3 classes el soroll és més gran
> (0.600–0.632 només canviant la partició).

**Deixant equips fora (leave-teams-out).** Es parteixen els 55 equips en 5 grups i, per cada
grup, s'entrena amb els altres i es prova sobre els equips retirats, que el model **no ha vist
mai**. També s'exclouen de l'entrenament les rondes on l'equip retirat era el **rival**, per
evitar fuga. Respon a: *el model llegeix la tàctica o memoritza la taxa base de cada equip?*

| Fold | equips fora | rondes per entrenar | rondes de test | plants | site (A/B) |
|---|---|---|---|---|---|
| 1 | 8 | 4264 | 1334 | 750 | 0.899 |
| 2 | 8 | 4173 | 1332 | 755 | 0.894 |
| 3 | 11 | 4216 | 1343 | 712 | 0.865 |
| 4 | 14 | 4172 | 1331 | 701 | 0.882 |
| 5 | 14 | 4086 | 1335 | 667 | 0.891 |
| **Conjunt** | 55 | — | 6675 | 3585 | **0.886** |

Els cinc folds van de 0.865 a 0.899 i tots entrenen amb ~4100–4300 rondes. Repetint el protocol
sencer amb **vuit inicialitzacions**: de 0.886 a 0.894, mitjana **0.891 ±0.003**.

> **El resultat més important d'aquesta secció:** el holdout dona **0.899** i els equips no
> vistos **0.891**. Menys d'un punt de diferència. Si el model memoritzés la taxa base de cada
> equip, retirar equips sencers l'hauria d'enfonsar, i no passa.

### Dos baselines, i per què no són intercanviables

Totes les taules porten el baseline **A contra B**: el site més freqüent d'aquell equip en
aquell mapa, calculat sobre les rondes d'entrenament i avaluat **només sobre els plants**, que
és el mateix conjunt sobre el qual es mesura `site`. Val **0.533** al holdout i **0.510**
deixant equips fora.

El baseline de **3 classes** es mesura sobre **totes** les rondes i val 0.450. Com que el 46 %
de les rondes són NoPlant, aquell baseline sobretot prediu NoPlant i **no és comparable** amb un
encert d'A contra B. Cada mètrica va amb el seu. El de timing (la classe més freqüent, `late`)
val 0.583.

---

## 3. El model per defecte

**φ 18→32→24 · atenció · ρ 32→2 · ReLU**, α = 1e-4, lr = 5e-3, Adam amb early stopping i
calibratge de temperatura. Entrena la site head també amb les rondes sense plant de les quals es
coneix la intenció (§7), i sobre la utility fins al plant (§2).

| Mètrica | Model | Baseline | Protocol |
|---|---|---|---|
| Site (A contra B, donat un plant) | **0.899** ±0.005 | 0.533 | holdout 80/20, 5 particions |
| Timing (rush/default/late) | **0.880** ±0.006 | 0.583 | ídem |
| 3 classes (A/B/NoPlant) | **0.614** ±0.011 | 0.450 | ídem |
| Site sobre **equips no vistos** | **0.891** ±0.003 | 0.510 | deixant equips fora, 5 folds, 8 llavors |
| ECE (calibratge) | 0.045 → **0.035** | — | holdout, 5 particions |

> **El model que serveix `/scouting` encara és el del 2026-08-30**, entrenat abans del filtre i
> de les rondes sense plant. La seva targeta ensenya 0.625 de 3 classes, que està inflat (§8).
> Fins que no es reentreni, aquesta taula descriu el model que sortirà en reentrenar, no el que
> hi ha.

El timing puja 9 punts respecte de la versió anterior (0.792), i **no és que el cap hagi
millorat**: el §8 explica què llegeix. El desglossat per mapa és al §6.

---

## 4. Configuracions de xarxa

Dinou configuracions, cadascuna canviant **un sol factor** respecte del defecte. La profunditat,
l'activació i les amplades són paràmetres (`TrainConfig` a `app/ml/model.py`).

Com que el backprop està escrit a mà, cada variant nova podria portar un gradient equivocat que
no donaria cap error, només resultats pitjors. La suite el comprova per **diferències finites**
en 15 combinacions — les 3 activacions × els 3 poolings, més sis variants de profunditat.

| Configuració | Què canvia | site — holdout (5 particions) | site — equips fora |
|---|---|---|---|
| `baseline` | — | 0.899 ±0.005 | **0.886** |
| `phi1` | φ sense capa oculta | 0.900 ±0.006 | 0.896 |
| `rho1` | ρ sense capa oculta | 0.900 ±0.004 | 0.892 |
| `phi1_rho1` | cap capa oculta enlloc | **0.698** ±0.018 | **0.684** |
| `phi3` | φ amb 2 capes ocultes | 0.898 ±0.009 | 0.888 |
| `rho3` | ρ amb 2 capes ocultes | 0.898 ±0.010 | 0.895 |
| `phi3_rho3` | les dues amb 2 ocultes | 0.894 ±0.011 | 0.884 |
| `narrow` | 16/12/16 | 0.897 ±0.010 | 0.891 |
| `wide` | 64/48/64 | 0.900 ±0.005 | 0.889 |
| `xwide` | 128/64/128 | 0.902 ±0.007 | 0.890 |
| `tanh` | activació tanh | 0.899 ±0.004 | 0.893 |
| `leaky_relu` | activació leaky ReLU | 0.901 ±0.007 | 0.892 |
| `pool_mean` | pooling per mitjana | **0.847** ±0.006 | **0.841** |
| `pool_sum` | pooling per suma | **0.834** ±0.013 | **0.831** |
| `lr_1e-3` | lr més baix | 0.892 ±0.007 | 0.882 |
| `lr_1e-2` | lr més alt | 0.900 ±0.005 | 0.893 |
| `wd_0` | sense weight decay | 0.901 ±0.008 | 0.890 |
| `wd_1e-3` | weight decay ×10 | 0.905 ±0.006 | 0.893 |
| `intent_off` | sense les rondes del §7 | 0.893 ±0.014 | 0.885 |

**Què en surt:**

- **Cap configuració millora el defecte.** **Setze de les dinou** cauen entre 0.892 i 0.905 al
  holdout, i entre 0.882 i 0.896 amb equips fora: dins d'un soroll d'un punt. Les tres que en
  surten, en surten **per sota**.
- **Ni la profunditat ni l'amplada són el coll d'ampolla.** Afegir o treure una capa a φ o a ρ no
  canvia res mesurable, i de 16/12/16 a 128/64/128 hi ha mig punt de diferència: vuit vegades
  més paràmetres no compren res. L'única variant que cau de debò és `phi1_rho1`, que **deixa la
  xarxa sencera sense cap no-linealitat** — llavors deixa de ser un DeepSets i passa a ser un
  model lineal sobre la suma dels tokens. És el control que confirma que la no-linealitat cal,
  no que en calguin més capes.
- **L'activació és indiferent**: ReLU, tanh i leaky ReLU queden a menys d'un punt.
- **El pooling sí que importa, i és l'única decisió d'arquitectura que aguanta.** L'atenció guanya
  la mitjana i la suma en **tots dos protocols** (0.899 / 0.847 / 0.834 al holdout; 0.886 / 0.841
  / 0.831 amb equips fora), amb barres d'error d'un punt.
- **El learning rate baix no sempre convergeix.** `lr_1e-3` dona un site normal, però en una de
  les cinc particions deixa el timing a **0.623** (les altres, 0.871–0.881): d'aquí el ±0.101 de
  timing. És la mateixa fragilitat que a la versió anterior sortia com a site baix amb equips
  fora (0.819), ara en un altre cap.

**La columna d'equips fora s'ha de repetir igualment.** `phi1` hi dona 0.896 i `rho3` 0.895,
tots dos per sobre del defecte. Repetint el protocol sencer tres vegades:

| Configuració | rep. 1 | rep. 2 | rep. 3 | mitjana | desviació |
|---|---|---|---|---|---|
| `baseline` | 0.886 | 0.887 | 0.893 | **0.889** | 0.004 |
| `intent_off` | 0.885 | 0.879 | 0.888 | 0.884 | 0.004 |
| `narrow` | 0.892 | 0.892 | 0.891 | 0.892 | **0.000** |
| `rho3` | 0.895 | 0.890 | 0.887 | 0.891 | 0.004 |
| `pool_sum` | 0.831 | 0.826 | 0.829 | **0.829** | 0.003 |
| `lr_1e-3` | 0.882 | 0.887 | 0.880 | 0.883 | 0.003 |

`narrow` i `rho3` **empaten** amb el defecte: la diferència és de 2–3 mil·lèsimes amb
desviacions de 4. `pool_sum` segueix sis punts per sota a les tres.

> **`narrow` ja no és inestable.** A la versió anterior una de les tres repeticions donava
> 0.811 (desviació 0.031); ara les tres queden a 0.891–0.892. Per a `narrow` en concret no
> s'ha mesurat la causa, però encaixa amb el que es va veure mesurant el filtre: la llavor que
> pitjor sortia amb tota la utility (0.871) pujava a 0.883 només traient la post-plant (§8).
> Això no fa `narrow` millor que el defecte.
>
> `phi1` no es va repetir: les files de la taula són les de la versió anterior.

---

## 5. Ablacions: què llegeix realment el model

Mateix entrenador i mateixos protocols, però mutilant una entrada cada vegada. Diu **d'on surt
l'encert**, que és més informatiu que el número global. Holdout amb 3 particions.

| Ablació | Què es fa | site — holdout | site — equips fora | timing — holdout |
|---|---|---|---|---|
| cap | referència | 0.899 ±0.006 | 0.886 | 0.876 |
| sense posició | x,y al centre del radar | **0.582** ±0.015 | **0.564** | 0.869 |
| posició barrejada | es permuten les x,y entre tokens del mateix mapa | **0.574** ±0.017 | **0.571** | 0.868 |
| sense one-hot de mapa | el token no diu de quin mapa és | 0.778 ±0.010 | 0.680 | 0.872 |
| sense temps | t01 = 0 | 0.845 ±0.012 | 0.826 | **0.613** |
| sense alçada | z_lvl neutre | 0.875 ±0.013 | 0.871 | 0.872 |

**Què en surt:**

- **La posició és el senyal, i és el resultat més important del projecte.** Amb equips fora el
  model treu **37,6 punts** al baseline (0.886 contra 0.510); sense posició en treu **5,4**
  (0.564). O sigui que la posició n'explica el **86 %**, i la resta de la ronda —tipus de
  granada, instant, mapa— gairebé no diu res sobre A o B. La barreja de posicions és el control
  net —conserva exactament la distribució de posicions del mapa i només trenca l'aparellament
  ronda→posició— i també s'ensorra (0.571). O sigui que el model no s'aprofita d'"on cau la
  utility en general", sinó **d'on cau en aquesta ronda concreta**.
- **El mapa al token val 21 punts** amb equips fora (0.886 → 0.680) i 12 al holdout. Confirma
  amb una mesura el diagnòstic que va motivar el disseny: sense saber de quin mapa és, la relació
  posició→site apunta en direccions contràries segons el mapa i els gradients s'anul·len.
- **El temps val 6 punts** per al site (0.886 → 0.826) i és **imprescindible per al timing**:
  sense ell la cabeça de timing cau de 0.876 a **0.613**, quatre punts sobre el seu baseline
  (0.571 en aquestes 3 particions). La posició, en canvi, no li fa res (0.869). El §8 explica
  per què.
- **L'alçada val 1,5 punts** amb equips fora (0.886 → 0.871) i 2,4 al holdout. És informativa
  només a nuke, que és el **12,0 %** dels tokens (8447 de 70 204); dins de nuke, el 91,5 % de
  la utility va al nivell alt, o sigui que la feature segueix sent esbiaixada — però amb prou
  volum ja paga.

---

## 6. Precisió per mapa

Aquesta és la taula que respon a "el 0.86 es manté fora de dust2?". **Llegiu primer la columna de
plants**: és el nombre de decisions A-contra-B sobre les quals es calcula l'encert.

### Deixant equips fora (agregat sobre els 5 folds)

| Mapa | plants | site (A/B) | baseline A/B | Supera el baseline |
|---|---|---|---|---|
| de_dust2 | 879 | **0.911** | 0.534 | +37,7 |
| de_mirage | 531 | **0.911** | 0.629 | +28,2 |
| de_nuke | 435 | **0.791** | 0.497 | +29,4 |
| de_ancient | 418 | **0.890** | 0.471 | +41,9 |
| de_anubis | 366 | **0.885** | 0.454 | +43,1 |
| de_inferno | 340 | **0.912** | 0.438 | +47,4 |
| de_train | 262 | **0.824** | 0.458 | +36,6 |
| de_cache | 192 | **0.932** | 0.542 | +39,0 |
| de_overpass | 162 | **0.907** | 0.444 | +46,3 |

**Els nou mapes superen el seu baseline, tots per més de 28 punts.** Set dels nou van de 0.885
a 0.932 amb equips que el model no ha vist mai. És la resposta afirmativa a si el 0.86 de dust2
era un miratge d'un sol mapa: **no ho era**.

**Els dos mapes més fluixos segueixen sent nuke (0.791) i train (0.824)**, els únics per sota de
0.88. Train ha pujat sis punts respecte de la versió anterior (0.763); nuke no s'ha mogut
(0.789). No és falta de mostra —tenen 435 i 262 plants—, així que aquí caldria mirar què els
diferencia.

### Holdout 80/20 (mitjana de 5 particions)

| Mapa | plants al holdout | site (A/B) | baseline A/B |
|---|---|---|---|
| de_dust2 | 178 | 0.935 | 0.544 |
| de_mirage | 108 | 0.914 | 0.536 |
| de_nuke | 83 | 0.781 | 0.538 |
| de_ancient | 82 | 0.885 | 0.518 |
| de_anubis | 73 | 0.913 | 0.557 |
| de_inferno | 64 | 0.921 | 0.489 |
| de_train | 54 | 0.836 | 0.484 |
| de_cache | 40 | 0.941 | 0.545 |
| de_overpass | 34 | 0.960 | 0.565 |

> **Les dues taules diuen el mateix**, mapa a mapa: nuke i train baixos als dos, la resta per
> sobre de 0.88. Que dos protocols diferents coincideixin és més informatiu que qualsevol dels
> dos per separat. Cache i overpass tenen 34–40 plants per partició, així que el seu 0.94–0.96
> porta ±3–4 punts de soroll.

### Corba d'aprenentatge

Es reserva el 20 % de sempre i es va variant **només la quantitat de dades d'entrenament**, amb
el conjunt de test fix. 3 particions.

| Rondes d'entrenament | site (A/B) | 3 classes | timing |
|---|---|---|---|
| 1068 (20 %) | 0.861 ±0.031 | 0.589 ±0.011 | 0.852 ±0.015 |
| 2136 (40 %) | 0.881 ±0.012 | 0.599 ±0.018 | 0.862 ±0.004 |
| 3204 (60 %) | 0.900 ±0.011 | 0.611 ±0.013 | 0.859 ±0.004 |
| 4272 (80 %) | 0.904 ±0.009 | 0.611 ±0.012 | 0.869 ±0.007 |
| 5340 (100 %) | 0.899 ±0.006 | 0.614 ±0.013 | 0.876 ±0.004 |

**La corba fa pla a partir d'unes 3200 rondes.** De 3204 a 5340 el guany està dins del soroll, o
sigui que el volum global ha deixat de ser el coll d'ampolla. El que queda obert és una altra
cosa: **nuke i train** (no és mostra), la **diversitat d'equips** (20 dels 55 tenen menys de 30
rondes) i **de_vertigo**, que segueix a zero demos.

---

## 7. Les rondes que no van plantar

El **46 % de les rondes acaben sense plant**, i fins ara es feien servir només per al *gate*.
Però moltes no són "no volien plantar": són "anaven a B i els van matar abans". Això vol dir
que **la site head només havia après d'executes que van sortir bé**, i és un biaix de selecció
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
| jugadors | 74,3 % | 0.993 |
| bomba | 70,8 % | 0.983 |
| **unió** | **83,2 %** | **0.985** |

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
que canvia és si la site head veu aquestes rondes (`TrainConfig.use_intent`). És el defecte, i
totes les taules d'aquest document el porten; `intent_off` és la fila que el treu.

**Deixant equips fora, 8 llavors:**

| llavor | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| amb | 0.8862 | 0.8868 | 0.8934 | 0.8895 | 0.8923 | 0.8929 | 0.8907 | 0.8943 |
| sense | 0.8845 | 0.8789 | 0.8876 | 0.8764 | 0.8789 | 0.8831 | 0.8703 | 0.8778 |
| delta | +0.0017 | +0.0078 | +0.0059 | +0.0131 | +0.0134 | +0.0098 | +0.0204 | +0.0165 |

**0.8908 ±0.0030 contra 0.8797 ±0.0054 · +0.0111 ±0.0060 · t = 5,20 · 8 de 8 positives ·
p = 0,001**

**Holdout 80/20, 5 particions:**

| partició | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| delta | −0.0042 | +0.0172 | +0.0095 | −0.0101 | +0.0175 |

**+0.0060 ±0.0126 · t = 1,07 · p = 0,35** — res.

**Què en surt:**

- **El guany apareix només amb equips que el model no ha vist mai.** Al holdout 80/20 els
  mateixos equips són a train i a test, així que pot recolzar-se en la seva taxa base i la
  posició li pesa menys. Amb equips nous aquella drecera desapareix i llegir la posició és
  l'únic que li queda — i aquestes rondes són posició pura. Encaixa amb el §5.
- **El calibratge no en surt perjudicat**: ECE 0.035 amb contra 0.039 sense.
- **El timing i el 3 classes no es mouen** (0.880 i 0.614 als dos braços al holdout), com ha de
  ser: el canvi toca només la site head.
- **Control de reproducció**: les llavors 0, 1 i 2 d'aquesta mesura i les tres repeticions del
  §4, fetes en bateries diferents, donen **exactament** els mateixos números.

> **Tres llavors no bastaven, i el filtre del §8 no se'l menja.** Sense el filtre, amb tres
> llavors el delta sortia **+0.004 amb t = 1,59**, que no demostra res; amb vuit, **+0.008 amb
> t = 5,07**. La sospita era que el filtre i aquestes rondes arreglaven el mateix soroll i que
> un es menjaria l'altre. No: sumen.
>
> | | sense filtre | amb filtre |
> |---|---|---|
> | amb intent | 0.886 ±0.005 | **0.891 ±0.003** |
> | sense intent | 0.878 ±0.004 | 0.880 ±0.005 |
> | delta | +0.008 · t = 5,07 · 7/8 | **+0.011 · t = 5,20 · 8/8** |

### El biaix de selecció, que resulta que no hi era

> Mesurat el **2026-09-19**, abans del filtre, i no refet. Entrena una site head **només amb
> plants** (la dieta d'abans) i té el seu propi arnès. El filtre només treu utility posterior al
> plant, que els executes fallits no tenen, així que els fallits es mesuren igual; el que canvia
> és el 6 % de la utility dels plants d'entrenament.

La hipòtesi de partida era que la site head, entrenada només amb executes reeixits, llegiria
pitjor els que van fallar. Es mesura entrenant **només amb plants** i preguntant pels executes
fallits d'equips no vistos.

Els fallits porten **8,8 granades de mitjana contra 12,5**, així que cal estratificar:

| granades a la ronda | plants | fallits |
|---|---|---|
| 1–4 | 0.785 | 0.781 |
| 5–8 | 0.841 | **0.907** |
| 9–12 | 0.878 | **0.901** |
| 13+ | 0.899 | **0.936** |
| **re-pesat a la mateixa distribució** | **0.859** | **0.891** |

**Amb utility comparable, el model llegeix un execute que van tallar igual de bé o millor que un
que va sortir: +0.032.** No hi ha biaix de selecció. Replicat amb dues mides de mostra (626 i
988 rondes) donant +0.034 i +0.032.

I un límit que val la pena tenir escrit: **el 9,1 % dels executes fallits no tenen ni una
granada**. Allà el model no té res a llegir i respon sempre el mateix — encerta el 46 %, una
moneda a l'aire. No és un error, és el sostre del que la utility pot dir.

---

## 8. La utility posterior al plant

Fins al 2026-09-20 el conjunt de dades passava al model **tota** la utility T de la ronda,
inclosa la llançada després del plant. `round_tokens` deia "only T-side opening util", però no
hi havia cap filtre de temps. Són **2713 granades** (el 6 % de la utility T de les rondes amb
plant, en 1525 de les 3585), llançades una mediana de **7,4 s després** del plant.

Ara es descarten a `build_dataset`, que és qui sap l'instant del plant; la utility crua es
conserva per al visor i els analytics. La comparació és aparellada, 8 llavors, equips fora.

### On inflava: al gate, no a la site head

| | sense filtre | amb filtre | diferència |
|---|---|---|---|
| site (A/B) | 0.886 ±0.005 | 0.891 ±0.003 | **+0.005** · t = 2,71 · 5/8 |
| 3 classes | 0.626 ±0.004 | 0.600 ±0.005 | **−0.026** · t = 12,2 · 8/8 |

**La site head no se n'aprofitava**: filtrant llegeix igual o una mica millor, perquè una granada
per aguantar el site ja pres no és una pista d'on s'executarà, és soroll. **El gate sí**:
`round_context` li passa `n_util`, `t_min` i `t_mean` calculats sobre la ronda sencera, i una
granada llançada després del plant vol dir, per definició, que hi ha hagut plant.

**El 3 classes estava inflat 2,6 punts.** Al holdout, sobre les mateixes 5 particions, baixa de
0.631 a 0.614. És el número que baixa en aquesta versió del document; el 0.625 de la targeta
del model servit (§3) i el 0.619 de la corba anterior eren inflats.

### El timing: puja, però no perquè el cap sàpiga més

Sobre les mateixes 5 particions, el timing passa de **0.794 a 0.880**. El timing s'etiqueta amb
l'instant del plant, i ara l'última granada que veu el model és la de l'execute: el plant arriba
una mediana de **9,2 s** després (quartils 5,1 i 14,5 s). Una regla d'una línia ho mostra:

| | sense filtre | amb filtre |
|---|---|---|
| regla: etiqueta de (última granada + 9 s), sobre els 3585 plants | 0.774 | **0.866** |
| cap de timing, holdout | 0.794 | **0.880** |

**El cap de timing treu 1,4 punts a la regla.** No és una fuga en el sentit del
gate —a l'eina també es dibuixa només l'execute, i si es dibuixa quan cau, el timing en surt
gairebé sol—, però vol dir que el 0.880 és **"quan dibuixes l'execute"** i no una lectura de la
tàctica. És coherent amb el §5: sense temps el timing cau al baseline, i sense posició no es
mou.

### Què ha canviat respecte de la versió anterior

| Mètrica | abans (30-08) | ara | per què |
|---|---|---|---|
| site, holdout | 0.878 | **0.899** | filtre, rondes del §7 i particions noves* |
| site, equips no vistos | 0.873 | **0.891** | rondes del §7 i filtre: de 0.878 a 0.891 amb les mateixes 8 llavors |
| 3 classes, holdout | 0.625 | **0.614** | fuga al gate corregida |
| timing, holdout | 0.792 | **0.880** | la regla de dalt |
| `narrow`, desviació entre repeticions | 0.031 | **0.000** | probablement el post-plant (§4) |

\* En tornar a parsejar les demos va canviar l'ordre de les files, i la mateixa llavor dona una
partició 80/20 diferent. Els números del holdout només es comparen dins d'una mateixa bateria.


---

## 9. Com reproduir-ho

Les taules es regeneren dels JSON, i els JSON de la base de dades, amb els dos scripts de
`backend/scripts/`: **`sweep.py`** fa les bateries i **`sweep_report.py`** en treu les taules en
markdown. Els resultats crus queden a `data_store/sweep/*.json`, i els d'abans del filtre a
`data_store/sweep_preFiltre/`.

La bateria sencera (6 h amb 12 workers):

```bash
sweep.py --stage configs --seeds 5 --jobs 12
sweep.py --stage ablations --seeds 3 --jobs 12
sweep.py --stage lto --folds 5 --jobs 12
sweep.py --stage lto_ablations --folds 5 --jobs 12
sweep.py --stage curve --seeds 3 --fracs 0.2,0.4,0.6,0.8,1.0 --jobs 12
for s in 1 2; do
  sweep.py --stage lto --folds 5 --seed $s --out lto_seed$s \
      --only baseline,intent_off,narrow,rho3,pool_sum,lr_1e-3 --jobs 12
done
```

La comparació del §7, vuit llavors aparellades:

```bash
for s in 0 1 2 3 4 5 6 7; do
  sweep.py --stage lto --folds 5 --seed $s --out ltoF_seed$s --only baseline,intent_off --jobs 6
done
```

Comprovació del backprop, que és escrit a mà:

```bash
cd backend && PYTHONPATH=. ./.venv/bin/python -m pytest tests/test_ml.py -q
```
