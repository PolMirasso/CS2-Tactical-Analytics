# Seguiment de CS2 Tactical Analytics

## El projecte

El nucli és un model que prediu a quin bombsite executarà un equip a partir de la utility que
dibuixes al radar. Tot el que hi ha al voltant existeix per alimentar-lo o per poder-lo llegir: la
descàrrega de demos d'HLTV i el parseig, que són els que produeixen les dades; els analytics per
equip i mapa i el visor 2D de la partida, que és on es comprova el que diu el model; i la fitxa de
jugador d'HLTV.

| Capa | Què faig servir | Nota |
|---|---|---|
| Backend | FastAPI + SQLModel, Python 3.12 | Postgres en dev i prod |
| Parseig | awpy 2.0.2 | del `.dem` en surten rondes, kills, utility i el replay |
| Model | DeepSets escrit a mà en NumPy | sense PyTorch ni scikit-learn |
| Frontend | React + TypeScript + Vite + Tailwind | TanStack Query, React Router, traduccions en/es |

Una demo entra baixada d'HLTV o pujada a mà, el parser d'awpy la converteix en rondes, kills, utility
i estadístiques que van a la base de dades, i en guarda a disc una versió comprimida per al visor. El
model no llegeix mai el `.dem`: es construeix a partir del que ja hi ha a la base de dades.

---

## Com ha anat la feina

### Abans del model

Vaig muntar l'esquelet sencer abans de tocar res d'aprenentatge automàtic, i crec que va ser
encertat: quan vaig arribar al model ja tenia dades reals amb què provar-lo. Backend amb FastAPI,
descàrrega i parseig de demos d'HLTV, frontend en React, visor 2D sobre el radar del mapa i editor de
zones. D'aquí en surt el que després necessita el model: la posició de cada granada projectada sobre
el radar, el temps de ronda i el site on es va plantar.

### El primer model, i per què no servia

Vaig començar amb un MLP de scikit-learn. Funcionava en el sentit que donava un número, però no en el
sentit que servís de res.

El canvi de plantejament va venir amb la idea de que mani el requadre: que el model deixés de veure
només la regió (A, B o mig mapa) i passés a veure la posició exacta de cada granada. Això em va
obligar a canviar d'arquitectura, perquè l'entrada ja no és un vector de mida fixa sinó un conjunt de
granades de mida variable, i d'aquí van sortir els DeepSets.

El que em va costar aquí no va ser l'algorisme sinó dos bugs de dades que feien impossible que allò
funcionés. El primer: awpy reportava malament el bombsite i em donava `bombsite_b` també per als
plants d'A, així que a la base de dades hi havia zero rondes d'A i el model entrenava amb dues
classes. El segon: la posició de la utility estava a NULL, perquè les columnes les havia afegit
després d'haver parsejat les demos, o sigui que el model era cec justament a la feature que acabava
d'afegir. Cap dels dos donava error.

Amb tot arreglat, l'encert era d'un 0.53, que és exactament el prior de "no es planta". Calia
entendre per què.

### El model que sí funciona

Aquest és el bloc amb més contingut per a la memòria, perquè és on el model deixa de ser decoratiu.

El punt de partida del diagnòstic va ser que treure la posició de l'entrada no canviava l'accuracy:
no s'estava fent servir. Buscant per què, vaig trobar dues causes encadenades. La primera és que la
xarxa era cega al mapa: el token no deia de quin mapa era, així que el mateix píxel significava el
mateix a tot arreu, quan en realitat la relació entre posició i site apunta en direccions diferents
segons el mapa. Amb una xarxa compartida, aquests gradients s'anul·len entre ells. La segona és que
el context de ronda ofegava la posició: afegint-lo a la decisió d'A contra B, l'encert baixava.
L'equip és una drecera, i el model memoritzava la seva taxa base en comptes de mirar on cau la
utility.

La solució va ser partir el model en dues etapes: un *gate* que decideix si es planta o no i que sí
mira el context, i una *site head* que decideix A o B i que només veu les posicions. L'encert d'A
contra B va passar de 0.581 a 0.756.

### Afinar-lo

