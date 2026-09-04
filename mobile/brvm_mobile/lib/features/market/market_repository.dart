import 'package:dio/dio.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import '../watchlist/watchlist_providers.dart' show dioDetailMessage;
import 'market_models.dart';

/// 404 sur un courtier (identifiant inconnu ou autre utilisateur).
class BrokerNotFoundException implements Exception {
  const BrokerNotFoundException();

  @override
  String toString() => 'Courtier introuvable.';
}

/// 502 sur la lecture d'un article : le backend n'a pas pu le récupérer.
/// [message] porte le `detail` renvoyé par le serveur.
class ArticleFetchException implements Exception {
  const ArticleFetchException(this.message);

  final String message;

  @override
  String toString() => message;
}

class MarketRepository {
  MarketRepository(this._api);

  final ApiClient _api;

  Future<List<PalmaresStock>> getPalmares() async {
    final response = await _api.get('${AppConfig.apiPrefix}/market/palmares');
    return asMapList(asMap(response.data)['stocks'])
        .map(PalmaresStock.fromJson)
        .where((s) => s.symbol.isNotEmpty)
        .toList();
  }

  /// Dernier cours connu d'un titre (indicatif, ex. aide à la saisie).
  Future<double?> getQuote(String symbol) async {
    final response =
        await _api.get('${AppConfig.apiPrefix}/market/quotes/$symbol');
    return asDouble(asMap(response.data)['price']);
  }

  Future<List<BrokerEntry>> getBrokers() async {
    final response = await _api.get('${AppConfig.apiPrefix}/market/brokers');
    return brokerEntriesFromSection(asMap(response.data)['brokers']);
  }

  /// Détail d'un courtier par identifiant (404 → [BrokerNotFoundException]).
  Future<BrokerEntry> getBroker(int id) async {
    try {
      final response =
          await _api.get('${AppConfig.apiPrefix}/market/brokers/$id');
      return BrokerEntry.fromJson(asMap(asMap(response.data)['broker']));
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) {
        throw const BrokerNotFoundException();
      }
      rethrow;
    }
  }

  Future<NewsFeed> getNews() async {
    final response = await _api.get('${AppConfig.apiPrefix}/market/news');
    // Deux formes possibles : liste directe, ou
    // `{"items": [...], "warning": ..., "error": ...}`.
    return NewsFeed.fromSection(asMap(response.data)['news']);
  }

  /// Contenu d'un article lu in-app. 502 → [ArticleFetchException]
  /// portant le message `detail` du backend.
  Future<NewsArticle> getArticle(String url) async {
    try {
      final response = await _api.get(
        '${AppConfig.apiPrefix}/news/article',
        queryParameters: <String, dynamic>{'url': url},
      );
      return NewsArticle.fromJson(asMap(asMap(response.data)['article']));
    } on DioException catch (e) {
      if (e.response?.statusCode == 502) {
        throw ArticleFetchException(
          dioDetailMessage(e) ?? 'Article indisponible.',
        );
      }
      rethrow;
    }
  }
}
