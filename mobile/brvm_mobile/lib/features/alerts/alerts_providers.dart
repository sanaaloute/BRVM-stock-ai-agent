import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import '../../core/providers.dart';
import '../watchlist/watchlist_providers.dart' show dioDetailMessage;

/// Alerte de prix.
class PriceAlert {
  const PriceAlert({
    required this.id,
    required this.symbol,
    this.targetPrice,
    this.direction = 'above',
    this.notified = false,
    this.createdAt,
  });

  factory PriceAlert.fromJson(Map<String, dynamic> json) => PriceAlert(
        id: asString(json['id']) ?? '',
        symbol: asString(json['symbol']) ?? '',
        targetPrice: asDouble(json['target_price']),
        direction: asString(json['direction']) ?? 'above',
        notified: asBool(json['notified']),
        createdAt: asString(json['created_at']),
      );

  final String id;
  final String symbol;
  final double? targetPrice;
  final String direction;
  final bool notified;
  final String? createdAt;

  bool get isAbove => direction == 'above';
}

class AlertsRepository {
  AlertsRepository(this._api);

  final ApiClient _api;

  Future<List<PriceAlert>> get() async {
    final response = await _api.get('${AppConfig.apiPrefix}/alerts');
    return asMapList(asMap(response.data)['alerts'])
        .map(PriceAlert.fromJson)
        .toList();
  }

  /// Retourne `null` si OK, sinon le message d'erreur.
  Future<String?> create(String symbol, double targetPrice, String direction) async {
    try {
      await _api.post(
        '${AppConfig.apiPrefix}/alerts',
        data: <String, dynamic>{
          'symbol': symbol,
          'target_price': targetPrice,
          'direction': direction,
        },
      );
      return null;
    } on DioException catch (e) {
      return dioDetailMessage(e) ?? 'Impossible de créer l’alerte.';
    }
  }

  Future<void> delete(String id) async {
    await _api.delete('${AppConfig.apiPrefix}/alerts/$id');
  }
}

final alertsRepositoryProvider = Provider<AlertsRepository>(
  (ref) => AlertsRepository(ref.watch(apiClientProvider)),
);

final alertsProvider = AsyncNotifierProvider<AlertsNotifier, List<PriceAlert>>(
  AlertsNotifier.new,
);

class AlertsNotifier extends AsyncNotifier<List<PriceAlert>> {
  @override
  Future<List<PriceAlert>> build() =>
      ref.watch(alertsRepositoryProvider).get();

  Future<String?> create(String symbol, double targetPrice, String direction) async {
    final message = await ref
        .read(alertsRepositoryProvider)
        .create(symbol, targetPrice, direction);
    ref.invalidateSelf();
    return message;
  }

  Future<void> delete(String id) async {
    try {
      await ref.read(alertsRepositoryProvider).delete(id);
    } finally {
      ref.invalidateSelf();
    }
  }
}
