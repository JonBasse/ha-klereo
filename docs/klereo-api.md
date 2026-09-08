# Klereo Connect — documentation API

> **Provenance.** Ce document est la documentation que Klereo a envoyée à **@nopbop**, qui l'a
> relayée le **2026-08-24** dans [GitHub #58](https://github.com/JonBasse/ha-klereo/issues/58).
> C'est la **seule source officielle** dont ce projet dispose. Tout le reste de ce qu'il sait de
> l'API vient du [plugin Jeedom de MrWaloo](https://github.com/MrWaloo/jeedom-klereo), c'est-à-dire
> d'une réimplémentation, ou de suppositions — dont deux au moins se sont révélées fausses (#58,
> #94).
>
> Il est committé ici parce qu'un commentaire de tracker n'est pas un support durable, et qu'aucune
> autre copie n'existe.
>
> **⚠️ Ce fichier n'a plus une seule provenance.** Depuis le relevé du **2026-09-03** (#147) il
> porte aussi ce que le **plugin Jeedom amont** et **notre propre `api.py`** savent de l'API, dans
> les sections marquées. Chaque affirmation nomme sa source, parce qu'elles n'ont pas le même
> poids : voir § *Surface complète*.
>
> 🔴 **Et depuis les 2026-09-05 / 2026-09-06, il porte une quatrième classe de source : le RELEVÉ
> RÉSEAU du client web officiel.** @StephanH27 et @nopbop ont capturé, dans l'onglet Réseau de
> leur navigateur, ce que les interfaces v1 et v3 envoient réellement — sur **deux installations**
> ([GitHub #55](https://github.com/JonBasse/ha-klereo/issues/55),
> [#61](https://github.com/JonBasse/ha-klereo/issues/61)). C'est la source **la plus lourde des
> quatre**, et la seule qui ne soit ni une documentation, ni une réimplémentation, ni une
> supposition : c'est l'API observée. Les faits qui en viennent sont marqués **mesuré sur le fil**,
> avec la portée de la mesure — deux installations ne sont pas toutes les installations.

## Comment lire ce fichier — trois réserves qui portent

1. **🔴 Les listes de champs de `GetIndex` et `GetPoolsDetails` sont ÉLIDÉES dans la source**, par
   des `...` que @nopbop a recopiés tels quels. Ni `params`, ni `RegulModes`, ni `ExtraParams`,
   ni `alerts` n'y apparaissent — **et cela ne prouve pas leur absence.** La question du conteneur
   de consignes (#94) reste donc **ouverte** : ce document ne la tranche pas, dans un sens ni dans
   l'autre. C'est la réserve la plus importante de ce fichier, parce que c'est précisément la
   question qu'on espérait voir résolue en le recevant.
2. **Les liens de la source sont abîmés.** Le collage porte des liens Markdown dont le texte et la
   cible divergent (texte `GetJWT.php` → cible `GetToken.php`, texte `SetOut.php` → cible
   `GetInfos.php`, …). **Le texte est l'URL réelle** ; les cibles sont un artefact du collage et
   ont été écartées. Les URL ci-dessous sont donc les textes.
3. **Le document est partiel** — mais la lacune que cette réserve signalait est **comblée**.
   La phrase sur le rafraîchissement toutes les 10 minutes ne figurait pas dans le collage
   d'origine ; @nopbop l'a fournie mot pour mot le **2026-08-28**, et elle a sa section
   ci-dessous. Elle a fait passer `SCAN_INTERVAL_MINUTES` de 5 à 10 (#139).

Une divergence entre ce document et l'API vivante reste possible et ordinaire. Une affirmation
tirée d'ici est mieux sourcée qu'une supposition — elle n'est pas une mesure.

---

## 🔴 Cadence de sondage — Klereo menace de bannir

Fourni verbatim par **@nopbop** le **2026-08-28** dans
[GitHub #58](https://github.com/JonBasse/ha-klereo/issues/58) ; absent du collage du 2026-08-24.

> *« Les données ne sont mises à jour que toutes les 10mn sur nos serveurs, il est donc inutile de
> faire un polling plus fréquent, vous risqueriez de vous faire bannir du serveur ! »*

Deux conséquences, et la seconde est celle qu'on oublie :

* **Sonder plus vite n'achète rien.** Au-dessus d'un appel par 10 minutes, le serveur rend la même
  charge utile. Il n'y a pas d'arbitrage fraîcheur / risque à faire ici.
* **Le bannissement tomberait sur le compte Klereo de l'UTILISATEUR**, lui coûtant l'intégration
  *et* son accès normal au service, pour une intégration qu'il a seulement installée.

D'où `SCAN_INTERVAL_MINUTES = SCAN_INTERVAL_MIN_MINUTES = 10`, le plancher étant appliqué à la
**lecture** dans `coordinator.py` et pas seulement dans le formulaire d'options — `scan_interval`
est une option *persistée*. Voir #139.

⚠️ **Ce que la source ne dit pas** : ni le seuil, ni la fenêtre, ni si quelqu'un a été banni. Ce
qui est établi, c'est que sonder plus vite est **inutile** et que Klereo **prévient**. C'est assez
pour corriger le défaut, et insuffisant pour affirmer que 5 minutes bannissait.

---

## Surface complète — les trois sources croisées

Relevé le **2026-09-03** (#147). Jusque-là ce fichier décrivait **une** source ; personne n'avait
croisé les trois, et le croisement change la carte : **chaque source ignore au moins un endpoint
que les deux autres connaissent.**

| Endpoint | Charge utile | Doc off. | Amont Jeedom | `api.py` |
|---|---|:--:|:--:|:--:|
| `GetJWT.php` | `login`, `password` (SHA-1) | ✅ | ✅ | ✅ |
| `GetIndex.php` | — (GET, bearer) | ✅ | ✅ | ✅ |
| `GetPoolDetails.php` | `poolID` | ✅ | ✅ | ✅ |
| `SetOut.php` | `poolID`, `outIdx`, `newMode`, `newState`, `comMode` | ✅ | ✅ | ✅ |
| `SetParam.php` | `poolID`, `paramID`, `newValue`, `comMode` | 🔴 **absent** | ✅ | ✅ |
| `SetAutoOff.php` | `poolID`, `outIdx`, `offDelay`, `comMode` | 🔴 **absent** | ✅ | ✅ (#162) |
| `CommandStatus.php` | `cmdID` | ✅ | ❌ | ✅ |
| `WaitCommand.php` | `cmdID` | ✅ | ✅ | ❌ écarté (#140) |

**Les trois sources et ce que chacune vaut.** La doc officielle est la seule *officielle*, et elle
est **élidée** — une absence n'y prouve rien (réserve 1). L'amont est une **réimplémentation**,
donc un témoignage sur l'API et pas l'API — mais c'est du code qui tourne chez des utilisateurs,
donc ce qu'il appelle **existe**. `api.py` est ce qu'on expédie.

⚠️ **Deux endpoints fantômes.** `GetToken.php` et `GetInfos.php` apparaissent dans la source
officielle et **n'existent pas** : ce sont des cibles de liens Markdown abîmées par le collage,
déjà écartées par la réserve 2. Les compter ferait une surface de dix endpoints au lieu de huit.

🔴 **`SetParam.php` est absent de la doc officielle et on l'expédie depuis #128.** Il n'est donc
adossé qu'à l'amont. Ce n'est pas une raison de le retirer — il fonctionne chez de vrais
utilisateurs — mais toute affirmation sur sa forme repose sur une seule source.

### ✅ La surface est complète — résultat NÉGATIF, mesuré sur le fil

**Le client web officiel n'appelle aucun endpoint hors des huit ci-dessus.** Mesuré le
**2026-09-05** par @StephanH27 ([GitHub #61](https://github.com/JonBasse/ha-klereo/issues/61)) :
le bouton de **rafraîchissement** des interfaces **v1 et v3** n'émet qu'une requête,
`POST GetPoolDetails.php` — celle que l'intégration appelle déjà. La v3 ajoute onze PNG en cache
et rien d'autre. Les captures de démarrage et d'arrêt de la PAC, du 2026-09-05 et du 2026-09-06,
ne montrent elles non plus que `SetParam`, `SetOut`, `WaitCommand` et `GetPoolDetails`.

**Ce résultat est écrit ici parce qu'un résultat négatif ne laisse aucune trace ailleurs.** Le
tableau ci-dessus croise trois sources qui sont toutes des *lectures* — de documentation ou de
code. Celle-ci est la première mesure **sur le fil**, et elle les corrobore. Sans cette ligne, la
question « existe-t-il un endpoint de synchronisation que nous ignorons ? » se rouvrira, et on la
reposera à un utilisateur qui y a déjà répondu.

⚠️ **Portée.** Deux interfaces, quelques gestes, deux installations. Cela ne prouve pas qu'aucun
neuvième endpoint n'existe — cela prouve que **les gestes observés n'en appellent aucun**, ce qui
est ce dont on avait besoin pour arrêter d'en chercher un.

---

## Authentification par JWT

**URL :** `https://connect.klereo.fr/php/GetJWT.php`

**Données POST :**

```
login=xxxxxxxxx
password=xxxxxxxxxxxxxxxxxxxxxxxxx
version=x.xx
```

- `login` — nom d'utilisateur du client
- `password` — mot de passe du client encodé en **SHA1**, ex. `SHA1('d')` =
  `3c363836cf4e16666669a25da280a1865c2d2874`
- `version` — version du client web

**Réponse JSON :**

| Champ | Sens |
|---|---|
| `status` | `'ok'` → authentification réussie · `'error'` → échouée |
| `detail` | raison du rejet, présent seulement si `status='error'` |
| `token` | clé de session valable 60 minutes — **deprecated, utiliser `jwt`** |
| `jwt` | *encrypted token* |
| `access` | droit d'accès **général du compte** (voir la table ci-dessous) |
| `id`, `histoAccess`, `cgAccepted`, `image`, `text`, `link` | « peut être ignoré » |

Le JWT doit ensuite être transmis dans l'en-tête de **toutes** les requêtes suivantes.

### Niveaux d'accès

| Niveau | Compte | Source |
|---|---|---|
| 5 | lecture seule | **doc officielle** |
| 10 | client final | **doc officielle** |
| 16 | utilisateur avancé | plugin Jeedom `klereo.class.php:467` — **absent de la doc** |
| 20 | professionnel / pisciniste | **doc officielle** |
| 25 et plus | accès Klereo | **doc officielle** |

⚠️ Deux écarts à connaître. La doc **ne mentionne pas le niveau 16** — il vient uniquement de
l'amont, qui l'affiche « Utilisateur avancé » ; l'absence dans une liste résumée n'est pas une
réfutation, mais ce niveau est moins bien sourcé que les autres. Et la doc dit **25 et plus** là où
notre `const.py` et l'amont raisonnent en `> 20` : la bande **21–24** n'est décrite par personne.

`access` apparaît à deux endroits et ce ne sont pas les mêmes : au login il vaut pour **le compte**,
et dans chaque élément de `response[]` il vaut pour **ce bassin**. C'est celui du bassin que porte
`KlereoPoolDetails.access`.

---

## Liste des bassins du compte authentifié

**URL :** `https://connect.klereo.fr/php/GetIndex.php` (réponse incluant les infos principales du
bassin)

## Détail d'un bassin

**URL :** `https://connect.klereo.fr/php/GetPoolsDetails.php`

⚠️ Le code appelle `GetPoolDetails.php`, **sans le `s`** (`api.py:15`). Le collage étant peu fiable
sur les URL (réserve 2 ci-dessus) et l'intégration fonctionnant chez de vrais utilisateurs, cet
écart est **noté et non corrigé**. À trancher par une mesure, pas par une lecture.

**Paramètres POST :**

```
poolID=xxx
lang='fr'
```

`poolID` est l'identifiant renvoyé par `GetIndex` → `response[].idSystem`.

**Réponse JSON — identique pour les deux routes dans la source :**

| Champ | Sens |
|---|---|
| `status` | `'ok'` / `'error'` |
| `detail` | raison du rejet, si `status='error'` |
| `response` | **JSON ARRAY**, chaque élément représente un bassin |

Chaque élément de `response[]` :

| Champ | Sens |
|---|---|
| `idSystem` | identification interne unique du bassin (num) |
| `poolNickname` | nom donné au bassin pour cet utilisateur (str) |
| `access` | droit d'accès **spécifique à ce bassin** |
| `podSerial` | numéro d'identification unique du POD de connexion (str) |
| `device` | index du bassin dans le POD (num) |
| `pin` | numéro PIN du boîtier de connexion (str) — **sortie seulement**, voir § *Le PIN du boîtier* |
| `probes[]` | array des capteurs du bassin |
| `EauCapteur` | `index` dans `probes[]` du capteur principal régulant la **température eau** |
| `pHCapteur` | idem pour le capteur principal régulant le **pH** |
| `TraitCapteur` | idem pour le capteur principal régulant le **désinfectant** |
| `PressionCapteur` | idem pour le capteur principal régulant la **pression** |
| `...` | **élidé dans la source** |

Chaque élément de `probes[]` :

| Champ | Sens |
|---|---|
| `index` | index interne du capteur (num) |
| `directValue` | dernière valeur mesurée (float) |
| `directTime` | temps écoulé depuis la dernière mesure, en secondes (num) |
| `filteredValue` | valeur mesurée à filtration tournante (float) |
| `filteredTime` | temps écoulé depuis la mesure `filteredValue`, en secondes (num) |
| `...` | **élidé dans la source** |

Les quatre champs `*Capteur` ne sont pas lus par l'intégration — suivi en #107.

---

## Écriture : un protocole en DEUX étapes

> Le contrôle de la sortie s'effectue en 2 étapes :
> 1. **`SetOut`** demande l'exécution de la commande (retour immédiat)
> 2. **`WaitCommand`** vérifie l'état d'exécution (**attend la fin** de l'exécution)
>    ou **`CommandStatus`** vérifie l'état d'exécution (**retour immédiat**)

C'est la confirmation officielle du défaut corrigé par #95 : un HTTP 200 sur `SetOut` signifie
« acceptée pour exécution », jamais « exécutée ».

⚠️ `WaitCommand` **bloque** et `CommandStatus` **rend la main tout de suite**. L'intégration
appelait `WaitCommand` sous un délai client de 10 s ; elle utilise **`CommandStatus` et sonde**
depuis #140, @nopbop ayant mesuré la latence réelle à **1 à 2 secondes** de `SetOut` à
`status: 9`, systématiquement (GitHub #58, 2026-08-28).

🔴 **Les deux moitiés sont inséparables.** Passer à `CommandStatus` sans boucler ferait tomber
presque chaque appel sur un statut *en vol* : toutes les écritures deviendraient « non
confirmées », en silence, et en ressemblant à un succès. Un rejet, lui, est un **verdict** et
quitte la boucle immédiatement — sans quoi une commande refusée serait dégradée en plafond épuisé,
soit exactement la panne que #95 existe pour empêcher.

⚠️ Et l'ordre compte à la lecture : @nopbop confirme que **les commandes les plus récentes
viennent en PREMIER** dans `response[]`. Lire `response[0]` rendrait le verdict d'une **autre**
commande — avec la bonne forme, le bon type et aucune erreur. L'appariement se fait sur `cmdID`.

✅ **Confirmé indépendamment le 2026-09-08** (sonde `SetAutoOff` sur Bioul, § plus bas), et la
mesure va plus loin que l'ordre : `CommandStatus` ne rend pas les commandes récentes, il rend
**tout un historique**. Un seul appel a renvoyé les deux commandes de la sonde, à trois minutes
d'intervalle, **suivies de commandes du 2026-06-03** — plus de trois mois plus tôt. L'appariement
sur `cmdID` n'est donc pas une prudence théorique : `response[]` contient en permanence des
verdicts qui ne sont pas le vôtre, et prendre `[0]` marche **par chance** tant qu'on sonde juste
après avoir écrit.

🔴 **Et les deux endpoints n'horodatent PAS de la même façon.** Sur `CommandStatus`,
`startTime` / `updateTime` sont des **chaînes formatées** — `"2026-09-08 11:30:09"` ; sur
`WaitCommand`, la capture du 2026-09-05 montre des **entiers epoch** — `1788686822`. Même nom de
champ, deux types. Un lecteur qui typerait ces clés depuis une seule des deux captures casserait
sur l'autre, et `api.py` ne les lit aujourd'hui ni l'une ni l'autre.

### Changer le mode de fonctionnement et l'état d'une sortie

**URL :** `https://connect.klereo.fr/php/SetOut.php`

**Paramètres POST :**

- `poolID` (num) — doit correspondre à l'`idSystem` rendu par `GetPool` ou `GetIndex`
- `outIdx` (num) — index de la sortie :

| Index | Sortie | | Index | Sortie |
|---|---|---|---|---|
| 0 | Éclairage | | 8 | Floculant **(Pro)** |
| 1 | Filtration | | 9 | Auxiliaire 4 |
| 2 | Correcteur pH **(Pro)** | | 10 | Auxiliaire 5 |
| 3 | Désinfectant **(Pro)** | | 11 | Auxiliaire 6 |
| 4 | Chauffage | | 12 | Auxiliaire 7 |
| 5 | Auxiliaire 1 | | 13 | Auxiliaire 8 |
| 6 | Auxiliaire 2 | | 14 | Auxiliaire 9 |
| 7 | Auxiliaire 3 | | 15 | Désinfectant hybride **(Pro)** |

- `newMode` (num) — mode de fonctionnement de la sortie
  > 🔴 **« NON VALABLE POUR LES SORTIES 2, 3, 4, 8, 15 »** (majuscules et points d'exclamation de
  > la source).

| `newMode` | Mode | Note |
|---|---|---|
| 0 | Manuel | |
| 1 | Plages horaires | |
| 2 | Minuterie | |
| 3 | Régulé | |
| 4 | Synchro filtration | |
| 5 | — | **USAGE INTERNE — ne pas utiliser** |
| 6 | Maintenance | |
| 7 | — | **USAGE INTERNE — ne pas utiliser** |
| 8 | Impulsionnel | |
| 9 | Automate | |

- `newState` (num) — état de la sortie : `0` arrêt · `1` marche · `2` automatique
- `comMode` (num) — mode de communication : **toujours 1**

**Réponse JSON :** `status` (`'ok'` / `'error'`) et `response`, **JSON ARRAY** dont chaque élément
porte `cmdID` (num) et `poolID` (num).

Sur la sortie 4, `newMode` porte le **mode KlereoTherm** (`0` Off, `1` Auto, `2` Cooling,
`3` Heating) et non le mode de sortie — c'est le défaut de #58, corrigé en 1.5.3. Les quatre autres
sorties que la doc exclut ne sont **pas** traitées : suivi en #104. La table des modes ci-dessus est
plus large que `OUTPUT_MODES` : suivi en #105.

L'amont valide les modes `{0,1,2,3,4,6,8,9}` hors sortie 4, et `{0,1,2,3}` sur la sortie 4
(`klereo.class.php:1198`) — soit exactement la table ci-dessus **moins 5 et 7**. Deux sources
écrites indépendamment qui s'accordent sur cette exclusion précise.

#### 🔴 Sur la sortie 4, `newState` est décidé par le mode CIBLE — mesuré sur le fil

La doc donne les trois valeurs de `newState` (`0` arrêt · `1` marche · `2` automatique) et ne dit
pas **laquelle va avec quel mode**. L'amont porte une règle — *tout mode autre que Manuel attend
`2`* — et le client web officiel **la contredit sur la sortie 4** :

| Cible (`newMode`) | `newState` envoyé | Mesure |
|---|:--:|---|
| Chauffe (3) | **1** | deux captures, **deux états de départ différents** |
| Auto (1) | **2** | une capture |
| Arrêt (0) | **0** | deux rapporteurs, deux installations |
| Froid (2) | **?** | 🔴 **jamais mesuré** |

Relevé les **2026-09-05** (@StephanH27, interface v1) et **2026-09-06** (@nopbop, trois captures),
[GitHub #55](https://github.com/JonBasse/ha-klereo/issues/55) · #166. Appliqué par l'intégration
depuis `state_for_heat_mode` (`api.py`), table unique partagée par `switch`, `select` et `climate`.

✅ **Confirmé sur le matériel le 2026-09-08**, pour la première fois hors du banc de test :
@nopbop, en **v1.16.0**, démarre sa PAC **depuis Home Assistant** — la pompe redémarre
physiquement, `Heating Mode` passe à `Heating`, le thermostat affiche `Heat 28 °C` et le client v1
confirme `Chauffe 28.0°C`. La ligne *Chauffe* est donc validée **de bout en bout, notre propre
commande comprise**, et non plus seulement relevée sur le fil du client officiel.
⚠️ **Une cible sur trois** : *Auto* et *Arrêt* n'ont jamais été exercées **depuis Home
Assistant** — elles ne sont mesurées que du côté client — et *Froid* reste sans porteur.

⚠️ **Et un résultat qui borne ce que ce correctif a acheté.** Le 2026-09-07, @StephanH27 démarre
sa PAC depuis Home Assistant **en v1.15.0**, c'est-à-dire *avant* cette table : les trois entités
de cette version envoyaient toutes `newMode: 3` avec `newState: 2` (`switch.py`, `select.py`,
`climate.py` de la v1.15.0 — vérifié dans l'arbre, pas relevé sur le fil). Sur son **M9**, la
paire `3` / `2` **démarre donc la pompe**. Ce qui le bloquait n'était pas le `newState`, c'était
la consigne absente.

Cela ne retire rien à la table — le client officiel envoie `1`, et `1` est désormais confirmé de
bout en bout sur la KlereoTherm de @nopbop. Mais il faut le dire dans ce sens-là : la table
**aligne l'intégration sur le client officiel**, elle n'a jamais été démontrée *nécessaire*. Deux
valeurs de `newState` sont acceptées pour la cible *Chauffe*, sur deux matériels différents.
🔴 C'est une **déduction** (son rapport + le code de la version qu'il exécutait), pas une capture
réseau : personne n'a relevé ce que sa box a reçu ce jour-là.

⚠️ **La valeur dépend de la cible, pas de l'état quitté.** C'est établi par une seule des quatre
lignes : *Chauffe* a été atteinte depuis *Auto* (pompe **en marche**) et depuis *Arrêt*, et les
deux envoient `1`. Les trois autres lignes sont **compatibles** avec une table par cible sans la
démontrer — un seul état de départ chacune.

🔴 **Ne pas inventer la case Froid par symétrie.** `1, 2, ?, 0` n'a aucun motif évident, et aucun
rapporteur des deux fils ne possède de PAC réversible. Une valeur plausible inscrite ici serait
pire que le blanc : ce fichier est la seule source durable du dépôt, et une supposition y prend
l'apparence d'une mesure.

#### `SetParam ConsigneEau` précède tout changement de mode sauf l'arrêt

Mesuré sur le fil, cinq captures, deux installations : avant chaque `SetOut` amenant la sortie 4
vers *Chauffe*, le client officiel écrit d'abord `SetParam.php` avec `paramID: "ConsigneEau"`.
**Y compris sur une pompe déjà en marche** — la capture *Auto → Chauffe* de @nopbop part d'un
widget affichant `Auto 28.0 °C` et écrit quand même `ConsigneEau: 28`, c'est-à-dire la valeur déjà
affichée. Ce n'est donc **pas** une écriture « de démarrage » : c'est une réaffirmation de la
consigne avant toute mise en régulation. Seul le passage vers *Arrêt* ne l'émet pas.

⚠️ **L'intégration n'émet pas cette première écriture.** La question que cela ouvrait — la box
accepte-t-elle une écriture de consigne pendant que la valeur lue est la sentinelle `-2000` ? —
est **tranchée depuis le 2026-09-07, et la réponse est oui.** Relevé de @StephanH27, box M9 dont
`ConsigneEau` valait `-2000`, deux preuves indépendantes :

- **les DEUX `WaitCommand`** de la paire `SetParam` + `SetOut` répondent `status: 9,
  detail: "Ok"` (cmdID `4396950` et `4396951`). L'attribution devient **inutile** : quel que soit
  celui des deux qui portait la consigne, elle a été acceptée ;
- **l'afficheur physique de la box** passe de `Arrêté` à `25.0 °C` — exactement la valeur écrite
  par le client v1 — et **y reste** après un nouvel arrêt. Ce n'est plus « le serveur a répondu
  Ok », c'est un effet observé sur le matériel.

🔴 **La sentinelle est donc une VALEUR, pas une permission**, et la garde qui refusait l'écriture
est retirée depuis v1.16.0 (#170/#171).

⚠️ **Et `-2000` n'est PAS l'état « arrêté ».** @nopbop a mesuré le 2026-09-08 que sa pompe
arrêtée porte `ConsigneEau: 28`. La sentinelle marque une consigne **jamais écrite** ; elle n'a
été observée que sur du chauffage tout-ou-rien, jamais sur une KlereoTherm. Corollaire de
méthode : sa capture 3 (*Arrêt → Chauffe*) n'était donc **pas** une écriture par-dessus la
sentinelle, contrairement au conditionnel qu'il posait le 2026-09-06. La preuve ci-dessus est
**entièrement** celle de @StephanH27 ; le second témoin n'a jamais existé.

### Lire l'état d'exécution d'une commande

**URL** *(la source précise : **session cookie requis**)* **:**
`https://connect.klereo.fr/php/WaitCommand.php` · `https://connect.klereo.fr/php/CommandStatus.php`

**Paramètre POST :** `cmdID` (num) — rendu par la commande.

⚠️ La doc ne liste **que** `cmdID` ; l'intégration envoie aussi `comMode` (`api.py:237`).

**Réponse JSON :** `status` (`'ok'` / `'error'`) et `response`, **JSON ARRAY** dont chaque élément
porte :

| Champ | Sens |
|---|---|
| `cmdID` | identifiant de la commande (num) |
| `status` | état de la commande (num, table ci-dessous) |
| `startTime` | heure de démarrage (epoch) |
| `updateTime` | heure de fin d'exécution (epoch) |
| `detail` | infos complémentaires (str) |

| `status` | Sens |
|---|---|
| 0 | commande en attente |
| 1 | commande en cours d'exécution |
| 9 | **commande terminée avec succès** |
| 10 | erreur : commande a échoué |
| 11 | erreur : mauvais paramètres |
| 12 | erreur : commande inconnue |
| 13 | erreur : droit d'accès insuffisant |
| 15 | erreur : temps d'exécution dépassé |
| 16 | erreur : abandonné |
| 17 | erreur : bassin non connecté |
| 18 | erreur : service indisponible |
| 19 | erreur : mise à jour du firmware coffret nécessaire |

Cette table est **exactement** celle que `CMD_STATUS_LABELS` (`api.py:34-48`) porte depuis 1.6.0,
codes 12/15/16/18 compris — qui venaient du plugin amont et non du rapport initial de #58. Le
commentaire qui les attribuait à « Klereo's own API documentation » était en avance sur sa preuve
au moment où il a été écrit ; il est exact depuis le 2026-08-24.

🔴 En revanche `response` est ici une **liste d'objets**, et le code lit `response` comme un
**entier nu** (`coordinator.py:159`) — les tests simulant la même forme, rien ne le signale.
C'est #106, et c'est la conséquence la plus lourde de ce document.

#### ✅ `status: 9` est un SUCCÈS — mesuré sur le fil, et une lecture ancienne à corriger

Corps de réponse d'un `WaitCommand.php` capturé par @StephanH27 le **2026-09-06**
([GitHub #55](https://github.com/JonBasse/ha-klereo/issues/55)) :

```json
status: "ok"
response: { "cmdID": 43…, "status": 9, "startTime": 1788686822, "updateTime": 1788686824, "detail": "Ok" }
```

La table ci-dessus l'annonçait ; c'est désormais **observé**, `detail: "Ok"` compris.

🔴 **La correction qui va avec.** [GitHub #59](https://github.com/JonBasse/ha-klereo/issues/59)
décrivait *« Status 9 and nothing happens »* comme le **symptôme d'une panne**. C'est faux, et
c'est précisément ce qui rendait ce diagnostic si difficile : la commande **réussissait** — c'est
son **contenu** qui était mauvais (`newMode` 0 sur la sortie 4, le défaut de #58). Un `9` n'est
donc jamais l'anomalie à instruire ; ce qui l'est, c'est ce qu'on a envoyé.

⚠️ **Ce que cette capture-ci ne dit PAS — et comment une autre l'a contourné.** Deux commandes
avaient été mises en file (`SetParam` puis `SetOut`) et le corps d'**un seul** des deux
`WaitCommand` est visible, son `cmdID` tronqué à l'affichage. Ce `Ok` n'est **attribuable à
aucune des deux**, et cela reste vrai de cette capture. Ce n'est plus la mesure qui manque : le
2026-09-07, @StephanH27 a capturé les **deux** corps, `status: 9, detail: "Ok"` l'un comme
l'autre — ce qui **contourne** l'attribution au lieu de la résoudre. Voir
§ *`SetParam ConsigneEau` précède tout changement de mode sauf l'arrêt*.

⚠️ **Et la forme de `response` diverge de la doc, sur ce seul endpoint.** La capture montre un
**objet**, pas une liste d'objets. Ce n'est pas une contradiction avec la mesure de @nopbop
(#140), qui porte sur **`CommandStatus.php`** et où `response` est bien un tableau, le plus
récent en premier — les deux endpoints ne rendent pas la même forme, ou l'un des deux varie. Une
capture, un endpoint, une installation : à confirmer avant d'en tirer quoi que ce soit pour #106,
qui reste écrit sur la doc officielle.

---

### Écrire un paramètre de régulation — `SetParam.php`

**Source : amont uniquement** (`klereo.class.php`, `function setParam`). Absent de la
documentation Klereo.

**URL :** `https://connect.klereo.fr/php/SetParam.php` · **POST**, `Authorization: Bearer <jwt>`

```
poolID    = int
paramID   = str      ← le nom du paramètre, p. ex. ConsigneEau
newValue  = <valeur>
comMode   = 1
```

Même protocole en deux étapes que `SetOut` : le retour porte un `cmdID` à confirmer.

✅ **Vérifié le 2026-09-03 : notre `api.py:302-319` envoie les quatre champs sous les mêmes noms
que l'amont**, `newValue` compris. Les deux implémentations s'accordent à l'octet près — ce qui
ne rend pas la forme *officielle*, mais retire l'hypothèse d'une divergence silencieuse entre la
seule source et le seul consommateur.

---

### Poser un délai d'extinction automatique — `SetAutoOff.php`

✅ **Exposée depuis #162** — `api.set_auto_off` / `coordinator.async_set_auto_off`, et une entité
`number` « Auto-Off Timer » par sortie qui porte le champ. C'était le dernier point de la matrice
où l'amont était **seul** à savoir quelque chose d'actionnable ; il ne l'est plus.

⚠️ Les deux inconnues de la fin de section (**le comportement à `0`**, **le sens sur une sortie
non-manuelle**) survivent à cette livraison : l'entité borne à `1` et n'annote rien, précisément
pour ne rien affirmer à leur sujet.

**Source : amont uniquement** (`klereo.class.php:1280-1299`, `function setAutoOff`).

**URL :** `https://connect.klereo.fr/php/SetAutoOff.php` · **POST**, `Authorization: Bearer <jwt>`

```
poolID    = int
outIdx    = int
offDelay  = int
comMode   = 1
```

**On LIT déjà `offDelay`** — il est arrivé dans l'export brut avec #145, et @nopbop a relevé
`offDelay: 5` sur sa sortie 1 (GitHub #58, 2026-09-02). Le champ est donc réel et renseigné en
production ; il n'a simplement jamais eu de chemin d'écriture ici.

✅ **Unité et bornes — tranchées le 2026-09-03.** L'amont déclare la commande Jeedom avec sa borne
et son unité (`klereo.class.php:938-939`) :

```php
createCmdInfo('offDelay_'.$outN, '… Temps minuterie', 'numeric', $order, 1, 600, 'min');
createCmdAction('offDelay_'.$outN, '… Consigne temps minuterie', 'slider', $order, 1, 600, 'min', …);
```

La signature est `($logicalId, $name, $subType, &$order, $min, $max, $unite)` — donc **minutes,
bornées 1 à 600** (10 h). Contrôles de lecture voisins, sans ambiguïté possible sur l'ordre des
arguments : `'Filtration_TodayTime', …, 0, 24, 'h'` et `'PHMinus_Today', …, 0, 36, 'mL'`.

**Recoupé sur Bioul le 2026-09-03** : les cinq sorties portent `240, 5, 2, 2, 240` — toutes dans
`[1, 600]`, et `240 min = 4 h` est une durée de minuterie plausible. La valeur `5` de @nopbop sur sa
sortie 1 tombe dans le même intervalle.

### ✅ L'existence côté serveur est MESURÉE — sonde du 2026-09-08 sur Bioul

Jusqu'ici cet endpoint n'était attesté que par du code amont qui tourne, jamais par une réponse de
`connect.klereo.fr`. Il l'est désormais, par une sonde en deux étages conçue pour ne rien changer.

**Étage 1 — existence, sans écriture possible.** `POST` avec le seul `poolID`, aucune sortie
nommée :

```json
HTTP 200  ·  {"status":"error","detail":"Mauvais délais"}
```

🔴 **C'est la preuve la plus forte des deux, et la moins attendue.** Une route inexistante ne
**valide** pas un `offDelay` — elle 404. Le serveur a lu la requête, cherché le délai, ne l'a pas
trouvé et l'a refusé avec un message métier **en français**. L'endpoint existe, parse ses
paramètres et contrôle ce champ.

**Étage 2 — réécriture idempotente**, `offDelay: 240 → 240` sur la sortie 0 (la valeur déjà en
place, donc changement d'état nul par construction) :

```json
SetAutoOff   → {"status":"ok","response":[{"cmdID":4399790,"poolID":121170}]}
CommandStatus→ {"cmdID":4399790,"status":9,"detail":"Ok", …}
relecture    → offDelay 240, inchangé
```

✅ **`status: 9` — la commande est ACCEPTÉE ET EXÉCUTÉE, et le compte est à `access: 10`.**
`SetAutoOff` ne demande donc **pas** l'accès professionnel : une entité bâtie dessus serait
utilisable par un utilisateur ordinaire, ce qui était la vraie question à trancher avant de la
construire. L'enveloppe est celle des autres écritures — `response` est un **tableau** dont le
premier élément porte `cmdID` et `poolID`, exactement la forme que `KlereoCoordinator._command_id`
lit déjà.

⚠️ Ce qui reste non mesuré : le comportement à `0`, et ce que `offDelay` signifie sur une sortie
en mode non-manuel. La sonde a délibérément réécrit une valeur existante, donc elle ne dit rien de
ces deux cas.

---

## La programmation horaire — `plans` / `plan64`

Chaque sortie porte un `plan64` : la programmation horaire de l'équipement, en base64. L'amont
sait la décoder (`klereo.class.php`, `static function plan2arr`), et c'est ce que le commentaire de
`diagnostics.py` annonçait comme « ce qu'une fonctionnalité de créneaux lirait ».

**Le décodage, et ses DEUX inversions** — se tromper sur l'une des deux rend un planning
plausible et faux :

1. `unpack('h*')` en PHP rend le **quartet de poids faible de chaque octet en premier** ;
2. la boucle interne lit les bits de l'indice 3 vers 0, donc **bit de poids faible d'abord** dans
   chaque quartet.

Un bit = un créneau, dans l'ordre chronologique de la journée.

✅ **La granularité est mesurée** (Bioul, 2026-09-03) : `plan64` fait **16 caractères base64**,
soit 12 octets, **96 bits — un créneau de 15 minutes sur 24 h**. La déduction précédente, tirée
d'une fixture inventée, se trouve confirmée par une charge utile réelle.

🔴 **En revanche le DÉCODAGE n'est pas validé, et le relevé ne pouvait pas le valider.** Les trois
`plan64` présents décodent à **tout zéro** — aucune sortie de ce bassin n'est en mode créneaux. Or
un plan tout à zéro rend le même résultat sous **n'importe quel ordre de bits** : les deux
inversions ci-dessus sont donc encore non éprouvées, et une transcription fausse serait
indiscernable d'une transcription juste.

⚠️ Le contrôle qui trancherait est une sortie **réellement programmée**, dont les plages décodées
peuvent être comparées à ce que le propriétaire sait de son installation. Tant qu'aucune ne l'est,
« ça n'a pas échoué » ne veut pas dire « ça marche » : le bras n'a pas été joué.

⚠️ **`plans` ne couvre pas toutes les sorties.** Sur Bioul, les sorties **2 et 9 n'ont aucune
entrée** — ce qui est distinct d'une entrée vide, et qu'un code lisant `plans[i]` sans garde
prendrait pour un planning nul.

✅ **Aucun endpoint d'écriture de programmation n'existe dans les trois sources.** Une
fonctionnalité de créneaux serait donc **en lecture seule** — la moitié qui ne peut casser
l'installation de personne.

---

## Le PIN du boîtier — une SORTIE, jamais une entrée

Question posée pour une raison de sécurité (#147) : *que permet la possession du seul PIN ?*

**Dans toute la surface connue : rien.** Deux sources indépendantes concordent, et l'une le fait
par une absence particulièrement nette :

- **Doc officielle** — `pin` apparaît **une seule fois**, comme champ *rendu* par
  `GetPoolDetails` (« numéro PIN du boîtier de connexion »). Aucun endpoint ne le prend en
  paramètre.
- **Amont Jeedom** — `grep -c pin` sur les 1 716 lignes de `klereo.class.php` rend **0**. La
  réimplémentation la plus complète qui existe ne le lit ni ne l'envoie jamais.

Et il n'est obtenable qu'**après** authentification JWT : le posséder ne raccourcit aucun chemin,
puisqu'il faut déjà le compte pour l'avoir.

⚠️ **Portée du verdict.** Il porte sur la surface **connue**. Il ne dit pas qu'aucun endpoint non
documenté n'accepte un PIN — et la question n'a délibérément **pas** été sondée : deviner des noms
d'endpoints chez un tiers qui menace de bannir ferait porter le risque sur le compte de
l'utilisateur.

---

## Ce que ce document NE règle PAS

- **Le conteneur des consignes** (#94) — `params` vs `RegulModes` vs `ExtraParams`. Les listes de
  champs sont élidées. Il faut toujours un export diagnostics d'une installation réelle.
- **La présence et la forme des alertes** (#57) — `alerts` n'apparaît pas dans les listes élidées.
  L'amont lit bien `$pool['alerts']` avec `code` et `param` (`klereo.class.php:509-517, 570-590`),
  ce qui reste notre meilleure source sur ce point.
- **Ce que `newMode` vaut sur les sorties 2, 3, 8 et 15** — la doc dit que la valeur diffère, jamais
  ce qu'elle vaut.
- 🔴 **Le `newState` du mode Froid sur la sortie 4** — les trois autres cibles sont mesurées,
  celle-ci ne l'est pas, et aucun rapporteur ne possède de PAC réversible. `1, 2, ?, 0` n'offre aucun motif
  à extrapoler : la case reste **blanche** plutôt que plausible. § *Changer le mode … d'une sortie*.
  ⚠️ Depuis le 2026-09-07 c'est aussi une **demande** — @StephanH27 souhaite chaud/froid/auto/arrêt
  « pour l'hiver » — et pas seulement un trou. Une demande n'est pas un instrument : la case reste
  blanche tant que personne ne peut la mesurer.
- 🔴 **Le décodage de `plan64` n'est pas éprouvé** (§ *La programmation horaire*). Le relevé du
  2026-09-03 a fermé la question de la **granularité** (96 bits, créneaux de 15 min, mesuré) et
  **pas** celle de l'ordre des bits : les trois plannings de Bioul sont à zéro, et un planning nul
  est invariant par toute permutation. Il faut une sortie **réellement programmée**.
- **L'unité de `outs[].totalTime`** — jamais lue par l'amont, donc non sourcée. Par analogie avec
  `params.Filtration_TotalTime`, que l'amont divise par 3600 pour obtenir des heures
  (`klereo.class.php:331`), la seconde est probable. C'est une **inférence**, et la lire comme un
  fait ferait de `28 414 540` autre chose que ~329 jours.
- **Ce qu'un endpoint NON documenté accepterait** — hors périmètre par décision, pas par oubli :
  deviner des noms chez un tiers qui menace de bannir ferait porter le risque sur le compte de
  l'utilisateur.
