from app import app, db, User, Ticket, TicketMessage # AJOUT DE Ticket et TicketMessage

with app.app_context():
    # ATTENTION: Si vous aviez des messages de contact importants dans l'ancienne table 'contact_message',
    # ils seront perdus car db.create_all() ne gère pas les migrations de schéma complexes.
    # Cette commande va créer les nouvelles tables 'ticket' et 'ticket_message'.
    db.create_all()
    print("Database tables created (or already existed).")
    # Si vous avez un utilisateur admin initial, vous pouvez le créer ici si la DB est vide.
    # Exemple (décommenter si nécessaire et remplacer les valeurs):
    # import os
    # from werkzeug.security import generate_password_hash
    # admin_email = os.environ.get('ADMIN_EMAIL')
    # admin_password = os.environ.get('ADMIN_PASSWORD')
    # if admin_email and admin_password:
    #     existing_admin = User.query.filter_by(email=admin_email).first()
    #     if not existing_admin:
    #         print(f"Creating initial admin user: {admin_email}")
    #         new_admin = User(email=admin_email, password_hash=generate_password_hash(admin_password), is_premium=True, is_admin=True)
    #         db.session.add(new_admin)
    #         db.session.commit()
    #         print("Initial admin user created successfully.")
    #     else:
    #         print(f"Admin user '{admin_email}' already exists. Skipping creation.")
    # else:
    #     print("WARNING: ADMIN_EMAIL or ADMIN_PASSWORD environment variables not set. Skipping admin user creation.")