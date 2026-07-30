# -*- coding: utf-8 -*-
from odoo import models,fields,api
from odoo.exceptions import Warning
from datetime import timedelta, time as dtime
import random
import logging
import pytz

_logger = logging.getLogger(__name__)

PARIS_TZ = pytz.timezone('Europe/Paris')


def _periodes_couvertes(start_dt, end_dt):
    """Calcule les (date, periode) couverts par un intervalle UTC [start_dt, end_dt), en heure
    locale Europe/Paris. periode vaut 'matin', 'apres_midi' ou 'journee' (frontière fixée à 12h,
    cohérente avec la coupure AM/PM utilisée partout ailleurs dans le planning).
    """
    if not start_dt or not end_dt or start_dt >= end_dt:
        return []
    start_local = pytz.utc.localize(start_dt).astimezone(PARIS_TZ)
    end_local = pytz.utc.localize(end_dt).astimezone(PARIS_TZ)
    # Fin exclusive : si elle tombe pile à minuit, le dernier jour n'est pas concerné
    last_day = end_local.date() if end_local.time() != dtime(0, 0) else (end_local.date() - timedelta(days=1))

    result = []
    cur_day = start_local.date()
    while cur_day <= last_day:
        start_hour = (start_local.hour + start_local.minute / 60) if cur_day == start_local.date() else 0
        end_hour = (end_local.hour + end_local.minute / 60) if cur_day == end_local.date() else 24
        covers_matin = start_hour < 12
        covers_apres_midi = end_hour > 12
        if covers_matin and covers_apres_midi:
            result.append((cur_day, 'journee'))
        elif covers_matin:
            result.append((cur_day, 'matin'))
        elif covers_apres_midi:
            result.append((cur_day, 'apres_midi'))
        cur_day = cur_day + timedelta(days=1)
    return result


def generer_couleur_foncee():
    """
    Génère une couleur hexadécimale aléatoire foncée pour assurer 
    une bonne lisibilité du texte blanc
    """
    # Génère des valeurs RGB entre 0 et 150 pour garantir des couleurs foncées
    r = random.randint(0, 190)
    g = random.randint(0, 190) 
    b = random.randint(0, 190)
    
    # Convertit en format hexadécimal
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


