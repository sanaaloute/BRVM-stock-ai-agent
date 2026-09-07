import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/auth_repository.dart';
import 'package:brvm_mobile/core/models/auth_user.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/settings/settings_providers.dart';
import 'package:brvm_mobile/features/settings/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Réponses en dur, sans réseau ; [deleteAccount] enregistre l'appel et
/// lève [AuthException] si [deleteError] est fourni.
class _FakeAuthRepository extends AuthRepository {
  _FakeAuthRepository({required this.user, this.deleteError})
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final AuthUser user;
  final String? deleteError;

  int deleteCalls = 0;
  String? deletedWithPassword;

  @override
  Future<AuthUser> me() async => user;

  @override
  Future<void> deleteAccount({String? password}) async {
    deleteCalls++;
    deletedWithPassword = password;
    final error = deleteError;
    if (error != null) throw AuthException(error);
  }
}

class _FakeSettingsRepository extends SettingsRepository {
  _FakeSettingsRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  @override
  Future<DigestSettings> getDigest() async => const DigestSettings();

  @override
  Future<Quota> getQuota() async => const Quota(used: 0, limit: 10);
}

void main() {
  Future<void> pumpScreen(
    WidgetTester tester, {
    required AuthUser user,
    required _FakeAuthRepository repo,
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
          authRepositoryProvider.overrideWithValue(repo),
          settingsRepositoryProvider
              .overrideWithValue(_FakeSettingsRepository()),
        ],
        child: const MaterialApp(home: SettingsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    // ListView paresseux : faire défiler jusqu'au bouton pour le construire.
    await tester.scrollUntilVisible(
      find.text('Supprimer mon compte'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Supprimer mon compte'));
    await tester.pumpAndSettle();
  }

  testWidgets(
      'compte avec mot de passe : champ requis, erreur affichée si incorrect',
      (tester) async {
    const user = AuthUser(
      id: 'u1',
      email: 'trader@brvm.ci',
      hasTelegram: false,
      hasPassword: true,
    );
    final repo = _FakeAuthRepository(
      user: user,
      deleteError: 'Mot de passe incorrect.',
    );
    await pumpScreen(tester, user: user, repo: repo);

    expect(find.text('Supprimer définitivement ?'), findsOneWidget);
    expect(find.byKey(const Key('delete-account-password')), findsOneWidget);

    // Confirmation désactivée tant que le mot de passe est vide.
    var confirm = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Supprimer définitivement'),
    );
    expect(confirm.onPressed, isNull);

    await tester.enterText(
      find.byKey(const Key('delete-account-password')),
      'mauvais',
    );
    await tester.pump();
    confirm = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Supprimer définitivement'),
    );
    expect(confirm.onPressed, isNotNull);

    await tester.tap(find.text('Supprimer définitivement'));
    await tester.pumpAndSettle();

    // Erreur affichée dans le dialogue, qui reste ouvert.
    expect(find.text('Mot de passe incorrect.'), findsOneWidget);
    expect(find.text('Supprimer définitivement ?'), findsOneWidget);
    expect(repo.deletedWithPassword, 'mauvais');
  });

  testWidgets(
      'compte démo (sans mot de passe) : pas de champ, suppression directe',
      (tester) async {
    const user = AuthUser(id: 'demo', hasTelegram: false);
    final repo = _FakeAuthRepository(user: user);
    await pumpScreen(tester, user: user, repo: repo);

    expect(find.text('Supprimer définitivement ?'), findsOneWidget);
    expect(find.byKey(const Key('delete-account-password')), findsNothing);

    final confirm = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Supprimer définitivement'),
    );
    expect(confirm.onPressed, isNotNull);

    await tester.tap(find.text('Supprimer définitivement'));
    await tester.pumpAndSettle();

    expect(repo.deleteCalls, 1);
    expect(repo.deletedWithPassword, isNull);
    // Dialogue fermé et session effacée : dans l'app réelle, la redirection
    // du routeur renvoie vers /auth/identifier.
    expect(find.text('Supprimer définitivement ?'), findsNothing);
    final container =
        ProviderScope.containerOf(tester.element(find.byType(SettingsScreen)));
    expect(container.read(authStateProvider), isA<AuthUnauthenticated>());
  });
}
