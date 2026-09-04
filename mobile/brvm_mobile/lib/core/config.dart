/// Configuration globale de l'application.
class AppConfig {
  /// URL de base de l'API backend.
  ///
  /// Par défaut : la passerelle de production (HTTPS via Cloudflare Tunnel :
  /// kbourse.neobytech.net → API locale). Pour le développement/test sur un
  /// réseau local :
  /// `flutter run --dart-define=API_BASE_URL=http://192.168.x.x:8002`
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://kbourse.neobytech.net',
  );

  static const String appName = 'Kora Bourse';
  static const String apiPrefix = '/mobile/v1';
}
