import '../../core/json_utils.dart';

/// Prévision quotidienne d'un titre, calculée par l'IA après la clôture.
/// La liste porte les champs principaux ; le détail ajoute [targetLow],
/// [targetHigh], [explanation] et [details]. Toutes les clés sont
/// optionnelles sauf le symbole.
class StockPrediction {
  const StockPrediction({
    required this.symbol,
    this.name,
    this.price,
    this.direction,
    this.confidencePct,
    this.expectedMovePct,
    this.score,
    this.signal,
    this.day,
    this.targetLow,
    this.targetHigh,
    this.explanation,
    this.details,
  });

  factory StockPrediction.fromJson(Map<String, dynamic> json) {
    final details = asMap(json['details']);
    return StockPrediction(
      symbol: asString(json['symbol']) ?? asString(json['symbole']) ?? '',
      name: asString(json['name']) ?? asString(json['nom']),
      price: asDouble(json['price']),
      // Normalisée en minuscules (« hausse » / « baisse » / « neutre »).
      direction: asString(json['direction'])?.toLowerCase(),
      confidencePct: asDouble(json['confidence_pct']),
      expectedMovePct: asDouble(json['expected_move_pct']),
      score: asDouble(json['score']),
      signal: asString(json['signal']),
      day: DateTime.tryParse(asString(json['day']) ?? ''),
      targetLow: asDouble(json['target_low']),
      targetHigh: asDouble(json['target_high']),
      explanation: asString(json['explanation']),
      details: details.isEmpty ? null : details,
    );
  }

  final String symbol;
  final String? name;
  final double? price;
  final String? direction;
  final double? confidencePct;
  final double? expectedMovePct;
  final double? score;
  final String? signal;
  final DateTime? day;
  final double? targetLow;
  final double? targetHigh;
  final String? explanation;

  /// Métriques détaillées renvoyées par le détail (structure libre,
  /// optionnelle côté backend).
  final Map<String, dynamic>? details;
}

/// Flux des prévisions du jour : date de calcul ([day], nulle tant que
/// rien n'a été calculé) + liste triée par confiance décroissante.
class PredictionsFeed {
  const PredictionsFeed({
    this.day,
    this.predictions = const <StockPrediction>[],
  });

  factory PredictionsFeed.fromJson(Map<String, dynamic> json) =>
      PredictionsFeed(
        day: DateTime.tryParse(asString(json['day']) ?? ''),
        predictions: asMapList(json['predictions'])
            .map(StockPrediction.fromJson)
            .where((p) => p.symbol.isNotEmpty)
            .toList(),
      );

  final DateTime? day;
  final List<StockPrediction> predictions;
}
