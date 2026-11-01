import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/updates/app_update_models.dart';
import 'package:brvm_mobile/features/updates/app_update_providers.dart';
import 'package:brvm_mobile/features/updates/update_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';

class _FakeAppUpdateRepository extends AppUpdateRepository {
  _FakeAppUpdateRepository({this.info})
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final AppVersionInfo? info;

  @override
  Future<AppVersionInfo?> fetchLatestVersion() async => info;
}

ProviderContainer _containerWith(AppUpdateRepository repo) {
  final container = ProviderContainer(
    overrides: <Override>[
      appUpdateRepositoryProvider.overrideWithValue(repo),
    ],
  );
  return container;
}

void main() {
  setUpAll(() {
    PackageInfo.setMockInitialValues(
      appName: 'Kora Bourse',
      packageName: 'com.neobytech.korabourse',
      version: '1.5.1',
      buildNumber: '12',
      buildSignature: '',
    );
  });

  group('compareAppVersions', () {
    test('versions égales', () {
      expect(compareAppVersions('1.5.1', '1.5.1'), 0);
      expect(compareAppVersions('1.5', '1.5.0'), 0);
      expect(compareAppVersions('1.5.1+12', '1.5.1'), 0);
    });

    test('comparaison numérique segment par segment', () {
      expect(compareAppVersions('1.5.1', '1.5.2'), lessThan(0));
      expect(compareAppVersions('1.5.2', '1.5.1'), greaterThan(0));
      // « 10 » > « 9 » : comparaison numérique, pas lexicographique.
      expect(compareAppVersions('1.9.9', '1.10.0'), lessThan(0));
      expect(compareAppVersions('2.0.0', '1.99.99'), greaterThan(0));
    });
  });

  group('AppVersionInfo.fromJson', () {
    test('valeurs présentes', () {
      final info = AppVersionInfo.fromJson(const <String, dynamic>{
        'latest_version': '1.6.0',
        'whats_new': 'Nouveautés :\n- Point A',
      });
      expect(info.latestVersion, '1.6.0');
      expect(info.whatsNew, 'Nouveautés :\n- Point A');
    });

    test('clés absentes ou vides → null', () {
      final info = AppVersionInfo.fromJson(const <String, dynamic>{
        'latest_version': null,
        'whats_new': '',
      });
      expect(info.latestVersion, isNull);
      expect(info.whatsNew, isNull);
    });
  });

  group('availableUpdateProvider', () {
    test('version store plus récente → mise à jour proposée', () async {
      final container = _containerWith(
        _FakeAppUpdateRepository(
          info: const AppVersionInfo(
              latestVersion: '1.6.0', whatsNew: 'Nouveau'),
        ),
      );
      addTearDown(container.dispose);

      final update = await container.read(availableUpdateProvider.future);
      expect(update, isNotNull);
      expect(update!.currentVersion, '1.5.1');
      expect(update.latestVersion, '1.6.0');
      expect(update.whatsNew, 'Nouveau');
    });

    test('version identique ou plus ancienne → rien', () async {
      for (final latest in <String>['1.5.1', '1.5.0', '1.4.9']) {
        final container = _containerWith(
          _FakeAppUpdateRepository(
              info: AppVersionInfo(latestVersion: latest)),
        );
        addTearDown(container.dispose);
        expect(
          await container.read(availableUpdateProvider.future),
          isNull,
          reason: 'latest=$latest ne doit pas proposer de mise à jour',
        );
      }
    });

    test('métadonnées indisponibles → rien', () async {
      final container = _containerWith(
        _FakeAppUpdateRepository(info: null),
      );
      addTearDown(container.dispose);
      expect(await container.read(availableUpdateProvider.future), isNull);

      final empty = _containerWith(
        _FakeAppUpdateRepository(info: const AppVersionInfo()),
      );
      addTearDown(empty.dispose);
      expect(await empty.read(availableUpdateProvider.future), isNull);
    });
  });

  group('UpdateAvailableDialog', () {
    const update = AppUpdate(
      currentVersion: '1.5.1',
      latestVersion: '1.6.0',
      whatsNew: 'Nouveautés :\n- Point A',
    );

    testWidgets('affiche versions et nouveautés', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: UpdateAvailableDialog(update: update)),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Mise à jour disponible'), findsOneWidget);
      expect(find.text('Votre version'), findsOneWidget);
      expect(find.text('1.5.1'), findsOneWidget);
      expect(find.text('Dernière version'), findsOneWidget);
      expect(find.text('1.6.0'), findsOneWidget);
      expect(find.text('Nouveautés'), findsOneWidget);
      expect(find.text('Nouveautés :\n- Point A'), findsOneWidget);
      expect(find.text('Plus tard'), findsOneWidget);
      expect(find.text('Mettre à jour'), findsOneWidget);
    });

    testWidgets('« Plus tard » ferme le dialogue (rappel au prochain '
        'lancement)', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => FilledButton(
              onPressed: () => showDialog<void>(
                context: context,
                builder: (context) =>
                    const UpdateAvailableDialog(update: update),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsOneWidget);

      await tester.tap(find.text('Plus tard'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
    });
  });
}
