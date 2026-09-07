import 'dart:convert';
import 'dart:typed_data';

import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/auth_repository.dart';
import 'package:brvm_mobile/core/models/auth_user.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

/// Adaptateur HTTP factice : répond via [handler] sans réseau.
class MockAdapter implements HttpClientAdapter {
  MockAdapter(this.handler);

  final ResponseBody Function(RequestOptions options) handler;

  final List<RequestOptions> requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody jsonResponse(
  Object? body,
  int statusCode, {
  Map<String, List<String>>? headers,
}) =>
    ResponseBody.fromString(
      jsonEncode(body),
      statusCode,
      headers: headers ??
          <String, List<String>>{
            Headers.contentTypeHeader: <String>['application/json'],
          },
    );

ApiClient buildClient(
  MockAdapter adapter, {
  TokenStorage? storage,
  void Function()? onSessionExpired,
}) {
  final dio = Dio(BaseOptions(baseUrl: 'https://api.test'));
  dio.httpClientAdapter = adapter;
  return ApiClient(
    storage ?? TokenStorage(MemoryKeyValueStore()),
    dio: dio,
    onSessionExpired: onSessionExpired,
  );
}

Future<TokenStorage> storageWithSession() async {
  final storage = TokenStorage(MemoryKeyValueStore());
  await storage.saveSession(
    const AuthSession(
      user: AuthUser(id: 'u1', email: 'a@b.co', hasTelegram: false),
      accessToken: 'expired-token',
      accessExpiresIn: 0,
      refreshToken: 'refresh-token',
      refreshExpiresIn: 100,
      tokenType: 'Bearer',
    ),
  );
  return storage;
}

void main() {
  group('AuthRepository.login', () {
    test('succès → session parsée, bonne route et corps de requête', () async {
      final adapter = MockAdapter(
        (options) => jsonResponse(<String, dynamic>{
          'ok': true,
          'user': <String, dynamic>{
            'id': 'u42',
            'email': 'trader@brvm.ci',
            'phone': '+2250707070707',
            'has_telegram': true,
          },
          'access_token': 'at-1',
          'access_expires_in': 900,
          'refresh_token': 'rt-1',
          'refresh_expires_in': 1209600,
          'token_type': 'Bearer',
        }, 200),
      );
      final repo = AuthRepository(buildClient(adapter));

      final session = await repo.login('trader@brvm.ci', 'motdepasse');

      expect(session.accessToken, 'at-1');
      expect(session.refreshToken, 'rt-1');
      expect(session.accessExpiresIn, 900);
      expect(session.user.id, 'u42');
      expect(session.user.hasTelegram, isTrue);
      final request = adapter.requests.single;
      expect(request.path, '/mobile/v1/auth/login');
      final sent = request.data as Map<String, dynamic>;
      expect(sent['identifier'], 'trader@brvm.ci');
      expect(sent['password'], 'motdepasse');
    });

    test('401 → message identifiants incorrects', () async {
      final adapter = MockAdapter(
        (options) => jsonResponse(<String, String>{'detail': 'nope'}, 401),
      );
      final repo = AuthRepository(buildClient(adapter));

      await expectLater(
        repo.login('trader@brvm.ci', 'mauvais'),
        throwsA(isA<AuthException>()),
      );
      try {
        await repo.login('trader@brvm.ci', 'mauvais');
      } on AuthException catch (e) {
        expect(e.message, 'E-mail/numéro ou mot de passe incorrect.');
      }
    });

    test('429 → message du detail (throttled)', () async {
      final adapter = MockAdapter(
        (options) => jsonResponse(<String, dynamic>{
          'detail': 'Trop de tentatives, réessayez dans une minute',
        }, 429),
      );
      final repo = AuthRepository(buildClient(adapter));

      try {
        await repo.login('trader@brvm.ci', 'motdepasse');
        fail('devrait lever AuthException');
      } on AuthException catch (e) {
        expect(e.message, contains('Trop de tentatives'));
      }
    });
  });

  group('AuthRepository.register', () {
    test('succès → session parsée', () async {
      final adapter = MockAdapter(
        (options) => jsonResponse(<String, dynamic>{
          'ok': true,
          'user': <String, dynamic>{
            'id': 'u7',
            'email': 'nouveau@brvm.ci',
            'has_telegram': false,
          },
          'access_token': 'at-2',
          'access_expires_in': 900,
          'refresh_token': 'rt-2',
          'refresh_expires_in': 1209600,
          'token_type': 'Bearer',
        }, 200),
      );
      final repo = AuthRepository(buildClient(adapter));

      final session = await repo.register('nouveau@brvm.ci', 'motdepasse');

      expect(session.accessToken, 'at-2');
      expect(session.user.id, 'u7');
      expect(adapter.requests.single.path, '/mobile/v1/auth/register');
    });

    test('409 → compte déjà existant', () async {
      final adapter = MockAdapter(
        (options) =>
            jsonResponse(<String, String>{'detail': 'Account exists'}, 409),
      );
      final repo = AuthRepository(buildClient(adapter));

      try {
        await repo.register('trader@brvm.ci', 'motdepasse');
        fail('devrait lever AuthException');
      } on AuthException catch (e) {
        expect(e.message, contains('existe déjà'));
        expect(e.message, contains('Connectez-vous'));
        expect(e.code, 'account_exists');
      }
    });

    test('400 → detail transmis tel quel (mot de passe faible)', () async {
      final adapter = MockAdapter(
        (options) => jsonResponse(<String, String>{
          'detail': 'Mot de passe : 8 caractères minimum.',
        }, 400),
      );
      final repo = AuthRepository(buildClient(adapter));

      try {
        await repo.register('trader@brvm.ci', '123');
        fail('devrait lever AuthException');
      } on AuthException catch (e) {
        expect(e.message, 'Mot de passe : 8 caractères minimum.');
      }
    });
  });

  group('ApiClient — renouvellement du jeton (401 → refresh → retry)', () {
    test('rejoue la requête après un refresh réussi et stocke les nouveaux jetons',
        () async {
      final storage = await storageWithSession();
      var refreshCalls = 0;
      final adapter = MockAdapter((options) {
        if (options.path.contains('/auth/refresh')) {
          refreshCalls++;
          return jsonResponse(<String, dynamic>{
            'user': <String, dynamic>{'id': 'u1', 'has_telegram': false},
            'access_token': 'new-access',
            'access_expires_in': 900,
            'refresh_token': 'new-refresh',
            'refresh_expires_in': 1209600,
            'token_type': 'Bearer',
          }, 200);
        }
        final auth = (options.headers['Authorization'] ?? '') as String;
        if (auth == 'Bearer expired-token') {
          return jsonResponse(<String, dynamic>{'detail': 'expired'}, 401);
        }
        if (auth == 'Bearer new-access') {
          return jsonResponse(<String, dynamic>{'ok': true}, 200);
        }
        return jsonResponse(<String, dynamic>{'detail': 'unexpected'}, 500);
      });
      final client = buildClient(adapter, storage: storage);

      final response = await client.get('/mobile/v1/portfolio');

      expect(response.statusCode, 200);
      expect(refreshCalls, 1);
      expect(await storage.readAccessToken(), 'new-access');
      expect(await storage.readRefreshToken(), 'new-refresh');
      // 3 requêtes : originale (401), refresh, retry.
      expect(adapter.requests.length, 3);
      expect(adapter.requests.last.headers['Authorization'],
          'Bearer new-access');
    });

    test('refresh en échec → jetons effacés et onSessionExpired appelé',
        () async {
      final storage = await storageWithSession();
      var expiredCalled = false;
      final adapter = MockAdapter((options) {
        if (options.path.contains('/auth/refresh')) {
          return jsonResponse(<String, dynamic>{'detail': 'invalid'}, 401);
        }
        return jsonResponse(<String, dynamic>{'detail': 'expired'}, 401);
      });
      final client = buildClient(
        adapter,
        storage: storage,
        onSessionExpired: () => expiredCalled = true,
      );

      await expectLater(
        client.get('/mobile/v1/portfolio'),
        throwsA(isA<DioException>()),
      );

      expect(expiredCalled, isTrue);
      expect(await storage.readAccessToken(), isNull);
      expect(await storage.readRefreshToken(), isNull);
    });

    test('pas de refresh pour les routes auth', () async {
      var refreshCalls = 0;
      final adapter = MockAdapter((options) {
        if (options.path.contains('/auth/refresh')) {
          refreshCalls++;
        }
        return jsonResponse(<String, dynamic>{'detail': 'nope'}, 401);
      });
      final client = buildClient(adapter, storage: await storageWithSession());

      await expectLater(
        client.post('/mobile/v1/auth/login',
            data: <String, dynamic>{'identifier': 'a', 'password': 'b'}),
        throwsA(isA<DioException>()),
      );
      expect(refreshCalls, 0);
      // Une seule requête : aucun retry déclenché.
      expect(adapter.requests, hasLength(1));
    });

    test('attache le jeton d’accès aux requêtes authentifiées', () async {
      final adapter = MockAdapter(
        (options) => jsonResponse(<String, dynamic>{'ok': true}, 200),
      );
      final client = buildClient(adapter, storage: await storageWithSession());

      await client.get('/mobile/v1/quota');

      expect(adapter.requests.single.headers['Authorization'],
          'Bearer expired-token');
    });
  });
}