class is_gestion_tache_planning(models.Model):
    _name='is.gestion.tache.planning'
    _description='Planning pour la gestion des tâches'
    _order='name'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    name           = fields.Char("Planning", required=True, tracking=True)
    active         = fields.Boolean('Actif', default=True, tracking=True)
    tache_ids      = fields.One2many('is.gestion.tache'           , 'planning_id', string="Tâches", tracking=True)
    affaire_ids    = fields.One2many('is.gestion.tache.affaire'   , 'planning_id', string="Affaires", tracking=True)
    operateur_ids  = fields.One2many('is.gestion.tache.operateur' , 'planning_id', string="Opérateurs", tracking=True)
    workcenter_ids = fields.One2many('is.gestion.tache.workcenter', 'planning_id', string="Postes de charge", tracking=True)
    fermeture_ids  = fields.One2many('is.gestion.tache.fermeture', 'planning_id', string="Fermetures", tracking=True)
    date_fin_planning = fields.Date(string="Date fin planning", help="Limite supérieure de la période du planning pour le chargement des tâches.", tracking=True)
    type_donnees  = fields.Selection([
        ('operation', 'Opération'),
        ('of', 'OF'),
    ], string="Type de données", default=lambda self: 'operation' if self.env.company.is_site == 'bsa' else 'of', tracking=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Poste de charge', tracking=True)
    affaire       = fields.Char(string="Affaire", help="Filtre sur le nom d'affaire. Vous pouvez saisir plusieurs valeurs séparées par des virgules.", tracking=True)
    is_pret       = fields.Selection([
            ('oui', 'Oui'),
            ('non', 'Non'),
        ], "Prêt", help="Prêt à produire", default='oui', tracking=True)
    maj_of_auto   = fields.Boolean(string="Mise à jour OF automatique", default=False, tracking=True, help="Si coché, met à jour automatiquement les dates des OF")
    tache_count   = fields.Integer(string="Nb tâches", compute="_compute_counts")

    def _compute_counts(self):
        for rec in self:
            rec.tache_count = len(rec.tache_ids)


    def _update_operation_employees_from_tasks(self, tasks):
        """Met à jour le champ employe_id sur les lignes d'OT ou les OF
        à partir des tâches fournies (operator_id).
        Retourne le nombre de lignes mises à jour.
        """
        updated_lines = 0
        for t in tasks:
            employe = t.operator_id
            if self.type_donnees=='operation':
                operation_line = t.operation_id
                if operation_line and employe and operation_line.employe_id.id != employe.id:
                    operation_line.write({'employe_id': employe.id})
                    updated_lines += 1
            # else:
            #     production = t.production_id
            #     if production and employe:
            #         production.is_employe_id = employe.id 
            #         updated_lines += 1
        return updated_lines


    def _update_operation_durations_from_tasks(self, tasks):
        """Met à jour le champ duree_unitaire sur les lignes d'OT (is.ordre.travail.line)
        à partir des tâches fournies (duration_hours).

        Retourne le nombre de lignes mises à jour.
        """
        updated_durations = 0
        for t in tasks:
            line = t.operation_id
            if line and t.duration_hours and line.duree_unitaire != t.duration_hours:
                try:
                    line.write({'duree_unitaire': t.duration_hours})
                    updated_durations += 1
                except Exception:
                    # Ignorer les erreurs pour ne pas bloquer l'action globale
                    continue
        return updated_durations


    def action_chargement_taches(self):
        """Action pour charger les tâches selon le type de données sélectionné"""
        cr=self._cr

        #** Mise à jour des opérateurs ************************************
        domain=[]
        if self.type_donnees=='operation' and self.workcenter_id:
            domain=[('is_workcenter_id', '=', self.workcenter_id.id)]
        if self.type_donnees=='of':
            domain=[('department_id', '=', 16)]  # Acier
        new_operators = self.env['hr.employee'].search(domain)
        new_operator_ids = set(new_operators.ids)
        # Supprimer les opérateurs qui ne correspondent plus
        self.operateur_ids.filtered(lambda o: o.operator_id.id not in new_operator_ids).unlink()
        # Ajouter les opérateurs manquants
        existing_operator_ids = set(self.operateur_ids.mapped('operator_id').ids)
        default_operator_id = False
        for operateur in new_operators:
            if operateur.id not in existing_operator_ids:
                self.env['is.gestion.tache.operateur'].create({
                    "operator_id": operateur.id,
                    "planning_id": self.id,
                })
            default_operator_id = operateur.id
        #******************************************************************

        #** Mise à jour des postes de charges *****************************
        new_workcenters = self.env['mrp.workcenter'].search([('is_gestion_tache', '=', True)])
        new_workcenter_ids = set(new_workcenters.ids)
        # Supprimer les postes qui ne correspondent plus
        self.workcenter_ids.filtered(lambda w: w.workcenter_id.id not in new_workcenter_ids).unlink()
        # Ajouter les postes manquants
        existing_workcenter_ids = set(self.workcenter_ids.mapped('workcenter_id').ids)
        default_workcenter_id = False
        for workcenter in new_workcenters:
            if workcenter.id not in existing_workcenter_ids:
                self.env['is.gestion.tache.workcenter'].create({
                    "workcenter_id": workcenter.id,
                    "planning_id"  : self.id,
                })
            default_workcenter_id = workcenter.id
        #******************************************************************

        #** Recherche des taches et affaires ******************************
        if self.type_donnees=='operation' and self.workcenter_id:
            SQL="""
                select 
                    so.id order_id,
                    so.is_nom_affaire affaire_name,
                    so.is_couleur_affaire,
                    mp.name mp_name,
                    pt.name product_name,
                    pp.id product_id,
                    mp.id production_id,
                    ot.id ordre_travail_id,
                    ot.name ot_name,
                    line.id operation_id,
                    line.ordre_id,
                    line.workcenter_id,
                    line.name line_name,
                    line.state,
                    line.duree_totale duration_hours,
                    line.heure_debut start_date,
                    line.employe_id,
                    pt.default_code,
                    mp.product_qty,
                    sol.is_derniere_date_prevue,
                    ot.duree_planifiee
                from is_ordre_travail_line line join is_ordre_travail ot on line.ordre_id=ot.id
                                                join mrp_production mp on ot.production_id=mp.id
                                                join sale_order so on mp.is_sale_order_id=so.id
                                                join product_product pp on mp.product_id=pp.id
                                                join product_template pt on pp.product_tmpl_id=pt.id
                                                 left join sale_order_line sol on mp.is_sale_order_line_id=sol.id
                where line.state not in ('annule','termine')
                    and ot.state!='termine'
                    and mp.state not in  ('cancel','done')
                    and line.workcenter_id=%s
            """
        else:
            SQL="""
                select 
                    so.id order_id,
                    so.is_nom_affaire affaire_name,
                    so.is_couleur_affaire,
                    mp.name mp_name,
                    pt.name product_name,
                    pp.id product_id,
                    mp.id production_id,
                    ot.id ordre_travail_id,
                    ot.name ot_name,
                    null operation_id,
                    null ordre_id,
                    null line_name,
                    null state,
                    mp.date_planned_start start_date,
                    null employe_id,
                    mp.is_workcenter_id as workcenter_id,
                    pt.default_code,
                    mp.product_qty,
                    sol.is_derniere_date_prevue,
                    ot.duree_prevue,
                    ot.duree_planifiee
                from is_ordre_travail ot join mrp_production mp on ot.production_id=mp.id
                                         join sale_order so on mp.is_sale_order_id=so.id
                                         join product_product pp on mp.product_id=pp.id
                                         join product_template pt on pp.product_tmpl_id=pt.id
                                         left join sale_order_line sol on mp.is_sale_order_line_id=sol.id

                where so.id>0
                    -- and line.state not in ('annule','termine')
                    and ot.state!='termine'
                    and mp.state not in  ('cancel','done')
                    -- and line.workcenter_id=%s
            """
        if self.is_pret:
            SQL += " and is_pret='%s' "%self.is_pret

        # Paramètres de base (poste de charge)
        params = [self.workcenter_id.id]

        # Ajout éventuel du filtre sur les affaires (sur le nom d'affaire)
        if self.affaire:
            # Supporte plusieurs termes séparés par des virgules => OR
            terms = [t.strip() for t in self.affaire.split(',') if t.strip()]
            if terms:
                clauses = ["so.is_nom_affaire ILIKE %s" for _ in terms]
                SQL += "\n                    and (" + " OR ".join(clauses) + ")\n"
                params.extend([f"%{t}%" for t in terms])


        #print(params,SQL)


        cr.execute(SQL, params)
        rows = cr.dictfetchall()

        # Indexer les affaires et tâches existantes pour la mise à jour différentielle
        existing_affaires = {a.order_id.id: a for a in self.affaire_ids if a.order_id}
        if self.type_donnees == 'operation':
            existing_tasks = {t.operation_id.id: t for t in self.tache_ids if t.operation_id}
        else:
            existing_tasks = {t.ordre_travail_id.id: t for t in self.tache_ids if t.ordre_travail_id}

        seen_order_ids = set()
        seen_task_keys = set()

        for row in rows:
            #** Mise à jour ou création de l'affaire **********************
            order_id = row['order_id']
            seen_order_ids.add(order_id)
            if order_id not in existing_affaires:
                color = row['is_couleur_affaire']
                if not color:
                    color = generer_couleur_foncee()
                    lines = self.env['sale.order'].search([('id', '=', order_id)])
                    for line in lines:
                        line.is_couleur_affaire = color
                vals = {
                    "name"       : row['affaire_name'] or '??',
                    "order_id"   : order_id,
                    "planning_id": self.id,
                    "color"      : color,
                }
                affaire = self.env['is.gestion.tache.affaire'].create(vals)
                existing_affaires[order_id] = affaire
            else:
                affaire = existing_affaires[order_id]
            #**************************************************************

            #** Mise à jour ou création de la tâche ***********************
            if self.type_donnees == 'operation':
                task_key = row['operation_id']
            else:
                task_key = row['ordre_travail_id']

            if affaire and task_key:
                if task_key in seen_task_keys:
                    _logger.warning("action_chargement_taches : task_key %s (type_donnees=%s) déjà vu dans cette même exécution -> la requête SQL renvoie plusieurs lignes pour la même clé (production_id=%s, ordre_travail_id=%s, operation_id=%s)",
                                     task_key, self.type_donnees, row.get('production_id'), row.get('ordre_travail_id'), row.get('operation_id'))
                seen_task_keys.add(task_key)
                start_date = row['start_date']
                operator_id = row['employe_id']    or default_operator_id
                workcenter_id = row['workcenter_id'] or default_workcenter_id
                # Glisse le début au prochain slot ouvert si besoin (week-end + fermetures du planning).
                # Avance slot par slot (AM->PM->AM du jour suivant...) : une fermeture couvrant toute
                # la journée, le premier slot ouvert rencontré est donc naturellement le AM du premier
                # jour ouvré (pas de cas particulier à coder pour "revenir le matin").
                safety = 0
                while safety < 730 and not self.est_jour_ouvre(start_date.date(), 'matin' if start_date.hour < 12 else 'apres_midi', operator_id=operator_id, workcenter_id=workcenter_id):
                    if start_date.hour < 12:
                        start_date = start_date.replace(hour=14, minute=0, second=0, microsecond=0)
                    else:
                        start_date = (start_date + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
                    safety += 1
                product = self.env['product.product'].search([('id', '=', row['product_id'])])[0]
                variant = product.product_template_attribute_value_ids._get_combination_name()
                if self.type_donnees == 'operation':
                    name = "[%s] %s" % (variant, row.get('product_name'))
                    duration_hours = row.get('duration_hours')
                else:
                    name = "[%s] %s" % (row.get('default_code'), row.get('product_name'))
                    duration_hours = row.get('duree_planifiee') or row.get('duree_prevue')
                vals = {
                    "name"            : name,
                    "operator_id"     : operator_id,
                    "workcenter_id"   : workcenter_id,
                    "affaire_id"      : affaire.id,
                    "start_date"      : start_date,
                    "duration_hours"  : duration_hours,
                    "planning_id"     : self.id,
                    "order_id"        : order_id,
                    "production_id"   : row['production_id'],
                    "product_qty"     : row['product_qty'],
                    "ordre_travail_id": row['ordre_travail_id'],
                    "operation_id"    : row['operation_id'],
                    "is_derniere_date_prevue": row['is_derniere_date_prevue'],
                }
                if task_key in existing_tasks:
                    existing_tasks[task_key].write(vals)
                else:
                    new_task = self.env['is.gestion.tache'].create(vals)
                    _logger.info("action_chargement_taches : création tâche %s pour task_key=%s (type_donnees=%s, workcenter_id=%s, start_date=%s)",
                                 new_task.id, task_key, self.type_donnees, vals.get('workcenter_id'), vals.get('start_date'))
                    # Sans cette ligne, une deuxième ligne SQL avec le même task_key dans cette
                    # même exécution recréerait un doublon au lieu de faire un write().
                    existing_tasks[task_key] = new_task
            #**************************************************************

        # Supprimer les tâches qui ne sont plus dans les résultats
        if self.type_donnees == 'operation':
            self.tache_ids.filtered(lambda t: t.operation_id.id not in seen_task_keys).unlink()
        else:
            self.tache_ids.filtered(lambda t: t.ordre_travail_id.id not in seen_task_keys).unlink()

        # Supprimer les affaires qui ne sont plus dans les résultats
        self.affaire_ids.filtered(lambda a: a.order_id.id not in seen_order_ids).unlink()

        self.action_maj_fermetures()
        return True


    def action_maj_fermetures(self):
        """Met à jour la liste des fermetures à partir des absences (is.absence).

        Règles:
        - On cible les opérateurs du planning (onglet Opérateurs). Si absent, on prend
          les employés du poste de charge sélectionné.
                - On supprime d'abord les fermetures existantes du planning puis on recrée
                    une ligne par jour et par opérateur pour chaque absence et pour chaque
                    fermeture issue des calendriers (resource.calendar.leaves) des employés.
                - L'intitulé reprend le motif d'absence et le commentaire éventuel pour is.absence,
                    et le nom de la fermeture de calendrier pour resource.calendar.leaves.
        """
        for planning in self:
            # Supprimer les fermetures existantes de ce planning
            planning.fermeture_ids.unlink()
            vals_list = []
            if planning.type_donnees=='of':
                conges = self.env['resource.calendar.leaves'].search([
                    ('workcenter_id', '=', False),
                    ('resource_id', '=', False),
                ])
                workcenters = self.env['mrp.workcenter'].search([
                    ('is_gestion_tache', '=', True),
                ])
                for workcenter in workcenters:
                    res = self.env['resource.calendar.leaves'].search([
                        ('workcenter_id', '=', workcenter.id),
                    ])
                    conges+=res

                # Créer les fermetures à partir des congés
                fermeture_keys = set()
                for conge in conges:
                    start_dt = conge.date_from
                    end_dt = conge.date_to

                    # Intitulé depuis le congé
                    intitule = conge.name or 'Fermeture'

                    # Déterminer le workcenter_id
                    workcenter_id = None
                    if conge.workcenter_id:
                        workcenter_id = conge.workcenter_id.id

                    # date_from/date_to sont stockés en UTC : _periodes_couvertes convertit en heure
                    # locale et détermine, par jour, si le congé couvre le matin, l'après-midi ou les deux.
                    for cur_day, periode in _periodes_couvertes(start_dt, end_dt):
                        # Clé unique pour éviter les doublons (workcenter, jour, période)
                        key = (workcenter_id, cur_day, periode)
                        if key not in fermeture_keys:
                            vals_list.append({
                                'planning_id': planning.id,
                                'operator_id': None,  # Pas d'opérateur spécifique pour les OF
                                'workcenter_id': workcenter_id,
                                'date_fermeture': cur_day,
                                'periode': periode,
                                'intitule': intitule,
                            })
                            fermeture_keys.add(key)






            if planning.type_donnees=='operation':


                # Déterminer la liste des employés cibles
                employee_ids = planning.operateur_ids.mapped('operator_id')
                if not employee_ids and planning.workcenter_id:
                    employee_ids = self.env['hr.employee'].search([
                        ('is_workcenter_id', '=', planning.workcenter_id.id)
                    ])

                if not employee_ids:
                    continue

                # Set pour éviter les doublons (opérateur, jour)
                fermeture_keys = set()

                # 1) Récupérer toutes les absences (is.absence) des employés cibles
                absences = self.env['is.absence'].search([
                    ('employe_id', 'in', employee_ids.ids),
                ])
                for absn in absences:
                    start_dt = absn.date_debut
                    end_dt = absn.date_fin

                    # Intitulé = motif [+ commentaire]
                    intitule = absn.motif_id.name or 'Absence'
                    if absn.commentaire:
                        intitule = f"{intitule} - {absn.commentaire}"

                    for cur_day, periode in _periodes_couvertes(start_dt, end_dt):
                        key = (absn.employe_id.id, cur_day, periode)
                        if key not in fermeture_keys:
                            vals_list.append({
                                'planning_id': planning.id,
                                'operator_id': absn.employe_id.id,
                                'date_fermeture': cur_day,
                                'periode': periode,
                                'intitule': intitule,
                            })
                            fermeture_keys.add(key)

                # 2) Récupérer les fermetures issues des calendriers (resource.calendar.leaves)
                # Associer chaque employé à son calendrier
                employees_by_calendar = {}
                calendar_ids = set()
                for emp in employee_ids:
                    cal = emp.resource_calendar_id
                    if cal:
                        employees_by_calendar.setdefault(cal.id, []).append(emp)
                        calendar_ids.add(cal.id)

                if calendar_ids:
                    # Chercher toutes les fermetures pour ces calendriers
                    calendar_leaves = self.env['resource.calendar.leaves'].search([
                        ('calendar_id', 'in', list(calendar_ids)),
                    ])

                    for leave in calendar_leaves:
                        start_dt = leave.date_from
                        end_dt = leave.date_to

                        # Intitulé depuis le calendrier
                        intitule = leave.name or 'Fermeture calendrier'

                        # Pour tous les employés rattachés à ce calendrier
                        emps = employees_by_calendar.get(leave.calendar_id.id, [])
                        if not emps:
                            continue

                        for cur_day, periode in _periodes_couvertes(start_dt, end_dt):
                            for emp in emps:
                                key = (emp.id, cur_day, periode)
                                if key not in fermeture_keys:
                                    vals_list.append({
                                        'planning_id': planning.id,
                                        'operator_id': emp.id,
                                        'date_fermeture': cur_day,
                                        'periode': periode,
                                        'intitule': intitule,
                                    })
                                    fermeture_keys.add(key)

            if vals_list:
                self.env['is.gestion.tache.fermeture'].create(vals_list)

        return True


    def est_jour_ouvre(self, date, periode, operator_id=False, workcenter_id=False):
        """Indique si un slot (matin/après-midi) est ouvert pour un opérateur (mode 'operation')
        ou un poste de charge (mode 'of').

        `periode` vaut 'matin' ou 'apres_midi'. Un slot est fermé s'il tombe un week-end, ou si
        une fermeture du planning (fermeture_ids) le couvre : une fermeture 'journee' ferme les
        deux périodes, une fermeture 'matin'/'apres_midi' ne ferme que la période correspondante.
        La fermeture peut être propre à cet opérateur/poste, ou globale (ni operator_id ni
        workcenter_id renseignés).
        """
        self.ensure_one()
        if date.weekday() in (5, 6):
            return False
        for fermeture in self.fermeture_ids:
            if fermeture.date_fermeture != date:
                continue
            if fermeture.periode != 'journee' and fermeture.periode != periode:
                continue
            if fermeture.operator_id:
                if operator_id and fermeture.operator_id.id == operator_id:
                    return False
            elif fermeture.workcenter_id:
                if workcenter_id and fermeture.workcenter_id.id == workcenter_id:
                    return False
            else:
                return False
        return True


    def action_open_taches(self):
        """Ouvre la liste des tâches rattachées à ce planning."""
        self.ensure_one()
        return {
            'name': 'Tâches du planning',
            'type': 'ir.actions.act_window',
            'res_model': 'is.gestion.tache',
            'view_mode': 'tree,form',
            'domain': [('planning_id', '=', self.id)],
            'context': {'default_planning_id': self.id},
            'target': 'current',
        }


    def action_open_productions(self):
        """Ouvre la liste des OF (mrp.production) référencés dans les tâches du planning."""
        self.ensure_one()
        prod_ids = self.tache_ids.mapped('production_id').ids
        domain = [('id', 'in', prod_ids)] if prod_ids else [('id', '=', 0)]
        return {
            'name': 'Ordres de fabrication liés',
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'view_mode': 'tree,form',
            'domain': domain,
            'target': 'current',
        }


    def action_open_fermetures(self):
        """Ouvre la liste des fermetures rattachées à ce planning."""
        self.ensure_one()
        return {
            'name': 'Fermetures du planning',
            'type': 'ir.actions.act_window',
            'res_model': 'is.gestion.tache.fermeture',
            'view_mode': 'tree,form',
            'domain': [('planning_id', '=', self.id)],
            'context': {'default_planning_id': self.id},
            'target': 'current',
        }


    def action_open_operation_lines(self):
        """Ouvre la liste des lignes d'opérations (is.ordre.travail.line) référencées dans les tâches du planning."""
        self.ensure_one()
        operation_ids = self.tache_ids.mapped('operation_id').ids
        domain = [('id', 'in', operation_ids)] if operation_ids else [('id', '=', 0)]
        return {
            'name': 'Lignes d\'opérations liées',
            'type': 'ir.actions.act_window',
            'res_model': 'is.ordre.travail.line',
            'view_mode': 'tree,form',
            'domain': domain,
            'target': 'current',
        }


    def action_maj_date_of(self):
        """Pour chaque OF présent dans ce planning, met à jour mrp.production.date_planned_start
        avec la start_date la plus récente parmi toutes les tâches is.gestion.tache liées à cet OF.
        Les autres tâches ne sont pas traitées.
        Gère aussi les reliquats : remplace les OF terminés par leurs reliquats
        et supprime du planning les OF sans reliquat.
        """

        # --- Phase 1 : Gestion des reliquats ---
        # Remplacer les OF terminés (done) par leurs reliquats,
        # et supprimer du planning les OF done/cancel sans reliquat.
        tasks_to_remove = self.env['is.gestion.tache']
        for task in self.tache_ids:
            production = task.production_id
            if not production or production.state not in ['done', 'cancel']:
                continue

            # Chercher le reliquat (production active dans le même groupe)
            backorder = False
            if production.state == 'done' and production.procurement_group_id:
                backorder = self.env['mrp.production'].search([
                    ('procurement_group_id', '=', production.procurement_group_id.id),
                    ('state', 'not in', ['done', 'cancel']),
                    ('id', '!=', production.id),
                ], limit=1, order='backorder_sequence desc')

            if backorder:
                _logger.info("OF %s → reliquat %s (qty=%s)", production.name, backorder.name, backorder.product_qty)
                # Mettre à jour la tâche pour pointer vers le reliquat
                vals = {
                    'production_id': backorder.id,
                    'product_qty': backorder.product_qty,
                }
                if backorder.is_ordre_travail_id:
                    vals['ordre_travail_id'] = backorder.is_ordre_travail_id.id
                if self.type_donnees == 'of' and backorder.is_workcenter_id:
                    vals['workcenter_id'] = backorder.is_workcenter_id.id
                task.write(vals)
            else:
                # Pas de reliquat → marquer pour suppression
                _logger.info("OF %s → supprimé du planning (pas de reliquat)", production.name)
                tasks_to_remove |= task

        nb_reliquats = len(self.tache_ids) - len(tasks_to_remove)  # avant suppression
        nb_supprimes = len(tasks_to_remove)
        if tasks_to_remove:
            tasks_to_remove.unlink()

        # --- Phase 2 : Mise à jour des dates ---
        productions={}
        for task in self.tache_ids:
            if task.start_date:
                if task.production_id not in productions:
                    productions[task.production_id]=task
                if productions[task.production_id].start_date>task.start_date:
                    productions[task.production_id]=task

        for production in productions:
            if production.state not in ['done','cancel']:
                heure_debut_operation_modifiee = productions[production].start_date
                date_planned_start_new = heure_debut_operation_modifiee
                if self.type_donnees=='of':
                    production.is_workcenter_id = productions[production].workcenter_id.id
                    duree_planifiee = productions[production].duration_hours
                    production.is_ordre_travail_id.duree_planifiee = duree_planifiee
                if self.type_donnees=='operation':
                    heure_debut_operation_actuelle = productions[production].operation_id.heure_debut
                    date_planned_start_of_actuelle =  production.date_planned_start
                    if heure_debut_operation_actuelle and date_planned_start_of_actuelle:
                        delta = heure_debut_operation_actuelle - date_planned_start_of_actuelle
                        #La nouvelle heure de début de l'OF est égale à la nouvelle heure de l'opération moins ce delta
                        date_planned_start_new = heure_debut_operation_modifiee - delta

                _logger.info("OF %s : date_planned_start %s → %s", production.name, production.date_planned_start, date_planned_start_new)
                production.date_planned_start = date_planned_start_new
            
      
        # Mettre à jour l'employé sur les opérations liées aux tâches
        #tasks = self.tache_ids.filtered(lambda t: t.operation_id and t.start_date)
        tasks = self.tache_ids
        updated_lines = self._update_operation_employees_from_tasks(tasks)


        nb = len(productions)
        msg_parts = [f"{nb} OF mis à jour"]
        if nb_supprimes:
            msg_parts.append(f"{nb_supprimes} OF terminés retirés du planning")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Mise à jour date OF',
                'message': ", ".join(msg_parts) + ".",
                'type': 'success' if nb else 'warning',
                'sticky': False,
            }
        }




    def action_maj_date_operation(self):
        """Ajuste heure_debut des opérations (is.ordre.travail.line) depuis les start_date des tâches,
        puis recalcule les opérations suivantes de chaque OT en conservant la logique actuelle (au plus tôt).
        """
        self.ensure_one()
        Task = self.env['is.gestion.tache']
        Op = self.env['is.ordre.travail.line']
        Ordre = self.env['is.ordre.travail']

        tasks = self.tache_ids.filtered(lambda t: t.operation_id and t.start_date)
        if not tasks:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Mise à jour opérations',
                    'message': "Aucune tâche avec opération et date de début.",
                    'type': 'warning',
                    'sticky': False,
                }
            }

        # Grouper par OT et traiter dans l'ordre des séquences
        ops_by_ordre = {}
        for t in tasks:
            line = t.operation_id
            if not line.ordre_id:
                continue
            ops_by_ordre.setdefault(line.ordre_id.id, []).append((line, t.start_date))

        updated_ops = 0

        for ordre_id, items in ops_by_ordre.items():
            ordre = Ordre.browse(ordre_id)
            # Indexer les lignes de l'OT par id pour accès rapide et ordonner par sequence
            all_lines = self.env['is.ordre.travail.line'].search([('ordre_id', '=', ordre.id)], order="sequence")
            seq_index = {l.id: i for i, l in enumerate(all_lines)}
            # Trier les items par la position de la ligne dans l'OT (séquence croissante)
            items.sort(key=lambda it: seq_index.get(it[0].id, 10**9))

            for line, start_dt in items:
                # 0) Trouver la tâche correspondante pour récupérer la durée
                corresponding_task = None
                for t in tasks:
                    if t.operation_id.id == line.id:
                        corresponding_task = t
                        break
                
                # 1) Fixer l'heure_debut de la ligne concernée et recalculer son heure_fin
                line.heure_debut = start_dt
                
                # 1.1) Mettre à jour duree_unitaire avec la durée de la tâche si disponible
                if corresponding_task and corresponding_task.duration_hours:
                    line.duree_unitaire = corresponding_task.duration_hours
                
                workcenter_id = line.workcenter_id.id
                duree = line.reste
                # Recalcule heure_fin de cette ligne en tenant compte des dispos
                heure_fin = ordre.get_heure_debut_fin(workcenter_id, duree, heure_debut=start_dt, tache=line)
                line.heure_fin = heure_fin
                updated_ops += 1

                # 2) Recalculer les opérations suivantes (logique au_plus_tot)
                # Préparer variables de propagation comme dans calculer_charge_ordre_travail
                heure_debut = heure_fin
                duree_precedente = (heure_fin - start_dt).total_seconds()/3600 if (heure_fin and start_dt) else 0
                mem_tps_apres = line.tps_apres

                # Parcourir les lignes suivantes dans l'ordre
                found_current = False
                for tache in all_lines:
                    if not found_current:
                        if tache.id == line.id:
                            found_current = True
                        continue
                    # Décale la date de début car 'Tps passage après' (en heures ouvrées)
                    if mem_tps_apres and mem_tps_apres > 0 and heure_debut:
                        heure_debut = ordre.get_heure_debut_fin(tache.workcenter_id.id, mem_tps_apres, heure_debut=heure_debut, tache=False)
                    # Recouvrement (% de la durée précédente)
                    duree_recouvrement = (duree_precedente or 0) * (tache.recouvrement or 0) / 100.0
                    if heure_debut:
                        heure_debut = heure_debut - timedelta(hours=duree_recouvrement)
                    # Durée de la tache
                    duree = tache.reste
                    # Calcul heure_fin selon dispos et lier la tache aux dispos
                    heure_fin = ordre.get_heure_debut_fin(tache.workcenter_id.id, duree, heure_debut=heure_debut, tache=tache)
                    # Écriture
                    tache.heure_debut = heure_debut
                    tache.heure_fin = heure_fin
                    updated_ops += 1
                    # Préparer pour la suivante
                    duree_relle = (heure_fin - heure_debut).total_seconds()/3600 if (heure_fin and heure_debut) else 0
                    heure_debut = heure_fin
                    duree_precedente = duree_relle
                    mem_tps_apres = tache.tps_apres

        # Mettre à jour l'employé sur les opérations liées aux tâches
        updated_lines = self._update_operation_employees_from_tasks(tasks)
        
        # Mettre à jour les durées unitaires sur les opérations liées aux tâches
        updated_durations = self._update_operation_durations_from_tasks(tasks)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Mise à jour opérations',
                'message': f"{updated_ops} opérations recalculées, {updated_lines} employés affectés, {updated_durations} durées mises à jour.",
                'type': 'success' if (updated_ops or updated_lines or updated_durations) else 'warning',
                'sticky': False,
            }
        }


