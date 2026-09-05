import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import '../../core/providers.dart';

/// Titre suivi dans la watchlist.
class WatchlistEntry {
  const WatchlistEntry({required this.symbol, this.price});

  factory WatchlistEntry.fromJson(Map<String, dynamic> json) =>
      WatchlistEntry(
        symbol: asString(json['symbol']) ?? '',
        price: asDouble(json['price']),
      );

  final String symbol;
  final double? price;
}

/// Extrait le message `detail` d'une réponse d'erreur Dio.
String? dioDetailMessage(DioException error) {
  final detail = asMap(error.response?.data)['detail'];
  if (detail is Map) return asString(detail['message']);
  return asString(detail);
}

class WatchlistRepository {
  WatchlistRepository(this._api);

  final ApiClient _api;

  Future<List<WatchlistEntry>> get() async {
    final response = await _api.get('${AppConfig.apiPrefix}/watchlist');
    return asMapList(asMap(response.data)['symbols'])
        .map(WatchlistEntry.fromJson)
        .where((e) => e.symbol.isNotEmpty)
        .toList();
  }

  /// Retourne `null` en cas de succès, sinon le message d'erreur.
  Future<String?> add(String symbol) async {
    try {
      await _api.post(
        '${AppConfig.apiPrefix}/watchlist',
        data: <String, dynamic>{'symbol': symbol},
      );
      return null;
    } on DioException catch (e) {
      return dioDetailMessage(e) ?? 'Impossible d’ajouter ce symbole.';
    }
  }

  Future<void> remove(String symbol) async {
    await _api.delete('${AppConfig.apiPrefix}/watchlist/$symbol');
  }
}

final watchlistRepositoryProvider = Provider<WatchlistRepository>(
  (ref) => WatchlistRepository(ref.watch(apiClientProvider)),
);

final watchlistProvider =
    AsyncNotifierProvider<WatchlistNotifier, List<WatchlistEntry>>(
  WatchlistNotifier.new,
);

class WatchlistNotifier extends AsyncNotifier<List<WatchlistEntry>> {
  @override
  Future<List<WatchlistEntry>> build() {
    // Changement de compte → rechargement automatique (pas de cache croisé).
    ref.watch(currentUserIdProvider);
    return ref.watch(watchlistRepositoryProvider).get();
  }

  /// Ajoute un symbole. Retourne `null` si OK, sinon le message d'erreur.
  Future<String?> add(String symbol) async {
    final message = await ref.read(watchlistRepositoryProvider).add(symbol);
    ref.invalidateSelf();
    return message;
  }

  Future<void> remove(String symbol) async {
    try {
      await ref.read(watchlistRepositoryProvider).remove(symbol);
    } finally {
      ref.invalidateSelf();
    }
  }
}
