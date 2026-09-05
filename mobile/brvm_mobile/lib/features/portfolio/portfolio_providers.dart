import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import '../../core/providers.dart';
import '../watchlist/watchlist_providers.dart' show dioDetailMessage;
import 'portfolio_models.dart';

class PortfolioRepository {
  PortfolioRepository(this._api);

  final ApiClient _api;

  Future<PortfolioData> get() async {
    final response = await _api.get('${AppConfig.apiPrefix}/portfolio');
    return PortfolioData.fromJson(asMap(response.data));
  }

  /// Ajoute un lot d'achat (chaque POST crée une nouvelle ligne).
  /// Retourne `null` si OK, sinon le message d'erreur.
  Future<String?> addLot(
    String symbol,
    double buyPrice,
    String buyDate,
    double quantity,
  ) async {
    try {
      await _api.post(
        '${AppConfig.apiPrefix}/portfolio',
        data: <String, dynamic>{
          'symbol': symbol,
          'buy_price': buyPrice,
          'buy_date': buyDate,
          'quantity': quantity,
        },
      );
      return null;
    } on DioException catch (e) {
      return dioDetailMessage(e) ?? 'Impossible d’enregistrer l’achat.';
    }
  }

  /// Modifie un lot existant. Retourne `null` si OK, sinon le message
  /// d'erreur (404 si le lot n'appartient pas à l'utilisateur).
  Future<String?> updateLot(
    int lotId, {
    double? buyPrice,
    String? buyDate,
    double? quantity,
  }) async {
    try {
      await _api.put(
        '${AppConfig.apiPrefix}/portfolio/lots/$lotId',
        data: <String, dynamic>{
          'buy_price': ?buyPrice,
          'buy_date': ?buyDate,
          'quantity': ?quantity,
        },
      );
      return null;
    } on DioException catch (e) {
      return dioDetailMessage(e) ?? 'Impossible de modifier ce lot.';
    }
  }

  Future<void> deleteLot(int lotId) async {
    await _api.delete('${AppConfig.apiPrefix}/portfolio/lots/$lotId');
  }

  Future<void> deleteSymbol(String symbol) async {
    await _api.delete('${AppConfig.apiPrefix}/portfolio/$symbol');
  }
}

final portfolioRepositoryProvider = Provider<PortfolioRepository>(
  (ref) => PortfolioRepository(ref.watch(apiClientProvider)),
);

final portfolioProvider =
    AsyncNotifierProvider<PortfolioNotifier, PortfolioData>(
  PortfolioNotifier.new,
);

class PortfolioNotifier extends AsyncNotifier<PortfolioData> {
  @override
  Future<PortfolioData> build() {
    // Changement de compte → rechargement automatique (pas de cache croisé).
    ref.watch(currentUserIdProvider);
    return ref.watch(portfolioRepositoryProvider).get();
  }

  Future<String?> addLot(
    String symbol,
    double buyPrice,
    String buyDate,
    double quantity,
  ) async {
    final message = await ref
        .read(portfolioRepositoryProvider)
        .addLot(symbol, buyPrice, buyDate, quantity);
    ref.invalidateSelf();
    return message;
  }

  Future<String?> updateLot(
    int lotId, {
    double? buyPrice,
    String? buyDate,
    double? quantity,
  }) async {
    final message = await ref.read(portfolioRepositoryProvider).updateLot(
          lotId,
          buyPrice: buyPrice,
          buyDate: buyDate,
          quantity: quantity,
        );
    ref.invalidateSelf();
    return message;
  }

  Future<void> deleteLot(int lotId) async {
    try {
      await ref.read(portfolioRepositoryProvider).deleteLot(lotId);
    } finally {
      ref.invalidateSelf();
    }
  }

  Future<void> deleteSymbol(String symbol) async {
    try {
      await ref.read(portfolioRepositoryProvider).deleteSymbol(symbol);
    } finally {
      ref.invalidateSelf();
    }
  }
}
