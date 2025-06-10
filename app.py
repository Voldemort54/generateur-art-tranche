from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import shutil
from datetime import datetime, date, timedelta
import secrets
import functools
import json
import math # Import nécessaire pour math.ceil

# Importez vos fonctions de traitement d'image depuis le dossier core_logic
from core_logic.image_processing import generer_tranches_individuelles, generer_pdf_a_partir_tranches

app = Flask(__name__)

# Lire la clé secrète depuis les variables d'environnement
app.secret_key = os.environ.get('SECRET_KEY', 'votre_cle_secrete_de_secours_ici_pour_dev_seulement')

# --- Configuration de la base de données ---
db_uri_env = os.environ.get('DATABASE_URL')
print(f"DEBUG: DATABASE_URL from environment: {db_uri_env}")
if db_uri_env:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri_env.replace("postgres://", "postgresql://", 1)
    print("DEBUG: Using DATABASE_URL from environment.")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    print("DEBUG: DATABASE_URL not found, falling back to SQLite.")

print(f"DEBUG: Final SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Configuration Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
login_manager.login_message_category = 'info'

# --- Modèle Utilisateur ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_premium = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    premium_until = db.Column(db.Date, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'

class ContactMessage(db.Model):
    __tablename__ = 'contact_message_old'
    id = db.Column(db.Integer, primary_key=True)
    sender_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='Ouvert', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('TicketMessage', backref='ticket', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Ticket {self.id} - {self.subject} - {self.user_email}>'

class TicketMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read_by_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_read_by_user = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<TicketMessage {self.id} - Ticket {self.ticket_id} - {self.sender_type}>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Configuration des dossiers d'upload et de génération ---
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
GENERATED_PDF_FOLDER = os.path.join(app.root_path, 'generated_pdfs')
TEMP_PROCESSING_FOLDER = os.path.join(app.root_path, 'temp_processing')
SIMULATION_IMG_FOLDER = os.path.join(app.root_path, 'simulation_images')


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_PDF_FOLDER, exist_ok=True)
os.makedirs(TEMP_PROCESSING_FOLDER, exist_ok=True)
os.makedirs(SIMULATION_IMG_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Fonctions utilitaires ---
def admin_required(f):
    """Décorateur pour exiger que l'utilisateur soit un administrateur."""
    @login_required
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin: 
            flash("Accès non autorisé : Vous n'êtes pas un administrateur.", 'danger')
            return redirect(url_for('public_home'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes de l'application ---

@app.route('/')
def public_home():
    return render_template('home.html') 

@app.route('/app')
@login_required 
def app_dashboard():
    # Récupérer les chemins de la session si une génération vient d'avoir lieu
    simulation_image_url = session.pop('last_simulation_image_url', None)
    last_generated_pdf_filename = session.pop('last_generated_pdf_filename', None)
    
    # Calculer les jours restants si premium
    days_remaining = None
    if current_user.is_premium and current_user.premium_until:
        today = date.today()
        if current_user.premium_until >= today:
            days_remaining = (current_user.premium_until - today).days
        else:
            current_user.is_premium = False
            current_user.premium_until = None
            db.session.commit()
            flash("Votre abonnement a expiré. Veuillez le renouveler.", 'danger')
            return redirect(url_for('subscribe'))

    if not current_user.is_premium and not current_user.is_admin: 
        flash("Vous devez avoir un abonnement actif pour utiliser le générateur.", 'info')
        return redirect(url_for('subscribe'))
    
    return render_template('index.html', is_premium=current_user.is_premium, days_remaining=days_remaining, 
                           simulation_image_url=simulation_image_url, 
                           last_generated_pdf_filename=last_generated_pdf_filename)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('app_dashboard'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Connexion réussie !', 'success')
            return redirect(url_for('app_dashboard'))
        else:
            flash('Email ou mot de passe incorrect.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('app_dashboard'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Les mots de passe ne correspondent pas.', 'danger')
            return redirect(url_for('register'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Cet email est déjà enregistré.', 'danger')
            return redirect(url_for('register'))

        new_user = User(email=email, is_premium=False, is_admin=False)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Inscription réussie ! Vous pouvez maintenant vous connecter.', 'success')
        return redirect(url_for('login'))
            
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('public_home'))

@app.route('/subscribe')
@login_required
def subscribe():
    site_base_url = "https://generateur-art-tranche.onrender.com" 
    return render_template('subscribe.html', site_base_url=site_base_url)

@app.route('/legal')
def legal_info():
    return render_template('legal.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact_page():
    if request.method == 'POST':
        sender_email = request.form['sender_email']
        subject = request.form['subject']
        message_content = request.form['message_content']

        if not sender_email or not subject or not message_content:
            flash('Tous les champs du formulaire de contact sont requis.', 'danger')
            return redirect(url_for('contact_page'))
        
        if '@' not in sender_email or '.' not in sender_email:
            flash('Veuillez entrer une adresse e-mail valide.', 'danger')
            return redirect(url_for('contact_page'))

        try:
            new_ticket = Ticket(
                user_id=current_user.id if current_user.is_authenticated else None,
                user_email=sender_email,
                subject=subject,
                status='Ouvert'
            )
            db.session.add(new_ticket)
            db.session.flush()

            new_ticket_message = TicketMessage(
                ticket_id=new_ticket.id,
                sender_type='user',
                message_content=message_content,
                is_read_by_admin=False,
                is_read_by_user=True
            )
            db.session.add(new_ticket_message)
            db.session.commit()
            flash('Votre message a été envoyé avec succès ! Nous vous recontacterons bientôt.', 'success')
            return redirect(url_for('contact_page'))
        except Exception as e:
            db.session.rollback()
            flash(f'Une erreur est survenue lors de l\'envoi de votre message : {e}', 'danger')
            print(f"Erreur lors de l'enregistrement du message de contact: {e}")
            return redirect(url_for('contact_page'))

    prefill_email = current_user.email if current_user.is_authenticated else ''
    return render_template('contact.html', prefill_email=prefill_email)


@app.route('/account')
@login_required 
def account_management():
    return render_template('account.html', current_user=current_user)

@app.route('/account/tickets')
@login_required
def account_tickets():
    user_tickets = Ticket.query.filter_by(user_id=current_user.id).order_by(Ticket.updated_at.desc()).all()
    
    user_unread_tickets_count = db.session.query(TicketMessage).filter(
        TicketMessage.ticket.has(user_id=current_user.id),
        TicketMessage.sender_type == 'admin',
        TicketMessage.is_read_by_user == False
    ).count()

    for ticket in user_tickets:
        ticket.has_unread_messages_by_user = False
        last_message = TicketMessage.query.filter_by(ticket_id=ticket.id).order_by(TicketMessage.timestamp.desc()).first()
        if last_message and last_message.sender_type == 'admin' and not last_message.is_read_by_user:
             ticket.has_unread_messages_by_user = True

    return render_template('account_tickets.html', tickets=user_tickets, user_unread_tickets_count=user_unread_tickets_count)


@app.route('/account/tickets/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
def account_ticket_detail(ticket_id):
    ticket = Ticket.query.filter_by(id=ticket_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        if ticket.status == 'Fermé':
            flash("Ce ticket est fermé et ne peut plus recevoir de réponses.", 'warning')
            return redirect(url_for('account_ticket_detail', ticket_id=ticket.id))

        message_content = request.form['message_content']
        if not message_content:
            flash('Le message de réponse ne peut pas être vide.', 'danger')
        else:
            try:
                new_message = TicketMessage(
                    ticket_id=ticket.id,
                    sender_type='user',
                    message_content=message_content,
                    is_read_by_admin=False,
                    is_read_by_user=True
                )
                db.session.add(new_message)
                ticket.status = 'En attente (réponse admin)'
                db.session.commit()
                flash('Votre réponse a été envoyée.', 'success')
                return redirect(url_for('account_ticket_detail', ticket_id=ticket.id))
            except Exception as e:
                db.session.rollback()
                flash(f'Erreur lors de l\'envoi de la réponse : {e}', 'danger')
                print(f"Erreur lors de l'envoi de la réponse utilisateur: {e}")

    for message in ticket.messages:
        if message.sender_type == 'admin' and not message.is_read_by_user:
            message.is_read_by_user = True
    db.session.commit()

    return render_template('account_ticket_detail.html', ticket=ticket, current_user=current_user)


# --- ROUTES D'ADMINISTRATION (Protégées) ---
@app.route('/admin')
@admin_required 
def admin_dashboard():
    users = User.query.all()
    unread_tickets_count = db.session.query(Ticket).join(TicketMessage).filter(
        TicketMessage.sender_type == 'user',
        TicketMessage.is_read_by_admin == False
    ).group_by(Ticket.id).count()

    return render_template('admin.html', users=users, unread_tickets_count=unread_tickets_count)

@app.route('/admin/tickets', methods=['GET'])
@admin_required
def admin_tickets():
    filter_email = request.args.get('email', '')
    filter_status = request.args.get('status', '')
    
    query = Ticket.query
    
    if filter_email:
        query = query.filter(Ticket.user_email.ilike(f'%{filter_email}%'))
        
    if filter_status and filter_status != 'Tous':
        query = query.filter_by(status=filter_status)

    tickets = query.order_by(Ticket.updated_at.desc()).all()
        
    for ticket in tickets:
        ticket.has_unread_messages_by_admin = False
        last_message = TicketMessage.query.filter_by(ticket_id=ticket.id).order_by(TicketMessage.timestamp.desc()).first()
        if last_message and last_message.sender_type == 'user' and not last_message.is_read_by_admin:
             ticket.has_unread_messages_by_admin = True

    return render_template('admin_tickets.html', tickets=tickets, filter_email=filter_email, filter_status=filter_status)

@app.route('/admin/tickets/<int:ticket_id>', methods=['GET', 'POST'])
@admin_required
def admin_ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)

    if request.method == 'POST':
        message_content = request.form['message_content']
        if not message_content:
            flash('Le message de réponse ne peut pas être vide.', 'danger')
        else:
            try:
                new_message = TicketMessage(
                    ticket_id=ticket.id,
                    sender_type='admin',
                    message_content=message_content,
                    is_read_by_admin=True,
                    is_read_by_user=False
                )
                db.session.add(new_message)
                ticket.status = 'En attente (réponse utilisateur)' 
                db.session.commit()
                flash('Votre réponse a été envoyée au ticket.', 'success')
                return redirect(url_for('admin_ticket_detail', ticket_id=ticket.id))
            except Exception as e:
                db.session.rollback()
                flash(f'Erreur lors de l\'envoi de la réponse : {e}', 'danger')
                print(f"Erreur lors de l'envoi de la réponse admin: {e}")

    for message in ticket.messages:
        if message.sender_type == 'user' and not message.is_read_by_admin:
            message.is_read_by_admin = True
    db.session.commit()

    return render_template('admin_ticket_detail.html', ticket=ticket)

@app.route('/admin/tickets/mark-as-read/<int:ticket_id>', methods=['POST'])
@admin_required
def admin_mark_ticket_as_read(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    try:
        for message in ticket.messages:
            if message.sender_type == 'user' and not message.is_read_by_admin:
                message.is_read_by_admin = True
        db.session.commit()
        flash(f"Ticket #{ticket.id} marqué comme lu.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la mise à jour du ticket: {e}", 'danger')
    return redirect(url_for('admin_tickets'))

@app.route('/admin/tickets/change-status/<int:ticket_id>', methods=['POST'])
@admin_required
def admin_change_ticket_status(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    new_status = request.form['new_status']
    allowed_statuses = ['Ouvert', 'En attente (réponse admin)', 'En attente (réponse utilisateur)', 'Fermé']
    if new_status in allowed_statuses:
        try:
            ticket.status = new_status
            db.session.commit()
            flash(f"Statut du ticket #{ticket.id} changé en '{new_status}'.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors du changement de statut: {e}", 'danger')
    else:
        flash("Statut invalide.", 'danger')
    return redirect(url_for('admin_ticket_detail', ticket_id=ticket.id))


@app.route('/admin/tickets/delete/<int:ticket_id>', methods=['POST'])
@admin_required
def admin_delete_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    try:
        db.session.delete(ticket)
        db.session.commit()
        flash(f"Ticket #{ticket.id} (Sujet: '{ticket.subject}') supprimé avec succès.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la suppression du ticket: {e}", 'danger')
    return redirect(url_for('admin_tickets'))


@app.route('/admin/toggle-premium/<int:user_id>', methods=['POST'])
@admin_required
def admin_toggle_premium(user_id):
    user = User.query.get_or_404(user_id)
    user.is_premium = not user.is_premium
    if user.is_premium:
        user.premium_until = date.today() + timedelta(days=30) 
        flash(f"Compte '{user.email}' activé en mode Premium jusqu'au {user.premium_until} !", 'success')
        print(f"ADMIN ACTION: {user.email} set to premium until {user.premium_until}.")
    else:
        user.premium_until = None
        flash(f"Compte '{user.email}' désactivé du mode Premium.", 'info')
        print(f"ADMIN ACTION: {user.email} set to non-premium.")

    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/set-admin/<int:user_id>', methods=['POST'])
@admin_required
def admin_set_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f"Statut administrateur de '{user.email}' changé à {user.is_admin}.", 'info')
    print(f"ADMIN ACTION: {user.email} admin status set to {user.is_admin}.")
    return redirect(url_for('admin_dashboard'))


@app.route('/generate', methods=['POST'])
@login_required
def generate_foreedge_form():
    if not current_user.is_premium and not current_user.is_admin: 
        flash("Vous devez avoir un abonnement actif pour générer des PDFs.", 'danger')
        return redirect(url_for('subscribe'))

    if 'image_source' not in request.files:
        flash('Aucun fichier image n\'a été sélectionné.', 'danger')
        return redirect(request.url)

    file = request.files['image_source']

    if file.filename == '':
        flash('Aucun fichier sélectionné. Veuillez choisir un fichier.', 'danger')
        return redirect(request.url)

    if not allowed_file(file.filename):
        flash(f'Type de fichier non autorisé. Seules les images {", ".join(ALLOWED_EXTENSIONS).upper()} sont acceptées.', 'danger')
        return redirect(url_for('app_dashboard'))

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    original_filename_base, original_filename_ext = os.path.splitext(file.filename)
    unique_filename = f"{original_filename_base}_{timestamp}{original_filename_ext}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    
    pdf_output_filename = f"foreedge_pattern_{timestamp}.pdf"
    pdf_final_path = os.path.join(GENERATED_PDF_FOLDER, pdf_output_filename)

    temp_tranches_dir = os.path.join(app.root_path, 'temp_processing', f"session_{timestamp}_{secrets.token_hex(8)}")
    os.makedirs(temp_tranches_dir, exist_ok=True)

    try:
        file.save(filepath)

        # Récupérer et valider les 3 éléments de saisie pour le calcul des pages
        try:
            # Assurez-vous que les valeurs sont non vides avant de tenter la conversion
            derniere_page_numerotee_str = request.form.get('derniere_page_numerotee', '')
            feuilles_avant_premiere_page_str = request.form.get('feuilles_avant_premiere_page', '')
            feuilles_apres_derniere_page_str = request.form.get('feuilles_apres_derniere_page', '')
            hauteur_livre_str = request.form.get('hauteur_livre', '')
            largeur_tranche_etiree_cible_str = request.form.get('largeur_tranche_etiree_cible', '')

            # Validation côté serveur pour les champs de formulaire vides ou non numériques
            if not derniere_page_numerotee_str.strip():
                raise ValueError("Numéro de la dernière page numérotée est requis.")
            if not feuilles_avant_premiere_page_str.strip():
                raise ValueError("Nombre de feuilles avant est requis.")
            if not feuilles_apres_derniere_page_str.strip():
                raise ValueError("Nombre de feuilles après est requis.")
            if not hauteur_livre_str.strip():
                raise ValueError("Hauteur des pages du livre est requise.")
            if not largeur_tranche_etiree_cible_str.strip():
                raise ValueError("Largeur des bandes imprimée est requise.")

            # Conversion en entier (même pour hauteur/largeur si step="1")
            derniere_page_numerotee = int(derniere_page_numerotee_str)
            feuilles_avant_premiere_page = int(feuilles_avant_premiere_page_str)
            feuilles_apres_derniere_page = int(feuilles_apres_derniere_page_str)
            hauteur_livre = int(hauteur_livre_str) # Conversion en int
            largeur_tranche_etiree_cible = int(largeur_tranche_etiree_cible_str) # Conversion en int

            # Validation des valeurs minimales côté serveur
            if derniere_page_numerotee < 1:
                raise ValueError("Le numéro de la dernière page numérotée doit être au moins 1.")
            if feuilles_avant_premiere_page < 0:
                raise ValueError("Le nombre de feuilles avant ne peut pas être négatif.")
            if feuilles_apres_derniere_page < 0:
                raise ValueError("Le nombre de feuilles après ne peut pas être négatif.")
            if hauteur_livre < 1:
                raise ValueError("La hauteur des pages du livre doit être au moins 1mm.")
            if largeur_tranche_etiree_cible < 1:
                raise ValueError("La largeur des bandes imprimée doit être au moins 1mm.")

            # Calcul du nombre total de pages (chaque feuille = 2 pages)
            nombre_pages_calcule = derniere_page_numerotee + (feuilles_avant_premiere_page * 2) + (feuilles_apres_derniere_page * 2)
            
            # Validation finale du nombre de pages calculé
            if nombre_pages_calcule < 2: # Au moins 2 pages pour un motif
                raise ValueError("Le nombre total de pages doit être d'au moins 2 pour générer un motif.")

        except ValueError as ve:
            flash(f"Erreur de saisie : {ve}. Veuillez vérifier vos paramètres numériques.", 'danger')
            return redirect(url_for('app_dashboard'))
        except Exception as e:
            flash(f"Une erreur est survenue lors de la validation des paramètres : {e}", 'danger')
            print(f"Erreur inattendue lors de la validation des paramètres (app.py): {e}")
            return redirect(url_for('app_dashboard'))


        dossier_tranches_genere, erreur_tranches = generer_tranches_individuelles(
            chemin_image_source=filepath,
            hauteur_livre_mm=hauteur_livre,
            nombre_pages_livre=nombre_pages_calcule,
            dpi_utilise=dpi_utilise,
            largeur_tranche_etiree_cible_mm=largeur_tranche_etiree_cible,
            progress_callback=lambda val, msg: None
        )

        if erreur_tranches:
            flash(f"Erreur lors de la génération des tranches : {erreur_tranches}", 'danger')
            return redirect(url_for('app_dashboard'))

        if not dossier_tranches_genere:
            flash("Échec inattendu lors de la génération des tranches (aucun dossier retourné).", 'danger')
            return redirect(url_for('app_dashboard'))


        pdf_final_path_actual, erreur_pdf = generer_pdf_a_partir_tranches(
            dossier_tranches_source=dossier_tranches_genere,
            hauteur_livre_mm_pdf=hauteur_livre, 
            largeur_tranche_etiree_cible_mm_pdf=largeur_tranche_etiree_cible,
            debut_numero_tranche=1,
            pas_numero_tranche=2,
            progress_callback=lambda val, msg: None,
            image_source_original_path=filepath,
            nombre_pages_livre_original=nombre_pages_calcule,
            output_pdf_path=pdf_final_path
        )

        if erreur_pdf:
            flash(f"Erreur lors de la génération du PDF : {erreur_pdf}", 'danger')
            return redirect(url_for('app_dashboard'))
        
        if not pdf_final_path_actual:
            flash("Échec inattendu lors de la génération du PDF (aucun chemin retourné).", 'danger')
            return redirect(url_for('app_dashboard'))

        flash('Votre PDF a été généré avec succès ! Cliquez sur le lien pour télécharger.', 'success')
        session['last_generated_pdf_filename'] = os.path.basename(pdf_final_path_actual)
        session['last_simulation_image_url'] = None

        return redirect(url_for('app_dashboard'))


    except Exception as e:
        flash(f"Une erreur inattendue est survenue : {e}", 'danger')
        print(f"Erreur inattendue dans /generate (bloc principal): {e}")
        return redirect(url_for('app_dashboard'))
    finally:
        if os.path.exists(filepath): 
            try:
                os.remove(filepath)
                print(f"DEBUG: Fichier source '{filepath}' supprimé.")
            except OSError as e:
                print(f"Erreur lors du nettoyage du fichier source '{filepath}': {e}")
        
        if os.path.exists(temp_tranches_dir): 
            try:
                shutil.rmtree(temp_tranches_dir)
                print(f"DEBUG: Dossier temporaire des tranches '{temp_tranches_dir}' supprimé.")
            except OSError as e:
                print(f"Erreur lors du nettoyage du dossier temporaire '{temp_tranches_dir}': {e}")
        
        # Le dossier SIMULATION_IMG_FOLDER n'est plus utilisé pour le nettoyage direct ici.


@app.route('/generated-pdfs/<path:filename>')
def get_generated_pdf(filename):
    from flask import send_from_directory
    return send_from_directory(GENERATED_PDF_FOLDER, filename, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)