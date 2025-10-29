from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
from datetime import datetime, timedelta, date
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import os
import pytz
import math

# # Configuration du chemin Odoo
# ODOO_PATH = '/opt/odoo14'
# if ODOO_PATH not in sys.path:
#     sys.path.insert(0, ODOO_PATH)

# # Configuration des addons Odoo (ajustez selon votre configuration)
# ODOO_ADDONS_PATHS = [
#     '/opt/odoo14/addons',
#     '/home/tony/Documents/Développement/dev_odoo/14.0/bsa'  # Chemin vers vos addons personnalisés
# ]

try:
    from config import DATABASE_CONFIG, DATABASE_BASE_CONFIG, DATABASES
except ImportError:
    sys.exit(1)

app = Flask(__name__)

# Configuration de base de données actuelle
CURRENT_DATABASE_CONFIG = DATABASE_CONFIG.copy()
CURRENT_DATABASE_NAME = ""
CURRENT_DATABASE_URL_ODOO = ""
CURRENT_DATABASE_URL_TACHE_ODOO = ""
CURRENT_PLANNING_ID = None
CURRENT_PLANNING_END_DATE = None  # Date fin planning (date)

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
NUM_SLOTS = 90  # Par défaut, sera recalculé après sélection d'un planning

# Nouveaux paramètres
#START_DATE =  (datetime.now() - timedelta(days=30)).date() # datetime.now().date()  # Date de début du planning (date du jour par défaut)
START_DATE =  datetime.now().date()  # Date de début du planning (date du jour par défaut)
DAY_DURATION_HOURS = 7  # Durée d'une journée en heures
HALF_DAY_HOURS = DAY_DURATION_HOURS / 2  # Durée d'une demi-journée (AM ou PM)

# Fonctions de base de données
def get_db_connection():
    """Établit une connexion à la base PostgreSQL"""
    try:
        conn = psycopg2.connect(**CURRENT_DATABASE_CONFIG)
        return conn
    except psycopg2.Error as e:
        return None

