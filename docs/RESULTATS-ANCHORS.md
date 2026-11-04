# Explicabilitat: Anchors sobre DeepSets

> Anchors (Ribeiro et al., 2018) explica cada predicció amb una **regla**: el mínim de condicions
> que, si es compleixen, fan que el model digui gairebé sempre el mateix site. És l'altre tipus
> d'explicació respecte de SHAP (`RESULTATS-SHAP.md`): SHAP reparteix la predicció entre les
> granades, Anchors diu quina condició n'hi ha prou que es compleixi.
>
> Només la cap de site (A contra B), 3585 rondes amb plant. **Cada ronda l'explica el model del
> fold que no ha vist el seu equip**: els mateixos 5 models de SHAP (llavor 0, encert 0.8862).
> Un càlcul d'1 min per llindar, 2026-11-04.
>
> Codi: `app/ml/anchors.py`, `scripts/anchors_report.py`, `tests/test_anchors.py`. JSON crus a
> `data_store/anchors/` (`rounds_t<τ>.json` amb la regla de cada ronda, `summary_t<τ>.json`).

---

## 0. La resposta curta

| | τ = 0.95 | **τ = 0.9** |
|---|---|---|
| Rondes amb regla | 25,6 % | **70,2 %** |
| Condicions per regla (mitjana) | 1,6 | **1,4** |
| Cobertura a la meitat d'avaluació | 15,2 % | 18,9 % |
| Precisió a la meitat d'avaluació | 0.980 | 0.947 |
| Rondes amb regla on aquesta precisió arriba a τ | 88,0 % | 87,1 % |
| La regla coincideix amb el site real | 0.956 | 0.911 |
| Encert del model a les rondes **amb** regla | 0.962 | **0.940** |
| Encert del model a les rondes **sense** regla | 0.860 | **0.761** |
| La regla inclou el callout de la granada amb més pes SHAP | 42,8 % | 49,8 % |

**Lectura per a la memòria.** En dues de cada tres rondes n'hi ha prou amb una o dues
condicions: «SI utility a B Doors → B» explica 240 rondes de dust2 amb una precisió de 0.978.
Les regles són les que diria un jugador. I separen les rondes clares de les ambigües: on hi ha
regla, el model encerta el 94 %; on no n'hi ha, el 76 %. Això SHAP no ho donava.

---

## 1. Mètode

**Condicions.** De cada granada de la ronda en surten dues: «<tipus> a <callout>» i «utility a
<callout>» (qualsevol tipus). El callout té en compte el nivell a nuke. Una regla és una
conjunció de condicions, totes certes a la ronda que s'explica.

**Precisió i cobertura sobre rondes reals del mateix mapa.**

- precisió = de les rondes amb plant del mapa que compleixen la regla, en quantes el model (el
  del fold de la ronda explicada) prediu el mateix site que a la ronda explicada;
- cobertura = quina part de les rondes amb plant del mapa compleix la regla.

L'article genera les mostres pertorbant la instància (text, imatges) o barrejant-la amb files
d'entrenament (taules). Aquí totes les mostres són rondes jugades de veritat, i no s'avalua el
model amb rondes que no existeixen, que era la limitació principal de SHAP (§7 de
`RESULTATS-SHAP.md`). Com que les rondes són finites, la precisió es calcula sencera i no cal el
bandit (KL-LUCB) de l'article.

