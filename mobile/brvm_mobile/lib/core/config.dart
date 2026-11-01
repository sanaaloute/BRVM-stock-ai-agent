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

  /// Courte description affichée dans « À propos » (identique à la fiche
  /// Play Store).
  static const String appDescription =
      'Votre agent boursier IA : cotations BRVM, analyses, portefeuille, '
      'alertes.';

  /// Éditeur / concepteur affiché dans « À propos » et les conditions.
  static const String designerName = 'NeoByte Technology';

  /// Contact support (repris dans les conditions générales).
  static const String contactEmail = 'elsanal1995@gmail.com';

  /// Numéro WhatsApp du support au format international sans « + »
  /// (lien wa.me).
  static const String whatsappNumber = '8613141392484';

  /// Identifiants stores utilisés par l'invite de mise à jour.
  static const String androidPackageName = 'com.neobytech.korabourse';
  static const String appleAppStoreId = '6826883491';

  /// Politique de confidentialité hébergée (liée depuis les conditions).
  static const String privacyPolicyUrl =
      'https://kbourse.neobytech.net/privacy';
}
