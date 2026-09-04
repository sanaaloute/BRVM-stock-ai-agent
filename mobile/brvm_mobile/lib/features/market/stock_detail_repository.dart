import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import 'stock_detail_models.dart';

/// Détails investisseur d'un titre coté (cotation, historique, fiche,
/// dividendes, actualités, prévision, score).
class StockDetailRepository {
  StockDetailRepository(this._api);

  final ApiClient _api;

  Future<SymbolDetail> getSymbolDetail(
    String symbol, {
    String period = '3M',
  }) async {
    final response = await _api.get(
      '${AppConfig.apiPrefix}/market/symbols/$symbol',
      queryParameters: <String, dynamic>{'period': period},
    );
    return SymbolDetail.fromJson(symbol, asMap(response.data));
  }
}
