import 'dart:typed_data';

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

  Future<PortfolioData> get({String? sgi}) async {
    final response = await _api.get(
      '${AppConfig.apiPrefix}/portfolio',
      queryParameters: sgi == null ? null : <String, dynamic>{'sgi': sgi},
    );
    return PortfolioData.fromJson(asMap(response.data));
  }

  Future<SgiImportPreview> parseImport(Uint8List bytes, String filename) async {
    try {
      final formData = FormData.fromMap({
        'file': MultipartFile.fromBytes(bytes, filename: filename),
      });
      final response = await _api.post(
        '${AppConfig.apiPrefix}/portfolio/import/parse',
        data: formData,
      );
      return SgiImportPreview.fromJson(asMap(response.data));
    } on DioException catch (e) {
      throw StateError(
        dioDetailMessage(e) ?? 'Impossible d’analyser ce document.',
      );
    }
  }

  Future<Map<String, dynamic>> confirmImport(
    String contentHash,
    List<SgiTransaction> transactions,
  ) async {
    try {
      final response = await _api.post(
        '${AppConfig.apiPrefix}/portfolio/import/confirm',
        data: <String, dynamic>{
          'content_hash': contentHash,
          'transactions': transactions.map((tx) => tx.toJson()).toList(),
        },
      );
      return asMap(response.data);
    } on DioException catch (e) {
      throw StateError(
        dioDetailMessage(e) ?? 'Impossible d’appliquer ce document.',
      );
    }
  }

  Future<List<PortfolioHistoryPoint>> getHistory(
    int days, {
    String? sgi,
  }) async {
    final response = await _api.get(
      '${AppConfig.apiPrefix}/portfolio/history',
      queryParameters: <String, dynamic>{
        'days': days,
        if (sgi != null) ...{'sgi': sgi},
      },
    );
    return asMapList(
      asMap(response.data)['points'],
    ).map(PortfolioHistoryPoint.fromJson).toList();
  }

  /// Ajoute un lot d'achat (chaque POST crée une nouvelle ligne).
  /// Retourne `null` si OK, sinon le message d'erreur.
  Future<String?> addLot(
    String symbol,
    double buyPrice,
    String buyDate,
    double quantity, {
    String? sgi,
  }) async {
    try {
      await _api.post(
        '${AppConfig.apiPrefix}/portfolio',
        data: <String, dynamic>{
          'symbol': symbol,
          'buy_price': buyPrice,
          'buy_date': buyDate,
          'quantity': quantity,
          if (sgi != null) ...{'sgi': sgi},
        },
      );
      return null;
    } on DioException catch (e) {
      return dioDetailMessage(e) ?? 'Impossible d’enregistrer l’achat.';
    }
  }

  Future<String?> addDividend(
    String symbol,
    double amount,
    String paymentDate, {
    String? sgi,
  }) async {
    try {
      await _api.post(
        '${AppConfig.apiPrefix}/portfolio/dividends',
        data: <String, dynamic>{
          'symbol': symbol,
          'amount': amount,
          'payment_date': paymentDate,
          if (sgi != null) ...{'sgi': sgi},
        },
      );
      return null;
    } on DioException catch (e) {
      return dioDetailMessage(e) ?? 'Impossible d’enregistrer le dividende.';
    }
  }

  /// Modifie un lot existant. Retourne `null` si OK, sinon le message
  /// d'erreur (404 si le lot n'appartient pas à l'utilisateur).
  Future<String?> updateLot(
    int lotId, {
    double? buyPrice,
    String? buyDate,
    double? quantity,
    String? sgi,
  }) async {
    try {
      await _api.put(
        '${AppConfig.apiPrefix}/portfolio/lots/$lotId',
        data: <String, dynamic>{
          'buy_price': ?buyPrice,
          'buy_date': ?buyDate,
          'quantity': ?quantity,
          if (sgi != null) ...{'sgi': sgi},
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
    // Changement de compte ou de SGI → rechargement automatique.
    ref.watch(currentUserIdProvider);
    final sgi = ref.watch(portfolioSgiFilterProvider);
    return ref.watch(portfolioRepositoryProvider).get(sgi: sgi);
  }

  void _refresh() {
    ref.invalidateSelf();
    ref.invalidate(portfolioHistoryProvider);
  }

  Future<String?> addLot(
    String symbol,
    double buyPrice,
    String buyDate,
    double quantity, {
    String? sgi,
  }) async {
    final message = await ref
        .read(portfolioRepositoryProvider)
        .addLot(symbol, buyPrice, buyDate, quantity, sgi: sgi);
    _refresh();
    return message;
  }

  Future<String?> addDividend(
    String symbol,
    double amount,
    String paymentDate, {
    String? sgi,
  }) async {
    final message = await ref
        .read(portfolioRepositoryProvider)
        .addDividend(symbol, amount, paymentDate, sgi: sgi);
    _refresh();
    return message;
  }

  Future<String?> updateLot(
    int lotId, {
    double? buyPrice,
    String? buyDate,
    double? quantity,
    String? sgi,
  }) async {
    final message = await ref
        .read(portfolioRepositoryProvider)
        .updateLot(
          lotId,
          buyPrice: buyPrice,
          buyDate: buyDate,
          quantity: quantity,
          sgi: sgi,
        );
    _refresh();
    return message;
  }

  Future<void> deleteLot(int lotId) async {
    try {
      await ref.read(portfolioRepositoryProvider).deleteLot(lotId);
    } finally {
      _refresh();
    }
  }

  Future<void> deleteSymbol(String symbol) async {
    try {
      await ref.read(portfolioRepositoryProvider).deleteSymbol(symbol);
    } finally {
      _refresh();
    }
  }
}

typedef PortfolioHistoryQuery = ({int days, String? sgi});

final portfolioSgiFilterProvider = StateProvider<String?>((ref) => null);

final portfolioHistoryProvider = FutureProvider.autoDispose
    .family<List<PortfolioHistoryPoint>, PortfolioHistoryQuery>((ref, query) {
      ref.watch(currentUserIdProvider);
      return ref
          .watch(portfolioRepositoryProvider)
          .getHistory(query.days, sgi: query.sgi);
    });
