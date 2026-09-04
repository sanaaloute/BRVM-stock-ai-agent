import '../../core/json_utils.dart';

/// Titre du palmarès (scrapé : toutes les clés sont optionnelles).
class PalmaresStock {
  const PalmaresStock({
    required this.symbol,
    this.name,
    this.coursActuel,
    this.coursVeille,
    this.variationPct,
    this.volume,
    this.capitalisation,
  });

  factory PalmaresStock.fromJson(Map<String, dynamic> json) => PalmaresStock(
        symbol: asString(json['symbol']) ?? asString(json['symbole']) ?? '',
        name: asString(json['name']) ?? asString(json['nom']),
        coursActuel: asDouble(json['cours_actuel']),
        coursVeille: asDouble(json['cours_veille']),
        variationPct: asDouble(json['variation_pct']) ?? asDouble(json['variation']),
        volume: asDouble(json['volume']),
        capitalisation: asDouble(json['capitalisation']),
      );

  final String symbol;
  final String? name;
  final double? coursActuel;
  final double? coursVeille;
  final double? variationPct;
  final double? volume;
  final double? capitalisation;
}

/// Extraction des entrées courtier depuis la section `brokers` de la
/// réponse : liste directe, ou enveloppe
/// `{"items"|"sgi"|"brokers": [...], "count": n, ...}`.
List<BrokerEntry> brokerEntriesFromSection(dynamic raw) {
  final items = raw is List
      ? asMapList(raw)
      : asMapList(asMap(raw)['items'] ?? asMap(raw)['sgi'] ?? asMap(raw)['brokers']);
  return items.map(BrokerEntry.fromJson).toList();
}

/// Courtier agréé (SGI), liste comme détail : toutes les clés sont
/// optionnelles et l'identifiant peut être absent sur les vieux payloads.
class BrokerEntry {
  const BrokerEntry({
    required this.raw,
    this.id,
    this.name,
    this.country,
    this.countryCode,
    this.phone,
    this.url,
    this.email,
    this.address,
    this.minAmount,
    this.note,
    this.otherCountries = const <String>[],
    this.info,
    this.detailText,
  });

  factory BrokerEntry.fromJson(Map<String, dynamic> json) {
    String? firstOf(List<String> keys) {
      for (final key in keys) {
        final value = asString(json[key]);
        if (value != null) return value;
      }
      return null;
    }

    List<String> countriesOf(dynamic value) {
      if (value is List) return asStringList(value);
      if (value is String) {
        // Tolère une chaîne « Sénégal, Côte d'Ivoire ».
        return value
            .split(',')
            .map((c) => c.trim())
            .where((c) => c.isNotEmpty)
            .toList();
      }
      return const <String>[];
    }

    return BrokerEntry(
      raw: json,
      id: asInt(json['id']),
      name: firstOf(const <String>[
        'name', 'nom', 'title', 'raison_sociale', 'denomination',
      ]),
      country: firstOf(const <String>['country', 'pays']),
      countryCode: firstOf(const <String>['country_code', 'pays_code']),
      phone: firstOf(const <String>[
        'phone', 'telephone', 'tel', 'contact', 'gsm',
      ]),
      url: firstOf(const <String>[
        'url', 'website', 'site', 'site_web', 'link', 'lien',
      ]),
      email: firstOf(const <String>['email', 'e-mail', 'courriel', 'mail']),
      address: firstOf(const <String>['address', 'adresse', 'siege']),
      minAmount: firstOf(const <String>['min_amount', 'montant_minimum']),
      note: firstOf(const <String>['note', 'remarque']),
      otherCountries: countriesOf(json['other_countries'] ?? json['autres_pays']),
      info: firstOf(const <String>['info', 'description']),
      detailText: firstOf(const <String>['detail_text', 'texte_detail']),
    );
  }

  final Map<String, dynamic> raw;
  final int? id;
  final String? name;
  final String? country;
  final String? countryCode;
  final String? phone;
  final String? url;
  final String? email;
  final String? address;
  final String? minAmount;
  final String? note;
  final List<String> otherCountries;
  final String? info;
  final String? detailText;
}

/// Actualité boursière.
class NewsItem {
  const NewsItem({
    required this.raw,
    this.title,
    this.date,
    this.source,
    this.summary,
    this.url,
  });

  factory NewsItem.fromJson(Map<String, dynamic> json) {
    String? firstOf(List<String> keys) {
      for (final key in keys) {
        final value = asString(json[key]);
        if (value != null) return value;
      }
      return null;
    }

    return NewsItem(
      raw: json,
      title: firstOf(const <String>['title', 'titre', 'headline']),
      date: firstOf(const <String>['date', 'published_at', 'pubdate']),
      source: firstOf(const <String>['source', 'origine']),
      summary: firstOf(const <String>[
        'snippet', 'summary', 'description', 'resume', 'résumé', 'excerpt',
      ]),
      url: firstOf(const <String>['url', 'link', 'lien']),
    );
  }

  final Map<String, dynamic> raw;
  final String? title;
  final String? date;
  final String? source;
  final String? summary;
  final String? url;
}

/// Flux d'actualités : items + avertissement éventuel (source de repli)
/// + erreur de section (les items peuvent être présents malgré tout).
class NewsFeed {
  const NewsFeed({
    this.items = const <NewsItem>[],
    this.warning,
    this.error,
  });

  /// Accepte les deux formes : liste directe ou
  /// `{"items": [...], "warning": ..., "error": ...}`.
  factory NewsFeed.fromSection(dynamic raw) {
    if (raw is List) {
      return NewsFeed(
        items: asMapList(raw).map(NewsItem.fromJson).toList(),
      );
    }
    final map = asMap(raw);
    return NewsFeed(
      items: asMapList(map['items']).map(NewsItem.fromJson).toList(),
      warning: asString(map['warning']),
      error: asString(map['error']),
    );
  }

  final List<NewsItem> items;
  final String? warning;
  final String? error;
}

/// Article complet lu dans l'application (GET /news/article).
class NewsArticle {
  const NewsArticle({this.title, this.date, this.url, this.text});

  factory NewsArticle.fromJson(Map<String, dynamic> json) => NewsArticle(
        title: asString(json['title']),
        date: asString(json['date']),
        url: asString(json['url']),
        text: asString(json['text']),
      );

  final String? title;
  final String? date;
  final String? url;
  final String? text;
}
