# Prise en compte des week-ends / congés / absences dans le planning des tâches

Ce document décrit l'état actuel du système et propose une approche pour que le
planning (`is.gestion.tache.planning` + application Flask) tienne réellement
compte des week-ends, des congés (`resource.calendar.leaves`) et des absences
(`is.absence`), aussi bien en mode `type_donnees='operation'` qu'en mode
`type_donnees='of'`. Il ne contient aucune implémentation — c'est un document
de conception à valider avant de coder.


## 1. État des lieux (existant)

### 1.1 Ce qui existe déjà

- **`is.gestion.tache.fermeture`** (`is_gestion_tache.py`, méthode
  `action_maj_fermetures`) : calcule des fermetures par jour
  (et par employé en mode `operation`, par poste/global en mode `of`), à
  partir de `is.absence` + `resource.calendar.leaves`. **Uniquement utilisé
  pour l'affichage** aujourd'hui (grisage CSS côté Flask) ; rien ne les relit
  pour bloquer un placement.
- **Week-end** : grisé côté Flask par un test codé en dur
  (`day_name in ['Samedi', 'Dimanche']`, `app.py`), indépendant de
  `is.gestion.tache.fermeture`.
- **`is.dispo.ressource`** (`is_bsa14/models/hr.py`) : table de disponibilité
  pré-calculée par poste, par tranche de 30 min (cron quotidien, `hr.py`),
  lue par `get_heure_debut_fin` (`is_ordre_travail.py`) pour enchaîner les
  opérations d'un OT
  (`calculer_charge_ordre_travail`). **Décision : hors périmètre de ce
  chantier** — cet usage existant (recalcul des opérations, y compris la
  première) fonctionne et reste inchangé ; on ne l'utilise pas pour
  l'affichage ni le blocage du planning (voir §3, raisons détaillées).

### 1.2 Ce qui ne fonctionne pas / est incomplet

| Aspect | `operation` | `of` |
|---|---|---|
| Fermetures affichées | `is.absence` + `resource.calendar.leaves` par **employé** | `resource.calendar.leaves` par **poste/global** uniquement |
| Déplacement manuel (drag&drop / clavier / resize dans Flask) | **Aucun contrôle** — seule la collision entre tâches est vérifiée (`move_task`, `resize_task`, `keyboard_move_task`, `app.py`) | Idem |
| `action_maj_date_of` / `action_maj_date_operation` (report des dates Flask → Odoo) | Date acceptée telle quelle, aucun contrôle | Date reportée brute sur `mrp.production.date_planned_start`, aucun contrôle |

**Conclusion** : rien n'empêche réellement de déposer une tâche un samedi ou
pendant un congé — seul un grisage visuel prévient l'utilisateur, et
seulement si `action_maj_fermetures` a été lancé.


## 1.3 Champs de date/durée utilisés dans chaque mode

Les deux modes ne stockent pas la date de début / date de fin / durée sur les
mêmes champs, ni sur le même modèle « source de vérité ». La tâche Flask
(`is.gestion.tache`) est toujours alimentée en copiant ces valeurs depuis le
modèle source lors de `action_chargement_taches` (`is_gestion_tache.py`).