**Cerca.** Com a l'article, cerca en feix per mida (feix de 10, fins a 5 condicions), però el feix
es tria per la cota inferior de la precisió en lloc del bandit. A cada mida, les regles amb **cota
inferior de Wilson ≥ τ** (confiança del 90 %, el δ = 0.1 de l'article) són vàlides, i es tria la
de més cobertura. Si a cap mida n'hi ha cap de vàlida, la ronda queda sense regla.

**Sense trampa.** Les rondes amb plant de cada mapa es parteixen per la meitat a l'atzar (llavor 0):
la regla es busca amb una meitat, i la precisió i la cobertura que es donen són les de **l'altra**,
sense comptar-hi la ronda explicada.

**La llibreria (alibi) no serveix** pel mateix motiu que la de SHAP: espera un nombre fix de
variables per instància, i cada ronda té un nombre diferent de granades.

---

## 2. Per què τ = 0.9

L'article fa servir τ = 0.95. Amb rondes reals, la precisió es mesura sobre les que hi ha: per
superar 0.95 amb confiança, una regla necessita unes 32 rondes sense cap error a la meitat de
cerca (les regles trobades en tenen 39 de mediana). Només dust2 i mirage, els mapes amb més plants
i regles més netes, en tenen per a una part important de les rondes:

| Mapa | plants | amb regla, τ = 0.95 | amb regla, τ = 0.9 |
|---|---|---|---|
| de_dust2 | 879 | 63 % | 88 % |
| de_mirage | 531 | 44 % | 80 % |
| de_cache | 192 | 23 % | 64 % |
| de_anubis | 366 | 13 % | 76 % |
| de_inferno | 340 | 10 % | 52 % |
| de_ancient | 418 | 2 % | 72 % |
| de_nuke | 435 | 0 % | 40 % |
| de_overpass | 162 | 0 % | 73 % |
| de_train | 262 | 0 % | 55 % |

Amb τ = 0.9 la precisió a la meitat d'avaluació és 0.947, per sobre del llindar, i hi arriba el
87 % de les rondes amb regla, igual que amb τ = 0.95 (88 %). La resta del document és amb τ = 0.9.

---

## 3. Per mapa

| Mapa | plants | amb regla | condicions | cobertura | precisió | site real |
|---|---|---|---|---|---|---|
| de_dust2 | 879 | **88 %** | 1,15 | 18,9 % | 0.964 | 0.938 |
| de_mirage | 531 | 80 % | 1,19 | 19,9 % | 0.961 | 0.951 |
| de_anubis | 366 | 76 % | 1,66 | 15,7 % | 0.918 | 0.859 |
| de_overpass | 162 | 73 % | 1,67 | 30,7 % | 0.936 | 0.909 |
| de_ancient | 418 | 72 % | 1,60 | 14,9 % | 0.965 | 0.923 |
| de_cache | 192 | 64 % | 1,30 | 38,0 % | **0.900** | 0.858 |
| de_train | 262 | 55 % | **2,04** | 16,9 % | **0.901** | **0.824** |
| de_inferno | 340 | 52 % | 1,59 | 15,1 % | 0.956 | 0.922 |
| de_nuke | 435 | **40 %** | 1,40 | 12,3 % | 0.928 | 0.853 |

**Nuke i train**, els dos mapes on el model falla més (0.791 i 0.824), també hi surten malament:
nuke és el que té menys rondes amb regla, i train té les regles més llargues i les que menys
coincideixen amb el site real. A nuke encaixa amb SHAP: el 61 % de les granades cauen a A Site i
Outside, que no apunten a cap site. Surten en 52 de les 176 regles de nuke, però mai soles: sempre
cal una altra condició que digui el site.

---

## 4. Les regles més usades

Les 3 regles que expliquen més rondes de cada mapa. Rondes = quantes rondes explica. La cobertura,
la precisió i el site real són a la meitat d'avaluació, de mitjana entre les rondes que explica (que
poden ser de folds diferents, i per tant de models diferents).

| Mapa | Regla | Rondes | Cobertura | Precisió | Site real |
|---|---|---|---|---|---|
| de_dust2 | SI utility a B Doors → B | 240 | 25,6 % | 0.978 | 0.965 |
| | SI utility a Elevator → A | 109 | 26,5 % | 0.964 | 0.914 |
| | SI utility a A Ramp → A | 88 | 14,9 % | 0.989 | 0.970 |
| de_mirage | SI utility a CT → A | 146 | 26,1 % | 0.986 | 0.986 |
| | SI utility a Balcony → A | 62 | 28,0 % | 0.958 | 0.947 |
| | SI smoke a Market → B | 60 | 13,4 % | 0.949 | 0.916 |
| de_ancient | SI utility a Back Halls I utility a Square → B | 57 | 15,6 % | 0.953 | 0.970 |
| | SI utility a Big Box → A | 42 | 17,9 % | 0.973 | 0.895 |
| | SI utility a A Site → A | 29 | 14,6 % | 1.000 | 0.967 |
| de_anubis | SI flash a Plateau → A | 61 | 18,9 % | 0.986 | 0.857 |
| | SI utility a Palace I utility a Street → B | 35 | 14,6 % | 0.962 | 0.962 |
| | SI utility a Back Site → B | 29 | 18,3 % | 0.845 | 0.821 |
| de_cache | SI utility a Hell → B | 83 | 49,4 % | 0.947 | 0.874 |
| | SI utility a Squeaky I flash a A Site → A | 22 | 11,0 % | 0.872 | 0.905 |
| | SI utility a A Main I smoke a Squeaky → A | 14 | 16,1 % | **0.645** | 0.677 |
| de_inferno | SI utility a Coffins → B | 19 | 19,6 % | 0.940 | 0.821 |
| | SI smoke a Garden → B | 18 | 16,8 % | 1.000 | 0.967 |
| | SI utility a Garden → B | 18 | 23,8 % | 1.000 | 0.975 |
| de_nuke | SI molotov a Heaven → A | 50 | 17,6 % | 0.942 | 0.898 |
| | SI utility a B Site → B | 38 | 15,8 % | 0.978 | 0.915 |
| | SI molotov a Bottom Ramp → B | 18 | 6,2 % | 0.918 | 0.787 |
| de_overpass | SI utility a Sniper's Nest I flash a B Site → B | 31 | 21,7 % | 0.943 | 0.888 |
| | SI utility a Connector I smoke a Back of A → A | 27 | 29,1 % | 0.915 | 0.915 |
| | SI utility a Back of A → A | 23 | 38,8 % | 0.936 | 0.907 |
| de_train | SI utility a Bomb Train (B) → B | 43 | 17,1 % | 0.990 | 0.913 |
| | SI molotov a Sidewalk I smoke a B Halls → B | 11 | 11,1 % | **0.794** | **0.662** |
| | SI utility a Bomb Train (A) I utility a Camera → A | 11 | 24,8 % | 0.846 | 0.846 |