def load_plannings_from_db():
    """Charge les plannings depuis la base PostgreSQL avec le nombre de tâches et d'affaires"""
    try:
        conn = get_db_connection()
        if not conn:
            raise Exception("Impossible de se connecter à la base de données PostgreSQL")
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT p.id, p.name,
                       COUNT(DISTINCT t.id) as tache_count,
                       COUNT(DISTINCT a.id) as affaire_count
                FROM is_gestion_tache_planning p
                LEFT JOIN is_gestion_tache t ON t.planning_id = p.id
                LEFT JOIN is_gestion_tache_affaire a ON a.planning_id = p.id
                WHERE p.active=true
                GROUP BY p.id, p.name
                ORDER BY p.name
            """)
            
            rows = cursor.fetchall()
            plannings = []
            
            for row in rows:
                plannings.append({
                    "id": row['id'],
                    "name": row['name'],
                    "tache_count": row['tache_count'] or 0,
                    "affaire_count": row['affaire_count'] or 0
                })
            
            conn.close()
            return plannings
            
    except Exception as e:
        raise Exception(f"Erreur lors du chargement des plannings depuis la base de données: {str(e)}")

def load_affaires_from_db(planning_id=None):
    """Charge les affaires depuis la base PostgreSQL"""
    try:
        conn = get_db_connection()
        if not conn:
            raise Exception("Impossible de se connecter à la base de données PostgreSQL")
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            affaires = []
            if planning_id:
                cursor.execute("""
                    SELECT id, name, color 
                    FROM is_gestion_tache_affaire 
                    WHERE planning_id = %s
                    ORDER BY name
                """, (planning_id,))
           
            
                rows = cursor.fetchall()
                
                for i, row in enumerate(rows):
                    affaires.append({
                        "id": row['id'],
                        "name": row['name'],
                        "color": row['color'] if row['color'] else "#808080"  # Couleur par défaut si NULL
                    })
                
            conn.close()
            return affaires
            
    except Exception as e:
        raise Exception(f"Erreur lors du chargement des affaires depuis la base de données: {str(e)}")


def get_type_donnees(cr,planning_id=None):
    type_donnees = False
    cr.execute("SELECT id,type_donnees FROM is_gestion_tache_planning WHERE id=%s"%planning_id)
    rows= cr.fetchall()
    for  row in rows:
        type_donnees = row['type_donnees']
    return type_donnees


def load_operators_from_db(planning_id=None):
    """Charge les opérateurs depuis la base PostgreSQL"""
    operators = []
    if planning_id:
        cnx = get_db_connection()
        if not cnx:
            raise Exception("Impossible de se connecter à la base de données PostgreSQL")
        cr = cnx.cursor(cursor_factory=RealDictCursor)
        type_donnees = get_type_donnees(cr,planning_id)
        # cr.execute("SELECT id,type_donnees FROM is_gestion_tache_planning WHERE id=%s"%planning_id)
        # rows= cr.fetchall()
        # type_donnees = False
        # for  row in rows:
        #     type_donnees = row['type_donnees']
        if type_donnees:
            if type_donnees=='operation':
                cr.execute("""
                    SELECT op.operator_id, he.name
                    FROM is_gestion_tache_operateur op join hr_employee he on op.operator_id=he.id 
                    WHERE planning_id = %s
                    ORDER BY name
                """, (planning_id,))
                rows = cr.fetchall()
                for i, row in enumerate(rows):
                    operators.append({
                        "id": row['operator_id'],
                        "name": row['name'],
                        "absences": []
                    })
            if type_donnees=='of':
                cr.execute("""
                    SELECT w.workcenter_id,mw.name
                    FROM is_gestion_tache_workcenter w join mrp_workcenter mw on w.workcenter_id=mw.id 
                    WHERE planning_id = %s
                    ORDER BY name
                """, (planning_id,))
                rows = cr.fetchall()
                for i, row in enumerate(rows):
                    operators.append({
                        "id": row['workcenter_id'],
                        "name": row['name'],
                        "absences": []
                    })
    cnx.close()
    return operators





def load_tasks_from_db(planning_id=None):
    """Charge les tâches depuis la base PostgreSQL"""
    tasks = []
    if planning_id:
        cnx = get_db_connection()
        if not cnx:
            raise Exception("Impossible de se connecter à la base de données PostgreSQL")
        utc_tz = pytz.UTC
        paris_tz = pytz.timezone('Europe/Paris')
        cr = cnx.cursor(cursor_factory=RealDictCursor)
        type_donnees = get_type_donnees(cr,planning_id)
        rows=False
        if type_donnees=='operation':
            cr.execute("""
                SELECT 
                    t.id, t.name, t.operator_id, t.affaire_id, t.start_date, t.duration_hours,
                    t.operation_id, t.product_qty, t.production_id, t.is_derniere_date_prevue,
                    l.name AS operation_name,
                    mp.is_employe_ids_txt
                FROM is_gestion_tache t
                LEFT JOIN is_ordre_travail_line l ON l.id = t.operation_id
                LEFT JOIN mrp_production mp ON mp.id = t.production_id
                WHERE t.planning_id = %s
                ORDER BY t.start_date, t.operator_id
            """, (planning_id,))
            rows = cr.fetchall()


        if type_donnees=='of':
            cr.execute("""
                SELECT 
                    t.id, t.name, 
                    t.workcenter_id as operator_id, 
                    t.affaire_id, t.start_date, t.duration_hours,
                    t.operation_id, t.product_qty, t.production_id, t.is_derniere_date_prevue,
                    null AS operation_name,
                    mp.is_employe_ids_txt
                FROM is_gestion_tache t 
                LEFT JOIN mrp_production mp ON mp.id = t.production_id
                WHERE t.planning_id = %s
                ORDER BY t.start_date, t.operator_id
            """, (planning_id,))
            rows = cr.fetchall()





        if type_donnees and rows:

            for i, row in enumerate(rows):

                # Convertir l'heure UTC en heure de Paris
                start_date_utc = row['start_date']
                if start_date_utc.tzinfo is None:
                    # Si pas de timezone, on assume que c'est UTC
                    start_date_utc = utc_tz.localize(start_date_utc)
                elif start_date_utc.tzinfo != utc_tz:
                    # Convertir vers UTC si ce n'est pas déjà le cas
                    start_date_utc = start_date_utc.astimezone(utc_tz)
                
                # Convertir vers l'heure de Paris
                start_date_paris = start_date_utc.astimezone(paris_tz)
                
                # Déterminer le slot selon la logique : avant 12H = AM, après 12H = PM
                paris_hour = start_date_paris.hour
                if paris_hour < 12:
                    # Slot AM (8H)
                    adjusted_start_date = start_date_paris.replace(hour=8, minute=0, second=0, microsecond=0)
                else:
                    # Slot PM (14H)
                    adjusted_start_date = start_date_paris.replace(hour=14, minute=0, second=0, microsecond=0)
                
                # Convertir en datetime naïf (sans timezone) pour compatibilité avec le reste du code
                adjusted_start_date = adjusted_start_date.replace(tzinfo=None)
                
                # Convertir les données de la base vers le format attendu par l'application
                task = {
                    "id": str(row['id']),  # Convertir en string pour compatibilité
                    "operator_id": row['operator_id'],
                    "affaire_id": row['affaire_id'],
                    "start_date": adjusted_start_date,  # Utiliser la date ajustée
                    "duration_hours": float(row['duration_hours']),  # S'assurer que c'est un float
                    "name": row['name'],
                    "operation_id": row.get('operation_id'),
                    "operation_name": row.get('operation_name'),
                    "product_qty": row.get('product_qty'),
                    "is_employe_ids_txt": row.get('is_employe_ids_txt'),
                    "is_derniere_date_prevue": row.get('is_derniere_date_prevue')
                }
                tasks.append(task)
            
            cr.close()
        return tasks
            




# def load_tasks_from_db(planning_id=None):
#     """Charge les tâches depuis la base PostgreSQL"""
#     try:
#         conn = get_db_connection()
#         if not conn:
#             raise Exception("Impossible de se connecter à la base de données PostgreSQL")
        
#         # Définir les fuseaux horaires
#         utc_tz = pytz.UTC
#         paris_tz = pytz.timezone('Europe/Paris')

#         tasks = []
#         with conn.cursor(cursor_factory=RealDictCursor) as cursor:
#             if planning_id:
#                 cursor.execute("""
#                     SELECT 
#                         t.id, t.name, t.operator_id, t.affaire_id, t.start_date, t.duration_hours,
#                         t.operation_id,
#                         l.name AS operation_name
#                     FROM is_gestion_tache t
#                     LEFT JOIN is_ordre_travail_line l ON l.id = t.operation_id
#                     WHERE t.planning_id = %s
#                     ORDER BY t.start_date, t.operator_id
#                 """, (planning_id,))
#                 rows = cursor.fetchall()
#                 for i, row in enumerate(rows):