class is_gestion_tache_affaire(models.Model):
    _name='is.gestion.tache.affaire'
    _description='Affaires pour la gestion des tâches'
    _order='name'

    name        = fields.Char("Affaire", required=True)
    order_id    = fields.Many2one('sale.order', string="Commande")
    color       = fields.Char(string="Couleur", compute='_compute_color', store=True, readonly=True)
    planning_id = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')


    @api.depends('order_id.is_couleur_affaire')
    def _compute_color(self):
        for obj in self:
            color = False
            if obj.order_id:
                color = obj.order_id.is_couleur_affaire
            obj.color = color


class is_gestion_tache_operateur(models.Model):
    _name='is.gestion.tache.operateur'
    _description='Opérateurs pour la gestion des tâches'
    _order='operator_id'
    _rec_name = 'operator_id'

    operator_id    = fields.Many2one('hr.employee', string="Opérateur", required=True)
    planning_id    = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')


class is_gestion_tache_workcenter(models.Model):
    _name='is.gestion.tache.workcenter'
    _description='Postes de charge pour la gestion des tâches'
    _order='workcenter_id'
    _rec_name = 'workcenter_id'

    workcenter_id = fields.Many2one('mrp.workcenter', string="Poste de charge", required=True)
    planning_id   = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')


class is_gestion_tache_fermeture(models.Model):
    _name='is.gestion.tache.fermeture'
    _description='Fermetures pour la gestion des tâches'
    _order='date_fermeture desc, operator_id'
    _rec_name = 'intitule'

    date_fermeture = fields.Date(string="Date de fermeture", required=True)
    periode        = fields.Selection([
        ('journee', 'Journée complète'),
        ('matin', 'Matin'),
        ('apres_midi', 'Après-midi'),
    ], string="Période", default='journee', required=True)
    operator_id    = fields.Many2one('hr.employee', string="Opérateur")
    workcenter_id  = fields.Many2one('mrp.workcenter', string="Poste de charge")
    intitule       = fields.Char(string="Intitulé")
    planning_id    = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')


