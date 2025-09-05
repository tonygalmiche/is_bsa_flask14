# -*- coding: utf-8 -*-
from odoo import models,fields,api
from odoo.exceptions import Warning
from datetime import datetime, timedelta, date
import random


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

    name          = fields.Char("Planning", required=True)
    tache_ids     = fields.One2many('is.gestion.tache'          , 'planning_id', string="Tâches")
    affaire_ids   = fields.One2many('is.gestion.tache.affaire'  , 'planning_id', string="Affaires")
    operateur_ids = fields.One2many('is.gestion.tache.operateur', 'planning_id', string="Opérateurs")
    fermeture_ids = fields.One2many('is.gestion.tache.fermeture', 'planning_id', string="Fermetures")
    affaire       = fields.Char(string="Affaire", help="Filtre sur le nom d'affaire. Vous pouvez saisir plusieurs valeurs séparées par des virgules.")
    type_donnees  = fields.Selection([
        ('operation', 'Opération'),
        ('of', 'OF'),
    ], string="Type de données", default='operation')
    workcenter_id = fields.Many2one('mrp.workcenter', 'Poste de charge')
    tache_count   = fields.Integer(string="Nb tâches", compute="_compute_counts")

    def _compute_counts(self):
        for rec in self:
            rec.tache_count = len(rec.tache_ids)


    def action_chargement_taches(self):
        """Action pour charger les tâches selon le type de données sélectionné"""
        cr=self._cr
        if self.type_donnees=='operation' and self.workcenter_id:
            self.tache_ids.unlink()
            self.affaire_ids.unlink()
            self.operateur_ids.unlink()


            #** Ajout des opérateurs ******************************************
            domain=[
                ('is_workcenter_id', '=' , self.workcenter_id.id),
            ]
            operateurs=self.env['hr.employee'].search(domain)

            default_operator_id=False
            for operateur in operateurs:
                vals={
                    "operator_id"  : operateur.id,
                    "planning_id"    : self.id,
                }
                res=self.env['is.gestion.tache.operateur'].create(vals)
                default_operator_id = operateur.id
            #******************************************************************

            #** Recherche des taches et affaires ******************************
            SQL="""
                select 
                    so.id order_id,
                    so.is_nom_affaire affaire_name,
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
                    line.reste duration_hours,
                    line.heure_debut start_date,
                    line.employe_id
                from is_ordre_travail_line line join is_ordre_travail ot on line.ordre_id=ot.id
                                                join mrp_production mp on ot.production_id=mp.id
                                                join sale_order so on mp.is_sale_order_id=so.id
                                                join product_product pp on mp.product_id=pp.id
                                                join product_template pt on pp.product_tmpl_id=pt.id

                where line.state not in ('annule','termine')
                    and ot.state!='termine'
                    and mp.state not in  ('cancer','done')
                    and line.workcenter_id=%s
                    and mp.is_pret='oui'
            """

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

            # SQL finale (limite optionnelle)
            # SQL += "\n                -- limit 20;\n            # "

            cr.execute(SQL, params)
            rows = cr.dictfetchall()   
            orders={}       
            for row in rows:

                #** Ajout de l'affaire ****************************************
                if row['order_id'] not in orders:
                    color = generer_couleur_foncee()
                    vals={
                        "name"       : row['affaire_name'],
                        "planning_id": self.id,
                        "color"      : color,
                    }
                    affaire=self.env['is.gestion.tache.affaire'].create(vals)
                    orders[row['order_id']] = affaire
                else:
                    affaire=orders[row['order_id']]
                #**************************************************************

                #** Ajout de la tache *****************************************
                if affaire:
                    start_date = row['start_date']
                    if start_date< datetime.now():
                        start_date =  datetime.now()

                    product = self.env['product.product'].search([('id','=',row['product_id'])])[0]
                    variant = product.product_template_attribute_value_ids._get_combination_name()
                    name = "[%s] %s" % (variant, row.get('product_name'))
                    vals={
                        "name"          : name,
                        "operator_id"   : row['employe_id'] or default_operator_id,
                        "affaire_id"    : affaire.id,
                        "start_date"    : start_date,
                        "duration_hours": row['duration_hours'],
                        "planning_id"   : self.id,
                        "order_id"   : row['order_id'],
                        "production_id"   : row['production_id'],
                        "ordre_travail_id"   : row['ordre_travail_id'],
                        "operation_id"   : row['operation_id'],
                    }
                    res=self.env['is.gestion.tache'].create(vals)
                #**************************************************************

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

            # Déterminer la liste des employés cibles
            employee_ids = planning.operateur_ids.mapped('operator_id')
            if not employee_ids and planning.workcenter_id:
                employee_ids = self.env['hr.employee'].search([
                    ('is_workcenter_id', '=', planning.workcenter_id.id)
                ])

            if not employee_ids:
                continue

            vals_list = []
            # Set pour éviter les doublons (opérateur, jour)
            fermeture_keys = set()

            # 1) Récupérer toutes les absences (is.absence) des employés cibles
            absences = self.env['is.absence'].search([
                ('employe_id', 'in', employee_ids.ids),
            ])
            for absn in absences:
                # Déterminer la plage de dates (par jour) couverte par l'absence
                start_dt = absn.date_debut
                end_dt = absn.date_fin
                if not start_dt or not end_dt or start_dt >= end_dt:
                    continue

                # Fin exclusive => soustraire 1 seconde pour inclure le dernier jour
                last_day = (end_dt - timedelta(seconds=1)).date()
                cur_day = start_dt.date()

                # Intitulé = motif [+ commentaire]
                intitule = absn.motif_id.name or 'Absence'
                if absn.commentaire:
                    intitule = f"{intitule} - {absn.commentaire}"

                while cur_day <= last_day:
                    key = (absn.employe_id.id, cur_day)
                    if key not in fermeture_keys:
                        vals_list.append({
                            'planning_id': planning.id,
                            'operator_id': absn.employe_id.id,
                            'date_fermeture': cur_day,
                            'intitule': intitule,
                        })
                        fermeture_keys.add(key)
                    cur_day = cur_day + timedelta(days=1)

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
                    if not start_dt or not end_dt or start_dt >= end_dt:
                        continue

                    # Fin exclusive => soustraire 1 seconde pour inclure le dernier jour
                    last_day = (end_dt - timedelta(seconds=1)).date()
                    cur_day = start_dt.date()

                    # Intitulé depuis le calendrier
                    intitule = leave.name or 'Fermeture calendrier'

                    # Pour tous les employés rattachés à ce calendrier
                    emps = employees_by_calendar.get(leave.calendar_id.id, [])
                    if not emps:
                        continue

                    while cur_day <= last_day:
                        for emp in emps:
                            key = (emp.id, cur_day)
                            if key not in fermeture_keys:
                                vals_list.append({
                                    'planning_id': planning.id,
                                    'operator_id': emp.id,
                                    'date_fermeture': cur_day,
                                    'intitule': intitule,
                                })
                                fermeture_keys.add(key)
                        cur_day = cur_day + timedelta(days=1)

            if vals_list:
                self.env['is.gestion.tache.fermeture'].create(vals_list)

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



    def action_maj_date_of(self):
        """Met à jour mrp.production.is_date_planifiee depuis les start_date des tâches du planning.
        Pour chaque OF lié, utilise la date de début la plus tôt.
        """
        self.ensure_one()
        tasks = self.tache_ids.filtered(lambda t: t.production_id and t.start_date)
        if not tasks:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Mise à jour date OF',
                    'message': "Aucune tâche avec OF et date de début.",
                    'type': 'warning',
                    'sticky': False,
                }
            }

        # Plus tôt par OF
        min_dates = {}
        for t in tasks:
            pid = t.production_id.id
            sd = t.start_date
            if pid not in min_dates or sd < min_dates[pid]:
                min_dates[pid] = sd

        # Adapter si le champ cible est de type Date
        field_def = self.env['mrp.production']._fields.get('is_date_planifiee')
        is_date_field = bool(field_def and getattr(field_def, 'type', None) == 'date')

        updated = 0
        for pid, dt in min_dates.items():
            prod = self.env['mrp.production'].browse(pid)
            value = dt.date() if is_date_field and hasattr(dt, 'date') else dt
            try:
                prod.write({'date_planned_start': value})
                updated += 1
            except Exception:
                # Ignorer silencieusement les erreurs d'accès/écriture pour ne pas bloquer l'action
                continue

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Mise à jour date OF',
                'message': f"{updated} OF mis à jour.",
                'type': 'success' if updated else 'warning',
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
                # 1) Fixer l'heure_debut de la ligne concernée et recalculer son heure_fin
                line.heure_debut = start_dt
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

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Mise à jour opérations',
                'message': f"{updated_ops} opérations recalculées.",
                'type': 'success' if updated_ops else 'warning',
                'sticky': False,
            }
        }


