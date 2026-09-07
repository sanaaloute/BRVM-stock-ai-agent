import 'package:dio/dio.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import 'predictions_models.dart';

/// 404 sur le détail d'une prévision (aucune prévision pour ce titre).
class PredictionNotFoundException implements Exception {
  const PredictionNotFoundException();

  @override
  String toString() => 'Aucune prévision disponible pour ce titre.';
}

class PredictionsRepository {
  PredictionsRepository(this._api);

  final ApiClient _api;

  Future<PredictionsFeed> getPredictions() async {
    final response =
        await _api.get('${AppConfig.apiPrefix}/market/predictions');
    return PredictionsFeed.fromJson(asMap(response.data));
  }

  /// Détail complet d'une prévision (explication, objectifs, métriques) ;
  /// 404 → [PredictionNotFoundException].
  Future<StockPrediction> getPrediction(String symbol) async {
    try {
      final response =
          await _api.get('${AppConfig.apiPrefix}/market/predictions/$symbol');
      final data = asMap(response.data);
      // Tolère une enveloppe `{"prediction": {...}}` comme une réponse plate.
      final envelope = asMap(data['prediction']);
      return StockPrediction.fromJson(envelope.isNotEmpty ? envelope : data);
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) {
        throw const PredictionNotFoundException();
      }
      rethrow;
    }
  }
}
