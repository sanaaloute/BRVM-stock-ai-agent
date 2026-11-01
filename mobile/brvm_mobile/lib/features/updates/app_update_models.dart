import '../../core/json_utils.dart';

/// Métadonnées de version servies par GET /mobile/v1/app-version.
class AppVersionInfo {
  const AppVersionInfo({this.latestVersion, this.whatsNew});

  factory AppVersionInfo.fromJson(Map<String, dynamic> json) =>
      AppVersionInfo(
        latestVersion: asString(json['latest_version']),
        whatsNew: asString(json['whats_new']),
      );

  final String? latestVersion;
  final String? whatsNew;
}

/// Mise à jour effectivement proposée à l'utilisateur : la version du store
/// est plus récente que la version installée et n'a pas été ignorée.
class AppUpdate {
  const AppUpdate({
    required this.currentVersion,
    required this.latestVersion,
    this.whatsNew,
  });

  final String currentVersion;
  final String latestVersion;
  final String? whatsNew;
}

/// Compare deux versions « x.y.z » (comparaison numérique segment par
/// segment, les segments manquants valent 0 : « 1.5 » == « 1.5.0 »).
/// Retourne une valeur négative si [a] < [b], 0 si égales, positive sinon.
int compareAppVersions(String a, String b) {
  final pa = _versionParts(a);
  final pb = _versionParts(b);
  final len = pa.length > pb.length ? pa.length : pb.length;
  for (var i = 0; i < len; i++) {
    final x = i < pa.length ? pa[i] : 0;
    final y = i < pb.length ? pb[i] : 0;
    if (x != y) return x < y ? -1 : 1;
  }
  return 0;
}

/// Extrait le préfixe numérique « x.y.z » (ignore build « +12 » ou suffixe
/// « -beta ») et le découpe en entiers.
List<int> _versionParts(String version) {
  final match = RegExp(r'\d+(?:\.\d+)*').firstMatch(version);
  if (match == null) return const <int>[0];
  return match
      .group(0)!
      .split('.')
      .map((segment) => int.tryParse(segment) ?? 0)
      .toList();
}
