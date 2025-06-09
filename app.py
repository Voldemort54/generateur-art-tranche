from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import shutil
from datetime import datetime, date # Importe datetime et date
import secrets

# Importez vos fonctions de traitement d'image depuis le dossier core_logic
from core_logic.image_processing import generer_tranches_individuelles, generer_pdf_a_partir_tranches

app = Flask(__name__)
app.secret_key = '04c3f5d7e8b2a196e0c7b4a1d8f3e9c2b7a6d5e4f3c2b1a0d9e8f7c6b5a4d3e2'

# --- Configuration de la base de données ---
# Utilise une variable d'environnement 'DATABASE_URL' pour la connexion à la base de données en production (PostgreSQL sur Render)
# Si 'DATABASE_URL' n'est pas définie (en développement local), utilise SQLite.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
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
    password_hash = db.Column(db.String(128), nullable=False)
    is_premium = db.Column(db.Boolean, default=False) # Champ pour le statut premium
    # premium_until = db.Column(db.Date, nullable=True) # Non utilisé dans cette version simplifiée de PayPal, mais gardé en mémoire pour une future extension

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Configuration des dossiers d'upload et de génération ---
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
GENERATED_PDF_FOLDER = os.path.join(app.root_path, 'generated_pdfs')
TEMP_PROCESSING_FOLDER = os.path.join(app.root_path, 'temp_processing')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_PDF_FOLDER, exist_ok=True)
os.makedirs(TEMP_PROCESSING_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes de l'application ---
@app.route('/')
@login_required
def index():
    if not current_user.is_premium:
        flash("Vous devez avoir un abonnement actif pour utiliser le générateur.", 'info')
        return redirect(url_for('subscribe'))
    
    # days_remaining = None # Non utilisé dans cette version simplifiée, mais gardé en mémoire pour une future extension
    return render_template('index.html', is_premium=current_user.is_premium, days_remaining=None) # Passe days_remaining=None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Connexion réussie !', 'success')
            return redirect(url_for('index')) 
        else:
            flash('Email ou mot de passe incorrect.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

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

        new_user = User(email=email, is_premium=False)
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
    return redirect(url_for('login'))

@app.route('/subscribe')
@login_required
def subscribe():
    # L'URL du site est passée à la template pour les redirections PayPal
    # L'URL complète de votre site déployé
    site_base_url = "https://generateur-art-tranche.onrender.com" 
    return render_template('subscribe.html', site_base_url=site_base_url)

# Routes de retour de PayPal (succès/annulation)
@app.route('/paypal-success')
@login_required
def paypal_success():
    flash('Paiement PayPal réussi ! Votre statut Premium sera activé sous peu.', 'success')
    flash('Veuillez noter que l\'activation peut prendre un moment ou nécessiter une vérification manuelle. Contactez l\'administrateur si nécessaire.', 'info')
    return redirect(url_for('index'))

@app.route('/paypal-cancel')
@login_required
def paypal_cancel():
    flash('Paiement PayPal annulé. Vous pouvez réessayer.', 'info')
    return redirect(url_for('index'))

@app.route('/generate', methods=['POST'])
@login_required
def generate_foreedge_form():
    if not current_user.is_premium: 
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
        return redirect(url_for('index'))

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    original_filename_base, original_filename_ext = os.path.splitext(file.filename)
    unique_filename = f"{original_filename_base}_{timestamp}{original_filename_ext}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    
    temp_tranches_dir = os.path.join(TEMP_PROCESSING_FOLDER, f"session_{timestamp}_{secrets.token_hex(8)}")
    os.makedirs(temp_tranches_dir, exist_ok=True)

    try:
        file.save(filepath)

        try:
            hauteur_livre = float(request.form['hauteur_livre'])
            if hauteur_livre <= 0:
                raise ValueError("La hauteur du livre doit être une valeur positive.")
            
            nombre_pages = int(request.form['nombre_pages'])
            if nombre_pages < 2:
                raise ValueError("Le nombre de pages doit être d'au moins 2.")
            
            largeur_tranche_etiree_cible = float(request.form['largeur_tranche_etiree_cible'])
            if largeur_tranche_etiree_cible <= 0:
                raise ValueError("La largeur de la tranche imprimée doit être une valeur positive.")
            
            debut_numero_tranche = int(request.form['debut_numero_tranche'])
            
            pas_numero_tranche = 2 

            dpi_utilise = 300 

        except ValueError as ve:
            flash(f"Erreur de saisie : {ve}. Veuillez vérifier vos paramètres numériques.", 'danger')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Une erreur est survenue lors de la validation des paramètres : {e}", 'danger')
            return redirect(url_for('index'))


        dossier_tranches_genere, erreur_tranches = generer_tranches_individuelles(
            chemin_image_source=filepath,
            hauteur_livre_mm=hauteur_livre,
            nombre_pages_livre=nombre_pages,
            dpi_utilise=dpi_utilise,
            largeur_tranche_etiree_cible_mm=largeur_tranche_etiree_cible,
            progress_callback=lambda val, msg: None
        )

        if erreur_tranches:
            flash(f"Erreur lors de la génération des tranches : {erreur_tranches}", 'danger')
            return redirect(url_for('index'))

        if not dossier_tranches_genere:
            flash("Échec inattendu lors de la génération des tranches (aucun dossier retourné).", 'danger')
            return redirect(url_for('index'))

        pdf_final_path, erreur_pdf = generer_pdf_a_partir_tranches(
            dossier_tranches_source=dossier_tranches_genere,
            hauteur_livre_mm_pdf=hauteur_livre, 
            largeur_tranche_etiree_cible_mm_pdf=largeur_tranche_etiree_cible,
            debut_numero_tranche=debut_numero_tranche,
            pas_numero_tranche=pas_numero_tranche,
            progress_callback=lambda val, msg: None,
            image_source_original_path=filepath,
            nombre_pages_livre_original=nombre_pages
        )

        if erreur_pdf:
            flash(f"Erreur lors de la génération du PDF : {erreur_pdf}", 'danger')
            return redirect(url_for('index'))
        
        if not pdf_final_path:
            flash("Échec inattendu lors de la génération du PDF (aucun chemin retourné).", 'danger')
            return redirect(url_for('index'))

        download_path = pdf_final_path 
        
        flash('Votre PDF a été généré avec succès !', 'success')
        return send_file(download_path, as_attachment=True, download_name=os.path.basename(download_path))

    except Exception as e:
        flash(f"Une erreur inattendue est survenue : {e}", 'danger')
        return redirect(url_for('index'))
    finally:
        if os.path.exists(filepath): 
            os.remove(filepath)
        if os.path.exists(temp_tranches_dir): 
            try:
                shutil.rmtree(temp_tranches_dir)
            except Exception as e:
                print(f"Erreur lors du nettoyage du dossier temporaire {temp_tranches_dir}: {e}")


if __name__ == '__main__':
    with app.app_context(): # Nécessaire pour créer la base de données
        # Supprime la base de données existante pour la recréer avec le nouveau modèle
        # Ne faites cela qu'en DÉVELOPPEMENT. En PRODUCTION, vous ferez une migration.
        # if os.path.exists('site.db'): # Cette ligne est commentée car la recréation se fait via shell
        #     os.remove('site.db') 
        # db.create_all() # Cette ligne est commentée car la recréation se fait via shell
        pass # Aucune action n'est nécessaire ici car db.create_all() est appelé via le shell Render
    app.run(debug=True)