| | `type_donnees = 'operation'` | `type_donnees = 'of'` |
|---|---|---|
| Modèle source de vérité | `is.ordre.travail.line` (une ligne = une opération) | `mrp.production` (un OF entier) + durée portée par `is.ordre.travail` |
| **Date de début** | `heure_debut` (`is_bsa14/models/is_ordre_travail.py`) — copiée dans `is.gestion.tache.start_date` via `line.heure_debut start_date` (`is_gestion_tache.py`) | `date_planned_start` (champ core `mrp.production`, `odoo/addons/mrp/models/mrp_production.py`) — copiée via `mp.date_planned_start start_date` (`is_gestion_tache.py`) |
| **Date de fin** | `heure_fin` (`is_ordre_travail.py`) — **non copiée** dans la tâche Flask ; `is.gestion.tache.end_date` est recalculée (voir Durée) | Pas de champ dédié utilisé côté chargement ; `is.gestion.tache.end_date` est recalculée (voir Durée). Champ existant mais non exploité ici : `is_date_planifiee_fin` (`is_bsa14/models/mrp_production.py`) |
| **Durée** | `duree_totale` (`is_ordre_travail.py`, compute stocké = `duree_unitaire × quantité`) — copiée via `line.duree_totale duration_hours` (`is_gestion_tache.py`) | `ot.duree_planifiee` (`is_ordre_travail.py`, « Durée fixée sur le planning des tâches ») en priorité, sinon `ot.duree_prevue` (`is_ordre_travail.py`, compute) — `row.get('duree_planifiee') or row.get('duree_prevue')` (`is_gestion_tache.py`) |
| **Champ tâche Flask (commun aux 2 modes)** | `is.gestion.tache.start_date` (Datetime) + `duration_hours` (Float) → `end_date` recalculée (compute stocké `_compute_end_date`, sur la base d'un forfait de 7h de travail/jour ramené à des créneaux calendaires de 12h) | *(idem — même modèle, mêmes champs)* |
| **Écriture retour vers la source** (déplacement manuel dans Flask, via `action_maj_date_operation` / `action_maj_date_of`) | `line.heure_debut` puis `line.heure_fin` recalculée par `get_heure_debut_fin` | `production.date_planned_start` — pas de mise à jour d'une "date de fin" d'OF |

Points notables :
- `is.gestion.tache.end_date` n'est **jamais** une copie directe d'un champ
  source : elle est toujours recalculée à partir de `start_date` +
  `duration_hours` avec un forfait horaire fixe (7h/jour), ce qui peut
  diverger de `heure_fin` (mode `operation`) si celle-ci a été calculée avec
  un calendrier réel tenant compte des pauses/horaires variables.
- En mode `of`, il n'existe **aucun champ "durée d'OF" au sens strict** :
  la durée utilisée est en réalité celle de l'OT associé (`ot.duree_planifiee`
  / `ot.duree_prevue`), pas un champ propre à `mrp.production`.
- `is_date_planifiee` / `is_date_planifiee_fin` (`mrp_production.py`)
  existent sur l'OF mais ne sont pas utilisés par le chargement des tâches
  (cf. confusion déjà rencontrée avec `date_planned_start` — voir
  échanges précédents sur ce sujet).


## 2. Objectif

1. Ne jamais **calculer automatiquement** une date de début de tâche sur un
   jour non ouvré (week-end, congé, absence).
2. Empêcher (ou au minimum alerter fortement) le dépôt manuel d'une tâche
   sur un jour fermé, dans l'app Flask, en mode `operation` **et** `of`.
3. Une seule source de vérité pour "ce jour est-il fermé ?", **la même pour
   les deux modes**, simple à exploiter côté Odoo et côté Flask.


## 3. Mécanisme retenu, pour les deux modes : fermetures explicites

**Décision : ni `is.dispo.ressource`, ni un nouveau calcul par employé —
uniquement le week-end (règle fixe) + `is.gestion.tache.fermeture`
(déjà calculé par `action_maj_fermetures`), pour `operation` comme pour `of`.**

Raisons :
- Sur `bsa14-acier` (mode `of`), 0 des 438 employés actifs n'a
  `is_workcenter_id` renseigné → `is.dispo.ressource` y est structurellement
  toujours vide (`hr.py`). Inutilisable pour ce site.
- Même là où `is.dispo.ressource` est alimenté (`bsa14-inox`), l'utiliser
  pour l'affichage/le blocage du planning est plus compliqué que prévu :
  granularité 30 min à agréger, un simple booléen `disponibilite=0` qui ne
  distingue pas "congé" de "hors horaire normal", table régénérée chaque
  jour par cron (fraîcheur non garantie). Pour un gain limité (affichage +
  blocage, pas de calcul de charge), ça n'en vaut pas la peine.
- **Simplicité** : un seul mécanisme, déjà en place, à réutiliser tel quel
  des deux côtés plutôt que d'en maintenir un second en parallèle.

Règle retenue, sans aucune dépendance à une table pré-calculée :

