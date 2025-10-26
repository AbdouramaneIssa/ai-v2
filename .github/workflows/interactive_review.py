import os
from github import Github
from google import genai

# --- Configuration ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GH_TOKEN = os.environ.get("GH_TOKEN")
PR_NUMBER = int(os.environ.get("PR_NUMBER"))
REPO_FULL_NAME = os.environ.get("REPO_FULL_NAME")

# Initialisation des clients
try:
    g = Github(GH_TOKEN)
    repo = g.get_repo(REPO_FULL_NAME)
    pr = repo.get_pull(PR_NUMBER)
    ai_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Erreur d'initialisation des clients GitHub/Gemini: {e}")
    exit(1)

def get_pr_files():
    """Récupère les fichiers modifiés et leur contenu pour l'analyse."""
    files_data = []
    for file in pr.get_files():
        # Nous n'analysons que les fichiers de code pertinents
        if file.filename.endswith(('.py', '.js', '.html', '.css', '.md')):
            # Utiliser le patch pour l'analyse la plus précise
            files_data.append({
                "filename": file.filename,
                "patch": file.patch,
                "status": file.status,
                "raw_url": file.raw_url
            })
    return files_data

def generate_ai_review(file_data):
    """Appelle Gemini pour obtenir une revue de code structurée."""
    
    # Le prompt demande une réponse structurée pour faciliter l'extraction des commentaires ligne par ligne
    prompt = f"""
    Vous êtes un expert en revue de code. Analysez le changement de fichier suivant (format patch) et fournissez un feedback constructif.
    
    Le format de votre réponse DOIT être uniquement une liste d'objets JSON.
    Chaque objet JSON doit avoir les clés suivantes :
    - "comment": Le texte du commentaire de revue de code (max 200 mots).
    - "line_number": Le numéro de ligne dans le fichier MODIFIÉ (head) où le commentaire doit être placé.
    - "is_critical": true si c'est une erreur bloquante ou une faille de sécurité, false sinon.
    
    Si le code est impeccable, renvoyez une liste JSON vide : [].
    
    --- Fichier: {file_data['filename']} (Statut: {file_data['status']}) ---
    {file_data['patch']}
    """
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        # Tenter d'extraire le bloc JSON
        text = response.text.strip()
        if text.startswith("```json"):
            text = text.strip("```json").strip("```").strip()
        
        return text
        
    except Exception as e:
        print(f"Erreur lors de l'appel à Gemini pour {file_data['filename']}: {e}")
        return None

def post_review_comments(file_data, review_data):
    """Poste les commentaires sur la Pull Request."""
    try:
        import json
        comments = json.loads(review_data)
    except json.JSONDecodeError:
        pr.create_issue_comment(f"Erreur: L'IA n'a pas renvoyé un format JSON valide pour le fichier {file_data['filename']}. Réponse brute:\n\n{review_data}")
        return

    if not comments:
        print(f"Pas de commentaires pour {file_data['filename']}.")
        return

    for comment in comments:
        try:
            # Créer un commentaire de revue de code sur la ligne spécifique
            pr.create_review_comment(
                body=comment['comment'],
                commit_id=pr.head.sha,
                path=file_data['filename'],
                position=comment['line_number']
            )
            print(f"Commentaire posté sur {file_data['filename']} à la ligne {comment['line_number']}.")
        except Exception as e:
            print(f"Erreur lors de la publication du commentaire pour {file_data['filename']}: {e}")

# --- Logique Principale ---

print(f"Démarrage de la revue de code interactive pour la PR #{PR_NUMBER} sur {REPO_FULL_NAME}")

# 1. Récupérer les fichiers de la PR
files_to_review = get_pr_files()

if not files_to_review:
    pr.create_issue_comment("Le bot de revue de code n'a trouvé aucun fichier de code pertinent à analyser dans cette Pull Request.")
    exit(0)

# 2. Analyser chaque fichier et poster les commentaires
for file_data in files_to_review:
    print(f"Analyse du fichier: {file_data['filename']}")
    
    # Appel à l'IA
    review_json = generate_ai_review(file_data)
    
    if review_json:
        # Poster les commentaires
        post_review_comments(file_data, review_json)

# 3. Poster un commentaire récapitulatif
pr.create_issue_comment(f"✅ Revue de code interactive par Gemini terminée. Veuillez vérifier les commentaires en ligne pour le feedback.")

print("Processus de revue de code terminé.")
