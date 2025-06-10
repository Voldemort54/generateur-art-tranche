from app import app, db, User, ContactMessage # AJOUT DE ContactMessage

with app.app_context():
    db.create_all()
    print("Database tables created (or already existed).")
    # Si vous avez un utilisateur admin initial, vous pouvez le créer ici si la DB est vide.
    # Exemple (décommenter si nécessaire et remplacer les valeurs):
    # admin_email = os.environ.get('ADMIN_EMAIL')
    # admin_password = os.environ.get('ADMIN_PASSWORD')
    # if admin_email and admin_password:
    #     existing_admin = User.query.filter_by(email=admin_email).first()
    #     if not existing_admin:
    #         from werkzeug.security import generate_password_hash # Import ici ou en haut
    #         print(f"Creating initial admin user: {admin_email}")
    #         new_admin = User(email=admin_email, password_hash=generate_password_hash(admin_password), is_premium=True, is_admin=True)
    #         db.session.add(new_admin)
    #         db.session.commit()
    #         print("Initial admin user created successfully.")
    #     else:
    #         print(f"Admin user '{admin_email}' already exists. Skipping creation.")
    # else:
    #     print("WARNING: ADMIN_EMAIL or ADMIN_PASSWORD environment variables not set. Skipping admin user creation.")