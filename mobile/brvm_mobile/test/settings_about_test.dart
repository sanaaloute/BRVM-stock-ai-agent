import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/auth_repository.dart';
import 'package:brvm_mobile/core/config.dart';
import 'package:brvm_mobile/core/models/auth_user.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_models.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_providers.dart';
import 'package:brvm_mobile/features/settings/settings_providers.dart';
import 'package:brvm_mobile/features/settings/settings_screen.dart';
import 'package:brvm_mobile/features/settings/terms_screen.dart';
import 'package:brvm_mobile/features/updates/app_update_models.dart';
import 'package:brvm_mobile/features/updates/app_update_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:package_info_plus/package_info_plus.dart';

class _FakeAuthRepository extends AuthRepository {
  _FakeAuthRepository({required this.user})
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final AuthUser user;

  @override
  Future<AuthUser> me() async => user;
}

class _FakeSettingsRepository extends SettingsRepository {
  _FakeSettingsRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  @override
  Future<Quota> getQuota() async => const Quota(used: 0, limit: 10);
}

class _FakePortfolioRepository extends PortfolioRepository {
  _FakePortfolioRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  @override
  Future<PortfolioData> get({String? sgi}) async =>
      PortfolioData.fromJson(const <String, dynamic>{
        'summary': <String, dynamic>{'positions_count': 0},
        'positions': <Map<String, dynamic>>[],
        'sgi_breakdown': <Map<String, dynamic>>[],
      });
}

const _user = AuthUser(id: 'u1', email: 'trader@brvm.ci', hasTelegram: false);

/// Pompe l'écran Compte dans un routeur minimaliste comprenant la route des
/// conditions générales, sur une surface assez grande pour tout afficher.
/// [versionInfo] simule la réponse du backend /app-version (défaut : aucune
/// info → pas de mise à jour proposée).
Future<void> _pumpScreen(WidgetTester tester, {AppVersionInfo? versionInfo}) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  final storage = TokenStorage(MemoryKeyValueStore());
  await storage.saveSession(
    AuthSession(
      user: _user,
      accessToken: 'at',
      accessExpiresIn: 900,
      refreshToken: 'rt',
      refreshExpiresIn: 1209600,
      tokenType: 'Bearer',
    ),
  );
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(path: '/', builder: (_, _) => const SettingsScreen()),
      GoRoute(
        path: '/moi/conditions',
        builder: (_, _) => const TermsScreen(),
      ),
    ],
  );
  addTearDown(router.dispose);

  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        storageProvider.overrideWithValue(storage),
        authRepositoryProvider
            .overrideWithValue(_FakeAuthRepository(user: _user)),
        settingsRepositoryProvider
            .overrideWithValue(_FakeSettingsRepository()),
        portfolioRepositoryProvider
            .overrideWithValue(_FakePortfolioRepository()),
        appVersionInfoProvider.overrideWith(
          (ref) async => versionInfo ?? const AppVersionInfo(),
        ),
      ],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() {
    PackageInfo.setMockInitialValues(
      appName: AppConfig.appName,
      packageName: AppConfig.androidPackageName,
      version: '1.5.1',
      buildNumber: '12',
      buildSignature: '',
    );
  });

  testWidgets('section Contact : bouton WhatsApp', (tester) async {
    await _pumpScreen(tester);

    expect(find.text('Contact'), findsOneWidget);
    expect(find.text('Contactez-nous'), findsOneWidget);
    expect(find.text('Discutez avec nous sur WhatsApp'), findsOneWidget);
    expect(find.byIcon(Icons.support_agent), findsOneWidget);
  });

  testWidgets('section À propos : nom, version, description, crédits',
      (tester) async {
    await _pumpScreen(tester);

    expect(find.text('À propos'), findsOneWidget);
    expect(find.text(AppConfig.appName), findsWidgets);
    expect(find.text('Version 1.5.1 (12)'), findsOneWidget);
    expect(find.text(AppConfig.appDescription), findsOneWidget);
    expect(find.text('Conçu et développé par'), findsOneWidget);
    expect(find.text(AppConfig.designerName), findsOneWidget);
    expect(
        find.text('Conditions générales d’utilisation'), findsOneWidget);
  });

  testWidgets('bouton « Mettre à jour » visible quand le store est plus '
      'récent', (tester) async {
    await _pumpScreen(
      tester,
      versionInfo: const AppVersionInfo(latestVersion: '1.6.0'),
    );

    expect(find.text('Mettre à jour vers 1.6.0'), findsOneWidget);
  });

  testWidgets('bouton « Mettre à jour » masqué quand l’app est à jour',
      (tester) async {
    await _pumpScreen(
      tester,
      versionInfo: const AppVersionInfo(latestVersion: '1.5.1'),
    );

    expect(find.textContaining('Mettre à jour'), findsNothing);
    // Le reste de la carte est inchangé.
    expect(find.text('Conçu et développé par'), findsOneWidget);
  });

  testWidgets('conditions générales : navigation puis sections et lien '
      'confidentialité', (tester) async {
    await _pumpScreen(tester);

    await tester.tap(find.text('Conditions générales d’utilisation'));
    await tester.pumpAndSettle();

    expect(find.text('1. Éditeur'), findsOneWidget);
    expect(find.text('3. Absence de conseil en investissement'),
        findsOneWidget);
    expect(
        find.text('9. Modifications des conditions'), findsOneWidget);

    // Le bouton de la politique de confidentialité est en bas de page.
    await tester.scrollUntilVisible(
      find.text('Consulter la politique de confidentialité'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Consulter la politique de confidentialité'),
        findsOneWidget);
    expect(find.text('10. Politique de confidentialité'), findsOneWidget);
  });
}