```
est_jour_ouvre(operator_id ou workcenter_id, date) =
    date.weekday() not in (5, 6)                     # week-end (codé en dur, cf. app.py)
    AND aucune ligne is.gestion.tache.fermeture       # pour cet operator_id/workcenter_id, à cette date
        active sur ce planning
```

`is.gestion.tache.fermeture` couvre déjà les deux granularités nécessaires
(`operator_id` en mode `operation`, `workcenter_id` en mode `of`) — rien à
ajouter au modèle, juste à exploiter `fermeture_ids` là où c'est aujourd'hui
seulement affiché.

**`is.dispo.ressource` / `get_heure_debut_fin` ne changent pas** : ils
continuent à servir uniquement à `calculer_charge_ordre_travail` (recalcul
des opérations d'un OT, y compris via `action_maj_date_operation` pour les
opérations suivantes) — c'est un mécanisme séparé, qui fonctionne déjà
correctement pour cet usage précis et n'a pas besoin d'être touché.


## 4. Début décalé, durée réelle vs durée calendaire

- **Début sur une fermeture** : si la date de début calculée tombe sur un
  jour fermé (§3), la décaler au prochain jour ouvré juste après.
- **Fermeture pendant la durée** : si une fermeture tombe entre le début et
  la fin, la fin doit "sauter" par-dessus → il faut allonger la durée
  calendaire en conséquence. D'où **deux notions de durée** :
  - **durée réelle (travaillée)** : celle qui existe déjà (`duree_totale`,
    `duree_planifiee`/`duree_prevue`, §1.3) — ne change pas, reste la
    référence pour la charge/les coûts.
  - **durée calendaire** : durée réelle + somme des fermetures rencontrées,
    utilisée uniquement pour positionner `end_date` dans le planning
    (affichage, largeur du bloc, détection de collision).
- **Cette durée calendaire n'a de sens que pour le planning** : elle n'a pas
  à être remontée dans l'OF (`mrp.production`) ni l'opération
  (`is.ordre.travail.line`) — leurs champs de durée restent la durée réelle.
- **Granularité** : `is.gestion.tache.fermeture.date_fermeture` est un champ
  `Date` (jour entier, pas de demi-journée) — une fermeture ferme donc
  toujours la journée complète (AM + PM). Pas d'ambiguïté à gérer ici.
- **Impact code** : `_compute_end_date` (`is_gestion_tache.py`), qui
  fait aujourd'hui un simple `start_date + timedelta`, devra avancer jour par
  jour en sautant les fermetures rencontrées (weekend + `fermeture_ids`),
  pour les deux modes, via le bloc commun ci-dessous (§5).
- **Aucune référence à "maintenant"** : le glissement (§4) déplace toujours
  une date fermée vers le **prochain jour ouvré qui la suit**, que cette date
  soit dans le passé ou le futur — jamais vers la date du jour. Un OF très en
  retard reste donc en retard : il glisse seulement du samedi fermé vers le
  lundi (qui peut lui-même être dans le passé), il ne "saute" jamais jusqu'à
  aujourd'hui. Faire remonter un OF en retard à la date du jour reste une
  action manuelle de l'utilisateur, jamais automatique (cf. incident
  précédent avec l'ancien clamp `start_date < now → now`, supprimé).


## 5. Bloc commun : fonction "jour ouvré"

Une fonction unique, appelable des deux côtés :

- **Côté Odoo** : méthode sur `is.gestion.tache.planning` (ou `is.gestion.tache`)
  type `est_jour_ouvre(operator_id, workcenter_id, date)` qui applique la
  règle du §3 (week-end + recherche dans `fermeture_ids` du planning).
