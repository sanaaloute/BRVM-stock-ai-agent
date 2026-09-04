import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'stock_detail_models.dart';
import 'stock_detail_repository.dart';

final stockDetailRepositoryProvider = Provider<StockDetailRepository>(
  (ref) => StockDetailRepository(ref.watch(apiClientProvider)),
);

/// Fiche complète (période par défaut 3M) : en-tête, score, profil,
/// dividendes, actualités et prévision.
final stockDetailProvider =
    FutureProvider.autoDispose.family<SymbolDetail, String>(
  (ref, symbol) => ref.watch(stockDetailRepositoryProvider).getSymbolDetail(symbol),
);

/// Historique des cours pour une période donnée, rafraîchi indépendamment
/// du reste de la fiche (le sélecteur de période ne recharge que le
/// graphique).
final stockHistoryProvider =
    FutureProvider.autoDispose.family<StockHistory, (String, String)>(
  (ref, record) {
    final (symbol, period) = record;
    return ref
        .watch(stockDetailRepositoryProvider)
        .getSymbolDetail(symbol, period: period)
        .then((detail) => detail.history);
  },
);
