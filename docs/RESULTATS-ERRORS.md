# Per què falla el model, i si té algun biaix

> Les rondes on la cap de site (A contra B) s'equivoca, mirades amb SHAP, Anchors i LIME
> (`RESULTATS-SHAP.md`, `RESULTATS-ANCHORS.md`, `RESULTATS-LIME.md`). Els mateixos 5 models dels
> folds d'equips no vistos (llavor 0, encert 0.8862).
>
> 3585 rondes amb plant · **408 errors**. 2026-11-08.
>
> Codi: `scripts/errors_report.py`. JSON a `data_store/errors/summary.json`.

---

## 0. La resposta curta

| | |
|---|---|
| Errors on la utility apunta **només a l'altre site** | **31,9 %** |
| Errors on apunta **als dos** sites | 43,1 % |
| Errors on **no apunta a cap** | 20,1 % |
| Errors on apunta només al site real | 4,9 % (20 rondes) |
| Errors amb confiança ≥ 0.8 | 43,1 % |
| Prediu B / B real | 46,7 % / 49,0 % · encert a les A 0.911, a les B **0.860** |
| A nuke | prediu B el 40,0 % (real 50,3 %) · encert a les B **0.689** |
| A train | prediu B el 45,0 % (real 54,2 %) · encert a les B **0.754** |
| Rondes B de nuke que falla: granades a zones que no apunten a cap site | **91 %** (a les que encerta, 71 %) |
| Descartat com a causa | les etiquetes d'intenció (milloren nuke i train) i el nivell de les granades a nuke |
| Encert per equip no vist (16 equips amb ≥ 40 plants) | de 0.828 a 0.938 |

**Lectura per a la memòria.** Les explicacions no mostren cap biaix que no toqui: el model es fixa
en on cau la utility, i la cap de site no veu l'equip. Els errors venen sobretot de rondes on la
utility no diu el site real: en una de cada tres apunta a l'altre site (un fake, o un canvi de
site després de la utility), i en una de cada cinc no apunta a cap. Sí que hi ha una **inclinació
cap a A**, concentrada a nuke i train. A nuke és el mateix problema: moltes rondes B no tenen
utility a B, i quan la utility no diu res el model tria A, que és el que passa més sovint en
aquestes rondes (61 %).

---

## 1. Mètode

**Error** = el site predit (P(B) > 0.5) no és el site on es va plantar.

**A quin site apunta un callout**: el φ mitjà de SHAP de les granades que hi cauen
(`RESULTATS-SHAP.md` §4). Per sobre de +0.05, B; per sota de −0.05, A; entremig, neutral. Una ronda
«apunta» a un site si té alguna granada en un callout d'aquell site.

---

## 2. La inclinació cap a A

| Mapa | rondes | B real | B predit | encert A | encert B |
|---|---|---|---|---|---|
| de_ancient | 418 | 0.529 | 0.543 | 0.868 | 0.910 |
| de_anubis | 366 | 0.546 | 0.536 | 0.886 | 0.885 |
| de_cache | 192 | 0.458 | 0.464 | 0.933 | 0.932 |
| de_dust2 | 879 | 0.466 | 0.462 | 0.921 | 0.900 |
| de_inferno | 340 | 0.562 | 0.568 | 0.893 | 0.927 |
| de_mirage | 531 | 0.371 | 0.350 | 0.946 | 0.853 |
| **de_nuke** | 435 | 0.503 | **0.400** | 0.894 | **0.689** |
| de_overpass | 162 | 0.556 | 0.525 | 0.931 | 0.889 |
| **de_train** | 262 | 0.542 | **0.450** | 0.908 | **0.754** |
| tots | 3585 | 0.490 | 0.467 | 0.911 | 0.860 |

A set dels nou mapes el model prediu B tant com n'hi ha (diferències de 0.031 o menys). Nuke i train, els dos mapes on
falla més, són els que s'inclinen cap a A.

**Amb poca utility també tira cap a A.** Sense cap granada, P(B) = 0.406 i prediu sempre A (20
rondes, la meitat B). Amb 1–3 granades prediu B el 42,5 % (real 49,4 %), i a partir d'11 la
diferència és d'uns 2 punts o menys.

| granades | rondes | encert | B real | B predit |
|---|---|---|---|---|
| 0 | 20 | 0.500 | 0.500 | 0.000 |
| 1–3 | 174 | 0.782 | 0.494 | 0.425 |
| 4–6 | 417 | 0.847 | 0.456 | 0.422 |
| 7–10 | 701 | 0.863 | 0.534 | 0.508 |
| 11–15 | 1445 | 0.912 | 0.493 | 0.472 |
| > 15 | 828 | 0.912 | 0.465 | 0.466 |

---

## 3. Per què falla

**On cau la utility de cada ronda:**

| | rondes | només al site predit | als dos | a cap | només al real |
|---|---|---|---|---|---|
| errors | 408 | **31,9 %** | 43,1 % | **20,1 %** | 4,9 % |
| encerts | 3177 | — | 95,1 % | 4,9 % | — |

- **31,9 %: la utility apunta a l'altre site.** Fakes o canvis de site després de llançar la
  utility. Amb només la utility, no es poden encertar.
- **43,1 %: apunta als dos.** El model tria un dels dos i s'equivoca.
- **20,1 %: no apunta a cap.** El model no té informació i tira cap a A (§2).
- **4,9 %: només al real.** Són els únics errors on la utility diu el site i el model no el llegeix:
  20 rondes.