#                     # Convertir l'heure UTC en heure de Paris
#                     start_date_utc = row['start_date']
#                     if start_date_utc.tzinfo is None:
#                         # Si pas de timezone, on assume que c'est UTC
#                         start_date_utc = utc_tz.localize(start_date_utc)
#                     elif start_date_utc.tzinfo != utc_tz:
#                         # Convertir vers UTC si ce n'est pas déjà le cas
#                         start_date_utc = start_date_utc.astimezone(utc_tz)
                    
#                     # Convertir vers l'heure de Paris
#                     start_date_paris = start_date_utc.astimezone(paris_tz)
                    
#                     # Déterminer le slot selon la logique : avant 12H = AM, après 12H = PM
#                     paris_hour = start_date_paris.hour
#                     if paris_hour < 12:
#                         # Slot AM (8H)
#                         adjusted_start_date = start_date_paris.replace(hour=8, minute=0, second=0, microsecond=0)
#                     else:
#                         # Slot PM (14H)
#                         adjusted_start_date = start_date_paris.replace(hour=14, minute=0, second=0, microsecond=0)
                    
#                     # Convertir en datetime naïf (sans timezone) pour compatibilité avec le reste du code
#                     adjusted_start_date = adjusted_start_date.replace(tzinfo=None)
                    
#                     # Convertir les données de la base vers le format attendu par l'application
#                     task = {
#                         "id": str(row['id']),  # Convertir en string pour compatibilité
#                         "operator_id": row['operator_id'],
#                         "affaire_id": row['affaire_id'],
#                         "start_date": adjusted_start_date,  # Utiliser la date ajustée
#                         "duration_hours": float(row['duration_hours']),  # S'assurer que c'est un float
#                         "name": row['name'],
#                         "operation_id": row.get('operation_id'),
#                         "operation_name": row.get('operation_name')
#                     }
                    
#                     tasks.append(task)
            
#             conn.close()
#             return tasks
            
#     except Exception as e:
#         raise Exception(f"Erreur lors du chargement des tâches depuis la base de données: {str(e)}")

def get_current_planning_type_donnees():
    """Récupère le type de données du planning actuel"""
    if not CURRENT_PLANNING_ID:
        return None
    try:
        conn = get_db_connection()
        if not conn:
            return None
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT type_donnees FROM is_gestion_tache_planning WHERE id = %s", (CURRENT_PLANNING_ID,))
            result = cursor.fetchone()
            conn.close()
            return result['type_donnees'] if result else None
    except Exception:
        return None

def update_task_in_database(task_id, operator_id, start_date, duration_hours):
    """Met à jour une tâche dans la base de données PostgreSQL"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        # Définir les fuseaux horaires
        paris_tz = pytz.timezone('Europe/Paris')
        utc_tz = pytz.UTC
        
        # Convertir la date de l'application vers UTC pour stockage en base
        # start_date dans l'application est naive et représente l'heure locale (Paris)
        if start_date.tzinfo is None:
            # Utiliser localize() avec normalize() pour gérer correctement l'heure d'été
            start_date_paris = paris_tz.normalize(paris_tz.localize(start_date))
        else:
            # Si elle a déjà une timezone, la convertir vers Paris
            start_date_paris = start_date.astimezone(paris_tz)
        
        # Convertir vers UTC pour stockage en base
        start_date_utc = start_date_paris.astimezone(utc_tz)
        
        # Déterminer le champ à mettre à jour selon le type de données
        type_donnees = get_current_planning_type_donnees()
        operator_field = "workcenter_id" if type_donnees == 'of' else "operator_id"
        
        with conn.cursor() as cursor:
            cursor.execute(f"""
                UPDATE is_gestion_tache 
                SET {operator_field} = %s, start_date = %s, duration_hours = %s
                WHERE id = %s
            """, (operator_id, start_date_utc, duration_hours, int(task_id)))
            
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            
            return rows_affected > 0
            
    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        return False

def update_multiple_tasks_in_database(tasks_data):
    """Met à jour plusieurs tâches dans la base de données en une transaction"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        # Définir les fuseaux horaires
        paris_tz = pytz.timezone('Europe/Paris')
        utc_tz = pytz.UTC
        
        # Déterminer le champ à mettre à jour selon le type de données
        type_donnees = get_current_planning_type_donnees()
        operator_field = "workcenter_id" if type_donnees == 'of' else "operator_id"
        
        with conn.cursor() as cursor:
            for task_data in tasks_data:
                task_id = task_data['id']
                operator_id = task_data['operator_id']
                start_date = task_data['start_date']
                duration_hours = task_data['duration_hours']
                
                # Convertir la date de l'application vers UTC pour stockage en base
                # start_date dans l'application est naive et représente l'heure locale (Paris)
                if start_date.tzinfo is None:
                    # Utiliser localize() avec normalize() pour gérer correctement l'heure d'été
                    start_date_paris = paris_tz.normalize(paris_tz.localize(start_date))
                else:
                    # Si elle a déjà une timezone, la convertir vers Paris
                    start_date_paris = start_date.astimezone(paris_tz)
                
                # Convertir vers UTC pour stockage en base
                start_date_utc = start_date_paris.astimezone(utc_tz)
                
                cursor.execute(f"""
                    UPDATE is_gestion_tache 
                    SET {operator_field} = %s, start_date = %s, duration_hours = %s
                    WHERE id = %s
                """, (operator_id, start_date_utc, duration_hours, int(task_id)))
            
            conn.commit()
            conn.close()
            return True
            
    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        return False

