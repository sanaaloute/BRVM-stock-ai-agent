import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'market_models.dart';
import 'market_repository.dart';

final marketRepositoryProvider = Provider<MarketRepository>(
  (ref) => MarketRepository(ref.watch(apiClientProvider)),
);

final palmaresProvider = FutureProvider.autoDispose<List<PalmaresStock>>(
  (ref) => ref.watch(marketRepositoryProvider).getPalmares(),
);

final palmaresSymbolsProvider = Provider<AsyncValue<List<String>>>(
  (ref) => ref.watch(palmaresProvider).whenData(
        (stocks) => stocks.map((s) => s.symbol).toList()..sort(),
      ),
);

/// Dernier cours connu d'un symbole (aide à la saisie, indicatif).
final quoteProvider =
    FutureProvider.autoDispose.family<double?, String>(
  (ref, symbol) => ref.watch(marketRepositoryProvider).getQuote(symbol),
);

/// Article complet (lecture in-app), indexé par l'URL de l'article.
final articleProvider = FutureProvider.autoDispose
    .family<NewsArticle, String>(
  (ref, url) => ref.watch(marketRepositoryProvider).getArticle(url),
);

final brokersProvider = FutureProvider.autoDispose<List<BrokerEntry>>(
  (ref) => ref.watch(marketRepositoryProvider).getBrokers(),
);

/// Détail d'un courtier (écran `/marche/courtier/:id`).
final brokerProvider = FutureProvider.autoDispose
    .family<BrokerEntry, int>(
  (ref, id) => ref.watch(marketRepositoryProvider).getBroker(id),
);

final newsProvider = FutureProvider.autoDispose<NewsFeed>(
  (ref) => ref.watch(marketRepositoryProvider).getNews(),
);
