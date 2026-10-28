import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/auth_repository.dart';
import 'package:brvm_mobile/core/format.dart';
import 'package:brvm_mobile/core/models/auth_user.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_models.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_providers.dart';
import 'package:brvm_mobile/features/settings/settings_providers.dart';
import 'package:brvm_mobile/features/settings/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

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
  _FakePortfolioRepository(this._json)
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final Map<String, dynamic> _json;

  @override
  Future<PortfolioData> get({String? sgi}) async =>
      PortfolioData.fromJson(_json);
}

const _emptyPortfolioJson = <String, dynamic>{
  'summary': <String, dynamic>{'positions_count': 0},
  'positions': <Map<String, dynamic>>[],
  'sgi_breakdown': <Map<String, dynamic>>[],
};

const _richPortfolioJson = <String, dynamic>{
  'summary': <String, dynamic>{
    'total_value_fcfa': 1520000,
    'total_gain_loss_fcfa': 120000,
    'total_gain_loss_pct': 8.57,
    'dividends_fcfa': 45000,
    'positions_count': 4,
    'lots_count': 6,
  },
  'positions': <Map<String, dynamic>>[],
  'sgi_breakdown': <Map<String, dynamic>>[],
};

Future<void> _pumpScreen(
  WidgetTester tester, {
  required AuthUser user,
  Map<String, dynamic> portfolioJson = _emptyPortfolioJson,
}) async {
  final storage = TokenStorage(MemoryKeyValueStore());
  await storage.saveSession(
    AuthSession(
      user: user,
      accessToken: 'at',
      accessExpiresIn: 900,
      refreshToken: 'rt',
      refreshExpiresIn: 1209600,
      tokenType: 'Bearer',
    ),
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        storageProvider.overrideWithValue(storage),
        authRepositoryProvider.overrideWithValue(_FakeAuthRepository(user: user)),
        settingsRepositoryProvider.overrideWithValue(_FakeSettingsRepository()),
        portfolioRepositoryProvider
            .overrideWithValue(_FakePortfolioRepository(portfolioJson)),
      ],
      child: const MaterialApp(home: SettingsScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('en-tête profil : icône personne, nom dérivé et coordonnées',
      (tester) async {
    const user = AuthUser(
      id: 'u1',
      email: 'trader@brvm.ci',
      phone: '+2250701020304',
      hasTelegram: true,
    );
    await _pumpScreen(tester, user: user);

    // Nom dérivé de la partie locale de l'e-mail.
    expect(find.text('Trader'), findsOneWidget);
    // Icône personne dans la pastille profil.
    expect(find.byIcon(Icons.person_outline), findsOneWidget);
    // Coordonnées.
    expect(find.text('trader@brvm.ci'), findsOneWidget);
    expect(find.text('+2250701020304'), findsOneWidget);
    expect(find.text('Telegram lié'), findsOneWidget);
  });

  testWidgets('carte portefeuille : valeur totale, performance, positions',
      (tester) async {
    const user = AuthUser(id: 'u1', email: 'trader@brvm.ci', hasTelegram: false);
    await _pumpScreen(tester, user: user, portfolioJson: _richPortfolioJson);

    expect(find.text('Portefeuille'), findsOneWidget);
    expect(find.text('Valeur totale'), findsOneWidget);
    // Montants formatés fr_FR (espaces insécables) : comparer via les
    // helpers de formatage eux-mêmes.
    expect(find.text(formatFcfa(1520000)), findsOneWidget);
    expect(find.text('Gain/Perte'), findsOneWidget);
    expect(find.text(formatSignedFcfa(120000)), findsOneWidget);
    expect(find.text('Dividendes'), findsOneWidget);
    expect(find.text(formatFcfa(45000)), findsOneWidget);
    expect(find.text('Positions'), findsOneWidget);
    expect(find.text('4'), findsOneWidget);
    expect(find.byKey(const Key('account-portfolio-link')), findsOneWidget);
  });

  testWidgets('portefeuille vide → état vide explicite', (tester) async {
    const user = AuthUser(id: 'u1', email: 'trader@brvm.ci', hasTelegram: false);
    await _pumpScreen(tester, user: user);

    expect(find.text('Aucune position pour le moment.'), findsOneWidget);
    expect(find.text('Valeur totale'), findsNothing);
  });
}
