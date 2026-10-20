import '../../core/json_utils.dart';

/// Lot d'achat : une ligne d'achat unitaire du portefeuille.
class Lot {
  const Lot({
    this.id,
    required this.symbol,
    this.sgi = 'Non affecté',
    this.buyPrice,
    this.buyDate,
    this.quantity,
  });

  factory Lot.fromJson(Map<String, dynamic> json) => Lot(
    id: asInt(json['id']),
    symbol: asString(json['symbol']) ?? '',
    sgi: asString(json['sgi']) ?? 'Non affecté',
    buyPrice: asDouble(json['buy_price']),
    buyDate: asString(json['buy_date']),
    quantity: asDouble(json['quantity']),
  );

  final int? id;
  final String symbol;
  final String sgi;
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
    this.sgi = 'Non affecté',
    this.quantity,
    this.avgBuyPrice,
    this.totalCost,
    this.currentPrice,
    this.currentValueFcfa,
    this.gainLossFcfa,
    this.gainLossPct,
    this.lots = const <Lot>[],
  });

  factory Position.fromJson(Map<String, dynamic> json) => Position(
    symbol: asString(json['symbol']) ?? '',
    sgi: asString(json['sgi']) ?? 'Non affecté',
    quantity: asDouble(json['quantity']),
    avgBuyPrice: asDouble(json['avg_buy_price']),
    totalCost: asDouble(json['total_cost']),
    currentPrice: asDouble(json['current_price']),
    currentValueFcfa: asDouble(json['current_value_fcfa']),
    gainLossFcfa: asDouble(json['gain_loss_fcfa']),
    gainLossPct: asDouble(json['gain_loss_pct']),
    lots: asMapList(json['lots']).map(Lot.fromJson).toList(),
  );

  final String symbol;
  final String sgi;
  final double? quantity;
  final double? avgBuyPrice;
  final double? totalCost;
  final double? currentPrice;
  final double? currentValueFcfa;
  final double? gainLossFcfa;
  final double? gainLossPct;
  final List<Lot> lots;
}

/// Synthèse du portefeuille.
class PortfolioSummary {
  const PortfolioSummary({
    this.totalCostFcfa,
    this.totalValueFcfa,
    this.gainLossFcfa,
    this.gainLossPct,
    this.dividendsFcfa,
    this.totalGainLossFcfa,
    this.totalGainLossPct,
    this.positionsCount,
    this.lotsCount,
  });

  factory PortfolioSummary.fromJson(Map<String, dynamic> json) =>
      PortfolioSummary(
        totalCostFcfa: asDouble(json['total_cost_fcfa']),
        totalValueFcfa: asDouble(json['total_value_fcfa']),
        gainLossFcfa: asDouble(json['gain_loss_fcfa']),
        gainLossPct: asDouble(json['gain_loss_pct']),
        dividendsFcfa: asDouble(json['dividends_fcfa']),
        totalGainLossFcfa: asDouble(json['total_gain_loss_fcfa']),
        totalGainLossPct: asDouble(json['total_gain_loss_pct']),
        positionsCount: asInt(json['positions_count']),
        lotsCount: asInt(json['lots_count']),
      );

  final double? totalCostFcfa;
  final double? totalValueFcfa;
  final double? gainLossFcfa;
  final double? gainLossPct;
  final double? dividendsFcfa;
  final double? totalGainLossFcfa;
  final double? totalGainLossPct;
  final int? positionsCount;
  final int? lotsCount;
}

class SgiSummary {
  const SgiSummary({
    required this.sgi,
    required this.positionsCount,
    required this.quantity,
    required this.totalCostFcfa,
    required this.currentValueFcfa,
    required this.gainLossFcfa,
    required this.gainLossPct,
    required this.dividendsFcfa,
  });

  factory SgiSummary.fromJson(Map<String, dynamic> json) => SgiSummary(
    sgi: asString(json['sgi']) ?? 'Non affecté',
    positionsCount: asInt(json['positions_count']) ?? 0,
    quantity: asDouble(json['quantity']) ?? 0,
    totalCostFcfa: asDouble(json['total_cost_fcfa']),
    currentValueFcfa: asDouble(json['current_value_fcfa']),
    gainLossFcfa: asDouble(json['gain_loss_fcfa']),
    gainLossPct: asDouble(json['gain_loss_pct']),
    dividendsFcfa: asDouble(json['dividends_fcfa']) ?? 0,
  );

