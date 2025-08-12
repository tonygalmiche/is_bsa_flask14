from flask import Flask, render_template, request, jsonify
import json
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)

# Sérialiseur personnalisé pour les dates
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

app.json_encoder = DateTimeEncoder

SLOT_WIDTH = 25  # Largeur d'un créneau en pixels (divisé par 3 : 60 -> 20)
ROW_HEIGHT = 55  # Hauteur d'une ligne d'opérateur
HEADER_HEIGHT = 80  # Hauteur de l'en-tête
NUM_SLOTS = 90  # Nombre total de créneaux (triplé : 30 -> 90)

# Nouveaux paramètres
START_DATE = datetime.now().date()  # Date de début du planning (date du jour par défaut)
DAY_DURATION_HOURS = 7  # Durée d'une journée en heures
HALF_DAY_HOURS = DAY_DURATION_HOURS / 2  # Durée d'une demi-journée (AM ou PM)

# Dates de congés (orange clair) - format datetime
VACATION_DATES = [
    datetime(2025, 8, 15, 8, 0),   # 15 août AM
    datetime(2025, 8, 15, 15, 0),  # 15 août PM
    datetime(2025, 8, 25, 8, 0),   # 25 août AM
    datetime(2025, 8, 25, 15, 0),  # 25 août PM
]

# Données initiales
OPERATORS = [
    {
        "id": 1, 
        "name": "Jean Dupont",
        "absences": [
            datetime(2025, 8, 12, 8, 0),   # 12 août AM
            datetime(2025, 8, 20, 15, 0),  # 20 août PM
        ]
    },
    {
        "id": 2, 
        "name": "Marie Martin",
        "absences": [
            datetime(2025, 8, 18, 8, 0),   # 18 août AM
        ]
    },
    {"id": 3, "name": "Pierre Durand", "absences": []},
    {"id": 4, "name": "Sophie Lambert", "absences": []},
    {"id": 5, "name": "Antoine Moreau", "absences": []},
    {"id": 6, "name": "Claire Rousseau", "absences": []},
    {"id": 7, "name": "Lucas Bernard", "absences": []},
    {"id": 8, "name": "Emma Lefevre", "absences": []},
    {"id": 9, "name": "Thomas Dubois", "absences": []},
    {"id": 10, "name": "Julie Garnier", "absences": []}
]

AFFAIRS = [
    {"id": 1, "name": "Projet Alpha", "color": "#FF6B6B"},
    {"id": 2, "name": "Projet Beta", "color": "#4ECDC4"},
    {"id": 3, "name": "Projet Gamma", "color": "#45B7D1"},
    {"id": 4, "name": "Projet Delta", "color": "#96CEB4"},
    {"id": 5, "name": "Projet Epsilon", "color": "#FFEAA7"},
    {"id": 6, "name": "Projet Zeta", "color": "#DDA0DD"},
    {"id": 7, "name": "Projet Eta", "color": "#FFB347"},
    {"id": 8, "name": "Projet Theta", "color": "#98D8C8"}
]

