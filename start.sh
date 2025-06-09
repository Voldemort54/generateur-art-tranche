#!/bin/bash

# Ce script lance simplement Gunicorn.
# L'initialisation de la base de données est maintenant gérée par la Build Command.
gunicorn app:app --bind 0.0.0.0:$PORT