Amb l'arquitectura ja resolta, la resta de feina sobre el model va anar per aquí:

- **Alçada al token.** A nuke, A i B cauen gairebé al mateix punt del radar 2D, així que sense
  l'altura de la detonació són el mateix punt per al model.
- **Pooling configurable** (mitjana, suma o atenció), amb comprovació de gradient per diferències
  finites, ja que el backprop està escrit a mà. Guanya l'atenció.
- **Calibració de la confiança**, perquè amb poques dades el softmax és massa confiat. Amb una guarda:
  si la calibració no millora l'error, es reverteix.
- **Inferència per mostreig.** L'usuari dibuixa una àrea i una finestra de temps, no un punt i un
  instant, així que el model marginalitza sobre 24 mostres dins d'aquell requadre. Caixa gran,
  predicció més repartida.
- **Identitat d'equip per id d'HLTV** en comptes del nom del clan, que arribava en variants (`Spirit`,
  `Team Spirit`…) i inflava el one-hot sense motiu. Això em va destapar que la funció que llegia els
  equips d'una pàgina d'HLTV casava el tros de markup equivocat, i l'id del rival estava buit a totes
  les demos.
- **Una tercera cabeça per al timing** de l'execució (rush, default o late), condicional al fet que es
  planti: respon a "si executen, quan", no a "executaran".
- **Més context de ronda**: economia pròpia i del rival, quines armes hi ha a cada bàndol i la fase
  del partit. Tot això només ho veu el *gate*, no la *site head*.

L'últim punt em va portar un problema que val la pena explicar: amb els partits que tinc, gairebé
qualsevol combinació de filtres deixa una rodanxa diminuta de dades, i el model no dona cap error
quan prediu sobre una combinació que no ha vist mai. Et respon igualment i amb la mateixa cara de
seguretat. Per això vaig afegir un avís que compta les rondes que sostenen la selecció i, quan són
poques, diu quin filtre és el que més retalla.

### Mètriques honestes

El que més em servirà per a la memòria d'aquesta part és el holdout del 80/20 explícit: totes les
mètriques que ensenyo es mesuren sobre un 20 % que el model no ha vist mai, i sempre comparades amb
un baseline, que és el site més freqüent d'aquell equip en aquell mapa. Sense això els números no
volen dir res. També reporto l'encert desglossat per mapa, que és el que permetrà veure si generalitza
o si només sap de dust2.

### La resta de l'eina

La feina que no és el model, per ordre del que em va costar més:

- **Overlay de dany de la C4** al visor 2D. Valve no publica les dades de simulació de cada mapa i no
  serveix cap fórmula de radi simple, perquè l'ona rodeja les cantonades però no travessa les parets.
  Ho vaig reconstruir per enginyeria inversa d'una eina web pública, amb la procedència documentada a
  `backend/app/assets/bomb/SOURCE.md`. Va ser aquí on vaig descobrir el bug del tickrate.
- **Presets d'utility**: patrons d'execute minats de les rondes ja parsejades, per no haver de
  dibuixar-los a mà cada vegada. Es validen sense el model, mirant quin percentatge de les rondes amb
  una firma semblant va acabar en aquell site.
- **Analytics i avís de canvis de plantilla**, distribució de sites i heatmaps per equip i mapa.
- **`/players`**, la fitxa de jugador amb les estadístiques d'HLTV.
- **Migració de l'estilat a Tailwind**, que el tenia partit entre unes poques classes d'un CSS escrit
  a mà i més de dues-centes crides amb estils en línia.

---

## Per què he fet les coses així

Les decisions del model, que són les que hauré de justificar, amb l'alternativa que vaig descartar.

