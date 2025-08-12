# -*- coding: utf-8 -*-
# Configuration de la base de données PostgreSQL - EXEMPLE
# Copier ce fichier vers config.py et modifier les valeurs

DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'votre_base_odoo',  # Remplacer par le nom de votre base Odoo
    'user': 'odoo'                  # Utilisateur PostgreSQL (authentification sans mot de passe)
    # Si un mot de passe est nécessaire, décommentez la ligne suivante :
    # 'password': 'votre_mot_de_passe'
}
