#!/bin/bash

# Ce script lance simplement Gunicorn.
# L'initialisation de la base de données sera faite manuellement sur Render.
gunicorn app:app --bind 0.0.0.0:$PORT