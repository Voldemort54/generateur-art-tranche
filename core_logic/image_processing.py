from PIL import Image, ImageTk
import os
import shutil
# import tkinter as tk # Retiré car non utilisé dans le backend Flask
# from tkinter import filedialog, messagebox, ttk # Retiré car non utilisé dans le backend Flask
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm # Importation de mm pour les conversions
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import black
import threading
import math
from datetime import date, datetime # Importe date et datetime.datetime

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
        # Dans le contexte Flask, on retourne l'erreur sans messagebox.
        return None, f"Erreur: Fichier image non trouvé: {chemin_image_source}"
    except Exception as e:
        return None, f"Erreur: Erreur lors du chargement de l'image : {e}"

    if progress_callback:
        progress_callback(15, "Redimensionnement de l'image à la hauteur du livre (proportionnellement pour la découpe)...")

    hauteur_livre_pixels = int(round((hauteur_livre_mm / 25.4) * dpi_utilise))

    ratio_img_originale = img_originale.width / img_originale.height
    largeur_img_redimensionnee_hauteur = int(round(hauteur_livre_pixels * ratio_img_originale))
    
    img_redimensionnee_pour_decoupage = img_originale.resize((largeur_img_redimensionnee_hauteur, hauteur_livre_pixels), Image.LANCZOS)
    
    largeur_pixels_par_tranche_a_decouper = img_redimensionnee_pour_decoupage.width / nombre_tranches_reelles

    largeur_pixels_cible_par_tranche_etiree = int(round((largeur_tranche_etiree_cible_mm / 25.4) * dpi_utilise))

    temp_dir_for_slices_base = os.path.join(os.path.dirname(chemin_image_source), f"temp_tranches_for_{os.path.basename(chemin_image_source).split('.')[0]}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    os.makedirs(temp_dir_for_slices_base, exist_ok=True)
    chemin_complet_dossier_tranches = temp_dir_for_slices_base


    if progress_callback:
        progress_callback(30, f"Découpage et enregistrement de {nombre_tranches_reelles} tranches individuelles...")

    for i in range(nombre_tranches_reelles):
        left = int(i * largeur_pixels_par_tranche_a_decouper)
        upper = 0
        right = int((i + 1) * largeur_pixels_par_tranche_a_decouper)
        lower = hauteur_livre_pixels

        if right > img_redimensionnee_pour_decoupage.width:
            right = img_redimensionnee_pour_decoupage.width
        
        if right <= left:
            print(f"Avertissement: Largeur de tranche initiale pour la tranche {i+1} est trop petite ({right-left} pixels). Ignorée.")
            continue

        tranche_decoupee_originale_proportions = img_redimensionnee_pour_decoupage.crop((left, upper, right, lower))
        
        tranche_etiree_pour_impression = tranche_decoupee_originale_proportions.resize((largeur_pixels_cible_par_tranche_etiree, hauteur_livre_pixels), Image.LANCZOS)

        nom_fichier_tranche = f"tranche_{i+1:05d}.png"
        chemin_fichier_tranche = os.path.join(chemin_complet_dossier_tranches, nom_fichier_tranche)

        try:
            tranche_etiree_pour_impression.save(chemin_fichier_tranche, format="PNG")
        except Exception as e:
            # Correction de l'erreur d'indentation/SyntaxError ici.
            # Remplacement de l'ancien messagebox par un return None, message pour Flask.
            # messagebox.showwarning("Erreur d'enregistrement", f"Impossible d'enregistrer la tranche {i+1} : {e}")
            return None, f"Erreur d'enregistrement: Impossible d'enregistrer la tranche {i+1} : {e}"


        if progress_callback and (i % (max(1, nombre_tranches_reelles // 100)) == 0 or i == nombre_tranches_reelles - 1):
            progress_val = 30 + int(40 * (i / nombre_tranches_reelles))
            progress_callback(progress_val, f"Enregistrement de la tranche {i+1}/{nombre_tranches_reelles}...")
    
    return chemin_complet_dossier_tranches, None


# --- Partie 2: Logique de génération du PDF ---
def generer_pdf_a_partir_tranches(dossier_tranches_source, hauteur_livre_mm_pdf, largeur_tranche_etiree_cible_mm_pdf,
                                  debut_numero_tranche, pas_numero_tranche, progress_callback, image_source_original_path, nombre_pages_livre_original):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm 
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.colors import black
    # from datetime import date, datetime # déjà importé globalement ou pas besoin ici

    """
    Prend des images de tranches individuelles et les assemble dans un PDF au format A4 portrait.
    Chaque page du PDF contient une seule ligne de tranches.
    """
    if progress_callback:
        progress_callback(75, "Vérification des tranches pour le PDF...")

    fichiers_tranches = sorted([f for f in os.listdir(dossier_tranches_source) if f.lower().endswith('.png')])
    if not fichiers_tranches:
        # Comme pour l'autre fonction, retirons le messagebox pour le backend Flask.
        # messagebox.showwarning("Aucune tranche trouvée", f"Aucun fichier PNG trouvé dans le dossier :\n{dossier_tranches_source}")
        return None, "Erreur: Aucun fichier PNG trouvé."

    num_total_tranches_source = len(fichiers_tranches)
    
    chemin_dossier_parent_du_dossier_tranches = os.path.dirname(dossier_tranches_source)
    
    nom_dossier_base_tranches = os.path.basename(dossier_tranches_source)
    nom_fichier_pdf = f"{nom_dossier_base_tranches}_impression_horizontale.pdf"
    
    chemin_fichier_pdf = os.path.join(chemin_dossier_parent_du_dossier_tranches, nom_fichier_pdf)


    c = canvas.Canvas(chemin_fichier_pdf, pagesize=A4)
    largeur_page, hauteur_page = A4 


    # Marges fixes
    MARGE_HORIZONTALE_PAGE_MM = 10 
    MARGE_VERTICALE_HAUT_PAGE_MM = 12 
    MARGE_VERTICALE_BAS_PAGE_MM = 7 
    
    EPAISSEUR_LIGNE_DECOUPE = 0.5 
    
    TAILLE_POLICE_NUMERO = 8 
    TAILLE_POLICE_COPYRIGHT = 8 
    TAILLE_POLICE_PAGE_NUM = 8 
    TEXTE_COPYRIGHT = "© Voldemort" 

    # Marges INTERNES aux cadres de chaque tranche.
    MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM = 5 
    MARGE_INTERNE_TRANCHE_HORIZONTALE_DROITE_MM = 5 

    largeur_contenu_disponible_pt = largeur_page - (2 * MARGE_HORIZONTALE_PAGE_MM * mm)
    hauteur_contenu_disponible_pt = hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + MARGE_VERTICALE_BAS_PAGE_MM) * mm

    LONGUEUR_REPERE_VERTICAL_MM = 3 
    REPERE_OFFSET_Y_MM = 2 


    largeur_totale_par_tranche_bloc = largeur_tranche_etiree_cible_mm_pdf * mm + MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM * mm + MARGE_INTERNE_TRANCHE_HORIZONTALE_DROITE_MM * mm
    tranches_par_ligne_pdf = max(1, int(largeur_contenu_disponible_pt / largeur_totale_par_tranche_bloc))
    lignes_par_page_pdf = 1 

    num_pages_tranches = math.ceil(num_total_tranches_source / tranches_par_ligne_pdf)
    total_pdf_pages = num_pages_tranches + 1 

    current_pdf_page_number = 1 

    hauteur_disponible_pour_tranche_en_mm = (hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + MARGE_VERTICALE_BAS_PAGE_MM) * mm) / mm

    if hauteur_livre_mm_pdf > hauteur_disponible_pour_tranche_en_mm + 0.1:
        # messagebox.showerror("Erreur de Dimensions", f"La hauteur du livre spécifiée ({hauteur_livre_mm_pdf:.2f} mm) est trop grande ...")
        return None, f"Erreur: Hauteur du livre trop grande pour la page PDF: {hauteur_livre_mm_pdf:.2f} mm."


    try:
        c.setFont('Helvetica-Bold', 14)
        c.setFillColor(black)
        creation_date_formatted = datetime.date.today().strftime("%d/%m/%Y") 
        texte_titre = "Créé par Voldemort le " + creation_date_formatted
        text_width_titre = c.stringWidth(texte_titre, 'Helvetica-Bold', 14)
        c.drawString((largeur_page - text_width_titre) / 2, hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + 3) * mm, texte_titre)

        c.setFont('Helvetica', 10)
        line_height = 12 
        
        texte_nombre_tranches = f"Nombre total de tranches : {num_total_tranches_source} (correspondant à {nombre_pages_livre_original} pages)"
        text_width_tranches = c.stringWidth(texte_nombre_tranches, 'Helvetica', 10)
        c.drawString((largeur_page - text_width_tranches) / 2, hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + 3 + 12) * mm, texte_nombre_tranches)

        texte_hauteur_livre = f"Hauteur du livre : {hauteur_livre_mm_pdf:.2f} mm"
        text_width_hauteur = c.stringWidth(texte_hauteur_livre, 'Helvetica', 10)
        c.drawString((largeur_page - text_width_hauteur) / 2, hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + 3 + 12) * mm - line_height, texte_hauteur_livre)


        img_apercu_original = Image.open(image_source_original_path)
        
        y_top_image_area_pt = hauteur_page - (MARGE_VERTICALE_HAUT_PAGE_MM + 3 + 12) * mm - line_height - (5 * mm) 
        y_bottom_image_area_pt = MARGE_VERTICALE_BAS_PAGE_MM * mm

        max_apercu_height = y_top_image_area_pt - y_bottom_image_area_pt
        max_apercu_width = largeur_contenu_disponible_pt 
        
        apercu_ratio = img_apercu_original.width / img_apercu_original.height

        if (max_apercu_width / max_apercu_height) > apercu_ratio:
            apercu_height_pt = max_apercu_height
            apercu_width_pt = apercu_height_pt * apercu_ratio
        else:
            apercu_width_pt = max_apercu_width
            apercu_height_pt = apercu_width_pt / apercu_ratio
        
        x_apercu = (largeur_page - apercu_width_pt) / 2 
        y_apercu = y_bottom_image_area_pt + (max_apercu_height - apercu_height_pt) / 2 


        c.drawImage(ImageReader(image_source_original_path), x_apercu, y_apercu,
                    width=apercu_width_pt, height=apercu_height_pt)
        
        page_num_text = f"Page {current_pdf_page_number} sur {total_pdf_pages}"
        c.setFont('Helvetica', TAILLE_POLICE_PAGE_NUM)
        text_width_page_num = c.stringWidth(page_num_text, 'Helvetica', TAILLE_POLICE_PAGE_NUM) # Correction: Utilise page_num_text
        c.drawString(largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm - text_width_page_num - (20 * mm), 2 * mm, page_num_text)
        
        current_pdf_page_number += 1 
        c.showPage() 
    except Exception as e:
        return None, f"Erreur lors de l'ajout de la page d'aperçu : {e}"


    print(f"Disposition PDF: {tranches_par_ligne_pdf} tranches par ligne (calculé), {lignes_par_page_pdf} ligne par page (fixé).")


    tranche_actuelle_index_globale = 0
    numero_imprime_actuel = debut_numero_tranche

    if progress_callback:
        progress_callback(80, "Assemblage des tranches dans le PDF...")

    c.setStrokeColor(black)
    c.setLineWidth(EPAISSEUR_LIGNE_DECOUPE)

    y_global_top_line_page = hauteur_page - MARGE_VERTICALE_HAUT_PAGE_MM * mm 
    c.line(MARGE_HORIZONTALE_PAGE_MM * mm, y_global_top_line_page, largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm, y_global_top_line_page)


    for i, fichier_tranche in enumerate(fichiers_tranches):
        chemin_image_tranche = os.path.join(dossier_tranches_source, fichier_tranche)

        colonne_actuelle_sur_page = tranche_actuelle_index_globale % tranches_par_ligne_pdf

        if (tranche_actuelle_index_globale > 0 and colonne_actuelle_sur_page == 0):
            page_num_text = f"Page {current_pdf_page_number} sur {total_pdf_pages}"
            c.setFont('Helvetica', TAILLE_POLICE_PAGE_NUM)
            text_width_page_num = c.stringWidth(page_num_text, 'Helvetica', TAILLE_POLICE_PAGE_NUM) 
            c.drawString(largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm - text_width_page_num - (20 * mm), 2 * mm, page_num_text)
            
            current_pdf_page_number += 1 

            c.showPage() 
            c.setStrokeColor(black)
            c.setLineWidth(EPAISSEUR_LIGNE_DECOUPE)
            c.line(MARGE_HORIZONTALE_PAGE_MM * mm, y_global_top_line_page, largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm, y_global_top_line_page)
            
            print(f"Passage à une nouvelle page. Tranche actuelle globale : {tranche_actuelle_index_globale}")

        try:
            x_pos_frame_bottom_left = MARGE_HORIZONTALE_PAGE_MM * mm + (colonne_actuelle_sur_page * largeur_totale_par_tranche_bloc)
            
            frame_height = hauteur_livre_mm_pdf * mm 
            y_pos_frame_bottom_left = y_global_top_line_page - frame_height

            frame_width = largeur_tranche_etiree_cible_mm_pdf * mm + MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM * mm + MARGE_INTERNE_TRANCHE_HORIZONTALE_DROITE_MM * mm
            c.rect(x_pos_frame_bottom_left, y_pos_frame_bottom_left, frame_width, frame_height, stroke=1, fill=0)


            c.saveState() 
            
            x_pivot_block_text = x_pos_frame_bottom_left + (MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM * mm / 2)
            y_pivot_block_text = y_pos_frame_bottom_left + frame_height - (10 * mm) 

            c.translate(x_pivot_block_text, y_pivot_block_text) 
            c.rotate(270) 

            c.setFont('Helvetica-Bold', TAILLE_POLICE_NUMERO)
            c.setFillColor(black)
            texte_numero = f"{numero_imprime_actuel}"
            texte_largeur_numero_pt = c.stringWidth(texte_numero, 'Helvetica-Bold', TAILLE_POLICE_NUMERO)
            
            x_pos_numero_rot = 0
            y_pos_numero_rot = -texte_largeur_numero_pt / 2
            c.drawString(x_pos_numero_rot, y_pos_numero_rot, texte_numero) 

            c.setFont('Helvetica', TAILLE_POLICE_COPYRIGHT)
            texte_copyright_a_afficher = TEXTE_COPYRIGHT
            texte_largeur_copyright_pt = c.stringWidth(texte_copyright_a_afficher, 'Helvetica', TAILLE_POLICE_COPYRIGHT)

            espacement_mm = 2 
            espacement_pt = espacement_mm * mm 
            y_pos_copyright_start_rot = y_pos_numero_rot + texte_largeur_numero_pt + espacement_pt
            y_pos_copyright_local_centered = y_pos_numero_rot + (texte_largeur_numero_pt / 2) - (texte_largeur_copyright_pt / 2)
            x_pos_for_copyright_rot = x_pos_numero_rot + texte_largeur_numero_pt + espacement_pt 
            y_pos_for_copyright_rot = y_pos_numero_rot 

            c.drawString(x_pos_for_copyright_rot, y_pos_for_copyright_rot, texte_copyright_a_afficher)
            
            c.restoreState() 


            x_pos_image = x_pos_frame_bottom_left + MARGE_INTERNE_TRANCHE_HORIZONTALE_GAUCHE_MM * mm
            y_pos_image = y_pos_frame_bottom_left 
            c.drawImage(ImageReader(chemin_image_tranche), x_pos_image, y_pos_image,
                        width=largeur_tranche_etiree_cible_mm_pdf * mm, height=hauteur_livre_mm_pdf * mm)
            
            center_x_image_tranche = x_pos_image + (largeur_tranche_etiree_cible_mm_pdf * mm / 2)
            
            c.line(center_x_image_tranche, y_pos_frame_bottom_left + frame_height + REPERE_OFFSET_Y_MM * mm,
                   center_x_image_tranche, y_pos_frame_bottom_left + frame_height + REPERE_OFFSET_Y_MM * mm + LONGUEUR_REPERE_VERTICAL_MM * mm)

            c.line(center_x_image_tranche, y_pos_frame_bottom_left - REPERE_OFFSET_Y_MM * mm,
                   center_x_image_tranche, y_pos_frame_bottom_left - REPERE_OFFSET_Y_MM * mm - LONGUEUR_REPERE_VERTICAL_MM * mm)

            tranche_actuelle_index_globale += 1
            numero_imprime_actuel += pas_numero_tranche

            if progress_callback:
                progress_val = 80 + int(15 * (i / num_total_tranches_source))
                progress_callback(progress_val, f"Ajout de la tranche {i+1}/{num_total_tranches_source} au PDF...")

            except Exception as e:
                return None, f"Erreur lors de l'ajout de la tranche '{fichier_tranche}' au PDF : {e}"
        
        page_num_text = f"Page {current_pdf_page_number} sur {total_pdf_pages}"
        c.setFont('Helvetica', TAILLE_POLICE_PAGE_NUM)
        text_width_page_num = c.stringWidth(page_num_text, 'Helvetica', TAILLE_POLICE_PAGE_NUM) 
        c.drawString(largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm - text_width_page_num - (20 * mm), 2 * mm, page_num_text)
            
        y_global_bottom_line_page = y_pos_frame_bottom_left 
        c.line(MARGE_HORIZONTALE_PAGE_MM * mm, y_global_bottom_line_page, largeur_page - MARGE_HORIZONTALE_PAGE_MM * mm, y_global_bottom_line_page)


        c.save()

        if progress_callback:
            progress_callback(100, "PDF généré !")
        return chemin_fichier_pdf, None