- **Côté Flask** : requête SQL directe sur `is_gestion_tache_fermeture`
  (comme le fait déjà `load_fermetures_from_db` pour l'affichage), pour ne
  pas dépendre d'un aller-retour XML-RPC à chaque interaction utilisateur
  (perf du drag&drop). Le calcul du week-end (déjà présent, `app.py`)
  reste tel quel.

Pas de question de fallback à trancher ici : contrairement à
`is.dispo.ressource`, `is.gestion.tache.fermeture` est calculé à la demande
(`action_maj_fermetures`) et toujours disponible.


## 6. Ce qu'il faut changer, par mode

### 6.1 Mode `operation`

- **`action_maj_date_operation`** (`is_gestion_tache.py`) : **pas de
  changement nécessaire ici** — elle recopie `line.heure_debut = start_dt` à
  partir de `task.start_date`, qui est déjà garanti sur un jour ouvré grâce
  au glissement fait en amont (chargement + drag&drop, §7). Elle hérite donc
  automatiquement du comportement correct sans modification.
- **Drag & drop / clavier (Flask)** : `move_task`, `resize_task`,
  `keyboard_move_task` doivent, en plus du contrôle de collision existant
  (`check_collision`), vérifier la disponibilité via le bloc commun (§5).
- **Inchangé** : `calculer_charge_ordre_travail`/`get_heure_debut_fin`
  (`is.dispo.ressource`) continuent de gérer le recalcul des opérations d'un
  OT comme aujourd'hui (§1.1, §3).

### 6.2 Mode `of`

- **`action_maj_date_of`** : même chose, **pas de changement nécessaire** —
  elle écrit `production.date_planned_start` à partir de `task.start_date`,
  déjà glissé en amont.
- **Drag & drop (Flask)** : mêmes routes que §6.1, disponibilité vérifiée au
  niveau du **poste de charge** (`workcenter_id`), en cohérence avec
  `operator_field = "workcenter_id" if type_donnees=='of'` (`app.py`).


## 7. Questions tranchées

1. **Glissement automatique**, pas de refus dur : un début qui tombe sur un
   jour fermé est décalé automatiquement au prochain jour ouvré (§4), et la
   durée est allongée automatiquement pour sauter les fermetures rencontrées
   pendant la tâche (durée calendaire, §4) — aucun blocage/message d'erreur
   qui empêcherait l'action, dans les deux modes.
2. **Week-end fixe** (`weekday not in (5,6)`, codé en dur, §3) pour démarrer.
   À garder en tête comme amélioration possible pour une prochaine itération
   si un poste doit un jour travailler le week-end (§3.1 dans une version
   précédente du document — dérogation par `mrp.workcenter` à ce moment-là).
3. **Pas de rétroactivité** : les tâches déjà existantes ne sont pas
   retouchées automatiquement. Le nouveau calcul (glissement + durée
   calendaire) s'applique uniquement quand l'utilisateur relance "Charger
   les tâches" (`action_chargement_taches`).

Toutes les décisions nécessaires pour démarrer le développement sont prises.


## 8. Plan de développement, étape par étape (chaque étape testable seule)

1. **Bloc commun `est_jour_ouvre`** (§5). *Test* : ajouter une fermeture sur
   un poste (menu Congés), vérifier via le shell Odoo qu'elle renvoie `False`
   ce jour-là et `True` sinon (et `False` un week-end).
2. **Durée calendaire dans `_compute_end_date`** (§4). *Test* : créer une
   tâche dont la durée chevauche un week-end/fermeture, vérifier que
   `end_date` saute bien les jours fermés.
3. **Glissement du début au chargement** (`action_chargement_taches`), sans
   aucune référence à "maintenant" (§4). *Test* : mettre la date d'un
   OF/opération un samedi — y compris une date déjà passée — cliquer
   "Charger les tâches", vérifier que la tâche démarre le lundi suivant (qui
   peut donc lui aussi être dans le passé, ce n'est pas un bug).
4. **Glissement au drag & drop / resize / clavier** (Flask). *Test* :
   glisser une tâche sur le planning pour qu'elle empiète sur un jour fermé,
   vérifier qu'elle se recale automatiquement après.

Rien à faire côté `action_maj_date_of`/`action_maj_date_operation` : une fois
les étapes 3 et 4 en place, `task.start_date` est toujours déjà valide
quand ces méthodes le recopient vers l'OF/l'opération — vérifiable en testant
"Maj date OF"/"Maj date opération" après l'étape 4, sans code supplémentaire.
