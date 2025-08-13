# -*- coding: utf-8 -*-
from odoo import models,fields,api
from odoo.exceptions import Warning
import datetime




class is_gestion_tache_planning(models.Model):
    _name='is.gestion.tache.planning'
    _description='Planning pour la gestion des tâches'
    _order='name'

    name        = fields.Char("Planning", required=True)
    tache_ids   = fields.One2many('is.gestion.tache', 'planning_id', string="Tâches")
    affaire_ids = fields.One2many('is.gestion.tache.affaire', 'planning_id', string="Affaires")
    type_donnees = fields.Selection([
        ('operation', 'Opération'),
        ('of', 'OF'),
    ], string="Type de données", default='operation')
    workcenter_id = fields.Many2one('mrp.workcenter', 'Poste de charge')


    def action_chargement_taches(self):
        """Action pour charger les tâches selon le type de données sélectionné"""
        print(f"Chargement des tâches pour le planning '{self.name}' avec le type de données '{self.type_donnees}'")
        return True


class is_gestion_tache_affaire(models.Model):
    _name='is.gestion.tache.affaire'
    _description='Affaires pour la gestion des tâches'
    _order='name'

    name        = fields.Char("Affaire", required=True)
    color       = fields.Char(string="Couleur")
    planning_id = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')


class is_gestion_tache(models.Model):
    _name='is.gestion.tache'
    _description='Gestion des tâches dans Odoo avec interface en Flask / HTMX'
    _order='name'

    name           = fields.Char("Tache", required=True)
    operator_id    = fields.Many2one('hr.employee', string="Opérateur", required=True)
    affaire        = fields.Many2one('is.gestion.tache.affaire', string="Affaire", required=True)
    start_date     = fields.Datetime(string="Date de début", required=True)
    duration_hours = fields.Float(string="Durée (heures)", required=True)
    planning_id    = fields.Many2one('is.gestion.tache.planning', string="Planning", ondelete='cascade')

