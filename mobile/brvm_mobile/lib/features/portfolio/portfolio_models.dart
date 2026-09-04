import '../../core/json_utils.dart';

/// Lot d'achat : une ligne d'achat unitaire du portefeuille.
class Lot {
  const Lot({
    this.id,
    required this.symbol,
    this.buyPrice,
    this.buyDate,
    this.quantity,
  });

  factory Lot.fromJson(Map<String, dynamic> json) => Lot(
        id: asInt(json['id']),
        symbol: asString(json['symbol']) ?? '',
        buyPrice: asDouble(json['buy_price']),
        buyDate: asString(json['buy_date']),
        quantity: asDouble(json['quantity']),
      );

  final int? id;
  final String symbol;
  final double? buyPrice;
  final String? buyDate;
  final double? quantity;

  double? get invested =>
      (buyPrice != null && quantity != null) ? buyPrice! * quantity! : null;
}

/// Position agrégée : total des lots d'un symbole.
class Position {
  const Position({
    required this.symbol,
    this.quantity,
    this.avgBuyPrice,
    this.totalCost,
    this.currentPrice,
    this.gainLossPct,
    this.lots = const <Lot>[],
  });

  factory Position.fromJson(Map<String, dynamic> json) => Position(
        symbol: asString(json['symbol']) ?? '',
        quantity: asDouble(json['quantity']),
        avgBuyPrice: asDouble(json['avg_buy_price']),
        totalCost: asDouble(json['total_cost']),
        currentPrice: asDouble(json['current_price']),
        gainLossPct: asDouble(json['gain_loss_pct']),
        lots: asMapList(json['lots']).map(Lot.fromJson).toList(),
      );

  final String symbol;
  final double? quantity;
  final double? avgBuyPrice;
  final double? totalCost;
  final double? currentPrice;
  final double? gainLossPct;
  final List<Lot> lots;
}

/// Synthèse du portefeuille.
class PortfolioSummary {
  const PortfolioSummary({
    this.totalCostFcfa,
    this.totalValueFcfa,
    this.gainLossPct,
    this.positionsCount,
    this.lotsCount,
  });

  factory PortfolioSummary.fromJson(Map<String, dynamic> json) =>
      PortfolioSummary(
        totalCostFcfa: asDouble(json['total_cost_fcfa']),
        totalValueFcfa: asDouble(json['total_value_fcfa']),
        gainLossPct: asDouble(json['gain_loss_pct']),
        positionsCount: asInt(json['positions_count']),
        lotsCount: asInt(json['lots_count']),
      );

  final double? totalCostFcfa;
  final double? totalValueFcfa;
  final double? gainLossPct;
  final int? positionsCount;
  final int? lotsCount;
}

class PortfolioData {
  const PortfolioData({required this.summary, required this.positions});

  factory PortfolioData.fromJson(Map<String, dynamic> json) => PortfolioData(
        summary: PortfolioSummary.fromJson(asMap(json['summary'])),
        positions: asMapList(json['positions'])
            .map(Position.fromJson)
            .where((p) => p.symbol.isNotEmpty)
            .toList(),
      );

  final PortfolioSummary summary;
  final List<Position> positions;
}
