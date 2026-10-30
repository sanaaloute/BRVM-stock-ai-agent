import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/auth_repository.dart';
import '../core/config.dart';
import '../core/models/auth_user.dart';
import '../core/push_service.dart';
import '../core/token_storage.dart';

final storageProvider = Provider<TokenStorage>(
  (ref) => TokenStorage(SecureKeyValueStore()),
);

final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(ref.watch(storageProvider)),
);

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(ref.watch(apiClientProvider)),
);

/// Identifiant de l'utilisateur connecté, `null` tant que l'auth n'est pas
/// résolue. Les providers de données utilisateur l'observent : tout
/// changement de compte (connexion, déconnexion, switch) les recharge
/// automatiquement au lieu de servir le cache du compte précédent.
final currentUserIdProvider = Provider<String?>((ref) {
  final auth = ref.watch(authStateProvider);
  return auth is AuthAuthenticated ? auth.user.id : null;
});

/// État d'authentification global.
sealed class AuthState {
  const AuthState();
}

class AuthLoading extends AuthState {
  const AuthLoading();
}

class AuthUnauthenticated extends AuthState {
  const AuthUnauthenticated();
}

class AuthAuthenticated extends AuthState {
  const AuthAuthenticated(this.user);

  final AuthUser user;
}

final authStateProvider =
    StateNotifierProvider<AuthNotifier, AuthState>((ref) => AuthNotifier(ref));

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier(this._ref) : super(const AuthLoading()) {
    _ref.read(apiClientProvider).onSessionExpired = _handleSessionExpired;
    unawaited(_restore());
  }

  final Ref _ref;

  /// Restaure la session au démarrage : jeton d'accès en cache, sinon
  /// tentative de renouvellement via le refresh token.
  Future<void> _restore() async {
    final storage = _ref.read(storageProvider);
    try {
      final user = await storage.readUser();
      final accessToken = await storage.readAccessToken();
      // Un profil sans id (corrompu par un ancien /auth/refresh qui ne
      // renvoyait pas l'utilisateur) est réparé via le renouvellement
      // ci-dessous au lieu d'être utilisé tel quel : sans id, toutes les
      // conversations fusionneraient sur le thread serveur par défaut.
      if (user != null &&
          user.id.isNotEmpty &&
          accessToken != null &&
          accessToken.isNotEmpty) {
        state = AuthAuthenticated(user);
        unawaited(_registerDevice());
        return;
      }
      final refreshToken = await storage.readRefreshToken();
      if (refreshToken != null && refreshToken.isNotEmpty) {
        var session =
            await _ref.read(authRepositoryProvider).refresh(refreshToken);
        await storage.saveSession(session);
        if (session.user.id.isEmpty) {
          // Vieux backend sans profil dans /auth/refresh : le nouveau jeton
          // d'accès est déjà stocké, /me permet de récupérer le profil.
          try {
            final fresh = await _ref.read(authRepositoryProvider).me();
            if (fresh.id.isNotEmpty) {
              session = session.copyWith(user: fresh);
              await storage.saveSession(session);
            }
          } catch (_) {
            // Réparation impossible : la session reste utilisable telle
            // quelle (la prochaine connexion la corrigera).
          }
        }
        state = AuthAuthenticated(session.user);
        unawaited(_registerDevice());
        return;
      }
    } catch (_) {
      await storage.clear();
    }
    state = const AuthUnauthenticated();
  }

  void _handleSessionExpired() {
    if (state is AuthAuthenticated) {
      state = const AuthUnauthenticated();
    }
  }

  /// Connecte l'utilisateur. Retourne `null` si OK, sinon l'exception
  /// d'erreur à afficher (`e.message`).
  Future<AuthException?> login(String identifier, String password) async {
    try {
      final session =
          await _ref.read(authRepositoryProvider).login(identifier, password);
      await _ref.read(storageProvider).saveSession(session);
      state = AuthAuthenticated(session.user);
      unawaited(_registerDevice());
      return null;
    } on AuthException catch (e) {
      return e;
    }
  }

  /// Crée un compte puis ouvre la session (même flux que [login]).
  /// Retourne `null` si OK, sinon l'exception d'erreur à afficher
  /// (`e.message`).
  Future<AuthException?> register(String identifier, String password) async {
    try {
      final session = await _ref
          .read(authRepositoryProvider)
          .register(identifier, password);
      await _ref.read(storageProvider).saveSession(session);
      state = AuthAuthenticated(session.user);
      unawaited(_registerDevice());
      return null;
    } on AuthException catch (e) {
      return e;
    }
  }

  /// Mode démo : session sans mot de passe. Fonctionne seulement quand le
  /// backend tourne avec AUTH_PROVIDER=mock (403/503 sinon → message d'erreur).
  Future<String?> devLogin({String? identifier}) async {
    try {
      final session = await _ref
          .read(authRepositoryProvider)
          .devLogin(identifier: identifier);
      await _ref.read(storageProvider).saveSession(session);
      state = AuthAuthenticated(session.user);
      unawaited(_registerDevice());
      return null;
    } on AuthException catch (e) {
      return e.message;
    }
  }

  /// Met à jour le profil puis propage le nouvel utilisateur (état + stockage).
  /// Retourne `null` si OK, sinon le message d'erreur.
  Future<String?> updateProfile({
    String? name,
    String? email,
    String? phone,
    String? currentPassword,
  }) async {
    try {
      final user = await _ref
          .read(authRepositoryProvider)
          .updateProfile(
            name: name,
            email: email,
            phone: phone,
            currentPassword: currentPassword,
          );
      await _ref.read(storageProvider).saveUser(user);
      state = AuthAuthenticated(user);
      return null;
    } on AuthException catch (e) {
      return e.message;
    }
  }

  /// Recharge le profil depuis /me (après un upload/suppression de photo)
  /// et propage l'utilisateur à jour.
  Future<void> refreshProfile() async {
    try {
      final user = await _ref.read(authRepositoryProvider).me();
      await _ref.read(storageProvider).saveUser(user);
      state = AuthAuthenticated(user);
    } catch (_) {
      // Non bloquant : l'écran garde le repli sur l'utilisateur de session.
    }
  }

  /// Change le mot de passe (comptes avec mot de passe : le mot de passe
  /// actuel est exigé). Retourne `null` si OK, sinon le message d'erreur.
  Future<String?> changePassword({
    String? currentPassword,
    required String newPassword,
  }) async {
    try {
      await _ref
          .read(authRepositoryProvider)
          .changePassword(
            currentPassword: currentPassword,
            newPassword: newPassword,
          );
    } on AuthException catch (e) {
      return e.message;
    }
    // Le compte a désormais forcément un mot de passe → profil à jour.
    await refreshProfile();
    return null;
  }

  Future<void> signOut() async {
    final storage = _ref.read(storageProvider);
    final refreshToken = await storage.readRefreshToken();
    await _unregisterDevice();
    if (refreshToken != null && refreshToken.isNotEmpty) {
      try {
        await _ref.read(authRepositoryProvider).logout(refreshToken);
      } catch (_) {
        // Même en cas d'erreur réseau, on déconnecte localement.
      }
    }
    await storage.clear();
    state = const AuthUnauthenticated();
  }

  /// Supprime définitivement le compte côté serveur puis efface la session
  /// locale. Retourne `null` si OK, sinon le message d'erreur à afficher.
  /// Pas de logout serveur (contrairement à [signOut]) : le compte et ses
  /// jetons n'existent déjà plus après le DELETE.
  Future<String?> deleteAccount({String? password}) async {
    try {
      await _ref
          .read(authRepositoryProvider)
          .deleteAccount(password: password);
    } on AuthException catch (e) {
      return e.message;
    }
    await _ref.read(storageProvider).clear();
    state = const AuthUnauthenticated();
    return null;
  }

  /// Supprime le jeton FCM côté backend pour ne plus recevoir de
  /// notifications push après déconnexion. Meilleur effort : non bloquant.
  Future<void> _unregisterDevice() async {
    final push = PushService.instance;
    if (!push.isAvailable) return;
    try {
      final token = await push.getToken();
      if (token == null || token.isEmpty) return;
      await _ref
          .read(apiClientProvider)
          .delete('${AppConfig.apiPrefix}/devices/${Uri.encodeComponent(token)}');
    } catch (_) {
      // Non bloquant.
    }
  }

  /// Envoie le jeton FCM au backend pour les notifications push.
  Future<void> _registerDevice() async {
    final push = PushService.instance;
    if (!push.isAvailable) return;
    try {
      final token = await push.getToken();
      if (token == null || token.isEmpty) return;
      final platform =
          defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
      await _ref.read(apiClientProvider).post(
        '${AppConfig.apiPrefix}/devices',
        data: <String, dynamic>{'fcm_token': token, 'platform': platform},
      );
    } catch (_) {
      // Non bloquant : retenté à la prochaine connexion.
    }
  }
}
