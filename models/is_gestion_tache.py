# -*- coding: utf-8 -*-
from odoo import models,fields,api
from odoo.exceptions import Warning
from datetime import datetime
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
    type_donnees  = fields.Selection([
        ('operation', 'Opération'),
        ('of', 'OF'),
    ], string="Type de données", default='operation')
    workcenter_id = fields.Many2one('mrp.workcenter', 'Poste de charge')


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

