import 'package:dio/dio.dart';

import 'api_client.dart';
import 'config.dart';
import 'json_utils.dart';
import 'models/auth_user.dart';

/// Encapsule les appels d'authentification de l'API
/// (identifiant + mot de passe ; plus de code OTP).
class AuthRepository {
  AuthRepository(this._api);

  final ApiClient _api;

  /// Connexion. 401 → identifiants incorrects ; 429 → limité.
  Future<AuthSession> login(String identifier, String password) async {
    try {
      final response = await _api.post(
        '${AppConfig.apiPrefix}/auth/login',
        data: <String, dynamic>{
          'identifier': identifier,
          'password': password,
        },
      );
      return AuthSession.fromJson(asMap(response.data));
    } on DioException catch (e) {
      final (message, _) = _parseDetail(e.response?.data);
      switch (e.response?.statusCode) {
        case 401:
          throw const AuthException(
            'E-mail/numéro ou mot de passe incorrect.',
          );
        case 429:
          throw AuthException(
            message ?? 'Trop de tentatives. Veuillez réessayer plus tard.',
          );
        default:
          throw AuthException(
            message ?? 'Erreur réseau. Vérifiez votre connexion.',
          );
      }
    }
  }

  /// Création de compte. 400 → détail tel quel (ex. mot de passe faible) ;
  /// 409 → compte déjà existant.
  Future<AuthSession> register(String identifier, String password) async {
    try {
      final response = await _api.post(
        '${AppConfig.apiPrefix}/auth/register',
        data: <String, dynamic>{
          'identifier': identifier,
          'password': password,
        },
      );
      return AuthSession.fromJson(asMap(response.data));
    } on DioException catch (e) {
      final (message, _) = _parseDetail(e.response?.data);
      switch (e.response?.statusCode) {
        case 400:
          throw AuthException(
            message ?? 'Identifiant ou mot de passe invalide.',
          );
        case 409:
          throw const AuthException(
            'Un compte existe déjà pour cet identifiant. Connectez-vous.',
            code: 'account_exists',
          );
        case 429:
          throw AuthException(
            message ?? 'Trop de tentatives. Veuillez réessayer plus tard.',
          );
        default:
          throw AuthException(
            message ?? 'Erreur réseau. Vérifiez votre connexion.',
          );
      }
    }
  }

  /// Renouvelle une session à partir d'un refresh token.
  /// 401 → [AuthException] (force la reconnexion).
  Future<AuthSession> refresh(String refreshToken) async {
    try {
      final response = await _api.post(
        '${AppConfig.apiPrefix}/auth/refresh',
        data: <String, dynamic>{'refresh_token': refreshToken},
      );
      return AuthSession.fromJson(asMap(response.data));
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        throw const AuthException('Session expirée. Veuillez vous reconnecter.');
      }
      final (message, _) = _parseDetail(e.response?.data);
      throw AuthException(message ?? 'Erreur réseau. Vérifiez votre connexion.');
    }
  }

  /// Déconnexion côté serveur (révoque le refresh token).
  /// Les erreurs sont ignorées : le nettoyage local reste effectué.
  Future<void> logout(String refreshToken) async {
    try {
      await _api.post(
        '${AppConfig.apiPrefix}/auth/logout',
        data: <String, dynamic>{'refresh_token': refreshToken},
      );
    } catch (_) {
      // Meilleur effort.
    }
  }

  /// Profil frais de l'utilisateur authentifié (GET /mobile/v1/me).
  Future<AuthUser> me() async {
    final response = await _api.get('${AppConfig.apiPrefix}/me');
    return AuthUser.fromJson(asMap(response.data));
  }

  /// Mode démo : session sans compte. N'existe que quand le backend tourne
  /// avec AUTH_PROVIDER=mock (sinon 403/503 → [AuthException]).
  Future<AuthSession> devLogin({String? identifier}) async {
    try {
      final response = await _api.post(
        '${AppConfig.apiPrefix}/auth/dev-login',
        data: identifier == null
            ? <String, dynamic>{}
            : <String, dynamic>{'identifier': identifier},
      );
      return AuthSession.fromJson(asMap(response.data));
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      if (status == 403 || status == 503) {
        throw const AuthException(
          'Le mode démo est désactivé sur ce serveur (authentification réelle configurée).',
        );
      }
      final (message, _) = _parseDetail(e.response?.data);
      throw AuthException(message ?? 'Erreur réseau. Vérifiez votre connexion.');
    }
  }

  /// Extrait `(message, retry_after_seconds)` du champ `detail`, qui peut
  /// être une chaîne ou une carte `{message, retry_after_seconds}`.
  (String?, int?) _parseDetail(dynamic data) {
    final map = asMap(data);
    final detail = map['detail'];
    if (detail is Map) {
      final d = asMap(detail);
      return (asString(d['message']), asInt(d['retry_after_seconds']));
    }
    if (detail != null) {
      return (asString(detail), null);
    }
    return (null, null);
  }
}