# Dates de congés (orange clair) - format datetime
# VACATION_DATES = [
#     datetime(2025, 8, 15, 8, 0),   # 15 août AM
#     datetime(2025, 8, 15, 14, 0),  # 15 août PM
#     datetime(2025, 8, 25, 8, 0),   # 25 août AM
#     datetime(2025, 8, 25, 14, 0),  # 25 août PM
# ]
VACATION_DATES = []

# Chargement dynamique des opérateurs depuis la base de données
# Les données seront chargées lors de la sélection de la base de données
OPERATORS = []
AFFAIRES = []
TASKS = []

# Utilitaire: générer les datetimes AM/PM pour une date (naïf, heure locale affichage)
def _halfday_datetimes(d: date):
    return [
        datetime(d.year, d.month, d.day, 8, 0, 0),
        datetime(d.year, d.month, d.day, 14, 0, 0),
    ]

def load_fermetures_from_db(planning_id=None):
    """Charge les fermetures (is_gestion_tache_fermeture) et met à jour:
    - VACATION_DATES: jours fermés globalement (tous les opérateurs ou enregistrements sans opérateur)
    - OPERATORS[i]['absences']: demi-journées d'absence pour chaque opérateur
    """
    global VACATION_DATES, OPERATORS
    VACATION_DATES = []
    if not planning_id:
        return

    try:
        conn = get_db_connection()
        if not conn:
            return
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT date_fermeture, operator_id
                FROM is_gestion_tache_fermeture
                WHERE planning_id = %s
                """,
                (planning_id,),
            )
            rows = cursor.fetchall()

        conn.close()

        if not rows:
            return

        # Indexer opérateurs pour set absences
        operator_ids = [op['id'] for op in OPERATORS] if OPERATORS else []
        operator_set = set(operator_ids)
        # Préparer map opérateur -> set(date)
        absences_by_operator = {op_id: set() for op_id in operator_ids}
        # Map date -> opérateurs ayant fermeture ce jour
        operators_by_date = {}

        for r in rows:
            d = r['date_fermeture']
            op_id = r.get('operator_id')
            # Normaliser d en type date
            if isinstance(d, datetime):
                d = d.date()
            if not isinstance(d, date):
                continue

            # Indexer par date les opérateurs concernés
            operators_by_date.setdefault(d, set())
            if op_id is None:
                # Enregistrement sans opérateur => fermeture globale ce jour
                # On marque tous les opérateurs comme absents et on tag en congé global
                if operator_ids:
                    for oid in operator_ids:
                        absences_by_operator.setdefault(oid, set()).add(d)
                # Tag global (sera transformé en AM/PM ci-dessous)
                operators_by_date[d] = set(operator_ids) if operator_ids else {None}
            else:
                operators_by_date[d].add(op_id)
                if op_id in absences_by_operator:
                    absences_by_operator[op_id].add(d)

        # Renseigner absences sur OPERATORS en AM/PM
        for op in OPERATORS:
            dates_for_op = absences_by_operator.get(op['id'], set())
            abs_halfdays = []
            for day in sorted(dates_for_op):
                abs_halfdays.extend(_halfday_datetimes(day))
            op['absences'] = abs_halfdays

        # Calcul des jours de congé global: jours couverts pour tous les opérateurs
        global_vacation_dates = []
        for d, ops in operators_by_date.items():
            if not operator_set:
                # S'il n'y a pas d'opérateurs chargés, considérer les jours sans opérateur comme globaux
                if ops == {None}:
                    global_vacation_dates.extend(_halfday_datetimes(d))
            else:
                if ops.issuperset(operator_set):
                    global_vacation_dates.extend(_halfday_datetimes(d))

        VACATION_DATES = global_vacation_dates

    except Exception:
        # En cas d'erreur, ne rien bloquer: garder listes vides
        VACATION_DATES = []






def calculate_planning_start_date(tasks):
    """Calcule la date de début du planning basée sur la première tâche"""
    if not tasks:
        return datetime.now().date()  # Si pas de tâches, utiliser la date actuelle
    
    # Trouver la date de la première tâche
    earliest_date = None
    for task in tasks:
        task_date = task.get('start_date')
        if task_date:
            if isinstance(task_date, datetime):
                task_date_only = task_date.date()
            elif isinstance(task_date, date):
                task_date_only = task_date
            else:
                continue
                
            if earliest_date is None or task_date_only < earliest_date:
                earliest_date = task_date_only
    
    return earliest_date if earliest_date else datetime.now().date()

def calculate_num_slots():
    """Calcule NUM_SLOTS en fonction de START_DATE, CURRENT_PLANNING_END_DATE et TASKS"""
    global START_DATE, NUM_SLOTS
    
    if CURRENT_PLANNING_END_DATE:
        days_inclusive = (CURRENT_PLANNING_END_DATE - START_DATE).days + 1
        required_slots = max(0, days_inclusive) * 2
        NUM_SLOTS = max(required_slots, 60)
    else:
        # Si pas de date de fin, calculer en fonction des tâches
        if TASKS:
            # Trouver la dernière tâche
            latest_date = START_DATE
            for task in TASKS:
                task_date = task.get('start_date')
                if task_date:
                    if isinstance(task_date, datetime):
                        task_date_only = task_date.date()
                    elif isinstance(task_date, date):
                        task_date_only = task_date
                    else:
                        continue
                    if task_date_only > latest_date:
                        latest_date = task_date_only
            
            # Ajouter quelques jours de marge après la dernière tâche
            days_inclusive = (latest_date - START_DATE).days + 1 + 7  # +7 jours de marge
            required_slots = days_inclusive * 2
            NUM_SLOTS = max(required_slots, 60)
        else:
            NUM_SLOTS = max(60, NUM_SLOTS)

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
    # Logique modifiée : avant 12H = AM (slot 0), après 12H = PM (slot 1)
    is_pm = hour >= 12
    
    result_slot = days_diff * 2 + (1 if is_pm else 0)
    return result_slot

def hours_to_slots(hours):
    """Convertit un nombre d'heures en nombre de slots (arrondi à l'entier supérieur)"""
    import math
    return int(math.ceil(hours / HALF_DAY_HOURS))

def slots_to_hours(slots):
    """Convertit un nombre de slots en heures"""
    return slots * HALF_DAY_HOURS

def slot_to_date(slot):
    """Convertit un numéro de slot en date et heure"""
    days_offset = slot // 2
    is_pm = slot % 2 == 1
    
    result_date = START_DATE + timedelta(days=days_offset)
    
    # Ajuster selon la nouvelle logique : AM = 8H, PM = 14H (mais basé sur 12H)
    if is_pm:
        result_datetime = datetime.combine(result_date, datetime.min.time().replace(hour=14))
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
    return next((affair for affair in AFFAIRES if affair["id"] == affaire_id), None)

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
def database_selection():
    """Page de sélection de la base de données"""
    return render_template('database_selection.html', databases=DATABASES)

@app.route('/select_database/<database_id>')
def select_database(database_id):
    """Sélectionne une base de données et redirige vers la sélection de planning"""
    global CURRENT_DATABASE_CONFIG, CURRENT_DATABASE_NAME, CURRENT_DATABASE_URL_ODOO, CURRENT_DATABASE_URL_TACHE_ODOO
    
    # Trouver la configuration de la base de données
    selected_db = next((db for db in DATABASES if db['id'] == database_id), None)
    if not selected_db:
        return render_template('database_selection.html', 
                             databases=DATABASES, 
                             error="Base de données non trouvée")
    
    # Mettre à jour la configuration de base de données
    CURRENT_DATABASE_CONFIG = {
        **DATABASE_BASE_CONFIG,
        'database': selected_db['database']
    }
    CURRENT_DATABASE_NAME = selected_db['name']
    CURRENT_DATABASE_URL_ODOO = selected_db.get('url_odoo', '')
    CURRENT_DATABASE_URL_TACHE_ODOO = selected_db.get('url_tache_odoo', '')
    
    try:
        # Tester la connexion à la base
        conn = get_db_connection()
        if not conn:
            raise Exception("Impossible de se connecter à la base de données")
        conn.close()
        
        # Rediriger vers la sélection de planning
        return redirect(url_for('planning_selection'))
        
    except Exception as e:
        return render_template('database_selection.html', 
                             databases=DATABASES, 
                             error=f"Erreur lors de la connexion à {selected_db['name']}: {str(e)}")

@app.route('/planning_selection')
def planning_selection():
    """Page de sélection du planning"""
    try:
        plannings = load_plannings_from_db()
        return render_template('planning_selection.html', 
                             plannings=plannings,
                             current_database=CURRENT_DATABASE_NAME,
                             current_database_url_odoo=CURRENT_DATABASE_URL_ODOO)
    except Exception as e:
        return render_template('planning_selection.html', 
                             plannings=[], 
                             current_database=CURRENT_DATABASE_NAME,
                             current_database_url_odoo=CURRENT_DATABASE_URL_ODOO,
                             error=str(e))

@app.route('/select_planning/<int:planning_id>')
def select_planning(planning_id):
    """Sélectionne un planning et redirige vers 'Gestion de tâches'"""
    global CURRENT_PLANNING_ID, OPERATORS, AFFAIRES, TASKS, CURRENT_PLANNING_END_DATE, NUM_SLOTS, START_DATE
    
    try:
        # Sauvegarder l'ID du planning
        CURRENT_PLANNING_ID = planning_id

        # Récupérer la date de fin du planning
        CURRENT_PLANNING_END_DATE = None
        try:
            conn = get_db_connection()
            if conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT date_fin_planning
                        FROM is_gestion_tache_planning
                        WHERE id = %s
                        """,
                        (planning_id,)
                    )
                    row = cursor.fetchone()
                    if row and row.get('date_fin_planning'):
                        # S'assurer d'avoir un objet date
                        dfp = row['date_fin_planning']
                        if isinstance(dfp, datetime):
                            dfp = dfp.date()
                        CURRENT_PLANNING_END_DATE = dfp
                conn.close()
        except Exception:
            CURRENT_PLANNING_END_DATE = None

        # Calculer NUM_SLOTS en fonction de la date du jour et de la date fin planning (2 slots/jour), min 60
        today = date.today()
        if CURRENT_PLANNING_END_DATE:
            days_inclusive = (CURRENT_PLANNING_END_DATE - today).days + 1
            required_slots = max(0, days_inclusive) * 2
            NUM_SLOTS = max(required_slots, 60)
        else:
            NUM_SLOTS = max(60, NUM_SLOTS)
        
        # Charger les données filtrées par planning
        AFFAIRES = load_affaires_from_db(planning_id)
        TASKS = load_tasks_from_db(planning_id)
        OPERATORS = load_operators_from_db(planning_id)
        
        # Calculer la date de début du planning basée sur la première tâche
        START_DATE = calculate_planning_start_date(TASKS)
        
        # Recalculer NUM_SLOTS en fonction de la nouvelle date de début
        calculate_num_slots()
        
        # Charger les fermetures (met à jour VACATION_DATES et les absences opérateurs)
        load_fermetures_from_db(planning_id)
        
        # Rediriger vers le planning
        return redirect(url_for('planning'))
        
    except Exception as e:
        return render_template('planning_selection.html', 
                             plannings=load_plannings_from_db(),
                             current_database=CURRENT_DATABASE_NAME,
                             error=f"Erreur lors du chargement du planning: {str(e)}")

