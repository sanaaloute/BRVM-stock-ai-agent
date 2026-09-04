import 'package:dio/dio.dart';

import 'api_client.dart';
import 'config.dart';
import 'json_utils.dart';
import 'models/auth_user.dart';

/// Résultat de POST /mobile/v1/auth/request-code.
class RequestCodeResult {
  const RequestCodeResult._({
    required this.ok,
    this.channel = '',
    this.devCode,
    this.errorMessage,
    this.retryAfterSeconds,
    this.invalidIdentifier = false,
    this.authDisabled = false,
  });

  factory RequestCodeResult.success({
    required String channel,
    String? devCode,
  }) =>
      RequestCodeResult._(ok: true, channel: channel, devCode: devCode);

  factory RequestCodeResult.failure({
    String? message,
    int? retryAfterSeconds,
    bool invalidIdentifier = false,
    bool authDisabled = false,
  }) =>
      RequestCodeResult._(
        ok: false,
        errorMessage: message,
        retryAfterSeconds: retryAfterSeconds,
        invalidIdentifier: invalidIdentifier,
        authDisabled: authDisabled,
      );

  final bool ok;
  final String channel;
  final String? devCode;
  final String? errorMessage;
  final int? retryAfterSeconds;
  final bool invalidIdentifier;
  final bool authDisabled;
}

/// Résultat de POST /mobile/v1/auth/verify-code.
class VerifyCodeResult {
  const VerifyCodeResult._({this.session, this.errorMessage});

  factory VerifyCodeResult.success(AuthSession session) =>
      VerifyCodeResult._(session: session);

  factory VerifyCodeResult.failure(String message) =>
      VerifyCodeResult._(errorMessage: message);

  final AuthSession? session;
  final String? errorMessage;

  bool get isSuccess => session != null;
}

/// Encapsule les appels d'authentification de l'API.
class AuthRepository {
  AuthRepository(this._api);

  final ApiClient _api;

  Future<RequestCodeResult> requestCode(String identifier) async {
    try {
      final response = await _api.post(
        '${AppConfig.apiPrefix}/auth/request-code',
        data: <String, dynamic>{'identifier': identifier},
      );
      final data = asMap(response.data);
      return RequestCodeResult.success(
        channel: asString(data['channel']) ?? 'email',
        devCode: asString(data['dev_code']),
      );
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      final (message, retryAfter) = _parseDetail(e.response?.data);
      switch (status) {
        case 429:
          return RequestCodeResult.failure(
            message: message ?? 'Trop de tentatives. Veuillez réessayer plus tard.',
            retryAfterSeconds: retryAfter,
          );
        case 400:
          return RequestCodeResult.failure(
            message: message ?? 'Identifiant invalide.',
            invalidIdentifier: true,
          );
        case 503:
          return RequestCodeResult.failure(
            message: message ?? 'L’authentification est temporairement désactivée.',
            authDisabled: true,
          );
        default:
          return RequestCodeResult.failure(
            message: message ?? 'Erreur réseau. Vérifiez votre connexion.',
          );
      }
    }
  }

  Future<AuthSession> verifyCode(String identifier, String code) async {
    try {
      final response = await _api.post(
        '${AppConfig.apiPrefix}/auth/verify-code',
        data: <String, dynamic>{'identifier': identifier, 'code': code},
      );
      return AuthSession.fromJson(asMap(response.data));
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        throw const AuthException('Code incorrect ou expiré.');
      }
      final (message, _) = _parseDetail(e.response?.data);
      throw AuthException(message ?? 'Erreur réseau. Vérifiez votre connexion.');
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

  /// Profil frais de l'utilisateur authentifié (GET /mobile/v1/me).
  Future<AuthUser> me() async {
    final response = await _api.get('${AppConfig.apiPrefix}/me');
    return AuthUser.fromJson(asMap(response.data));
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

  /// Mode démo : session sans OTP. N'existe que quand le backend tourne avec
  /// AUTH_PROVIDER=mock (sinon 403/503 → [AuthException]).
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
