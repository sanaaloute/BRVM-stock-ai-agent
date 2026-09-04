import 'package:brvm_mobile/core/models/auth_user.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late MemoryKeyValueStore store;
  late TokenStorage storage;

  setUp(() {
    store = MemoryKeyValueStore();
    storage = TokenStorage(store);
  });

  AuthSession buildSession() => const AuthSession(
        user: AuthUser(
          id: 'u1',
          email: 'user@example.com',
          phone: null,
          hasTelegram: true,
        ),
        accessToken: 'access-abc',
        accessExpiresIn: 900,
        refreshToken: 'refresh-xyz',
        refreshExpiresIn: 2592000,
        tokenType: 'Bearer',
      );

  test('round-trip complet d’une session', () async {
    await storage.saveSession(buildSession());

    expect(await storage.readAccessToken(), 'access-abc');
    expect(await storage.readRefreshToken(), 'refresh-xyz');

    final user = await storage.readUser();
    expect(user, isNotNull);
    expect(user!.id, 'u1');
    expect(user.email, 'user@example.com');
    expect(user.hasTelegram, isTrue);
  });

  test('clear efface jetons et utilisateur', () async {
    await storage.saveSession(buildSession());
    await storage.clear();

    expect(await storage.readAccessToken(), isNull);
    expect(await storage.readRefreshToken(), isNull);
    expect(await storage.readUser(), isNull);
  });

  test('readUser retourne null quand rien n’est stocké', () async {
    expect(await storage.readUser(), isNull);
  });

  test('readUser retourne null sur JSON corrompu (défensif)', () async {
    await store.write('user_json', '{pas-du-json');
    expect(await storage.readUser(), isNull);
  });
}