  final String sgi;
  final int positionsCount;
  final double quantity;
  final double? totalCostFcfa;
  final double? currentValueFcfa;
  final double? gainLossFcfa;
  final double? gainLossPct;
  final double dividendsFcfa;
}

class PortfolioData {
  const PortfolioData({
    required this.summary,
    required this.positions,
    required this.sgiBreakdown,
  });

  factory PortfolioData.fromJson(Map<String, dynamic> json) => PortfolioData(
    summary: PortfolioSummary.fromJson(asMap(json['summary'])),
    positions: asMapList(
      json['positions'],
    ).map(Position.fromJson).where((p) => p.symbol.isNotEmpty).toList(),
    sgiBreakdown: asMapList(
      json['sgi_breakdown'],
    ).map(SgiSummary.fromJson).toList(),
  );

  final PortfolioSummary summary;
  final List<Position> positions;
  final List<SgiSummary> sgiBreakdown;
}

class SgiTransaction {
  const SgiTransaction({
    required this.symbol,
    required this.side,
    required this.date,
    required this.quantity,
    required this.price,
    this.amount,
    this.sgi = 'Non affecté',
  });

  factory SgiTransaction.fromJson(Map<String, dynamic> json) => SgiTransaction(
    symbol: asString(json['symbol']) ?? '',
    side: asString(json['side']) ?? 'buy',
    date: asString(json['date']) ?? '',
    quantity: asDouble(json['quantity']) ?? 0,
    price: asDouble(json['price']) ?? 0,
    amount: asDouble(json['amount']),
    sgi: asString(json['sgi']) ?? 'Non affecté',
  );

  final String symbol;
  final String side;
  final String date;
  final double quantity;
  final double price;
  final double? amount;
  final String sgi;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'symbol': symbol,
    'side': side,
    'date': date,
    'quantity': quantity,
    'price': price,
    'amount': amount,
    'sgi': sgi,
  };

  String get sideLabel {
    if (side == 'sell') return 'Vente';
    if (side == 'dividend') return 'Dividende';
    return 'Achat';
  }
}

class SgiImportPreview {
  const SgiImportPreview({
    required this.contentHash,
    required this.transactions,
    required this.warnings,
  });

  factory SgiImportPreview.fromJson(Map<String, dynamic> json) =>
      SgiImportPreview(
        contentHash: asString(json['content_hash']) ?? '',
        transactions: asMapList(
          json['transactions'],
        ).map(SgiTransaction.fromJson).toList(),
        warnings: (json['warnings'] as List<dynamic>? ?? const <dynamic>[])
            .map((warning) => warning.toString())
            .toList(),
      );

  final String contentHash;
  final List<SgiTransaction> transactions;
  final List<String> warnings;
}

class PortfolioHistoryPoint {
  const PortfolioHistoryPoint({
    required this.day,
    required this.totalCostFcfa,
    required this.totalValueFcfa,
    required this.gainLossFcfa,
    required this.gainLossPct,
    required this.dividendsFcfa,
  });

  factory PortfolioHistoryPoint.fromJson(Map<String, dynamic> json) =>
      PortfolioHistoryPoint(
        day: DateTime.tryParse(asString(json['day']) ?? ''),
        totalCostFcfa: asDouble(json['total_cost_fcfa']),
        totalValueFcfa: asDouble(json['total_value_fcfa']),
        gainLossFcfa: asDouble(json['gain_loss_fcfa']),
        gainLossPct: asDouble(json['gain_loss_pct']),
        dividendsFcfa: asDouble(json['dividends_fcfa']) ?? 0,
      );

  final DateTime? day;
  final double? totalCostFcfa;
  final double? totalValueFcfa;
  final double? gainLossFcfa;
  final double? gainLossPct;
  final double dividendsFcfa;
}
