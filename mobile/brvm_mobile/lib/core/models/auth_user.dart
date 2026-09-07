import '../json_utils.dart';

/// Utilisateur authentifié (tel que renvoyé par /mobile/v1/auth/register
/// ou /mobile/v1/auth/login).
class AuthUser {
  const AuthUser({
    required this.id,
    this.email,
    this.phone,
    required this.hasTelegram,
    this.hasPassword = false,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
        id: asString(json['id']) ?? '',
        email: asString(json['email']),
        phone: asString(json['phone']),
        hasTelegram: asBool(json['has_telegram']),
        hasPassword: asBool(json['has_password']),
      );

  final String id;
  final String? email;
  final String? phone;
  final bool hasTelegram;

  /// `true` si le compte a un mot de passe (faux pour les comptes démo) :
  /// la suppression de compte ne le demande que dans ce cas.
  final bool hasPassword;

  /// Libellé d'affichage : e-mail ou téléphone selon ce qui existe.
  String get displayName => email ?? phone ?? 'Utilisateur';

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'email': email,
        'phone': phone,
        'has_telegram': hasTelegram,
        'has_password': hasPassword,
      };
}

/// Session complète : utilisateur + jetons.
class AuthSession {
  const AuthSession({
    required this.user,
    required this.accessToken,
    required this.accessExpiresIn,
    required this.refreshToken,
    required this.refreshExpiresIn,
    required this.tokenType,
  });

  factory AuthSession.fromJson(Map<String, dynamic> json) => AuthSession(
        user: AuthUser.fromJson(asMap(json['user'])),
        accessToken: asString(json['access_token']) ?? '',
        accessExpiresIn: asInt(json['access_expires_in']) ?? 0,
        refreshToken: asString(json['refresh_token']) ?? '',
        refreshExpiresIn: asInt(json['refresh_expires_in']) ?? 0,
        tokenType: asString(json['token_type']) ?? 'Bearer',
      );

  final AuthUser user;
  final String accessToken;
  final int accessExpiresIn;
  final String refreshToken;
  final int refreshExpiresIn;
  final String tokenType;
}

/// Exception métier renvoyée par [AuthRepository].
class AuthException implements Exception {
  const AuthException(this.message, {this.statusCode, this.code});

  final String message;
  final int? statusCode;

  /// Code machine stable pour certains cas (ex. `account_exists` en 409
  /// à l'inscription) ; `null` sinon.
  final String? code;

  @override
  String toString() => message;
}