| Decisió | Alternativa | Per què |
|---|---|---|
| DeepSets escrit a mà en NumPy | PyTorch | Instal·lar torch arrossega un stack de CUDA de diversos GB. Les meves dades són centenars de rondes i això entrena en CPU en menys de 6 segons. El preu és haver d'escriure el backprop a mà, i per això té comprovació de gradient per diferències finites |
| DeepSets | Un MLP amb vector fix | L'entrada és un conjunt de granades de mida variable, i l'ordre en què les dibuixo no ha de canviar la predicció |
| Dues etapes | Una sola cabeça sobre A/B/no-planta | El context ofegava la posició; el model memoritzava la taxa base de cada equip |
| Que la site head no vegi el context | Passar-li el context sencer | Afegir-l'hi baixa l'encert d'A contra B de 0.776 a ~0.58 |
| Posar el mapa a cada token | Posar-lo només al context de ronda | Sense això la xarxa és compartida entre mapes i els gradients s'anul·len |
| Alçada al token | Ignorar-la | A nuke, A i B cauen gairebé al mateix punt del radar 2D. Mesurant-ho després, aporta poc |
| Pooling per atenció | Mitjana o suma | Mesurat: 0.902 contra 0.829 |
| Calibració de la confiança | Deixar el softmax cru | Amb poques dades és massa confiat, i la guarda evita que empitjori |
| Holdout 80/20 explícit | Reportar sobre les dades d'entrenament | Una mètrica sobre dades vistes no diu res |
| Inferència per mostreig | Un punt i un instant exactes | L'usuari dibuixa una àrea i un rang, no un píxel. Marginalitzar hi posa la incertesa |
| Identitat d'equip per id d'HLTV | Pel nom del clan | Dedupica les variants del mateix equip i redueix el one-hot |
| Que el període no acoti el model | Reentrenar per finestra | Seria un model per període; queda fora d'abast. El selector només mou el baseline |

De la resta hi ha quatre decisions que val la pena tenir apuntades: els mapes són data-driven (afegir-ne
un és deixar-hi tres fitxers, sense tocar codi), les zones d'un mapa es poden generar de les mateixes
demos en comptes de dibuixar-les a mà, els presets es minen fora de línia perquè no canvien entre
peticions, i la fase del partit surt del número de ronda per no haver d'afegir una columna ni tornar a
parsejar.

---

## Coses que se'm van trencar

Primer les que van afectar el model. Val la pena fixar-se en quantes no donaven cap error: només
resultats equivocats, que són les cares de trobar.

| Problema | Com es manifestava | Causa | Com ho vaig arreglar |
|---|---|---|---|
| awpy reporta malament el bombsite | Zero rondes d'A a la BD i el model no predeia mai A, sense cap error | Bug d'awpy: dona `bombsite_b` també per als plants d'A | Deduir el site de l'esdeveniment del plant, amb reserva per posició |
| Posició de la utility a NULL | El model era cec a la posició tot i tenir-la com a feature, i no ho deia | Vaig afegir les columnes després d'haver parsejat | Re-parseig, i reserva per zona per a les files antigues |
| Tickrate 128 contra 64 | El replay corria al doble i el temps de ronda, que és una feature, estava a la meitat | awpy assumeix 128 per defecte i CS2 va a 64 | Passar-li el tickrate explícit. Obliga a tornar a parsejar |
| L'id del rival, buit a totes les demos | El filtre per rival no trobava res | La regex casava el tros de markup equivocat de la pàgina | Regex corregida i un backfill que reconsulta els partits sense tornar a parsejar |
| Canviar la mida del token invalida el model | `/scouting` serveix el baseline però la targeta segueix ensenyant les mètriques velles, sense avisar | La guarda de càrrega rebutja el model i no ho crida | Documentat. Em passa ara mateix |
| Les demos sense data cauen de qualsevol filtre de període | Desapareixen de les tendències sense avisar | A SQL, comparar un NULL amb una data sempre és fals | Documentat; amb el filtre desactivat tornen |

La resta van ser d'infraestructura i les llisto només perquè hi siguin: la ronda del descans venia
inflada amb un minut de frames congelats perquè awpy etiqueta els ticks fins al final oficial; el
radar de cache va arribar sense canal alpha i tenyia el llenç sencer; la configuració compilada de
Vite guanyava a la font i editar-la no tenia cap efecte; l'esborrat de demos no netejava totes les
taules; re-parsejar-ho tot esborrava l'equip de les pujades manuals; els arxius d'1 GB no es
netejaven quan la descàrrega fallava; i la font del dany de la bomba té A i B intercanviats en dos
mapes.

