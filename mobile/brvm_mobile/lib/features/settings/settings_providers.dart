import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import '../../core/models/auth_user.dart';
import '../../core/providers.dart';

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

  Future<Quota> getQuota() async {
    final response = await _api.get('${AppConfig.apiPrefix}/quota');
    return Quota.fromJson(asMap(response.data));
  }
}

final settingsRepositoryProvider = Provider<SettingsRepository>(
  (ref) => SettingsRepository(ref.watch(apiClientProvider)),
);

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

/// Photo de profil (octets) de l'utilisateur connecté, `null` si absente.
/// Se recharge quand l'utilisateur de session change (refreshProfile après
/// un upload/suppression).
final userPhotoProvider = FutureProvider.autoDispose<Uint8List?>(
  (ref) {
    final auth = ref.watch(authStateProvider);
    final user = auth is AuthAuthenticated ? auth.user : null;
    if (user == null || !user.hasPhoto) return null;
    return ref.watch(authRepositoryProvider).fetchPhoto();
  },
);