@app.route('/planning')
def planning():
    """Page principale 'Gestion de tâches'"""
    # Récupérer le nom du planning sélectionné
    current_planning_name = "Planning non sélectionné"
    if CURRENT_PLANNING_ID:
        try:
            conn = get_db_connection()
            if conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT name FROM is_gestion_tache_planning WHERE id = %s", (CURRENT_PLANNING_ID,))
                    result = cursor.fetchone()
                    if result:
                        current_planning_name = result['name']
                conn.close()
        except Exception:
            pass  # En cas d'erreur, garder le nom par défaut
    
    # Générer les en-têtes de colonnes (NUM_SLOTS demi-journées)
    time_slots = []
    months = []
    weeks = []
    days = []
    start_date = datetime.combine(START_DATE, datetime.min.time()).replace(hour=8, minute=0, second=0, microsecond=0)
    
    current_month = None
    current_week = None
    current_day = None
    
    # Conversion des jours en français (une seule fois)
    day_names_fr = {
        'Monday': 'Lundi', 'Tuesday': 'Mardi', 'Wednesday': 'Mercredi',
        'Thursday': 'Jeudi', 'Friday': 'Vendredi', 'Saturday': 'Samedi', 'Sunday': 'Dimanche'
    }
    
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
            day_name_en = current_date.strftime("%A")  # Nom complet en anglais
            day_name_fr = day_names_fr.get(day_name_en, day_name_en)
            days.append({
                "date": day_key,
                "start_slot": i,
                "day_name": day_name_fr  # Nom du jour en français
            })
        
        # Utilisation du dictionnaire de conversion déclaré en début de boucle
        day_name_en = current_date.strftime("%A")  # Nom complet en anglais
        day_name_fr = day_names_fr.get(day_name_en, day_name_en)
        
        time_slots.append({
            "slot": i,
            "date": current_date.strftime("%d/%m"),
            "period": time_label,
            "day_name": day_name_fr,  # Nom du jour en français
            "is_vacation": is_vacation_slot(i)  # Ajouter l'info de congé
        })
    
    # Convertir les tâches pour l'affichage (compatibilité avec le template)
    display_tasks = []
    
    for i, task in enumerate(TASKS):
        # Vérifier si l'affaire existe
        affair = get_affair_by_id(task['affaire_id'])
        if not affair:
            # Utiliser l'affaire par défaut ou sauter cette tâche
            continue
        
        display_task = task.copy()
        display_task["start_slot"] = get_task_start_slot(task)
        display_task["duration"] = get_task_duration_slots(task)
        display_tasks.append(display_task)
    
    # Utiliser tous les opérateurs au lieu de filtrer par ceux qui ont des tâches
    # filtered_operators = [op for op in OPERATORS if op['id'] in operators_with_tasks]
    
    # Pré-calculer les informations d'absence pour tous les opérateurs et slots
    operator_absences = {}
    for operator in OPERATORS:
        operator_absences[operator["id"]] = {}
        for i in range(NUM_SLOTS):
            operator_absences[operator["id"]][i] = is_absence_slot(operator["id"], i)
    
    return render_template('index.html', 
                         operators=OPERATORS,  # Utiliser tous les opérateurs
                         time_slots=time_slots,
                         months=months,
                         weeks=weeks,
                         days=days,
                         tasks=display_tasks, 
                         affairs=AFFAIRES,
                         operator_absences=operator_absences,
                         slot_width=SLOT_WIDTH,
                         row_height=ROW_HEIGHT,
                         header_height=HEADER_HEIGHT,
                         num_slots=NUM_SLOTS,
                         start_date=START_DATE,
                         day_duration_hours=DAY_DURATION_HOURS,
                         current_planning_name=current_planning_name,
                         current_database_url_odoo=CURRENT_DATABASE_URL_ODOO,
                         current_database_url_tache_odoo=CURRENT_DATABASE_URL_TACHE_ODOO)

