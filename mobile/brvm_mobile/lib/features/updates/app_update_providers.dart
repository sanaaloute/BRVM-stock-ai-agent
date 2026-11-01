import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import '../../core/providers.dart';
import 'app_update_models.dart';

/// Accès aux métadonnées de version publiées sur les stores.
class AppUpdateRepository {
  AppUpdateRepository(this._api);

  final ApiClient _api;

  /// Métadonnées de la dernière version publiée ; `null` si le serveur est
  /// injoignable (dans ce cas aucune invite n'est affichée).
  Future<AppVersionInfo?> fetchLatestVersion() async {
    try {
      final response = await _api.get('${AppConfig.apiPrefix}/app-version');
      return AppVersionInfo.fromJson(asMap(response.data));
    } catch (_) {
      return null;
    }
  }
}

final appUpdateRepositoryProvider = Provider<AppUpdateRepository>(
  (ref) => AppUpdateRepository(ref.watch(apiClientProvider)),
);

/// Version installée, `null` si indisponible (tests).
Future<String?> _installedVersion() async {
  try {
    final info = await PackageInfo.fromPlatform();
    return info.version.isEmpty ? null : info.version;
  } catch (_) {
    return null;
  }
}

/// Métadonnées de la dernière version publiée (partagé entre l'invite
/// automatique et le bouton de la carte « À propos » : un seul appel réseau).
final appVersionInfoProvider = FutureProvider<AppVersionInfo?>(
  (ref) => ref.watch(appUpdateRepositoryProvider).fetchLatestVersion(),
);

/// Mise à jour disponible : la version du store est plus récente que la
/// version installée. Alimente l'invite automatique au démarrage (une fois
/// par lancement — « Plus tard » reporte simplement au lancement suivant,
/// pour maximiser l'adoption des nouvelles versions) et le bouton
/// « Mettre à jour » de la carte « À propos ».
final availableUpdateProvider = FutureProvider<AppUpdate?>((ref) async {
  final info = await ref.watch(appVersionInfoProvider.future);
  final latest = info?.latestVersion;
  if (latest == null) return null;
  final current = await _installedVersion();
  if (current == null) return null;
  if (compareAppVersions(latest, current) <= 0) return null;
  return AppUpdate(
    currentVersion: current,
    latestVersion: latest,
    whatsNew: info!.whatsNew,
  );
});
