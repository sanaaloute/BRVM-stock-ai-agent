import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/auth_repository.dart';
import 'package:brvm_mobile/core/models/auth_user.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeAuthRepository extends AuthRepository {
  _FakeAuthRepository({this.onRefresh, this.onMe})
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final AuthSession Function()? onRefresh;
  final AuthUser Function()? onMe;
  int refreshCalls = 0;
  int meCalls = 0;

  @override
  Future<AuthSession> refresh(String refreshToken) async {
    refreshCalls++;
    final fn = onRefresh;
    if (fn == null) throw const AuthException('Session expirée.');
    return fn();
  }

  @override
  Future<AuthUser> me() async {
    meCalls++;
    final fn = onMe;
    if (fn == null) throw StateError('pas de /me');
    return fn();
  }
}

AuthSession _session(String id, {String email = 'trader@brvm.ci'}) =>
    AuthSession(
      user: AuthUser(id: id, email: email, hasTelegram: false),
      accessToken: 'at-$id',
      accessExpiresIn: 900,
      refreshToken: 'rt-$id',
      refreshExpiresIn: 1209600,
      tokenType: 'Bearer',
    );

Future<AuthState> _waitRestore(ProviderContainer container) async {
  // Le constructeur d'AuthNotifier lance _restore en arrière-plan.
  for (var i = 0; i < 200; i++) {
    final auth = container.read(authStateProvider);
    if (auth is! AuthLoading) return auth;
    await Future<void>.delayed(const Duration(milliseconds: 2));
  }
  return container.read(authStateProvider);
}

ProviderContainer _container(TokenStorage storage, _FakeAuthRepository repo) =>
    ProviderContainer(
      overrides: <Override>[
        storageProvider.overrideWithValue(storage),
        authRepositoryProvider.overrideWithValue(repo),
      ],
    );

void main() {
  test('session valide en cache → authentifié directement, sans refresh',
      () async {
    final storage = TokenStorage(MemoryKeyValueStore());
    await storage.saveSession(_session('u1'));
    final repo = _FakeAuthRepository();
    final container = _container(storage, repo);
    addTearDown(container.dispose);

    final auth = await _waitRestore(container);

    expect(auth, isA<AuthAuthenticated>());
    expect((auth as AuthAuthenticated).user.id, 'u1');
    expect(repo.refreshCalls, 0);
    expect(repo.meCalls, 0);
  });

  test('profil stocké sans id (ancien bug refresh) → réparé au démarrage',
      () async {
    final storage = TokenStorage(MemoryKeyValueStore());
    // Session corrompue : id vide (écrasé par un /auth/refresh sans profil).
    await storage.saveSession(_session(''));
    final repo = _FakeAuthRepository(onRefresh: () => _session('u1'));
    final container = _container(storage, repo);
    addTearDown(container.dispose);

    final auth = await _waitRestore(container);

    expect(auth, isA<AuthAuthenticated>());
    expect((auth as AuthAuthenticated).user.id, 'u1');
    expect(repo.refreshCalls, 1);
    expect(repo.meCalls, 0); // backend corrigé : pas besoin de /me
    expect((await storage.readUser())?.id, 'u1');
    expect(await storage.readAccessToken(), 'at-u1');
  });

  test('profil sans id + refresh sans profil (vieux backend) → réparé via /me',
      () async {
    final storage = TokenStorage(MemoryKeyValueStore());
    await storage.saveSession(_session(''));
    final repo = _FakeAuthRepository(
      onRefresh: () => _session(''), // vieux backend : toujours pas de profil
      onMe: () => const AuthUser(id: 'u1', email: 'trader@brvm.ci',
          hasTelegram: false),
    );
    final container = _container(storage, repo);
    addTearDown(container.dispose);

    final auth = await _waitRestore(container);

    expect(auth, isA<AuthAuthenticated>());
    expect((auth as AuthAuthenticated).user.id, 'u1');
    expect(repo.meCalls, 1);
    expect((await storage.readUser())?.id, 'u1');
  });

  test('aucune session stockée → non authentifié', () async {
    final storage = TokenStorage(MemoryKeyValueStore());
    final repo = _FakeAuthRepository();
    final container = _container(storage, repo);
    addTearDown(container.dispose);

    final auth = await _waitRestore(container);

    expect(auth, isA<AuthUnauthenticated>());
    expect(repo.refreshCalls, 0);
  });
}
