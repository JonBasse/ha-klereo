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
| `SetAutoOff.php` | `poolID`, `outIdx`, `offDelay`, `comMode` | 🔴 **absent** | ✅ | 🔴 **absent** |
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

🔴 **Capacité non exposée par l'intégration.** C'est le seul point de la matrice où l'amont est
**seul** à savoir quelque chose d'actionnable.

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

⚠️ **Non mesuré : l'unité et la borne.** `5` est compatible avec des minutes comme avec des heures,
et aucune des deux sources ne le dit. ⚠️ **Non mesuré : l'existence côté serveur.** Elle est
attestée par du code amont qui tourne, pas par une réponse. C'est un endpoint d'**écriture** :
le sonder à l'aveugle change la configuration d'un vrai bassin.

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

🔴 **La granularité n'est pas mesurée.** Un `plan64` de 12 octets donnerait 96 bits, soit un
créneau de 15 minutes sur 24 h — mais cette longueur vient d'une **fixture inventée**, pas d'une
charge utile réelle. Un seul relevé la confirme ou la casse, et tant qu'il n'a pas eu lieu, ce
paragraphe est une déduction et non un fait.

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
- **L'unité et la borne d'`offDelay`** (§ *`SetAutoOff.php`*) — `5` est compatible avec des minutes
  comme avec des heures. Aucune des trois sources ne tranche.
- **La longueur réelle de `plan64`** (§ *La programmation horaire*) — elle décide de la granularité
  des créneaux, et la valeur dont on dispose vient d'une fixture **inventée**.
- **L'existence côté serveur de `SetAutoOff.php`** — attestée par du code amont qui tourne, jamais
  par une réponse. C'est un endpoint d'écriture ; le sonder n'est pas gratuit.
- **Ce qu'un endpoint NON documenté accepterait** — hors périmètre par décision, pas par oubli :
  deviner des noms chez un tiers qui menace de bannir ferait porter le risque sur le compte de
  l'utilisateur.
