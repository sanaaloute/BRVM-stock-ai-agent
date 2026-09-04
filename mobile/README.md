# Kora Bourse — Application mobile

Application Flutter de bourse (**Kora Bourse**), connectée à l'API REST du
backend [`BRVM-stock-ai-agent`](../README.md) (`/mobile/v1/*`). L'assistant
IA intégré se nomme **Kora**.

Fonctionnalités :

- **Authentification** par e-mail **ou** téléphone, via code OTP à 6 chiffres.
- **Marché** : palmarès, fiches investisseur détaillées (graphique, score IA,
  fondamentaux, dividendes, actualités), liste de suivi (watchlist),
  courtiers, actualités.
- **Kora (assistant IA)** : chat conversationnel (texte + graphiques), quota
  affiché, gestion/suppression des conversations.
- **Portefeuille** : positions, valorisation, gain/perte, ajout/modification.
- **Alertes de prix** : au-dessus / en dessous d'un cours cible.
- **Moi (Compte)** : profil, apparence (thème), digest quotidien/hebdomadaire,
  quota, déconnexion.

Toute l'interface est en **français**.

## Prérequis

- Flutter 3.35+ / Dart 3.12+ (`flutter --version`).
- En production, l'application parle à la passerelle `https://api.korabourse.com` (défaut, aucune configuration).
- En développement/test : lancer le backend localement puis pointer l'app dessus.

## Configuration

L'URL de l'API se configure par `--dart-define` (écrase la passerelle de production) :

```bash
flutter run --dart-define=API_BASE_URL=http://192.168.x.x:8002   # API locale (LAN)
```

Pour un émulateur Android, l'API du poste est joignable via `http://10.0.2.2:8002`.

## Lancer l'application

```bash
cd mobile/brvm_mobile
flutter pub get
flutter run                              # appareil connecté
flutter run --dart-define=API_BASE_URL=… # API distante
```

## Tests

```bash
flutter test
```

Couvre : validation d'identifiant, round-trip du stockage des jetons,
logique de renouvellement des jetons (401 → refresh → retry, mock Dio),
parsing des réponses chat (champ `error` en HTTP 200, images base64),
et un test widget de l'écran d'identification.

## Build

```bash
flutter build apk --debug      # APK de développement
flutter build apk --release    # APK de production
```

## Notifications push (désactivées)

La plateforme **n'utilise pas Firebase**. Le service push
(`lib/core/push_service.dart`) est un no-op : les alertes de prix et le
digest restent consultables dans l'application, mais il n'y a pas de
notification proactive pour l'instant.

Pour brancher un fournisseur plus tard (APNs direct, Supabase Realtime,
WebSockets…) : réimplémenter `PushService` avec la même API publique
(`init`, `getToken`, `requestPermission`, `onNavigate`) — le reste de
l'application n'a pas besoin de changer, et le backend expose déjà
`POST /mobile/v1/devices` pour l'enregistrement des jetons.

## Structure du code

```
lib/
├── core/            # client API (Dio + intercepteurs), jetons, auth, config
├── features/
│   ├── auth/        # écrans de connexion OTP + validation d'identifiant
│   ├── market/      # palmarès, fiches, courtiers, actualités, watchlist tab
│   ├── chat/        # conversations + écran de chat (bulles, graphiques)
│   ├── portfolio/   # positions + formulaire
│   ├── watchlist/   # providers watchlist
│   ├── alerts/      # alertes de prix
│   └── settings/    # digest, quota, notifications, déconnexion
├── app.dart         # routeur (go_router), thème, coquille à 5 onglets
└── main.dart
```
