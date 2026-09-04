/// Configuration globale de l'application.
class AppConfig {
  /// URL de base de l'API backend.
  ///
  /// Définie au build/run via :
  /// `flutter run --dart-define=API_BASE_URL=https://api.example.com`
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String appName = 'Kora Bourse';
  static const String apiPrefix = '/mobile/v1';
}