- **Dues de cada tres regles tenen una sola condició** (1694 de 2515). El tipus de granada hi surt
  poc: només el 31 % de les condicions diuen el tipus («smoke a…») i la resta són «utility a…».
  El model llegeix on cau la utility, com ja deia SHAP (§3 de `RESULTATS-SHAP.md`).
- A nuke, la regla de B és del nivell inferior (B Site, Bottom Ramp): és el que va sortir a SHAP
  un cop corregit el nivell.
- **No totes aguanten a l'altra meitat.** Una de cache baixa a 0.645 i una de train a 0.794. Totes
  dues tenien 15 de 15 a la meitat de cerca (la mediana és 39 rondes), just per passar la cota
  amb τ = 0.9. Passa al 2,4 % de les rondes amb regla (precisió < 0.8 a l'avaluació).

---

## 5. Rondes amb regla i sense

| | rondes | granades per ronda | encert del model |
|---|---|---|---|
| amb regla | 2515 (70,2 %) | 12,8 | **0.940** |
| sense regla | 1070 (29,8 %) | 9,3 | **0.761** |

Les rondes on cap condició simple no basta per decidir tenen menys utility, i és on el model falla
més. Anchors serveix per saber **quan fiar-se de la predicció**: si la ronda té una regla, l'encert
és del 94 %.

---

## 6. Anchors i SHAP

En el 49,8 % de les rondes la regla inclou el callout de la granada amb més pes SHAP. No diuen el
mateix, i no ho han de dir:

| | SHAP | Anchors |
|---|---|---|
| Pregunta | quant ha mogut cada granada aquesta predicció | quina condició basta per a aquesta predicció |
| Resultat | un número per granada | una regla d'1 a 4 condicions (1,4 de mitjana) |
| Com es valida | treient granades de la mateixa ronda | sobre altres rondes reals del mapa |
| Rondes que explica | totes | el 70 % |
| Què hi afegeix | el pes del moment (l'execute pesa ×3,4) | quan fiar-se del model (94 % contra 76 %) |

SHAP marca la granada que més ha pesat en aquesta ronda, que sol ser tardana (mediana 60 s, contra
27 s de totes les granades). Anchors busca la màxima cobertura, i per això tria la condició més
comuna que basta.

---

## 7. Limitacions

- **Les rondes reals són poques.** Fan que τ = 0.95 deixi gairebé sense regles tots els mapes menys
  dust2 i mirage (§2), i
  que algunes regles amb poques rondes no aguantin a l'altra meitat (§4).
- **Les condicions són presència a un callout**: no diuen res del moment del llançament, que SHAP
  troba important. Afegir-hi «després dels 45 s» multiplicaria les condicions i reduiria encara
  més les rondes de cada regla.
- **Les zones són les de `/maps/edit`**: una regla com «utility a CT» a mirage depèn de com està
  dibuixada aquella zona.
- **Una sola llavor i només la cap de site**, com a SHAP.

---

## 8. Com reproduir-ho

Fa servir els models de `data_store/shap/models/`, que surten de `shap_report.py --stage explain`.

```bash
# al contenidor del backend, amb anchors_report.py i shap_report.py copiats a /app
python anchors_report.py --tau 0.9    # i --tau 0.95 per a la comparació (1 min cadascun)
python anchors_report.py --tau 0.9 --report    # torna a imprimir les taules del JSON
```

Tests:

```bash
cd backend && PYTHONPATH=. ./.venv/bin/python -m pytest tests/test_anchors.py -q
```
