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

                where line.state not in ('annule','termine')
                    and ot.state!='termine'
                    and mp.state not in  ('cancer','done')
                    and line.workcenter_id=%s
                    and mp.is_pret='oui'
                    -- and mp.is_sale_order_id=756
                -- limit 20;
            """
            cr.execute(SQL,[self.workcenter_id.id])
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
                    vals={
                        "name"          : "[%s] %s"%(row['mp_name'],row['line_name']),
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
          une ligne par jour et par opérateur pour chaque absence.
        - L'intitulé reprend le motif d'absence et le commentaire éventuel.
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

            # Récupérer toutes les absences des employés cibles
            absences = self.env['is.absence'].search([
                ('employe_id', 'in', employee_ids.ids),
            ])

            vals_list = []
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
                    vals_list.append({
                        'planning_id': planning.id,
                        'operator_id': absn.employe_id.id,
                        'date_fermeture': cur_day,
                        'intitule': intitule,
                    })
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

