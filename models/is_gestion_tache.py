# -*- coding: utf-8 -*-
from odoo import models,fields,api
from odoo.exceptions import Warning
import datetime


class is_gestion_tache(models.Model):
    _name='is.gestion.tache'
    _description='Gestion des tâches dans Odoo avec interface en Flask / HTMX'
    _order='name'

    name = fields.Char("Tache", required=True)

    # operator_id = fields.Many2one('hr.employee', string="Opérateur", required=True)
    # affaire = fields.Many2one('is.affair', string="Affaire", required=True)
    # start_date = fields.Datetime(string="Date de début", required=True)
    # duration_hours = fields.Float(string="Durée (heures)", required=True)


#   "id": str(uuid.uuid4()),
#         "operator_id": 9,
#         "affair_id": 1,
#         "start_date": datetime.combine(START_DATE + timedelta(days=18), datetime.min.time().replace(hour=8)),  # Slot 36 (Jour 19 AM)
#         "duration_hours": 14,  # 4 slots
#         "name": "Review Alpha"
#     },