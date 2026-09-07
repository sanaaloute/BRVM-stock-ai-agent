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
      if (user != null && accessToken != null && accessToken.isNotEmpty) {
        state = AuthAuthenticated(user);
        unawaited(_registerDevice());
        return;
      }
      final refreshToken = await storage.readRefreshToken();
      if (refreshToken != null && refreshToken.isNotEmpty) {
        final session =
            await _ref.read(authRepositoryProvider).refresh(refreshToken);
        await storage.saveSession(session);
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

  Future<void> signOut() async {
    final storage = _ref.read(storageProvider);
    final refreshToken = await storage.readRefreshToken();
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
