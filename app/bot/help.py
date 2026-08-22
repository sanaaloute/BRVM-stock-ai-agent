"""Message d'aide pour les nouveaux utilisateurs et /help."""

HELP_MESSAGE = """Bienvenue sur l'assistant Bourse BRVM.

Ce bot vous aide avec la Bourse Régionale des Valeurs Mobilières (BRVM). Tous les cours sont en F CFA.

Ce que vous pouvez faire :

• Cours : « Quel est le cours de NTLC ? » ou « Compare NTLC et SLBC »
• Vue d'ensemble : « Action la plus tradée sur la BRVM ? » ou « Top gains »
• Graphiques : « Graphique NTLC du 2025-01-01 au 2025-02-21 »
• Actualités : « Dernières actualités sur Sonatel » ou « Actualités du marché BRVM »
• Bases BRVM : « C'est quoi la BRVM ? » ou « Comment investir sur la BRVM ? »
• Courtiers (SGI) : « Liste des SGI » ou « Où ouvrir un compte pour acheter des actions BRVM ? »

Portefeuille et alertes (vos données personnelles) :

• Portefeuille : « Affiche mon portefeuille » / « Ajoute NTLC à mon portefeuille : acheté à 50000 le 2025-01-15 » / « Retire NTLC de mon portefeuille » / « Évolution de mon portefeuille »
• Suivi : « Ajoute NTLC à ma liste de suivi » / « Qu'est-ce que je suis ? » / « Retire NTLC du suivi »
• Alertes de prix : « Préviens-moi quand NTLC atteint 55000 » / « Mes alertes de prix » / « Supprime l'alerte pour NTLC »
• Résumé marché (digest) : /digest jour (chaque jour de bourse) / /digest semaine (le vendredi) / /digest off

(Portefeuille, suivi, alertes et digest : disponibles sur Telegram uniquement — non encore disponible sur WhatsApp.)

• Effacer la mémoire : envoyez /clearmemory pour supprimer la mémoire de la conversation et repartir à zéro.

Vous pouvez taper ou envoyer un message vocal. Dites « aide » à tout moment pour revoir ce message."""


def get_help_message() -> str:
    return HELP_MESSAGE.strip()
