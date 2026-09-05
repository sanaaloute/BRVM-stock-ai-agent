import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/alerts/alerts_providers.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_models.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakePortfolioRepository extends PortfolioRepository {
  _FakePortfolioRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  int calls = 0;

  @override
  Future<PortfolioData> get() async {
    calls++;
    return PortfolioData.fromJson(<String, dynamic>{
      'positions': <Map<String, dynamic>>[
        <String, dynamic>{'symbol': 'ETIT'},
      ],
    });
  }
}

class _FakeAlertsRepository extends AlertsRepository {
  _FakeAlertsRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  int calls = 0;

  @override
  Future<List<PriceAlert>> get() async {
    calls++;
    return <PriceAlert>[];
  }
}

/// Simule la résolution de l'auth : null puis u1, puis u2.
final _userIdFlip = StateProvider<String?>((ref) => null);

void main() {
  test('portfolioProvider se recharge quand le compte change', () async {
    final repo = _FakePortfolioRepository();
    final container = ProviderContainer(
      overrides: <Override>[
        portfolioRepositoryProvider.overrideWithValue(repo),
        currentUserIdProvider.overrideWith((ref) => ref.watch(_userIdFlip)),
      ],
    );
    addTearDown(container.dispose);

    container.read(_userIdFlip.notifier).state = 'u1';
    final first = await container.read(portfolioProvider.future);
    expect(first.positions.single.symbol, 'ETIT');
    expect(repo.calls, 1);

    // Changement de compte → rechargement automatique (watch), sans
    // invalidate manuel : pas de données de l'ancien compte servies.
    container.read(_userIdFlip.notifier).state = 'u2';
    await Future<void>.delayed(Duration.zero);
    final second = await container.read(portfolioProvider.future);
    expect(second.positions.single.symbol, 'ETIT');
    expect(repo.calls, 2);
  });

  test('alertsProvider se recharge quand le compte change', () async {
    final repo = _FakeAlertsRepository();
    final container = ProviderContainer(
      overrides: <Override>[
        alertsRepositoryProvider.overrideWithValue(repo),
        currentUserIdProvider.overrideWith((ref) => ref.watch(_userIdFlip)),
      ],
    );
    addTearDown(container.dispose);

    container.read(_userIdFlip.notifier).state = 'u1';
    await container.read(alertsProvider.future);
    expect(repo.calls, 1);

    container.read(_userIdFlip.notifier).state = 'u2';
    await Future<void>.delayed(Duration.zero);
    await container.read(alertsProvider.future);
    expect(repo.calls, 2);
  });
}
