import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'models/auth_user.dart';

/// Stockage clé/valeur minimal (abstrait pour la testabilité).
abstract class KeyValueStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

/// Implémentation sécurisée (Keychain / Keystore).
class SecureKeyValueStore implements KeyValueStore {
  SecureKeyValueStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

/// Implémentation en mémoire (tests).
class MemoryKeyValueStore implements KeyValueStore {
  final Map<String, String> _data = <String, String>{};

  @override
  Future<String?> read(String key) async => _data[key];

  @override
  Future<void> write(String key, String value) async {
    _data[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    _data.remove(key);
  }
}

/// Persistance des jetons et de l'utilisateur entre les sessions.
class TokenStorage {
  TokenStorage(this._store);

  final KeyValueStore _store;

  static const String _kAccessToken = 'access_token';
  static const String _kRefreshToken = 'refresh_token';
  static const String _kUser = 'user_json';

  Future<String?> readAccessToken() => _safeRead(_kAccessToken);

  Future<String?> readRefreshToken() => _safeRead(_kRefreshToken);

  Future<AuthUser?> readUser() async {
    final raw = await _safeRead(_kUser);
    if (raw == null || raw.isEmpty) return null;
    try {
      return AuthUser.fromJson(
        jsonDecode(raw) as Map<String, dynamic>,
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> saveSession(AuthSession session) async {
    await _store.write(_kAccessToken, session.accessToken);
    await _store.write(_kRefreshToken, session.refreshToken);
    await _store.write(_kUser, jsonEncode(session.user.toJson()));
  }

  Future<void> clear() async {
    for (final key in <String>[_kAccessToken, _kRefreshToken, _kUser]) {
      try {
        await _store.delete(key);
      } catch (_) {
        // Ignoré : on tente de tout effacer même si une clé pose problème.
      }
    }
  }

  Future<String?> _safeRead(String key) async {
    try {
      return await _store.read(key);
    } catch (_) {
      return null;
    }
  }
}