class is_gestion_tache_affaire(models.Model):
    _name='is.gestion.tache.affaire'
    _description='Affaires pour la gestion des tâches'
    _order='name'

    name        = fields.Char("Affaire", required=True)
    color       = fields.Char(string="Couleur")
    planning_id = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')



class is_gestion_tache_operateur(models.Model):
    _name='is.gestion.tache.operateur'
    _description='Opérateurs pour la gestion des tâches'
    _order='operator_id'
    _rec_name = 'operator_id'

    operator_id    = fields.Many2one('hr.employee', string="Opérateur", required=True)
    planning_id    = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')


class is_gestion_tache_fermeture(models.Model):
    _name='is.gestion.tache.fermeture'
    _description='Fermetures pour la gestion des tâches'
    _order='date_fermeture desc, operator_id'
    _rec_name = 'intitule'

    date_fermeture = fields.Date(string="Date de fermeture", required=True)
    operator_id    = fields.Many2one('hr.employee', string="Opérateur")
    intitule       = fields.Char(string="Intitulé")
    planning_id    = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')


class is_gestion_tache(models.Model):
    _name='is.gestion.tache'
    _description='Gestion des tâches dans Odoo avec interface en Flask / HTMX'
    _order='name'

    name           = fields.Char("Tache", required=True)
    operator_id    = fields.Many2one('hr.employee', string="Opérateur", required=True)
    affaire_id     = fields.Many2one('is.gestion.tache.affaire', string="Affaire", required=False)
    start_date     = fields.Datetime(string="Date de début", required=True)
    duration_hours = fields.Float(string="Durée (heures)", required=True)
    planning_id    = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')

    order_id         = fields.Many2one('sale.order', string="Commande")
    production_id    = fields.Many2one('mrp.production', string="OF")
    ordre_travail_id = fields.Many2one("is.ordre.travail", "Ordre de travail")
    operation_id     = fields.Many2one("is.ordre.travail.line", "Opération")

