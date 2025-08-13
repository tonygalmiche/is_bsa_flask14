# Gestion de tâches - Flask + HTMX

Application web pour gérer les tâches des opérateurs avec une interface de planning interactive.

## Fonctionnalités

- **Grille de planning** : Une ligne par opérateur, une colonne par demi-journée (30 créneaux)
- **Gestion des tâches** :
  - Déplacement par glisser-déposer (drag & drop)
  - Redimensionnement avec les poignées latérales
  - Navigation au clavier (flèches directionnelles)
  - Redimensionnement au clavier (+/- pour ajuster la durée)
- **Gestion intelligente des collisions** :
  - Déplacement automatique des tâches en conflit
  - Déplacement groupé lors du déplacement vers la gauche
  - Aucune superposition possible
- **Affaires colorées** : Chaque tâche est liée à une affaire avec une couleur distincte
- **Interface responsive** avec feedback visuel

## Installation

1. Cloner ou télécharger le projet
2. Installer les dépendances :
```bash
pip install -r requirements.txt
```

3. Lancer l'application :
```bash
python app.py
```

4. Ouvrir votre navigateur sur `http://localhost:5000`

## Structure du projet

```
flask-htmx/
├── app.py                 # Application Flask principale
├── requirements.txt       # Dépendances Python
├── static/
│   ├── style.css         # Styles CSS
│   └── script.js         # JavaScript pour les interactions
└── templates/
    └── index.html        # Template principal
```

## Utilisation

### Navigation à la souris
- **Déplacer une tâche** : Cliquer et glisser
- **Redimensionner** : Utiliser les poignées sur les bords gauche/droit des tâches
- **Sélectionner** : Cliquer sur une tâche

### Navigation au clavier
- **Flèches directionnelles** : Déplacer la tâche sélectionnée
- **+ / =** : Augmenter la durée de la tâche
- **-** : Diminuer la durée de la tâche
- **Suppr / Backspace** : Supprimer la tâche (avec confirmation)

### Données initiales
L'application est pré-remplie avec :
- 5 opérateurs
- 8 affaires avec couleurs distinctes
- 9 tâches d'exemple réparties sur les opérateurs

## Personnalisation

### Ajouter des opérateurs
Modifier la liste `OPERATORS` dans `app.py`

### Ajouter des affaires
Modifier la liste `AFFAIRS` dans `app.py` (inclure un nom et une couleur hexadécimale)

### Modifier le nombre de créneaux
Changer la valeur `30` dans la fonction `index()` et ajuster les validations

### Personnaliser les couleurs
Modifier les variables CSS dans `static/style.css`

## Architecture technique

- **Backend** : Flask (Python) avec API REST
- **Frontend** : HTML5, CSS3, JavaScript vanilla + HTMX
- **Stockage** : En mémoire (listes Python) - peut être étendu avec une base de données
- **Interactions** : Drag & Drop API native, gestion tactile de base

## API Endpoints

- `GET /` : Page principale du planning
- `POST /move_task` : Déplacer une tâche
- `POST /resize_task` : Redimensionner une tâche
- `GET /get_planning_data` : Récupérer les données du planning (JSON)

## Améliorations possibles

- Persistence en base de données (SQLite, PostgreSQL)
- Authentification et gestion des utilisateurs
- Export PDF/Excel du planning
- Notifications en temps réel
- API REST complète (CRUD)
- Mode sombre
- Gestion des congés et absences
- Filtres et recherche
