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
3. **Le document est partiel.** @nopbop citait par ailleurs une phrase sur le rafraîchissement des
   serveurs Klereo toutes les 10 minutes, avec une mise en garde contre un sondage plus fréquent :
   **elle ne figure pas dans ce qui a été collé.** Notre `SCAN_INTERVAL_MINUTES` est à 5
   (`const.py:12`) ; ce point reste **non vérifié**.

Une divergence entre ce document et l'API vivante reste possible et ordinaire. Une affirmation
tirée d'ici est mieux sourcée qu'une supposition — elle n'est pas une mesure.

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
| `pin` | numéro PIN du boîtier de connexion (str) |
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

⚠️ `WaitCommand` **bloque** et `CommandStatus` **rend la main tout de suite** — l'intégration
appelle aujourd'hui `WaitCommand` sous un délai client de 10 s (#106).

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

## Ce que ce document NE règle PAS

- **Le conteneur des consignes** (#94) — `params` vs `RegulModes` vs `ExtraParams`. Les listes de
  champs sont élidées. Il faut toujours un export diagnostics d'une installation réelle.
- **La présence et la forme des alertes** (#57) — `alerts` n'apparaît pas dans les listes élidées.
  L'amont lit bien `$pool['alerts']` avec `code` et `param` (`klereo.class.php:509-517, 570-590`),
  ce qui reste notre meilleure source sur ce point.
- **La cadence de rafraîchissement côté serveur** — voir la réserve 3 en tête de fichier.
- **Ce que `newMode` vaut sur les sorties 2, 3, 8 et 15** — la doc dit que la valeur diffère, jamais
  ce qu'elle vaut.
