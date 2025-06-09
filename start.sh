#!/bin/bash

# Exécute la commande pour créer la base de données
# -c exécute le code Python comme une chaîne de caractères
# app.app_context() assure que les opérations sur la base de données sont exécutées dans le bon contexte Flask
python -c "from app import db, app; with app.app_context(): db.create_all()"

# Lance Gunicorn en écoutant sur le port fourni par Render
# Le $PORT est une variable d'environnement définie par Render
gunicorn app:app --bind 0.0.0.0:$PORT