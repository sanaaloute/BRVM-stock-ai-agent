"""Public privacy policy page for Kora Bourse (Google Play requirement).

Served at GET /privacy on the API — reachable through the gateway at
https://kbourse.neobytech.net/privacy. Static HTML, French (the app's
language), no tracking, no auth.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_CONTACT_EMAIL = "elsanal1995@gmail.com"

_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kora Bourse — Politique de confidentialité</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
         max-width: 760px; margin: 0 auto; padding: 24px 18px 64px; color: #1c2430;
         background: #f7f9f8; line-height: 1.65; }}
  h1 {{ color: #0b6e4f; font-size: 1.6rem; margin-bottom: 2px; }}
  h2 {{ color: #0b6e4f; font-size: 1.15rem; margin-top: 2rem; }}
  .sub {{ color: #5a6575; font-size: .9rem; margin-top: 0; }}
  ul {{ padding-left: 1.2rem; }}
  footer {{ margin-top: 3rem; font-size: .85rem; color: #5a6575; border-top: 1px solid #d8e0dc; padding-top: 1rem; }}
</style>
</head>
<body>
<h1>Kora Bourse — Politique de confidentialité</h1>
<p class="sub">Dernière mise à jour : 7 septembre 2026</p>

<p>Kora Bourse (« l'Application ») est un assistant d'investissement pour la
bourse régionale d'Afrique de l'Ouest, édité par NeoBytech. Cette politique
décrit quelles données sont collectées, pourquoi, et comment elles sont
protégées.</p>

<h2>1. Données collectées</h2>
<ul>
  <li><strong>Identifiant de connexion</strong> : adresse e-mail ou numéro de
      téléphone, fourni lors de la création du compte.</li>
  <li><strong>Mot de passe</strong> : stocké exclusivement sous forme chiffrée
      (fonction de dérivation scrypt avec sel) — jamais en clair.</li>
  <li><strong>Données de portefeuille</strong> : lignes d'achat (symbole,
      quantité, prix, date) saisies par vous.</li>
  <li><strong>Historique de conversation</strong> : questions posées à
      l'assistant IA « Kora » et ses réponses, conservées pour permettre la
      continuité de vos conversations.</li>
  <li><strong>Préférences</strong> : liste de suivi, alertes de prix,
      abonnement au digest, préférence de thème.</li>
</ul>
<p>L'Application ne collecte <strong>aucune donnée de localisation précise,
aucun contact, aucun fichier multimédia, aucun identifiant publicitaire</strong>.</p>

<h2>2. Utilisation</h2>
<ul>
  <li>Authentifier votre compte et sécuriser vos sessions (jetons JWT à durée
      limitée).</li>
  <li>Afficher vos portefeuilles, suivis et alertes sur vos appareils.</li>
  <li>Permettre à l'assistant IA de répondre dans le contexte de vos
      conversations.</li>
</ul>

<h2>3. Hébergement et partage</h2>
<p>Les données sont hébergées sur un serveur privé de l'éditeur et ne sont
<strong>jamais vendues ni partagées avec des tiers</strong> à des fins
commerciales. Seules exceptions : obligations légales, ou prestataires
strictement nécessaires à l'exploitation (hébergeur du serveur), soumis aux
mêmes obligations.</p>

<h2>4. Sécurité</h2>
<ul>
  <li>Connexions chiffrées en HTTPS (TLS) entre l'Application et le serveur.</li>
  <li>Mots de passe hachés avec scrypt (salage individuel).</li>
  <li>Sessions par jetons signés à durée limitée, révocables.</li>
</ul>

<h2>5. Conservation et suppression</h2>
<p>Les données sont conservées tant que votre compte est actif. Vous pouvez
supprimer votre compte directement dans l'Application (voir section 6), ou
demander à tout moment la consultation ou la <strong>suppression définitive
de vos données</strong> en écrivant à
<a href="mailto:{email}">{email}</a> ; la suppression est alors effectuée
sous 30 jours.</p>

<h2>6. Suppression du compte</h2>
<p>Vous pouvez supprimer votre compte à tout moment, directement dans
l'Application : <strong>Compte → Supprimer mon compte</strong>. La suppression
est <strong>immédiate et définitive</strong> ; elle efface :</p>
<ul>
  <li>votre identifiant de connexion (e-mail ou numéro de téléphone) et votre
      mot de passe ;</li>
  <li>vos sessions, jetons d'accès et appareils enregistrés ;</li>
  <li>vos portefeuilles, listes de suivi, alertes de prix et abonnement au
      digest ;</li>
  <li>l'historique de vos conversations avec l'assistant IA ;</li>
  <li>vos données d'usage et préférences.</li>
</ul>

<h2>7. Cookies et traceurs</h2>
<p>L'Application et cette page n'utilisent <strong>aucun cookie ni traceur
publicitaire</strong>.</p>

<h2>8. Mineurs</h2>
<p>L'Application s'adresse à un public adulte (investisseurs). Elle n'est pas
destinée aux enfants de moins de 13 ans.</p>

<h2>9. Modifications</h2>
<p>Cette politique peut être mise à jour ; la date de dernière révision figure
en tête de page. Toute modification substantielle sera signalée dans
l'Application.</p>

<h2>10. Contact</h2>
<p>Éditeur : NeoBytech — {email}</p>

<footer>Kora Bourse — NeoBytech. Les contenus générés par l'assistant IA sont
informatifs et ne constituent pas un conseil en investissement.</footer>
</body>
</html>
"""


@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy() -> str:
    return _HTML.format(email=_CONTACT_EMAIL)