**La granada que decideix un error és més primerenca i més sovint neutral.** La granada amb més pes SHAP
cap al site predit:

| | moment del llançament (mediana) | en un callout del site predit | en un callout neutral |
|---|---|---|---|
| errors | 47 s | 65,3 % | **33,4 %** |
| encerts | 61 s | 87,7 % | 12,2 % |

**El model sap quan dubta.** L'encert puja amb la confiança, de 0.539 (0.5–0.6) a 0.974 (≥ 0.97).
Però el 43,1 % dels errors tenen confiança ≥ 0.8, i la meitat d'aquests (50,6 %) són de
utility només a l'altre site. Amb confiança < 0.8 dominen els errors amb utility als dos sites
(44,8 %) i sense cap (30,6 %).

| Confiança | 0.5–0.6 | 0.6–0.7 | 0.7–0.8 | 0.8–0.9 | 0.9–0.97 | ≥ 0.97 |
|---|---|---|---|---|---|---|
| rondes | 178 | 214 | 348 | 714 | 1397 | 734 |
| encert | 0.539 | 0.664 | 0.776 | 0.882 | 0.948 | 0.974 |

**Els altres mètodes ho confirmen.** Anchors troba regla en el 37,3 % dels errors i en el 74,4 %
dels encerts. L'R² de LIME és més alt als errors (0.705 contra 0.516): són rondes on el model no
està saturat per una granada clara (`RESULTATS-LIME.md` §5).

---

## 4. Nuke i train

**Les rondes B, encertades i fallades:**

| | rondes | granades | alguna a un callout de B | alguna a un d'A | granades A / B / neutrals | nivell inferior |
|---|---|---|---|---|---|---|
| nuke, encertades | 151 | 10,7 | 95 % | 40 % | 5 / 22 / 71 % | 23 % |
| nuke, **fallades** | 68 | 8,6 | **21 %** | 35 % | 5 / 3 / **91 %** | **3 %** |
| train, encertades | 107 | 11,6 | 99 % | 88 % | 26 / 55 / 18 % | — |
| train, **fallades** | 35 | 9,6 | 77 % | **94 %** | **42** / 32 / 24 % | — |

- **Nuke**: les B que falla gairebé no tenen utility a B (el 3 % al nivell inferior, contra el 23 %
  a les que encerta). La utility cau a Outside i A Site, que no diuen cap site. Hi ha 112 rondes de
  nuke on tota la utility és neutral: el 39 % són B, el model els dona P(B) = 0.32 de mitjana i en
  prediu B l'11 %. Com que en aquestes rondes guanya A, tirar cap a A és el que més encerta.
- **Train**: un altre problema. Les B que falla sí que tenen utility a B, però més a A (42 % contra
  32 % de les granades). Probablement fakes o execucions dividides.

**Descartat: les etiquetes d'intenció.** La cap de site també s'entrena amb les rondes sense plant
on es pot llegir on anaven (`RESULTATS.md` §7). A nuke i train aquestes etiquetes són molt més A
que els plants:

| Mapa | B als plants | B a les etiquetes | encert amb | sense | diferència | llavors a favor |
|---|---|---|---|---|---|---|
| de_nuke | 0.50 | **0.36** | 0.782 | 0.761 | **+0.021** | 7 de 8 |
| de_train | 0.54 | **0.34** | 0.828 | 0.802 | **+0.026** | 6 de 8 |
| de_overpass | 0.56 | 0.54 | 0.927 | 0.870 | +0.058 | 8 de 8 |
| de_anubis | 0.55 | 0.50 | 0.890 | 0.891 | −0.002 | 2 de 8 |

(La resta de mapes, entre +0.002 i +0.012.) Però treure-les fa **pitjor** nuke i train, no millor.
Si empenyen cap a A, el que aporten pesa més.

**Descartat: el nivell de les granades a nuke.** B és just a sota d'A, i en 2D una granada a B que
es llegís com si fos a dalt cauria a A Site. No passa: cap granada de nuke es queda sense nivell, i
l'altura de les granades dels T que cauen sobre A Site en 2D (1372, abans del plant) té dos pics ben
separats, el terra de B (−800 a −650: 148) i el d'A (−450 a −350: 798), amb el tall (−495) al
mig. Només 9 granades queden a menys de 50 unitats del tall.

---

## 5. Equips

La cap de site no rep l'equip, així que no pot tenir-ne un biaix. Tot i així, l'encert per equip
no vist va de **0.828 a 0.938** (16 equips amb ≥ 40 plants, mediana 0.895): hi ha equips més
difícils de llegir, probablement els que fan més fakes.

---

## 6. Limitacions

- **«A quin site apunta un callout» surt del mateix SHAP** que s'analitza, i el llindar de ±0.05 és
  una tria. Serveix per classificar errors, no per demostrar res del model.
- **Fake o canvi de site no es distingeixen**: caldria el moviment dels jugadors.
- **Una sola llavor**, com SHAP i Anchors. La comparació amb i sense intenció sí que és de 8
  llavors.

---

## 7. Com reproduir-ho

Necessita els JSON de SHAP, Anchors (τ 0.9) i LIME, i la base de dades per al nivell de nuke.

```bash
# al contenidor del backend, amb errors_report.py i shap_report.py copiats a /app
python errors_report.py     # segons
```
