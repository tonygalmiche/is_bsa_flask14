# -*- coding: utf-8 -*-
{
    "name" : "InfoSaône - Gestion des tâches pour BSA avec Odoo 14 et interface en Flask / HTMX",
    "version" : "0.1",
    "author" : "InfoSaône / Tony Galmiche",
    "category" : "InfoSaône",
    "description": """
InfoSaône - Gestion des tâches pour BSA avec Odoo 14 et interface en Flask / HTMX
===================================================
""",
    "maintainer": "InfoSaône",
    "website": "http://www.infosaone.com",
    "depends" : [
        "is_bsa14",       
    ],
    "data" : [
        "security/ir.model.access.csv",    
        "views/is_gestion_tache_view.xml",
    ],
    "installable": True,
    "active": False,
    "application": True
}