# Planning initial avec tâches pré-remplies - RÉPARTI SANS COLLISIONS
TASKS = [
    {
        "id": str(uuid.uuid4()),
        "operator_id": 1,
        "affaire_id": 1,
        "start_date": datetime.combine(START_DATE, datetime.min.time().replace(hour=8)),  # Slot 0 (Jour 1 AM)
        "duration_hours": 21,  # 6 slots (3.5h * 6 = 21h)
        "name": "Analyse Alpha"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 1,
        "affaire_id": 2,
        "start_date": datetime.combine(START_DATE + timedelta(days=4), datetime.min.time().replace(hour=8)),  # Slot 8 (Jour 5 AM)
        "duration_hours": 14,  # 4 slots (3.5h * 4 = 14h)
        "name": "Dev Beta"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 2,
        "affaire_id": 3,
        "start_date": datetime.combine(START_DATE + timedelta(days=1), datetime.min.time().replace(hour=8)),  # Slot 2 (Jour 2 AM)
        "duration_hours": 17.5,  # 5 slots (3.5h * 5 = 17.5h)
        "name": "Tests Gamma"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 2,
        "affaire_id": 4,
        "start_date": datetime.combine(START_DATE + timedelta(days=5), datetime.min.time().replace(hour=8)),  # Slot 10 (Jour 6 AM)
        "duration_hours": 21,  # 6 slots (3.5h * 6 = 21h)
        "name": "Review Delta"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 3,
        "affaire_id": 5,
        "start_date": datetime.combine(START_DATE + timedelta(days=2), datetime.min.time().replace(hour=8)),  # Slot 4 (Jour 3 AM)
        "duration_hours": 10.5,  # 3 slots (3.5h * 3 = 10.5h)
        "name": "Config Epsilon"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 3,
        "affaire_id": 1,
        "start_date": datetime.combine(START_DATE + timedelta(days=4), datetime.min.time().replace(hour=15)),  # Slot 9 (Jour 5 PM)
        "duration_hours": 14,  # 4 slots (3.5h * 4 = 14h)
        "name": "Impl Alpha"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 4,
        "affaire_id": 6,
        "start_date": datetime.combine(START_DATE + timedelta(days=6), datetime.min.time().replace(hour=8)),  # Slot 12 (Jour 7 AM)
        "duration_hours": 17.5,  # 5 slots
        "name": "Design Zeta"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 5,
        "affaire_id": 7,
        "start_date": datetime.combine(START_DATE + timedelta(days=7), datetime.min.time().replace(hour=8)),  # Slot 14 (Jour 8 AM)
        "duration_hours": 14,  # 4 slots
        "name": "Debug Eta"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 5,
        "affaire_id": 8,
        "start_date": datetime.combine(START_DATE + timedelta(days=9), datetime.min.time().replace(hour=8)),  # Slot 18 (Jour 10 AM)
        "duration_hours": 10.5,  # 3 slots
        "name": "Deploy Theta"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 6,
        "affaire_id": 2,
        "start_date": datetime.combine(START_DATE + timedelta(days=10), datetime.min.time().replace(hour=8)),  # Slot 20 (Jour 11 AM)
        "duration_hours": 14,  # 4 slots
        "name": "Setup Beta"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 6,
        "affaire_id": 7,
        "start_date": datetime.combine(START_DATE + timedelta(days=12), datetime.min.time().replace(hour=8)),  # Slot 24 (Jour 13 AM)
        "duration_hours": 10.5,  # 3 slots
        "name": "Test Eta"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 7,
        "affaire_id": 3,
        "start_date": datetime.combine(START_DATE + timedelta(days=13), datetime.min.time().replace(hour=15)),  # Slot 27 (Jour 14 PM)
        "duration_hours": 17.5,  # 5 slots
        "name": "Code Gamma"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 8,
        "affaire_id": 4,
        "start_date": datetime.combine(START_DATE + timedelta(days=15), datetime.min.time().replace(hour=8)),  # Slot 30 (Jour 16 AM)
        "duration_hours": 14,  # 4 slots
        "name": "QA Delta"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 9,
        "affaire_id": 5,
        "start_date": datetime.combine(START_DATE + timedelta(days=16), datetime.min.time().replace(hour=15)),  # Slot 33 (Jour 17 PM)
        "duration_hours": 10.5,  # 3 slots
        "name": "Doc Epsilon"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 9,
        "affaire_id": 1,
        "start_date": datetime.combine(START_DATE + timedelta(days=18), datetime.min.time().replace(hour=8)),  # Slot 36 (Jour 19 AM)
        "duration_hours": 14,  # 4 slots
        "name": "Review Alpha"
    },
    {
        "id": str(uuid.uuid4()),
        "operator_id": 10,
        "affaire_id": 6,
        "start_date": datetime.combine(START_DATE + timedelta(days=20), datetime.min.time().replace(hour=8)),  # Slot 40 (Jour 21 AM)
        "duration_hours": 21,  # 6 slots
        "name": "Arch Zeta"
    }
]

