import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import '../../core/models/auth_user.dart';
import '../../core/providers.dart';
import '../watchlist/watchlist_providers.dart' show dioDetailMessage;

/// Préférences du récapitulatif (digest).
class DigestSettings {
  const DigestSettings({this.enabled = false, this.frequency = 'daily'});

  factory DigestSettings.fromJson(Map<String, dynamic> json) =>
      DigestSettings(
        enabled: asBool(json['enabled']),
        frequency: asString(json['frequency']) ?? 'daily',
      );

  final bool enabled;
  final String frequency;
}

/// Quota d'utilisation du chat.
class Quota {
  const Quota({this.used, this.limit, this.exempt = false});

  factory Quota.fromJson(Map<String, dynamic> json) => Quota(
        used: asInt(json['used']),
        limit: asInt(json['limit']),
        exempt: asBool(json['exempt']),
      );

  final int? used;
  final int? limit;
  final bool exempt;
}

class SettingsRepository {
  SettingsRepository(this._api);

  final ApiClient _api;

  Future<DigestSettings> getDigest() async {
    final response = await _api.get('${AppConfig.apiPrefix}/digest');
    return DigestSettings.fromJson(asMap(response.data));
  }

  Future<String?> updateDigest(String frequency, bool enabled) async {
    try {
      await _api.put(
        '${AppConfig.apiPrefix}/digest',
        data: <String, dynamic>{'frequency': frequency, 'enabled': enabled},
      );
      return null;
    } on DioException catch (e) {
      return dioDetailMessage(e) ?? 'Impossible de mettre à jour le digest.';
    }
  }

  Future<Quota> getQuota() async {
    final response = await _api.get('${AppConfig.apiPrefix}/quota');
    return Quota.fromJson(asMap(response.data));
  }
}

final settingsRepositoryProvider = Provider<SettingsRepository>(
  (ref) => SettingsRepository(ref.watch(apiClientProvider)),
);

final digestProvider =
    AsyncNotifierProvider<DigestNotifier, DigestSettings>(
  DigestNotifier.new,
);

class DigestNotifier extends AsyncNotifier<DigestSettings> {
  @override
  Future<DigestSettings> build() {
    // Changement de compte → rechargement automatique (pas de cache croisé).
    ref.watch(currentUserIdProvider);
    return ref.watch(settingsRepositoryProvider).getDigest();
  }

  Future<String?> save(String frequency, bool enabled) async {
    final message = await ref
        .read(settingsRepositoryProvider)
        .updateDigest(frequency, enabled);
    ref.invalidateSelf();
    return message;
  }
}

final quotaProvider = FutureProvider.autoDispose<Quota>(
  (ref) {
    ref.watch(currentUserIdProvider);
    return ref.watch(settingsRepositoryProvider).getQuota();
  },
);

/// Profil frais de l'utilisateur connecté (GET /mobile/v1/me).
/// Retombe côté UI sur l'utilisateur de session si l'appel échoue.
final meProvider = FutureProvider.autoDispose<AuthUser>(
  (ref) {
    ref.watch(currentUserIdProvider);
    return ref.watch(authRepositoryProvider).me();
  },
);