@app.route('/change_database')
def change_database():
    """Retourne à la sélection de base de données"""
    return redirect(url_for('database_selection'))

@app.route('/change_planning')
def change_planning():
    """Retourne à la sélection de planning"""
    return redirect(url_for('planning_selection'))

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
        
        # Mise à jour de la base de données PostgreSQL pour TOUTES les tâches de l'opérateur impacté
        tasks_to_update = [
            {
                'id': t['id'],
                'operator_id': t['operator_id'],
                'start_date': t['start_date'],
                'duration_hours': t['duration_hours']
            }
            for t in TASKS if t['operator_id'] == new_operator_id
        ]
        db_success = update_multiple_tasks_in_database(tasks_to_update) if tasks_to_update else True
        if not db_success:
            # En cas d'échec de la base de données, annuler la tâche principale au minimum
            task["operator_id"] = old_operator_id
            update_task_from_slots(task, old_start_slot, duration_slots)
            return jsonify({"success": False, "error": "Erreur lors de la mise à jour en base de données"})
        
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
                # Si le déplacement est bloqué, ne rien enregistrer
                if result.get('blocked'):
                    return jsonify(result)

                # Persistons toutes les tâches de l'opérateur affecté (poussées comprises)
                task = next((t for t in TASKS if t["id"] == task_id), None)
                if task:
                    operator_id = task["operator_id"]
                    # Préparer un bulk update pour toutes les tâches de cet opérateur
                    tasks_to_update = [
                        {
                            'id': t['id'],
                            'operator_id': t['operator_id'],
                            'start_date': t['start_date'],
                            'duration_hours': t['duration_hours']
                        }
                        for t in TASKS if t['operator_id'] == operator_id
                    ]
                    if tasks_to_update:
                        db_success = update_multiple_tasks_in_database(tasks_to_update)
                        if not db_success:
                            return jsonify({"success": False, "error": "Erreur lors de la mise à jour en base de données"})
            return jsonify(result)
        
        elif direction in ['up', 'down']:
            # Déplacement vertical avec gestion des opérateurs dans l'ordre de la base de données
            task = next((t for t in TASKS if t["id"] == task_id), None)
            if not task:
                return jsonify({"success": False, "error": "Tâche non trouvée"})
            
            current_operator_id = task["operator_id"]
            
            # Utiliser les opérateurs dans l'ordre de la requête SQL (ordre alphabétique par nom)
            # Ce sont les mêmes opérateurs affichés dans l'interface
            operator_ids_in_order = [op['id'] for op in OPERATORS]  # Garde l'ordre de la requête SQL
            
            # Trouver la position actuelle dans la liste
            try:
                current_index = operator_ids_in_order.index(current_operator_id)
            except ValueError:
                return jsonify({"success": False, "error": "Opérateur actuel introuvable"})
            
            new_operator_id = current_operator_id
            if direction == 'up' and current_index > 0:
                new_operator_id = operator_ids_in_order[current_index - 1]
            elif direction == 'down' and current_index < len(operator_ids_in_order) - 1:
                new_operator_id = operator_ids_in_order[current_index + 1]
            
            if new_operator_id != current_operator_id:
                # Sauvegarder l'ancienne position au cas où le déplacement échoue
                old_operator_id = task["operator_id"]
                start_slot = get_task_start_slot(task)
                duration_slots = get_task_duration_slots(task)
                
                # Vérifier d'abord si le déplacement est possible en utilisant la même logique robuste que pour les autres déplacements
                push_success = push_all_colliding_tasks_right(new_operator_id, start_slot, duration_slots, task_id)
                
                if push_success:
                    # Le déplacement est possible, effectuer le changement d'opérateur
                    task["operator_id"] = new_operator_id

                    # Persistons toutes les tâches du NOUVEL opérateur (poussées comprises)
                    tasks_to_update = [
                        {
                            'id': t['id'],
                            'operator_id': t['operator_id'],
                            'start_date': t['start_date'],
                            'duration_hours': t['duration_hours']
                        }
                        for t in TASKS if t['operator_id'] == new_operator_id
                    ]
                    db_success = update_multiple_tasks_in_database(tasks_to_update) if tasks_to_update else True
                    if not db_success:
                        # En cas d'échec de la base de données, annuler les modifications en mémoire
                        task["operator_id"] = old_operator_id
                        return jsonify({"success": False, "error": "Erreur lors de la mise à jour en base de données"})
                else:
                    # Le déplacement n'est pas possible, garder l'opérateur actuel
                    return jsonify({"success": False, "error": "Impossible de déplacer la tâche vers cet opérateur : pas assez d'espace"})
            
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
        
        # Mise à jour de la base de données PostgreSQL pour toutes les tâches de l'opérateur (si des poussées ont eu lieu)
        operator_id = task["operator_id"]
        tasks_to_update = [
            {
                'id': t['id'],
                'operator_id': t['operator_id'],
                'start_date': t['start_date'],
                'duration_hours': t['duration_hours']
            }
            for t in TASKS if t['operator_id'] == operator_id
        ]
        db_success = update_multiple_tasks_in_database(tasks_to_update) if tasks_to_update else True
        if not db_success:
            # En cas d'échec de la base de données, annuler les modifications en mémoire
            update_task_from_slots(task, start_slot, old_duration_slots)
            return jsonify({"success": False, "error": "Erreur lors de la mise à jour en base de données"})
        
        return jsonify({"success": True})
    
    except Exception as e:
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
        
        # Mise à jour de la base de données PostgreSQL pour toutes les tâches du NOUVEL opérateur
        tasks_to_update = [
            {
                'id': t['id'],
                'operator_id': t['operator_id'],
                'start_date': t['start_date'],
                'duration_hours': t['duration_hours']
            }
            for t in TASKS if t['operator_id'] == operator_id
        ]
        db_success = update_multiple_tasks_in_database(tasks_to_update) if tasks_to_update else True
        if not db_success:
            # En cas d'échec de la base de données, annuler les modifications en mémoire
            task["operator_id"] = old_operator_id
            update_task_from_slots(task, old_start_slot, old_duration_slots)
            return jsonify({"success": False, "error": "Erreur lors de la mise à jour en base de données"})
        
        return jsonify({"success": True})
    
    except Exception as e:
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
    
    # Utiliser tous les opérateurs au lieu de filtrer par ceux qui ont des tâches
    # operators_with_tasks = set()
    # for task in display_tasks:
    #     operators_with_tasks.add(task['operator_id'])
    # 
    # # Garder seulement les opérateurs qui ont des tâches, dans l'ordre de la requête SQL
    # filtered_operators = [op for op in OPERATORS if op['id'] in operators_with_tasks]
    
    return jsonify({
        "tasks": display_tasks,
        "operators": OPERATORS,  # Utiliser tous les opérateurs
        "affairs": AFFAIRES
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

@app.route('/api/reload-data', methods=['POST'])
def reload_data():
    """Recharge à la fois les opérateurs, les affaires et les tâches depuis la base de données"""
    global OPERATORS, AFFAIRES, TASKS, START_DATE, NUM_SLOTS
    try:
        # # ÉTAPE 1 : Appeler action_maj_fermetures en premier
        # maj_fermetures_success = False
        # if CURRENT_PLANNING_ID:
        #     maj_fermetures_success = call_odoo_action_maj_fermetures(CURRENT_PLANNING_ID)
        
        # ÉTAPE 2 : Recharger les opérateurs
        new_operators = load_operators_from_db(CURRENT_PLANNING_ID)
        operators_count = len(new_operators)
        
        # Recharger les affaires (filtrées par planning si applicable)
        new_affaires = load_affaires_from_db(CURRENT_PLANNING_ID)
        affaires_count = len(new_affaires)
        
        # Recharger les tâches (filtrées par planning si applicable)
        new_tasks = load_tasks_from_db(CURRENT_PLANNING_ID)
        tasks_count = len(new_tasks)
        
        # Mettre à jour les variables globales seulement si tout s'est bien passé
        OPERATORS = new_operators
        AFFAIRES = new_affaires
        TASKS = new_tasks
        
        # Recalculer la date de début du planning basée sur les nouvelles tâches
        START_DATE = calculate_planning_start_date(TASKS)
        
        # Recalculer NUM_SLOTS
        calculate_num_slots()
        
        # Recharger les fermetures après avoir défini OPERATORS
        load_fermetures_from_db(CURRENT_PLANNING_ID)
        
        # Message avec statut des fermetures
        #fermetures_msg = "fermetures mises à jour" if maj_fermetures_success else "fermetures (erreur)"
        message = f"{operators_count} opérateurs, {affaires_count} affaires, {tasks_count} tâches rechargés"
        
        return jsonify({
            "success": True, 
            "message": message,
            "operators": OPERATORS,
            "affairs": AFFAIRES,
            "tasks_count": tasks_count
        })
    except Exception as e:
        return jsonify({
            "success": False, 
            "message": f"Erreur lors du rechargement: {str(e)}"
        }), 500

@app.route('/api/reload-affairs', methods=['POST'])
def reload_affairs():
    """Recharge les affaires depuis la base de données"""
    global AFFAIRES
    try:
        AFFAIRES = load_affaires_from_db(CURRENT_PLANNING_ID)
        return jsonify({
            "success": True, 
            "message": f"{len(AFFAIRES)} affaires rechargées",
            "affairs": AFFAIRES
        })
    except Exception as e:
        return jsonify({
            "success": False, 
            "message": f"Erreur lors du rechargement: {str(e)}"
        }), 500

@app.route('/api/reload-operators', methods=['POST'])
def reload_operators():
    """Recharge les opérateurs depuis la base de données"""
    global OPERATORS
    try:
        OPERATORS = load_operators_from_db(CURRENT_PLANNING_ID)
        # Recharger les fermetures dépendantes des opérateurs
        load_fermetures_from_db(CURRENT_PLANNING_ID)
        return jsonify({
            "success": True, 
            "message": f"{len(OPERATORS)} opérateurs rechargés",
            "operators": OPERATORS
        })
    except Exception as e:
        return jsonify({
            "success": False, 
            "message": f"Erreur lors du rechargement: {str(e)}"
        }), 500

@app.route('/api/reload-tasks', methods=['POST'])
def reload_tasks():
    """Recharge les tâches depuis la base de données"""
    global TASKS, START_DATE, NUM_SLOTS
    try:
        TASKS = load_tasks_from_db(CURRENT_PLANNING_ID)
        
        # Recalculer la date de début du planning basée sur les nouvelles tâches
        START_DATE = calculate_planning_start_date(TASKS)
        
        # Recalculer NUM_SLOTS
        calculate_num_slots()
        
        return jsonify({
            "success": True, 
            "message": f"{len(TASKS)} tâches rechargées",
            "tasks_count": len(TASKS)
        })
    except Exception as e:
        return jsonify({
            "success": False, 
            "message": f"Erreur lors du rechargement: {str(e)}"
        }), 500

@app.route('/api/affairs')
def get_affairs():
    """Retourne la liste des affaires"""
    return jsonify({"affairs": AFFAIRES})

@app.route('/api/operators')
def get_operators():
    """Retourne la liste des opérateurs"""
    return jsonify({"operators": OPERATORS})

@app.route('/test_timezone_conversion')
def test_timezone_conversion():
    """Endpoint de test pour vérifier la conversion des fuseaux horaires"""
    import pytz
    
    paris_tz = pytz.timezone('Europe/Paris')
    utc_tz = pytz.UTC
    
    # Test avec les heures de créneaux
    test_cases = [
        datetime(2025, 8, 26, 8, 0),   # 26 août 8H (AM)
        datetime(2025, 8, 26, 14, 0),  # 26 août 14H (PM)
        datetime(2025, 1, 15, 8, 0),   # 15 janvier 8H (hiver)
        datetime(2025, 1, 15, 14, 0),  # 15 janvier 14H (hiver)
    ]
    
    results = []
    for naive_date in test_cases:
        # Conversion Paris → UTC (comme dans update_task_in_database)
        paris_date = paris_tz.normalize(paris_tz.localize(naive_date))
        utc_date = paris_date.astimezone(utc_tz)
        
        results.append({
            "naive_paris": naive_date.strftime("%Y-%m-%d %H:%M:%S"),
            "paris_with_tz": paris_date.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "utc": utc_date.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "offset": paris_date.strftime("%z")
        })
    
    return jsonify({"timezone_conversion_test": results})

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
