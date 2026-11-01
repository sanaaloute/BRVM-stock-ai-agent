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
            _asTechnicalConfig(json['technical_config'] ?? json['config']),
      );

  final String? companyName;
  final String? trend;
  final double? confidence;
  final String? technicalConfig;
}

/// Le backend envoie `technical_config` comme liste de chaînes
/// (app/scrapers/richbourse_prediction.py) ; tolère aussi une chaîne simple.
String? _asTechnicalConfig(dynamic value) {
  final items = asStringList(value);
  if (items.isNotEmpty) return items.join('\n');
  return asString(value);
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

/// Actionnaire principal (pourcentage brut tel que publié, ex. « 61,39 »).
class Shareholder {
  const Shareholder({this.name, this.pct});

  factory Shareholder.fromJson(Map<String, dynamic> json) => Shareholder(
        name: asString(json['name']),
        pct: asString(json['pct']),
      );

  final String? name;
  final String? pct;
}

/// Une métrique du tableau de performance, par année (« 2024 » → « 7,87 »).
class PerformanceRow {
  const PerformanceRow({
    required this.key,
    required this.label,
    required this.byYear,
  });

  final String key;
  final String label;
  final Map<String, String> byYear;
}

/// Tableau de performance financière : années en colonnes, métriques en
/// lignes (ordre canonique CA → dividende, métriques inconnues à la fin).
class PerformanceTable {
  const PerformanceTable({required this.years, required this.rows});

  factory PerformanceTable.fromJson(Map<String, dynamic> json) {
    final years = <String>{};
    final rawRows = <String, Map<String, String>>{};
    for (final entry in json.entries) {
      final byYear = <String, String>{};
      for (final y in asMap(entry.value).entries) {
        final value = asString(y.value);
        if (value == null) continue;
        byYear[y.key] = value;
        years.add(y.key);
      }
      if (byYear.isNotEmpty) rawRows[entry.key] = byYear;
    }
    final sortedYears = years.toList()..sort();
    final orderedKeys = <String>[
      ..._performanceLabels.keys.where(rawRows.containsKey),
      ...rawRows.keys.where((k) => !_performanceLabels.containsKey(k)),
    ];
    final rows = <PerformanceRow>[
      for (final key in orderedKeys)
        PerformanceRow(
          key: key,
          label: _performanceLabels[key] ?? _humanize(key),
          byYear: rawRows[key]!,
        ),
    ];
    return PerformanceTable(years: sortedYears, rows: rows);
  }

  final List<String> years;
  final List<PerformanceRow> rows;

  bool get isEmpty => years.isEmpty || rows.isEmpty;

  static const _performanceLabels = <String, String>{
    'chiffre_affaires': "Chiffre d'affaires (MFCFA)",
    'croissance_ca': 'Croissance du CA',
    'resultat_net': 'Résultat net (MFCFA)',
    'croissance_rn': 'Croissance du RN',
    'bnpa': 'BNPA (FCFA)',
    'per': 'PER',
    'dividende': 'Dividende (FCFA)',
  };
}

/// Séance du jour (bloc `market.day`).
class DaySession {
  const DaySession({this.open, this.high, this.low, this.volume});

  factory DaySession.fromJson(Map<String, dynamic> json) => DaySession(
        open: asDouble(json['ouverture']),
        high: asDouble(json['plus_haut']),
        low: asDouble(json['plus_bas']),
        volume: asDouble(json['volume_titres']),
      );

  final double? open;
  final double? high;
  final double? low;
  final double? volume;

  bool get isEmpty => open == null && high == null && low == null && volume == null;
}

/// Indicateurs de marché du bloc `market` (hors fourchettes et dividendes).
class MarketIndicators {
  const MarketIndicators({
    this.beta1an,
    this.rsi14,
    this.capitalEchangePct,
    this.valorisationMillions,
    this.day,
  });

  factory MarketIndicators.fromJson(Map<String, dynamic> json) {
    final day = DaySession.fromJson(asMap(json['day']));
    return MarketIndicators(
      beta1an: asDouble(json['beta_1an']),
      rsi14: asDouble(json['rsi_14']),
      capitalEchangePct: asDouble(json['capital_echange_pct']),
      valorisationMillions: asDouble(json['valorisation_millions']),
      day: day.isEmpty ? null : day,
    );
  }

  final double? beta1an;
  final double? rsi14;
  final double? capitalEchangePct;
  final double? valorisationMillions;
  final DaySession? day;

  bool get isEmpty =>
      beta1an == null &&
      rsi14 == null &&
      capitalEchangePct == null &&
      valorisationMillions == null &&
      day == null;
}

/// Fourchette de cours sur une période (« 1 an », « 5 ans »…).
class PriceRange {
  const PriceRange({required this.label, this.high, this.low, this.variationPct});

  final String label;
  final double? high;
  final double? low;
  final double? variationPct;
}

/// Dividende annuel du bloc `market.dividend_history`.
class DividendYear {
  const DividendYear({this.year, this.montant, this.rendementPct});

  factory DividendYear.fromJson(Map<String, dynamic> json) => DividendYear(
        year: asInt(json['year']),
        montant: asDouble(json['montant']),
        rendementPct: asDouble(json['rendement_pct']),
      );

  final int? year;
  final double? montant;
  final double? rendementPct;
}

/// Comptage des signaux d'un groupe (tendance, momentum…) — jamais le texte
/// source, qui n'est pas repris dans l'interface.
class SignalGroupSummary {
  const SignalGroupSummary({
    required this.label,
    required this.up,
    required this.down,
    required this.neutral,
  });

  final String label;
  final int up;
  final int down;
  final int neutral;

  int get total => up + down + neutral;

  /// Direction majoritaire du groupe : 'up', 'down' ou 'neutral' à égalité.
  String get majority {
    if (up > down && up > neutral) return 'up';
    if (down > up && down > neutral) return 'down';
    return 'neutral';
  }

  int get majorityCount {
    switch (majority) {
      case 'up':
        return up;
      case 'down':
        return down;
      default:
        return neutral;
    }
  }
}

/// Résumé agrégé des signaux techniques (les textes détaillés, repris d'une
/// source externe, sont volontairement remplacés par cette synthèse).
class TechnicalSummary {
  const TechnicalSummary({
    required this.up,
    required this.down,
    required this.neutral,
    required this.groups,
  });

  factory TechnicalSummary.fromJson(Map<String, dynamic> json) {
    final byGroup = <String, List<int>>{};
    for (final signal in asMapList(json['signals'])) {
      final key = asString(signal['group']) ?? 'autres';
      final counters = byGroup.putIfAbsent(key, () => <int>[0, 0, 0]);
      switch (asString(signal['direction'])) {
        case 'up':
          counters[0]++;
        case 'down':
          counters[1]++;
        default:
          counters[2]++;
      }
    }
    var up = 0, down = 0, neutral = 0;
    final orderedKeys = <String>[
      ..._groupLabels.keys.where(byGroup.containsKey),
      ...byGroup.keys.where((k) => !_groupLabels.containsKey(k)),
    ];
    final groups = <SignalGroupSummary>[
      for (final key in orderedKeys)
        SignalGroupSummary(
          label: _groupLabels[key] ?? _humanize(key),
          up: byGroup[key]![0],
          down: byGroup[key]![1],
          neutral: byGroup[key]![2],
        ),
    ];
    for (final g in groups) {
      up += g.up;
      down += g.down;
      neutral += g.neutral;
    }
    if (groups.isEmpty) {
      // Fiches anciennes : seuls les totaux sont présents.
      up = asInt(json['up']) ?? 0;
      down = asInt(json['down']) ?? 0;
      neutral = asInt(json['neutral']) ?? 0;
    }
    if (up + down + neutral == 0) {
      return const TechnicalSummary(up: 0, down: 0, neutral: 0, groups: []);
    }
    return TechnicalSummary(up: up, down: down, neutral: neutral, groups: groups);
  }

  final int up;
  final int down;
  final int neutral;
  final List<SignalGroupSummary> groups;

  int get total => up + down + neutral;

  bool get isEmpty => total == 0;

  /// Direction dominante de l'ensemble des signaux.
  String get majority {
    if (up > down && up > neutral) return 'up';
    if (down > up && down > neutral) return 'down';
    return 'neutral';
  }

  static const _groupLabels = <String, String>{
    'tendance': 'Tendance',
    'momentum': 'Momentum',
    'oscillateurs': 'Oscillateurs',
    'volumes_chandeliers': 'Volumes & chandeliers',
  };
}

String _humanize(String key) {
  final cleaned = key.replaceAll('_', ' ').trim();
  if (cleaned.isEmpty) return key;
  return cleaned[0].toUpperCase() + cleaned.substring(1);
}

/// Fiche société structurée pour l'affichage mobile. Les champs internes
/// (source, contact, dates de collecte, pairs) ont déjà été retirés par le
/// backend ; la présentation est le résumé réécrit par l'IA.
class CompanyProfile {
  const CompanyProfile({
    this.presentation,
    this.code,
    this.sectorName,
    this.dirigeants = const <({String role, String name})>[],
    this.nombreTitres,
    this.flottant,
    this.valorisation,
    this.shareholders = const <Shareholder>[],
    this.performance,
    this.market,
    this.ranges = const <PriceRange>[],
    this.dividendHistory = const <DividendYear>[],
    this.technical,
  });

  factory CompanyProfile.fromJson(Map<String, dynamic> json) {
    final performance = PerformanceTable.fromJson(asMap(json['performance']));
    final market = MarketIndicators.fromJson(asMap(json['market']));
    final technical = TechnicalSummary.fromJson(asMap(json['technical_analysis']));
    return CompanyProfile(
      presentation: asString(json['presentation']),
      code: asString(json['code']),
      sectorName: _titleCase(asString(asMap(json['sector'])['name'])),
      dirigeants: _parseDirigeants(asString(json['dirigeants'])),
      nombreTitres: asString(json['nombre_titres']),
      flottant: asString(json['flottant']),
      valorisation: asString(json['valorisation']),
      shareholders:
          asMapList(json['shareholders']).map(Shareholder.fromJson).toList(),
      performance: performance.isEmpty ? null : performance,
      market: market.isEmpty ? null : market,
      ranges: _parseRanges(asMap(json['market'])['ranges']),
      dividendHistory: asMapList(asMap(json['market'])['dividend_history'])
          .map(DividendYear.fromJson)
          .toList(),
      technical: technical.isEmpty ? null : technical,
    );
  }

  final String? presentation;
  final String? code;
  final String? sectorName;

  /// Dirigeants éclatés (rôle, nom) ; vide si le texte brut n'a pas pu
  /// être découpé (le libellé brut n'est alors pas affiché).
  final List<({String role, String name})> dirigeants;
  final String? nombreTitres;
  final String? flottant;
  final String? valorisation;
  final List<Shareholder> shareholders;
  final PerformanceTable? performance;
  final MarketIndicators? market;
  final List<PriceRange> ranges;
  final List<DividendYear> dividendHistory;
  final TechnicalSummary? technical;

  bool get hasIdentity =>
      presentation != null ||
      code != null ||
      sectorName != null ||
      dirigeants.isNotEmpty ||
      nombreTitres != null ||
      flottant != null ||
      valorisation != null ||
      shareholders.isNotEmpty;

  bool get hasFundamentals =>
      performance != null ||
      market != null ||
      ranges.isNotEmpty ||
      dividendHistory.isNotEmpty;

  bool get isEmpty => !hasIdentity && !hasFundamentals && technical == null;

  static const _rangeLabels = <String, String>{
    '1_semaine': '1 semaine',
    '1_mois': '1 mois',
    '1er_janvier': 'Depuis le 1er janv.',
    '1_an': '1 an',
    '3_ans': '3 ans',
    '5_ans': '5 ans',
  };

  static List<PriceRange> _parseRanges(dynamic raw) {
    final ranges = asMap(raw);
    return <PriceRange>[
      for (final key in _rangeLabels.keys)
        if (ranges[key] case final r?)
          PriceRange(
            label: _rangeLabels[key]!,
            high: asDouble(asMap(r)['plus_haut']),
            low: asDouble(asMap(r)['plus_bas']),
            variationPct: asDouble(asMap(r)['variation_pct']),
          ),
    ];
  }

  /// « Président : A NDIAYE Directeur Général : B BA » → liste (rôle, nom).
  /// Le scraper concatène tout sur une ligne ; on redécoupe devant chaque
  /// intitulé de fonction connu.
  static List<({String role, String name})> _parseDirigeants(String? raw) {
    if (raw == null || raw.isEmpty) return const [];
    final starts = RegExp(
      r'(?=(?:Présidente?|Directe(?:ur|rice)|Administrateur|Secrétaire|Commissaire)\b)',
    );
    final result = <({String role, String name})>[];
    for (final part in raw.split(starts)) {
      final trimmed = part.trim();
      if (trimmed.isEmpty) continue;
      final sep = trimmed.indexOf(' : ');
      if (sep <= 0) return const []; // format inattendu : mieux vaut masquer
      final role = trimmed.substring(0, sep).trim();
      final name = trimmed.substring(sep + 3).trim();
      if (role.isEmpty || name.isEmpty) return const [];
      result.add((role: role, name: name));
    }
    return result;
  }

  static String? _titleCase(String? value) {
    if (value == null || value.isEmpty) return null;
    if (value.toUpperCase() != value) return value;
    final lower = value.toLowerCase();
    return lower[0].toUpperCase() + lower.substring(1);
  }
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

  /// Fiche société (dictionnaire arbitraire, déjà assaini par le backend).
  final Map<String, dynamic> profile;
  final String? profileError;

  /// Fiche société structurée pour les cartes Profil / Fondamentaux /
  /// Analyse technique.
  CompanyProfile get companyProfile => CompanyProfile.fromJson(profile);

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