def date_to_slot(task_date):
    """Convertit une date/datetime en numéro de slot"""
    if isinstance(task_date, str):
        try:
            task_datetime = datetime.strptime(task_date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                task_datetime = datetime.strptime(task_date, "%Y-%m-%d")
            except ValueError:
                task_datetime = datetime.now()
    elif isinstance(task_date, datetime):
        task_datetime = task_date
    else:
        task_datetime = datetime.combine(task_date, datetime.min.time().replace(hour=8))
    
    task_date_only = task_datetime.date()
    days_diff = (task_date_only - START_DATE).days
    
    hour = task_datetime.hour
    is_pm = hour >= 15
    
    result_slot = days_diff * 2 + (1 if is_pm else 0)
    return result_slot

def hours_to_slots(hours):
    """Convertit un nombre d'heures en nombre de slots"""
    return int(round(hours / HALF_DAY_HOURS))

def slots_to_hours(slots):
    """Convertit un nombre de slots en heures"""
    return slots * HALF_DAY_HOURS

def slot_to_date(slot):
    """Convertit un numéro de slot en date et heure"""
    days_offset = slot // 2
    is_pm = slot % 2 == 1
    
    result_date = START_DATE + timedelta(days=days_offset)
    
    if is_pm:
        result_datetime = datetime.combine(result_date, datetime.min.time().replace(hour=15))
    else:
        result_datetime = datetime.combine(result_date, datetime.min.time().replace(hour=8))
    
    return result_datetime

def get_task_start_slot(task):
    """Récupère le slot de début d'une tâche"""
    return date_to_slot(task["start_date"])

def get_task_duration_slots(task):
    """Récupère la durée en slots d'une tâche"""
    return hours_to_slots(task["duration_hours"])

def update_task_from_slots(task, start_slot, duration_slots):
    """Met à jour une tâche avec des valeurs en slots"""
    start_datetime = slot_to_date(start_slot)
    duration_hours = slots_to_hours(duration_slots)
    
    task["start_date"] = start_datetime
    task["duration_hours"] = duration_hours

def get_affair_by_id(affaire_id):
    return next((affair for affair in AFFAIRS if affair["id"] == affaire_id), None)

def get_operator_by_id(operator_id):
    return next((operator for operator in OPERATORS if operator["id"] == operator_id), None)

def is_vacation_slot(slot):
    """Vérifie si un slot correspond à une date de congé"""
    slot_datetime = slot_to_date(slot)
    for vacation_date in VACATION_DATES:
        if (slot_datetime.date() == vacation_date.date() and 
            slot_datetime.hour == vacation_date.hour):
            return True
    return False

def is_absence_slot(operator_id, slot):
    """Vérifie si un slot correspond à une absence pour un opérateur donné"""
    operator = get_operator_by_id(operator_id)
    if not operator or "absences" not in operator:
        return False
    
    slot_datetime = slot_to_date(slot)
    for absence_date in operator["absences"]:
        if (slot_datetime.date() == absence_date.date() and 
            slot_datetime.hour == absence_date.hour):
            return True
    return False

def get_tasks_for_operator(operator_id):
    return [task for task in TASKS if task["operator_id"] == operator_id]

def check_collision(operator_id, start_slot, duration, exclude_task_id=None):
    """Vérifie s'il y a collision avec une autre tâche (retourne la première trouvée)"""
    tasks = get_tasks_for_operator(operator_id)
    for task in tasks:
        if exclude_task_id and task["id"] == exclude_task_id:
            continue
        task_start_slot = get_task_start_slot(task)
        task_duration_slots = get_task_duration_slots(task)
        task_end = task_start_slot + task_duration_slots
        new_end = start_slot + duration
        
        # Vérification de collision
        if not (new_end <= task_start_slot or start_slot >= task_end):
            return task
    return None

def get_all_colliding_tasks(operator_id, start_slot, duration, exclude_task_id=None):
    """Retourne toutes les tâches qui sont en collision avec la position donnée"""
    tasks = get_tasks_for_operator(operator_id)
    colliding_tasks = []
    
    for task in tasks:
        if exclude_task_id and task["id"] == exclude_task_id:
            continue
        task_start_slot = get_task_start_slot(task)
        task_duration_slots = get_task_duration_slots(task)
        task_end = task_start_slot + task_duration_slots
        new_end = start_slot + duration
        
        # Vérification de collision
        if not (new_end <= task_start_slot or start_slot >= task_end):
            colliding_tasks.append(task)
    
    return colliding_tasks

def push_all_colliding_tasks_right(operator_id, start_slot, duration, exclude_task_id=None):
    """Pousse toutes les tâches en collision vers la droite, en cascade
    
    Returns:
        bool: True si toutes les tâches ont pu être déplacées, False sinon
    """
    # Obtenir toutes les tâches de l'opérateur, exclure la tâche qu'on déplace
    all_tasks = get_tasks_for_operator(operator_id)
    if exclude_task_id:
        all_tasks = [task for task in all_tasks if task["id"] != exclude_task_id]
    
    # Trier par position de début
    all_tasks.sort(key=lambda x: get_task_start_slot(x))
    
    new_task_end = start_slot + duration
    
    # Trouver toutes les tâches qui sont réellement en collision avec la nouvelle position
    tasks_to_push = []
    for task in all_tasks:
        task_start = get_task_start_slot(task)
        task_duration = get_task_duration_slots(task)
        task_end = task_start + task_duration
        
        # Vérification de collision réelle : les deux tâches se chevauchent
        if not (new_task_end <= task_start or start_slot >= task_end):
            tasks_to_push.append(task)
    
    if not tasks_to_push:
        return True  # Aucune tâche à pousser
    
    # Trier les tâches en collision par position (de gauche à droite)
    tasks_to_push.sort(key=lambda x: get_task_start_slot(x))
    
    # Phase 1 : Déplacer les tâches en collision directe
    cascade_tasks = []
    current_position = new_task_end
    
    for task in tasks_to_push:
        new_position = current_position
        task_duration = get_task_duration_slots(task)
        
        # Vérifier si cette nouvelle position crée une collision avec d'autres tâches
        potential_collision = check_collision(operator_id, new_position, task_duration, task["id"])
        
        if potential_collision and potential_collision not in tasks_to_push:
            # Il y a une nouvelle collision, ajouter cette tâche à la cascade
            cascade_tasks.append(potential_collision)
        
        # Mettre à jour la position de cette tâche
        update_task_from_slots(task, new_position, task_duration)
        current_position = new_position + task_duration
    
    # Phase 2 : Gérer les tâches en cascade (récursivement)
    while cascade_tasks:
        next_cascade = []
        cascade_tasks.sort(key=lambda x: get_task_start_slot(x))
        
        for task in cascade_tasks:
            new_position = current_position
            task_duration = get_task_duration_slots(task)
            
            # Vérifier si on dépasse la limite
            if new_position + task_duration > NUM_SLOTS:
                return False  # Pas assez d'espace
            
            # Vérifier les nouvelles collisions
            potential_collision = check_collision(operator_id, new_position, task_duration, task["id"])
            
            if potential_collision and potential_collision not in tasks_to_push and potential_collision not in cascade_tasks:
                next_cascade.append(potential_collision)
            
            # Mettre à jour la position
            update_task_from_slots(task, new_position, task_duration)
            current_position = new_position + task_duration
        
        # Préparer la prochaine itération
        cascade_tasks = next_cascade
    
    return True

def handle_keyboard_push(task_id, direction):
    """Gère la poussée des tâches lors du déplacement au clavier"""
    try:
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return {"success": False, "error": "Tâche non trouvée"}
        
        operator_id = task["operator_id"]
        current_slot = get_task_start_slot(task)
        duration = get_task_duration_slots(task)
        
        if direction == "left":
            new_slot = max(0, current_slot - 1)
            if new_slot != current_slot:
                # Vérifier s'il y a collision avant de déplacer
                collision = check_collision(operator_id, new_slot, duration, task_id)
                if collision:
                    # Essayer de pousser la tâche en collision vers la gauche
                    push_success = push_task_cascade(collision, "left", new_slot)
                    if not push_success:
                        # Si impossible de pousser, la tâche reste à sa position actuelle
                        return {"success": True, "new_slot": current_slot, "blocked": True}
                
                # Déplacer la tâche principale
                update_task_from_slots(task, new_slot, duration)
                
        elif direction == "right":
            new_slot = min(NUM_SLOTS - duration, current_slot + 1)
            if new_slot != current_slot:
                # Vérifier s'il y a collision avant de déplacer
                collision = check_collision(operator_id, new_slot, duration, task_id)
                if collision:
                    # Essayer de pousser la tâche en collision vers la droite
                    push_success = push_task_cascade(collision, "right", new_slot + duration)
                    if not push_success:
                        # Si impossible de pousser, la tâche reste à sa position actuelle
                        return {"success": True, "new_slot": current_slot, "blocked": True}
                
                # Déplacer la tâche principale
                update_task_from_slots(task, new_slot, duration)
        
        final_slot = get_task_start_slot(task)
        return {"success": True, "new_slot": final_slot}
        
    except Exception as e:
        return {"success": False, "error": f"Erreur lors du déplacement: {str(e)}"}

def push_task_cascade(task, direction, boundary_position):
    """Pousse une tâche dans une direction en utilisant une approche itérative
    
    Args:
        task: La tâche à pousser
        direction: 'left' ou 'right'
        boundary_position: Position de fin (pour left) ou de début (pour right) à respecter
    
    Returns:
        bool: True si le déplacement est possible, False sinon
    """
    operator_id = task["operator_id"]
    tasks_to_move = []
    
    # Collecter toutes les tâches qui doivent être déplacées
    current_task = task
    current_boundary = boundary_position
    
    max_iterations = 20  # Protection contre les boucles infinies
    iteration = 0
    
    while current_task and iteration < max_iterations:
        iteration += 1
        duration = get_task_duration_slots(current_task)
        
        if direction == "left":
            # Calculer la nouvelle position
            new_start_slot = current_boundary - duration
            # Vérifier si on dépasse le bord gauche
            if new_start_slot < 0:
                return False
        else:  # direction == "right"
            # Calculer la nouvelle position
            new_start_slot = current_boundary
            # Vérifier si on dépasse le bord droit
            if new_start_slot + duration > NUM_SLOTS:
                return False
        
        # Ajouter la tâche à la liste des tâches à déplacer
        tasks_to_move.append({
            "task": current_task,
            "new_position": new_start_slot
        })
        
        # Chercher la prochaine collision
        next_collision = check_collision(operator_id, new_start_slot, duration, current_task["id"])
        
        if next_collision:
            current_task = next_collision
            if direction == "left":
                current_boundary = new_start_slot
            else:  # right
                current_boundary = new_start_slot + duration
        else:
            break
    
    # Si on arrive ici, tous les déplacements sont possibles
    # Déplacer toutes les tâches collectées
    for move_info in tasks_to_move:
        task_duration = get_task_duration_slots(move_info["task"])
        update_task_from_slots(move_info["task"], move_info["new_position"], task_duration)
    
    if iteration >= max_iterations:
        return False
    
    return True

def resolve_all_collisions_on_operator(operator_id):
    """Résout toutes les collisions sur un opérateur en poussant les tâches vers la droite"""
    tasks = get_tasks_for_operator(operator_id)
    
    # Si moins de 2 tâches, pas de collision possible
    if len(tasks) < 2:
        return
    
    max_iterations = 50  # Éviter les boucles infinies
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        collision_found = False
        
        # Trier les tâches par position de début
        tasks.sort(key=lambda x: get_task_start_slot(x))
        
        # Vérifier chaque paire de tâches adjacentes
        for i in range(len(tasks) - 1):
            task1 = tasks[i]
            task2 = tasks[i + 1]
            
            task1_start_slot = get_task_start_slot(task1)
            task1_duration_slots = get_task_duration_slots(task1)
            task2_start_slot = get_task_start_slot(task2)
            task2_duration_slots = get_task_duration_slots(task2)
            
            task1_end = task1_start_slot + task1_duration_slots
            
            # Si les tâches se chevauchent (collision réelle)
            if task1_end > task2_start_slot:
                collision_found = True
                
                # Calculer l'espace nécessaire pour déplacer task2
                needed_slot = task1_end
                max_possible_slot = NUM_SLOTS - task2_duration_slots
                
                # Déplacer task2 vers la droite
                if needed_slot <= max_possible_slot:
                    update_task_from_slots(task2, needed_slot, task2_duration_slots)
                else:
                    # Si pas assez de place à droite, déplacer task1 vers la gauche
                    needed_slot_left = task2_start_slot - task1_duration_slots
                    if needed_slot_left >= 0:
                        update_task_from_slots(task1, needed_slot_left, task1_duration_slots)
                    else:
                        # Cas extrême : déplacer task2 le plus loin possible à droite
                        update_task_from_slots(task2, max_possible_slot, task2_duration_slots)
                
                break  # Recommencer la vérification depuis le début
        
        # Si aucune collision trouvée, on a terminé
        if not collision_found:
            break

@app.route('/')
def index():
    # Générer les en-têtes de colonnes (NUM_SLOTS demi-journées)
    time_slots = []
    months = []
    weeks = []
    days = []
    start_date = datetime.combine(START_DATE, datetime.min.time()).replace(hour=8, minute=0, second=0, microsecond=0)
    
    current_month = None
    current_week = None
    current_day = None
    
    for i in range(NUM_SLOTS):
        day_offset = i // 2
        is_morning = i % 2 == 0
        
        current_date = start_date + timedelta(days=day_offset)
        time_label = "AM" if is_morning else "PM"
        
        # Pour les mois
        month_year = current_date.strftime("%m/%Y")
        if month_year != current_month:
            current_month = month_year
            months.append({
                "name": month_year,
                "start_slot": i,
                "span": 0  # Sera calculé plus tard
            })
        if months:
            months[-1]["span"] += 1
        
        # Pour les semaines (vrais numéros de semaines ISO avec année)
        week_number = current_date.isocalendar()[1]  # Numéro de semaine ISO
        week_year = current_date.isocalendar()[0]    # Année ISO (peut différer de l'année civile)
        week_key = f"{week_year}-W{week_number:02d}"
        if week_key != current_week:
            current_week = week_key
            weeks.append({
                "name": f"S{week_number:02d}/{week_year}",
                "start_slot": i,
                "span": 0
            })
        if weeks:
            weeks[-1]["span"] += 1
            
        # Pour les jours
        day_key = current_date.strftime("%d/%m")
        if is_morning:  # Nouveau jour
            days.append({
                "date": day_key,
                "start_slot": i,
                "day_name": current_date.strftime("%a")  # Ajouter le nom du jour
            })
        
        time_slots.append({
            "slot": i,
            "date": current_date.strftime("%d/%m"),
            "period": time_label,
            "day_name": current_date.strftime("%a"),
            "is_vacation": is_vacation_slot(i)  # Ajouter l'info de congé
        })
    
    # Convertir les tâches pour l'affichage (compatibilité avec le template)
    display_tasks = []
    for task in TASKS:
        display_task = task.copy()
        display_task["start_slot"] = get_task_start_slot(task)
        display_task["duration"] = get_task_duration_slots(task)
        display_tasks.append(display_task)
    
    # Pré-calculer les informations d'absence pour chaque opérateur et slot
    operator_absences = {}
    for operator in OPERATORS:
        operator_absences[operator["id"]] = {}
        for i in range(NUM_SLOTS):
            operator_absences[operator["id"]][i] = is_absence_slot(operator["id"], i)
    
    return render_template('index.html', 
                         operators=OPERATORS, 
                         time_slots=time_slots,
                         months=months,
                         weeks=weeks,
                         days=days,
                         tasks=display_tasks, 
                         affairs=AFFAIRS,
                         operator_absences=operator_absences,
                         slot_width=SLOT_WIDTH,
                         row_height=ROW_HEIGHT,
                         header_height=HEADER_HEIGHT,
                         num_slots=NUM_SLOTS,
                         start_date=START_DATE,
                         day_duration_hours=DAY_DURATION_HOURS)

@app.route('/move_task', methods=['POST'])
def move_task():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Données JSON manquantes"})
        
        task_id = data.get('task_id')
        new_operator_id_raw = data.get('operator_id')
        new_start_slot_raw = data.get('start_slot')
        
        if not task_id:
            return jsonify({"success": False, "error": "ID de tâche manquant"})
        
        if new_operator_id_raw is None:
            return jsonify({"success": False, "error": "ID d'opérateur manquant"})
        
        if new_start_slot_raw is None:
            return jsonify({"success": False, "error": "Slot de début manquant"})
        
        try:
            new_operator_id = int(new_operator_id_raw)
            new_start_slot = int(new_start_slot_raw)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Paramètres invalides"})
        
        # Trouver la tâche
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return jsonify({"success": False, "error": "Tâche non trouvée"})
        
        # Sauvegarder l'ancienne position pour pouvoir revenir en arrière si nécessaire
        old_operator_id = task["operator_id"]
        old_start_slot = get_task_start_slot(task)
        duration_slots = get_task_duration_slots(task)
        
        # Utiliser la nouvelle fonction qui pousse toutes les tâches en collision vers la droite
        push_success = push_all_colliding_tasks_right(new_operator_id, new_start_slot, duration_slots, task_id)
        
        if not push_success:
            # Si impossible de pousser toutes les tâches vers la droite, ne pas déplacer la tâche
            return jsonify({"success": False, "error": "Impossible de placer la tâche : pas assez d'espace"})
        
        # Mettre à jour la tâche uniquement si le déplacement des collisions a réussi
        task["operator_id"] = new_operator_id
        update_task_from_slots(task, new_start_slot, duration_slots)
        
        # Résoudre les éventuelles collisions résiduelles sur le nouvel opérateur seulement si nécessaire
        if old_operator_id != new_operator_id:
            # Vérifier s'il y a réellement des collisions avant de résoudre
            collision = check_collision(new_operator_id, new_start_slot, duration_slots, task_id)
            if collision:
                resolve_all_collisions_on_operator(new_operator_id)
        
        # TODO: Ici vous pourrez ajouter la mise à jour PostgreSQL
        # update_task_in_database(task_id, new_operator_id, task["start_date"], task["duration_hours"])
        
        return jsonify({"success": True})
    
    except Exception as e:
        return jsonify({"success": False, "error": f"Erreur serveur: {str(e)}"})

@app.route('/keyboard_move_task', methods=['POST'])
def keyboard_move_task():
    """Endpoint spécifique pour les déplacements au clavier avec poussée"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        direction = data.get('direction')  # 'left', 'right', 'up', 'down'
        
        if direction in ['left', 'right']:
            result = handle_keyboard_push(task_id, direction)
            if result["success"]:
                # TODO: Ici vous pourrez ajouter la mise à jour PostgreSQL pour toutes les tâches modifiées
                # update_tasks_in_database()
                pass
            return jsonify(result)
        
        elif direction in ['up', 'down']:
            # Déplacement vertical standard
            task = next((t for t in TASKS if t["id"] == task_id), None)
            if not task:
                return jsonify({"success": False, "error": "Tâche non trouvée"})
            
            current_operator_id = task["operator_id"]
            
            if direction == 'up':
                new_operator_id = current_operator_id - 1 if current_operator_id > 1 else current_operator_id
            else:  # down
                new_operator_id = current_operator_id + 1 if current_operator_id < len(OPERATORS) else current_operator_id
            
            if new_operator_id != current_operator_id:
                task["operator_id"] = new_operator_id
                
                # Résoudre toutes les collisions sur le nouvel opérateur seulement si nécessaire
                start_slot = get_task_start_slot(task)
                duration_slots = get_task_duration_slots(task)
                collision = check_collision(new_operator_id, start_slot, duration_slots, task_id)
                if collision:
                    resolve_all_collisions_on_operator(new_operator_id)
                
                # TODO: Mise à jour PostgreSQL
                # update_task_in_database(task_id, new_operator_id, task["start_date"], task["duration_hours"])
            
            return jsonify({"success": True, "new_operator_id": task["operator_id"]})
        
        return jsonify({"success": False, "error": "Direction invalide"})
        
    except Exception as e:
        return jsonify({"success": False, "error": f"Erreur serveur: {str(e)}"})

@app.route('/resize_task', methods=['POST'])
def resize_task():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Données JSON manquantes"})
        
        task_id = data.get('task_id')
        new_duration_raw = data.get('duration')
        
        # Log avant traitement
        print(f"� RESIZE_TASK reçu - task_id: {task_id}, nouvelle durée: {new_duration_raw}")
        
        if not task_id:
            return jsonify({"success": False, "error": "ID de tâche manquant"})
        
        if new_duration_raw is None:
            return jsonify({"success": False, "error": "Durée manquante"})
        
        try:
            new_duration_slots = int(new_duration_raw)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Durée invalide"})
        
        if new_duration_slots <= 0:
            return jsonify({"success": False, "error": "La durée doit être positive"})
        
        # Trouver la tâche
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return jsonify({"success": False, "error": "Tâche non trouvée"})
        
        # Sauvegarder l'ancienne durée pour comparaison
        old_duration_slots = get_task_duration_slots(task)
        
        # Mettre à jour la durée
        start_slot = get_task_start_slot(task)
        update_task_from_slots(task, start_slot, new_duration_slots)
        
        # Résoudre toutes les collisions créées par le redimensionnement seulement si nécessaire
        collision = check_collision(task["operator_id"], start_slot, new_duration_slots, task_id)
        if collision:
            resolve_all_collisions_on_operator(task["operator_id"])
        
        # Log après traitement
        print(f"📥 RESIZE_TASK traité - Durée changée de {old_duration_slots} à {new_duration_slots} slots")
        
        return jsonify({"success": True})
    
    except Exception as e:
        print(f"❌ Erreur dans resize_task: {str(e)}")
        return jsonify({"success": False, "error": f"Erreur serveur: {str(e)}"})

@app.route('/resize_and_move_task', methods=['POST'])
def resize_and_move_task():
    """Endpoint combiné pour modifier à la fois la position et la durée d'une tâche (left resize)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Données JSON manquantes"})
        
        task_id = data.get('task_id')
        operator_id = data.get('operator_id')
        new_start_slot = data.get('start_slot')
        new_duration_raw = data.get('duration')
        
        # Log avant traitement
        print(f"🔄 RESIZE_AND_MOVE_TASK reçu - task_id: {task_id}, operator: {operator_id}, start_slot: {new_start_slot}, durée: {new_duration_raw}")
        
        # Validation des paramètres
        if not task_id:
            return jsonify({"success": False, "error": "ID de tâche manquant"})
        
        if operator_id is None:
            return jsonify({"success": False, "error": "ID opérateur manquant"})
        
        if new_start_slot is None:
            return jsonify({"success": False, "error": "Slot de départ manquant"})
        
        if new_duration_raw is None:
            return jsonify({"success": False, "error": "Durée manquante"})
        
        try:
            new_start_slot = int(new_start_slot)
            new_duration_slots = int(new_duration_raw)
            operator_id = int(operator_id)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Paramètres numériques invalides"})
        
        if new_start_slot < 0:
            return jsonify({"success": False, "error": "Le slot de départ doit être positif"})
        
        if new_duration_slots <= 0:
            return jsonify({"success": False, "error": "La durée doit être positive"})
        
        # Trouver la tâche
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return jsonify({"success": False, "error": "Tâche non trouvée"})
        
        # Sauvegarder les anciennes valeurs pour comparaison
        old_start_slot = get_task_start_slot(task)
        old_duration_slots = get_task_duration_slots(task)
        old_operator_id = task["operator_id"]
        
        # Mettre à jour la tâche avec les nouvelles position et durée
        task["operator_id"] = operator_id
        update_task_from_slots(task, new_start_slot, new_duration_slots)
        
        # Résoudre toutes les collisions créées par le déplacement/redimensionnement
        collision = check_collision(operator_id, new_start_slot, new_duration_slots, task_id)
        if collision:
            resolve_all_collisions_on_operator(operator_id)
        
        # Résoudre aussi les collisions sur l'ancien opérateur si différent
        if old_operator_id != operator_id:
            resolve_all_collisions_on_operator(old_operator_id)
        
        # Log après traitement
        print(f"📥 RESIZE_AND_MOVE_TASK traité - Position: {old_start_slot}→{new_start_slot}, Durée: {old_duration_slots}→{new_duration_slots} slots")
        
        return jsonify({"success": True})
    
    except Exception as e:
        print(f"❌ Erreur dans resize_and_move_task: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/get_planning_data')
def get_planning_data():
    # Convertir les tâches pour l'affichage (même logique que dans index())
    display_tasks = []
    for task in TASKS:
        display_task = task.copy()
        start_slot = get_task_start_slot(task)
        duration_slots = get_task_duration_slots(task)
        display_task["start_slot"] = start_slot
        display_task["duration"] = duration_slots
        display_tasks.append(display_task)
    
    return jsonify({
        "tasks": display_tasks,
        "operators": OPERATORS,
        "affairs": AFFAIRS
    })

@app.route('/debug_tasks')
def debug_tasks():
    """Endpoint de debug pour vérifier l'état des tâches"""
    debug_info = []
    for task in TASKS:
        debug_info.append({
            "name": task["name"],
            "operator_id": task["operator_id"],
            "start_date": str(task["start_date"]),
            "duration_hours": task["duration_hours"],
            "calculated_slot": get_task_start_slot(task),
            "calculated_duration_slots": get_task_duration_slots(task)
        })
    
    return jsonify(debug_info)

@app.route('/debug_html')
def debug_html():
    """Endpoint de debug pour vérifier le rendu HTML des tâches"""
    # Convertir les tâches pour l'affichage (même logique que dans index())
    display_tasks = []
    for task in TASKS:
        display_task = task.copy()
        display_task["start_slot"] = get_task_start_slot(task)
        display_task["duration"] = get_task_duration_slots(task)
        # Ajouter des informations de debug
        display_task["start_date_str"] = str(task["start_date"])
        display_task["start_date_iso"] = task["start_date"].isoformat()
        display_tasks.append(display_task)
    
    return jsonify(display_tasks)

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