class is_gestion_tache(models.Model):
    _name='is.gestion.tache'
    _description='Gestion des tâches dans Odoo avec interface en Flask / HTMX'
    _order='name'

    @api.depends('start_date', 'duration_hours')
    def _compute_end_date(self):
        for obj in self:
            end_date = False
            if obj.start_date and obj.duration_hours:
                # Calculer end_date basé sur les slots (fin calendaire)
                # DAY_DURATION_HOURS = 7 heures de travail par jour
                # HALF_DAY_HOURS = 3.5 heures de travail par slot
                # 1 journée = 24 heures calendaires = 2 slots
                # 1 slot = 12 heures calendaires
                DAY_DURATION_HOURS = 7.0  # Heures de travail par jour
                HALF_DAY_HOURS = DAY_DURATION_HOURS / 2  # 3.5 heures de travail par slot
                SLOT_CALENDAR_HOURS = 12.0  # Heures calendaires par slot (24h / 2 slots)

                # Convertir duration_hours en nombre de slots (arrondi au supérieur)
                import math
                remaining_slots = int(math.ceil(obj.duration_hours / HALF_DAY_HOURS))

                # Avance slot par slot (12h calendaires) en ne décomptant que les slots
                # dont le jour est ouvré : les slots des jours fermés (week-end, fermeture)
                # allongent la durée calendaire sans compter dans la durée réelle travaillée.
                planning = obj.planning_id
                current = obj.start_date
                while remaining_slots > 0:
                    if planning and not planning.est_jour_ouvre(
                        current.date(),
                        'matin' if current.hour < 12 else 'apres_midi',
                        operator_id=obj.operator_id.id,
                        workcenter_id=obj.workcenter_id.id,
                    ):
                        current = current + timedelta(hours=SLOT_CALENDAR_HOURS)
                        continue
                    remaining_slots -= 1
                    current = current + timedelta(hours=SLOT_CALENDAR_HOURS)
                end_date = current
            obj.end_date = end_date

    name           = fields.Char("Tache", required=True)
    operator_id    = fields.Many2one('hr.employee', string="Opérateur")
    workcenter_id  = fields.Many2one('mrp.workcenter', string="Poste de charge")
    affaire_id     = fields.Many2one('is.gestion.tache.affaire', string="Affaire", required=False)
    start_date     = fields.Datetime(string="Date de début", required=True)
    duration_hours = fields.Float(string="Durée (heures)", required=True)
    end_date       = fields.Datetime(string="Date de fin", compute='_compute_end_date', store=True, readonly=True)
    planning_id    = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')

    order_id         = fields.Many2one('sale.order', string="Commande")
    production_id    = fields.Many2one('mrp.production', string="OF")
    ordre_travail_id = fields.Many2one("is.ordre.travail", "Ordre de travail")
    operation_id     = fields.Many2one("is.ordre.travail.line", "Opération")
    product_qty      = fields.Float(string="Reste à produire")
    is_derniere_date_prevue = fields.Date("Dernière date prévue")

