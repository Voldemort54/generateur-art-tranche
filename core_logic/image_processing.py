from PIL import Image
import os
import shutil
import math
from datetime import date, datetime # Importe date et datetime pour usage précis

# --- Partie 1: Logique de génération des tranches individuelles ---
def generer_tranches_individuelles(chemin_image_source, hauteur_livre_mm, nombre_pages_livre, dpi_utilise, largeur_tranche_etiree_cible_mm, progress_callback):
    """
    Génère des images individuelles pour chaque tranche de feuille de papier dans un dossier.
    L'image source est redimensionnée à la hauteur du livre (proportionnellement),
    puis découpée en tranches de largeur originale.
    Chaque tranche est ENSUITE étirée individuellement pour correspondre à la largeur_tranche_etiree_cible_mm.

    Args:
        chemin_image_source (str): Chemin d'accès complet à l'image source.
        hauteur_livre_mm (float): La hauteur exacte du livre en millimètres.
        nombre_pages_livre (int): Le nombre total de pages NUMÉROTÉES du livre.
        dpi_utilise (int): Le DPI qui sera utilisé pour les calculs (obtenu de l'image source ou par défaut).
        largeur_tranche_etiree_cible_mm (float): La largeur physique que chaque tranche doit avoir après étirement (en mm).
                                                 C'est à cette largeur que chaque tranche sera étirée.
        progress_callback (callable): Fonction de rappel pour mettre à jour la barre de progression. (sera un lambda vide pour le web)

    Returns:
        tuple: (chemin_dossier_tranches, erreur_message)
                chemin_dossier_tranches (str or None): Chemin du dossier créé pour les tranches.
                erreur_message (str or None): Message d'erreur si une erreur survient.
    """
    nombre_tranches_reelles = math.ceil(nombre_pages_livre / 2)

    if progress_callback:
        progress_callback(5, "Chargement de l'image source...")

    try:
        img_originale = Image.open(chemin_image_source).convert("RGB")
    except FileNotFoundError:
        return None, f"Erreur: L'image source n'a pas été trouvée à l'emplacement :\n{chemin_image_source}"
    except Exception as e:
        return None, f"Erreur: Erreur lors du chargement de l'image : {e}"

    if progress_callback:
        progress_callback(15, "Redimensionnement de l'image à la hauteur du livre (proportionnellement pour la découpe)...")

    # Calcul de la hauteur en pixels pour la hauteur du livre demandée - C'est la hauteur que TOUTES les tranches DOIVENT avoir
    hauteur_livre_pixels = int(round((hauteur_livre_mm / 25.4) * dpi_utilise))

    # Redimensionner l'image originale pour que sa hauteur corresponde EXACTEMENT à hauteur_livre_pixels.
    # La largeur sera ajustée proportionnellement.
    ratio_img_originale = img_originale.width / img_originale.height
    largeur_img_redimensionnee_hauteur = int(round(hauteur_livre_pixels * ratio_img_originale))

    # L'image redimensionnée pour la découpe a maintenant la hauteur exacte désirée.
    img_redimensionnee_pour_decoupage = img_originale.resize((largeur_img_redimensionnee_hauteur, hauteur_livre_pixels), Image.LANCZOS)

    # Largeur de chaque tranche à découper de l'image redimensionnée
    largeur_pixels_par_tranche_a_decouper = img_redimensionnee_pour_decoupage.width / nombre_tranches_reelles

    # Largeur cible en pixels pour chaque tranche après étirement individuel
    largeur_pixels_cible_par_tranche_etiree = int(round((largeur_tranche_etiree_cible_mm / 25.4) * dpi_utilise))

    # Le dossier des tranches sera créé à l'intérieur du dossier des uploads pour faciliter le nettoyage
    # C'est la responsabilité de `app.py` de créer `dossier_tranches_genere` et de le passer ici.
    # Pour le test autonome de cette fonction ou si le chemin n'est pas passé par Flask,
    # nous allons créer un dossier temporaire ici. En utilisation normale avec Flask,
    # le chemin sera fourni par Flask et ce code sera ignoré.
    temp_dir_for_slices_base = os.path.join(os.path.dirname(chemin_image_source), f"temp_tranches_for_{os.path.basename(chemin_image_source).split('.')[0]}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    os.makedirs(temp_dir_for_slices_base, exist_ok=True)
    chemin_complet_dossier_tranches = temp_dir_for_slices_base


    if progress_callback:
        progress_callback(30, f"Découpage et enregistrement de {nombre_tranches_reelles} tranches individuelles...")

    for i in range(nombre_tranches_reelles):
        left = int(i * largeur_pixels_par_tranche_a_decouper)
        upper = 0
        right = int((i + 1) * largeur_pixels_par_tranche_a_decouper)
        lower = hauteur_livre_pixels # La hauteur de découpe est la hauteur du livre en pixels

        if right > img_redimensionnee_pour_decoupage.width:
            right = img_redimensionnee_pour_decoupage.width

        if right <= left:
            print(f"Avertissement: Largeur de tranche initiale pour la tranche {i+1} est trop petite ({right-left} pixels). Ignorée.")
            continue

        tranche_decoupee_originale_proportions = img_redimensionnee_pour_decoupage.crop((left, upper, right, lower))

        # Étirer chaque tranche à la largeur cible, EN FORÇANT LA HAUTEUR à hauteur_livre_pixels.
        tranche_etiree_pour_impression = tranche_decoupee_originale_proportions.resize((largeur_pixels_cible_par_tranche_etiree, hauteur_livre_pixels), Image.LANCZOS)

        nom_fichier_tranche = f"tranche_{i+1:05d}.png"
        chemin_fichier_tranche = os.path.join(chemin_complet_dossier_tranches, nom_fichier_tranche)

        try:
            tranche_etiree_pour_impression.save(chemin_fichier_tranche, format="PNG")
        except Exception as e:
            return None, f"Erreur d'enregistrement: Impossible d'enregistrer la tranche {i+1} : {e}"


        if progress_callback and (i % (max(1, nombre_tranches_reelles // 100)) == 0 or i == nombre_tranches_reelles - 1):
            progress_val = 30 + int(40 * (i / nombre_tranches_reelles))
            progress_callback(progress_val, f"Enregistrement de la tranche {i+1}/{nombre_tranches_reelles}...")

    return chemin_complet_dossier_tranches, None


# --- Partie 2: Logique de génération du PDF ---
# MODIFICATION: Ajout de l'argument 'output_pdf_path' à la signature de la fonction
def generer_pdf_a_partir_tranches(dossier_tranches_source, hauteur_livre_mm_pdf, largeur_tranche_etiree_cible_mm_pdf,
                                  debut_numero_tranche, pas_numero_tranche, progress_callback, image_source_original_path, nombre_pages_livre_original,
                                  output_pdf_path): # NOUVEL ARGUMENT ICI !
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.colors import black


    if progress_callback:
        progress_callback(75, "Vérification des tranches pour le PDF...")

    fichiers_tranches = sorted([f for f in os.listdir(dossier_tranches_source) if f.lower().endswith('.png')])
    if not fichiers_tranches:
        return None, "Erreur: Aucun fichier PNG trouvé."

    num_total_tranches_source = len(fichiers_tranches)

    # MODIFICATION: Utiliser le chemin 'output_pdf_path' fourni par l'appelant (app.py)
    chemin_fichier_pdf = output_pdf_path


    c = canvas.Canvas(chemin_fichier_pdf, pagesize=A4)
    largeur_page, hauteur_page = A4 # A4 est en points, on va utiliser mm pour le positionnement


    # Marges fixes
    MARGE_HORIZONTALE_PAGE_MM = 10
    MARGE_VERTICALE_HAUT_PAGE_MM = 12 # Marge supérieure
    MARGE_VERTICALE_BAS_PAGE_MM = 7 # Marge inférieure

    EPAISSEUR_LIGNE_DECOUPE = 0.5 # points, épaisseur standard pour une ligne fine

    TAILLE_POLICE_NUMERO = 8 # Taille de police pour le numéro (plus grand pour la lisibilité)
    TAILLE_POLICE_COPYRIGHT = 8 # Taille de police pour le copyright (plus grand pour la lisibilité)
    TAILLE_POLICE_PAGE_NUM = 8 # Taille de police pour la numérotation des pages du PDF
    TEXTE_COPYRIGHT = "© Voldemort" # Texte du copyright

    # Marges INTERNES aux cadres de chaque tranche.
    MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM = 5
    MARGE_INTERNE_TRANCHE_HORIZONTALE_DROITE_MM = 5

    # Largeur disponible pour le contenu sur la page PDF (en points)
    largeur_contenu_disponible_pt = largeur_page - (2 * MARGE_HORIZONTALE_PAGE_MM * mm)
    hauteur_contenu_disponible_pt = hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + MARGE_VERTICALE_BAS_PAGE_MM) * mm

    # Longueur du trait du repère vertical (s'étend au-dessus et en dessous du cadre)
    LONGUEUR_REPERE_VERTICAL_MM = 3
    REPERE_OFFSET_Y_MM = 2 # Distance du cadre pour les repères verticaux


    # Calcul du nombre total de pages du PDF
    largeur_totale_par_tranche_bloc = largeur_tranche_etiree_cible_mm_pdf * mm + MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM * mm + MARGE_INTERNE_TRANCHE_HORIZONTALE_DROITE_MM * mm
    tranches_par_ligne_pdf = max(1, int(largeur_contenu_disponible_pt / largeur_totale_par_tranche_bloc))
    lignes_par_page_pdf = 1 # Fixé à 1 pour cet usage

    num_pages_tranches = math.ceil(num_total_tranches_source / tranches_par_ligne_pdf)
    total_pdf_pages = num_pages_tranches + 1 # +1 pour la page de garde

    current_pdf_page_number = 1 # Initialise le compteur de pages PDF

    # --- VÉRIFICATION : HAUTEUR DU LIVRE TROP GRANDE POUR LA PAGE ---
    # La hauteur disponible pour le contenu (tranches) est hauteur_page - (marge_haut + marge_bas) en points.
    # On convertit cette hauteur en mm pour la comparaison.
    hauteur_disponible_pour_tranche_en_mm = (hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + MARGE_VERTICALE_BAS_PAGE_MM) * mm) / mm

    # On ajoute une petite tolérance pour les imprécisions des flottants, par exemple 0.1 mm
    if hauteur_livre_mm_pdf > hauteur_disponible_pour_tranche_en_mm + 0.1:
        return None, (f"Erreur: La hauteur du livre spécifiée ({hauteur_livre_mm_pdf:.2f} mm) est trop grande "
                      f"pour tenir sur la hauteur de la page PDF (A4) avec les marges actuelles.\n"
                      f"Hauteur disponible pour le contenu : {hauteur_disponible_pour_tranche_en_mm:.2f} mm.\n"
                      f"Veuillez réduire la hauteur du livre ou les marges verticales.")


    try:
        c.setFont('Helvetica-Bold', 14)
        c.setFillColor(black)
        creation_date_formatted = date.today().strftime("%d/%m/%Y") # CHANGEMENT ICI : Utilisation de date.today()
        texte_titre = "Créé par Voldemort le " + creation_date_formatted
        text_width_titre = c.stringWidth(texte_titre, 'Helvetica-Bold', 14)
        # Positionnement du titre : centré horizontalement, à 15mm du bord supérieur (MARGE_VERTICALE_HAUT_PAGE_MM + petit décalage)
        c.drawString((largeur_page - text_width_titre) / 2, hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + 3) * mm, texte_titre)

        # Informations ajoutées en dessous du titre
        c.setFont('Helvetica', 10)
        line_height = 12 # hauteur d'une ligne de texte en points

        texte_nombre_tranches = f"Nombre total de tranches : {num_total_tranches_source} (correspondant à {nombre_pages_livre_original} pages)"
        text_width_tranches = c.stringWidth(texte_nombre_tranches, 'Helvetica', 10)
        # Positionnement : centré horizontalement, sous le titre
        c.drawString((largeur_page - text_width_tranches) / 2, hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + 3 + 12) * mm, texte_nombre_tranches)

        texte_hauteur_livre = f"Hauteur du livre : {hauteur_livre_mm_pdf:.2f} mm"
        text_width_hauteur = c.stringWidth(texte_hauteur_livre, 'Helvetica', 10)
        # Positionnement : centré horizontalement, sous la ligne précédente
        c.drawString((largeur_page - text_width_hauteur) / 2, hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + 3 + 12) * mm - line_height, texte_hauteur_livre)


        # Charger l'image source originale pour l'aperçu
        img_apercu_original = Image.open(image_source_original_path)

        # Calculer l'espace disponible pour l'image après le texte d'information
        # Le haut de l'espace pour l'image: juste en dessous de la dernière ligne de texte + un petit décalage
        y_top_image_area_pt = hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + 3 + 12) * mm - line_height - (5 * mm) # 5mm de marge sous le texte info

        # Le bas de l'espace pour l'image est le haut de la marge basse
        y_bottom_image_area_pt = MARGE_VERTICALE_BAS_PAGE_MM * mm

        max_apercu_height = y_top_image_area_pt - y_bottom_image_area_pt
        max_apercu_width = largeur_contenu_disponible_pt # Utilise toute la largeur disponible dans le contenu

        apercu_ratio = img_apercu_original.width / img_apercu_original.height

        if (max_apercu_width / max_apercu_height) > apercu_ratio:
            # La hauteur est le facteur limitant
            apercu_height_pt = max_apercu_height
            apercu_width_pt = apercu_height_pt * apercu_ratio
        else:
            # La largeur est le facteur limitant
            apercu_width_pt = max_apercu_width
            apercu_height_pt = apercu_width_pt / apercu_ratio

        # Centrer l'image dans l'espace disponible
        x_apercu = (largeur_page - apercu_width_pt) / 2 # Centrage horizontal
        y_apercu = y_bottom_image_area_pt + (max_apercu_height - apercu_height_pt) / 2 # Centrage vertical


        c.drawImage(ImageReader(image_source_original_path), x_apercu, y_apercu,
                    width=apercu_width_pt, height=apercu_height_pt)

        # Numérotation de la page de garde (décalée de 2cm à gauche, EN DESSOUS de la marge du bas)
        page_num_text = f"Page {current_pdf_page_number} sur {total_pdf_pages}"
        c.setFont('Helvetica', TAILLE_POLICE_PAGE_NUM)
        text_width_page_num = c.stringWidth(page_num_text, 'Helvetica', TAILLE_POLICE_PAGE_NUM)
        # Positionnement : Largeur de la page - Marge droite - Largeur du texte - 20mm (2cm) de décalage
        # La numérotation est à 2mm DU BAS DE LA PAGE (zone non imprimable)
        c.drawString(largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm - text_width_page_num - (20 * mm), 2 * mm, page_num_text)

        current_pdf_page_number += 1 # Incrémente le compteur de pages PDF
        c.showPage() # Passe à la page suivante pour les tranches
    except Exception as e:
        return None, f"Erreur lors de l'ajout de la page d'aperçu : {e}"


    print(f"Disposition PDF: {tranches_par_ligne_pdf} tranches par ligne (calculé), {lignes_par_page_pdf} ligne par page (fixé).")


    tranche_actuelle_index_globale = 0
    numero_imprime_actuel = debut_numero_tranche

    if progress_callback:
        progress_callback(80, "Assemblage des tranches dans le PDF...")

    c.setStrokeColor(black)
    c.setLineWidth(EPAISSEUR_LIGNE_DECOUPE)

    # La ligne du haut du cadre global est à la marge haute de la page.
    y_global_top_line_page = hauteur_page - MARGE_VERTICALE_HAUT_PAGE_MM * mm
    c.line(MARGE_HORIZONTALE_PAGE_MM * mm, y_global_top_line_page, largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm, y_global_top_line_page)


    for i, fichier_tranche in enumerate(fichiers_tranches):
        chemin_image_tranche = os.path.join(dossier_tranches_source, fichier_tranche)

        colonne_actuelle_sur_page = tranche_actuelle_index_globale % tranches_par_ligne_pdf

        # Si c'est le début d'une nouvelle page de tranches (pas la toute première tranche du document)
        if (tranche_actuelle_index_globale > 0 and colonne_actuelle_sur_page == 0):
            # Dessiner le numéro de page pour la page précédente avant de la "fermer" et d'en ouvrir une nouvelle
            page_num_text = f"Page {current_pdf_page_number} sur {total_pdf_pages}"
            c.setFont('Helvetica', TAILLE_POLICE_PAGE_NUM)
            text_width_page_num = c.stringWidth(page_num_text, 'Helvetica', TAILLE_POLICE_PAGE_NUM)
            # Positionnement : Largeur de la page - Marge droite - Largeur du texte - 20mm (2cm) de décalage
            # La numérotation est à 2mm DU BAS DE LA PAGE
            c.drawString(largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm - text_width_page_num - (20 * mm), 2 * mm, page_num_text)

            current_pdf_page_number += 1 # Incrémente le compteur de pages PDF

            c.showPage() # Passe à la nouvelle page
            # On redessine le cadre supérieur de la nouvelle page de tranches
            c.setStrokeColor(black)
            c.setLineWidth(EPAISSEUR_LIGNE_DECOUPE)
            c.line(MARGE_HORIZONTALE_PAGE_MM * mm, y_global_top_line_page, largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm, y_global_top_line_page)

            print(f"Passage à une nouvelle page. Tranche actuelle globale : {tranche_actuelle_index_globale}")

        try:
            # Positionnement du CADRE complet de la tranche (incluant les marges internes gauche et droite)
            x_pos_frame_bottom_left = MARGE_HORIZONTALE_PAGE_MM * mm + (colonne_actuelle_sur_page * largeur_totale_par_tranche_bloc)

            # La hauteur du cadre est EXACTEMENT la hauteur du livre.
            frame_height = hauteur_livre_mm_pdf * mm
            y_pos_frame_bottom_left = y_global_top_line_page - frame_height

            frame_width = largeur_tranche_etiree_cible_mm_pdf * mm + MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM * mm + MARGE_INTERNE_TRANCHE_HORIZONTALE_DROITE_MM * mm
            c.rect(x_pos_frame_bottom_left, y_pos_frame_bottom_left, frame_width, frame_height, stroke=1, fill=0)


            # --- DESSIN DU NUMÉRO ET DU COPYRIGHT (dans la marge blanche de GAUCHE de CHAQUE TRANCHE) ---
            c.saveState() # Sauvegarder l'état actuel du canevas pour les transformations de texte

            # Position du pivot pour le bloc de texte (Numéro + Copyright)
            # Ce pivot est le centre de la marge gauche de la tranche, en haut.
            x_pivot_block_text = x_pos_frame_bottom_left + (MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM * mm / 2)
            y_pivot_block_text = y_pos_frame_bottom_left + frame_height - (10 * mm) # Décalé de 10mm du haut du cadre

            c.translate(x_pivot_block_text, y_pivot_block_text) # Déplacer l'origine au point de pivot
            c.rotate(270) # Tourner de 270 degrés (texte de haut en bas)

            # --- Dessiner le Numéro ---
            c.setFont('Helvetica-Bold', TAILLE_POLICE_NUMERO)
            c.setFillColor(black)
            texte_numero = f"{numero_imprime_actuel}"
            texte_largeur_numero_pt = c.stringWidth(texte_numero, 'Helvetica-Bold', TAILLE_POLICE_NUMERO)

            # Positionnement du numéro dans le système roté (X positif vers le bas, Y positif vers la gauche)
            # Le Y est pour le centrage du texte par rapport à l'origine (ici le milieu de la ligne de texte).
            # Le X est 0 pour le début du texte.
            x_pos_numero_rot = 0
            y_pos_numero_rot = -texte_largeur_numero_pt / 2
            c.drawString(x_pos_numero_rot, y_pos_numero_rot, texte_numero)

            # --- Dessiner le Copyright à la suite du Numéro ---
            c.setFont('Helvetica', TAILLE_POLICE_COPYRIGHT)
            texte_copyright_a_afficher = TEXTE_COPYRIGHT
            texte_largeur_copyright_pt = c.stringWidth(texte_copyright_a_afficher, 'Helvetica', TAILLE_POLICE_COPYRIGHT)

            espacement_mm = 2 # 2 mm d'espacement entre le numéro et le copyright
            espacement_pt = espacement_mm * mm # Convertir en points

            # Positionnement du copyright après le numéro sur l'axe "X roté" (vers le bas)
            x_pos_for_copyright_rot = x_pos_numero_rot + texte_largeur_numero_pt + espacement_pt

            # Centrage sur l'axe "Y roté" (gauche/droite)
            y_pos_for_copyright_rot = y_pos_numero_rot # Le même centrage que le numéro

            # Dessiner le copyright avec les positions calculées dans le système roté.
            c.drawString(x_pos_for_copyright_rot, y_pos_for_copyright_rot, texte_copyright_a_afficher)

            c.restoreState() # Restaurer l'état du canevas après les transformations et le dessin


            # Dessiner l'image de la tranche: placée après la marge interne gauche, et collée au bas du cadre.
            x_pos_image = x_pos_frame_bottom_left + MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM * mm
            y_pos_image = y_pos_frame_bottom_left # Le bas de l'image est le bas du cadre
            # Forcer la hauteur de l'image en points pour ReportLab
            c.drawImage(ImageReader(chemin_image_tranche), x_pos_image, y_pos_image,
                        width=largeur_tranche_etiree_cible_mm_pdf * mm, height=hauteur_livre_mm_pdf * mm)

            # --- AJOUT DES REPÈRES VERTICAUX CENTRÉS ---
            # Position X du centre de l'IMAGE de la tranche (pas du bloc entier)
            center_x_image_tranche = x_pos_image + (largeur_tranche_etiree_cible_mm_pdf * mm / 2)

            # Repère du HAUT (au-dessus du cadre)
            c.line(center_x_image_tranche, y_pos_frame_bottom_left + frame_height + REPERE_OFFSET_Y_MM * mm,
                   center_x_image_tranche, y_pos_frame_bottom_left + frame_height + REPERE_OFFSET_Y_MM * mm + LONGUEUR_REPERE_VERTICAL_MM * mm)

            # Repère du BAS (en dessous du cadre)
            # CORRECTION : 'REPERE_OFFSET_Y_Y_MM' a été remplacé par 'REPERE_OFFSET_Y_MM'
            c.line(center_x_image_tranche, y_pos_frame_bottom_left - REPERE_OFFSET_Y_MM * mm,
                   center_x_image_tranche, y_pos_frame_bottom_left - REPERE_OFFSET_Y_MM * mm - LONGUEUR_REPERE_VERTICAL_MM * mm)
            # --- FIN DES REPÈRES ---

            tranche_actuelle_index_globale += 1
            numero_imprime_actuel += pas_numero_tranche

            if progress_callback:
                progress_val = 80 + int(15 * (i / num_total_tranches_source))
                progress_callback(progress_val, f"Ajout de la tranche {i+1}/{num_total_tranches_source} au PDF...")

        except Exception as e:
            return None, f"Erreur lors de l'ajout de la tranche '{fichier_tranche}' au PDF : {e}"

    # Numérotation de la page pour la *dernière* page de tranches (qui ne déclenchera pas de showPage() après elle)
    page_num_text = f"Page {current_pdf_page_number} sur {total_pdf_pages}"
    c.setFont('Helvetica', TAILLE_POLICE_PAGE_NUM)
    text_width_page_num = c.stringWidth(page_num_text, 'Helvetica', TAILLE_POLICE_PAGE_NUM)
    # Positionnement : Largeur de la page - Marge droite - Largeur du texte - 20mm (2cm) de décalage
    # La numérotation est à 2mm DU BAS DE LA PAGE (zone non imprimable)
    c.drawString(largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm - text_width_page_num - (20 * mm), 2 * mm, page_num_text)

    # Correction de la ligne diagonale sur la dernière page
    y_global_bottom_line_page = y_pos_frame_bottom_left # Le bas du dernier cadre dessiné.
    c.line(MARGE_HORIZONTALE_PAGE_MM * mm, y_global_bottom_line_page, largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm, y_global_bottom_line_page)


    c.save() # Le PDF est sauvegardé au chemin 'output_pdf_path'

    if progress_callback:
        progress_callback(100, "PDF généré !")
    return chemin_fichier_pdf, None