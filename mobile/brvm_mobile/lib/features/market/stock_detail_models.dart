import '../../core/json_utils.dart';
import 'market_models.dart';

/// Point d'historique de cours : {date, price}.
class PricePoint {
  const PricePoint({this.date, this.price});

  factory PricePoint.fromJson(Map<String, dynamic> json) => PricePoint(
        date: DateTime.tryParse(asString(json['date']) ?? ''),
        price: asDouble(json['price']) ?? asDouble(json['cours']),
      );

  final DateTime? date;
  final double? price;
}

/// Historique de cours : liste de points, ou `error` si indisponible.
class StockHistory {
  const StockHistory({this.points = const <PricePoint>[], this.error});

  factory StockHistory.fromJson(dynamic json) {
    if (json is List) {
      return StockHistory(
        points: asMapList(json)
            .map(PricePoint.fromJson)
            .where((p) => p.price != null)
            .toList(),
      );
    }
    final map = asMap(json);
    return StockHistory(error: asString(map['error']));
  }

  final List<PricePoint> points;
  final String? error;

  bool get isEmpty => error != null || points.isEmpty;

  /// Dernier cours connu (utile quand le marché est fermé).
  double? get lastPrice => points.isEmpty ? null : points.last.price;
}

/// Ligne de dividende.
class DividendItem {
  const DividendItem({
    this.company,
    this.symbol,
    this.dividende,
    this.rendement,
    this.exDividende,
    this.datePaiement,
  });

  factory DividendItem.fromJson(Map<String, dynamic> json) => DividendItem(
        company: asString(json['company']) ?? asString(json['societe']),
        symbol: asString(json['symbol']) ?? asString(json['symbole']),
        dividende: asDouble(json['dividende']),
        rendement: asDouble(json['rendement']),
        exDividende: asString(json['ex_dividende']),
        datePaiement: asString(json['date_paiement']),
      );

  final String? company;
  final String? symbol;
  final double? dividende;
  final double? rendement;
  final String? exDividende;
  final String? datePaiement;
}

/// Actualité liée à un titre.
class StockNewsItem {
  const StockNewsItem({this.date, this.title, this.url, this.snippet});

  factory StockNewsItem.fromJson(Map<String, dynamic> json) => StockNewsItem(
        date: asString(json['date']) ?? asString(json['published_at']),
        title: asString(json['title']) ?? asString(json['titre']),
        url: asString(json['url']) ?? asString(json['link']),
        snippet: asString(json['snippet']) ?? asString(json['description']),
      );

  final String? date;
  final String? title;
  final String? url;
  final String? snippet;
}

/// Prévision technique (IA) : tendance, confiance, configuration.
class PredictionInfo {
  const PredictionInfo({
    this.companyName,
    this.trend,
    this.confidence,
    this.technicalConfig,
  });

  factory PredictionInfo.fromJson(Map<String, dynamic> json) =>
      PredictionInfo(
        companyName:
            asString(json['company_name']) ?? asString(json['company']),
        trend: asString(json['trend']) ?? asString(json['tendance']),
        confidence: asDouble(json['confidence']),
        technicalConfig:
            asString(json['technical_config']) ?? asString(json['config']),
      );

  final String? companyName;
  final String? trend;
  final double? confidence;
  final String? technicalConfig;
}

/// Score & signal du jour (0-100 + BUY/SELL/HOLD).
class AiScore {
  const AiScore({this.day, this.score, this.signal});

  factory AiScore.fromJson(Map<String, dynamic> json) => AiScore(
        day: DateTime.tryParse(asString(json['day']) ?? ''),
        score: asDouble(json['score']),
        signal: asString(json['signal']),
      );

  final DateTime? day;
  final double? score;
  final String? signal;
}

/// Réponse de `GET /mobile/v1/market/symbols/{symbol}`.
///
/// Chaque section se dégrade indépendamment : `quote` peut être null
/// (marché fermé), les sections en échec portent un `*Error` et une
/// liste vide.
class SymbolDetail {
  const SymbolDetail({
    required this.symbol,
    this.period = '3M',
    this.quote,
    this.history = const StockHistory(),
    this.profile = const <String, dynamic>{},
    this.profileError,
    this.dividends = const <DividendItem>[],
    this.dividendsError,
    this.news = const <StockNewsItem>[],
    this.newsError,
    this.prediction,
    this.score,
  });

  factory SymbolDetail.fromJson(String requestedSymbol, Map<String, dynamic> json) {
    String? sectionError(Map<String, dynamic> map) =>
        asString(map['error']) ?? asString(map['message']);

    // quote : ligne du palmarès, ou null quand le marché est fermé.
    final quoteMap = asMap(json['quote']);
    final quote = quoteMap.isEmpty ? null : PalmaresStock.fromJson(quoteMap);

    // profile : dictionnaire arbitraire, ou {"error": ...}.
    final profileMap = asMap(json['profile']);
    final profileError = sectionError(profileMap);
    final profile = profileError != null ? const <String, dynamic>{} : profileMap;

    // dividends / news : {"items": [...]} | [...] | {"error": ...}.
    (String?, List<Map<String, dynamic>>) itemsSection(dynamic raw) {
      if (raw is List) return (null, asMapList(raw));
      final map = asMap(raw);
      return (sectionError(map), asMapList(map['items']));
    }

    final (dividendsError, dividendMaps) = itemsSection(json['dividends']);
    final (newsError, newsMaps) = itemsSection(json['news']);

    // prediction : cachée en cas d'erreur ou d'absence.
    final predictionMap = asMap(json['prediction']);
    final prediction = predictionMap.isEmpty || sectionError(predictionMap) != null
        ? null
        : PredictionInfo.fromJson(predictionMap);

    // score : {} quand indisponible.
    final scoreMap = asMap(json['score']);
    final score = scoreMap.isEmpty ? null : AiScore.fromJson(scoreMap);

    return SymbolDetail(
      symbol: asString(json['symbol']) ?? requestedSymbol,
      period: asString(json['period']) ?? '3M',
      quote: quote,
      history: StockHistory.fromJson(json['history']),
      profile: profile,
      profileError: profileError,
      dividends: dividendMaps.map(DividendItem.fromJson).toList(),
      dividendsError: dividendsError,
      news: newsMaps.map(StockNewsItem.fromJson).toList(),
      newsError: newsError,
      prediction: prediction,
      score: score,
    );
  }

  final String symbol;
  final String period;

  /// Ligne du palmarès (null si marché fermé).
  final PalmaresStock? quote;

  /// Historique des cours (error si indisponible).
  final StockHistory history;

  /// Fiche société (dictionnaire arbitraire).
  final Map<String, dynamic> profile;
  final String? profileError;

  final List<DividendItem> dividends;
  final String? dividendsError;

  final List<StockNewsItem> news;
  final String? newsError;

  final PredictionInfo? prediction;
  final AiScore? score;

  /// Nom de la société : quote → profile → prédiction.
  String? get companyName {
    final fromQuote = quote?.name;
    if (fromQuote != null && fromQuote.isNotEmpty) return fromQuote;
    for (final key in const <String>['nom', 'name', 'raison_sociale', 'company']) {
      final value = asString(profile[key]);
      if (value != null && value.isNotEmpty) return value;
    }
    return prediction?.companyName;
  }
}
