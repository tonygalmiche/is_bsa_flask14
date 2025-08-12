# -*- coding: utf-8 -*-
from odoo import models,fields,api
from odoo.exceptions import Warning
import datetime


class is_gestion_tache(models.Model):
    _name='is.gestion.tache'
    _description='Gestion des tâches dans Odoo avec interface en Flask / HTMX'
    _order='name'

    name = fields.Char("Tache", required=True)

