import 'package:brvm_mobile/features/market/stock_detail_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('SymbolDetail.fromJson', () {
    test('toutes les sections présentes', () {
      final detail = SymbolDetail.fromJson('NTLC', <String, dynamic>{
        'symbol': 'NTLC',
        'period': '3M',
        'quote': <String, dynamic>{
          'symbol': 'NTLC',
          'name': 'ONATEL',
          'cours_actuel': 6205.0,
          'cours_veille': 6150.0,
          'variation_pct': 0.89,
          'volume': 1234567.0,
          'capitalisation': 123456789012.0,
        },
        'history': <Map<String, dynamic>>[
          <String, dynamic>{'date': '2026-06-01', 'price': 6205.0},
          <String, dynamic>{'date': '2026-06-02', 'price': 6180.5},
        ],
        'profile': <String, dynamic>{
          'secteur': 'Télécommunications',
          'fondamentaux': <String, dynamic>{'per': 12.5, 'beta': 0.8},
        },
        'dividends': <String, dynamic>{
          'items': <Map<String, dynamic>>[
            <String, dynamic>{
              'company': 'ONATEL',
              'symbol': 'NTLC',
              'dividende': 150.0,
              'rendement': 2.4,
              'ex_dividende': '2026-05-10',
              'date_paiement': '2026-06-15',
            },
          ],
        },
        'news': <String, dynamic>{
          'items': <Map<String, dynamic>>[
            <String, dynamic>{
              'date': '2026-08-30',
              'title': 'ONATEL publie ses résultats',
              'url': 'https://example.com/news/1',
              'snippet': 'Le CA progresse de 8 %.',
            },
          ],
        },
        'prediction': <String, dynamic>{
          'company_name': 'ONATEL',
          'trend': 'HAUSSE',
          'confidence': 0.72,
          'technical_config': 'RSI neutre, MACD haussier.',
        },
        'score': <String, dynamic>{
          'day': '2026-09-03',
          'score': 72.5,
          'signal': 'BUY',
        },
      });

      expect(detail.symbol, 'NTLC');
      expect(detail.period, '3M');

      // Quote (ligne du palmarès).
      final quote = detail.quote!;
      expect(quote.symbol, 'NTLC');
      expect(quote.name, 'ONATEL');
      expect(quote.coursActuel, 6205.0);
      expect(quote.coursVeille, 6150.0);
      expect(quote.variationPct, 0.89);
      expect(quote.volume, 1234567.0);
      expect(quote.capitalisation, 123456789012.0);

      // Historique.
      expect(detail.history.error, isNull);
      expect(detail.history.points, hasLength(2));
      expect(detail.history.points.first.date, DateTime(2026, 6, 1));
      expect(detail.history.points.first.price, 6205.0);
      expect(detail.history.lastPrice, 6180.5);

      // Profil (dictionnaire arbitraire conservé tel quel).
      expect(detail.profileError, isNull);
      expect(detail.profile['secteur'], 'Télécommunications');
      expect(detail.companyName, 'ONATEL');

      // Dividendes.
      expect(detail.dividendsError, isNull);
      expect(detail.dividends, hasLength(1));
      final dividend = detail.dividends.single;
      expect(dividend.symbol, 'NTLC');
      expect(dividend.dividende, 150.0);
      expect(dividend.rendement, 2.4);
      expect(dividend.exDividende, '2026-05-10');
      expect(dividend.datePaiement, '2026-06-15');

      // Actualités.
      expect(detail.newsError, isNull);
      expect(detail.news, hasLength(1));
      final news = detail.news.single;
      expect(news.title, 'ONATEL publie ses résultats');
      expect(news.url, 'https://example.com/news/1');
      expect(news.snippet, 'Le CA progresse de 8 %.');

      // Prévision + score.
      final prediction = detail.prediction!;
      expect(prediction.companyName, 'ONATEL');
      expect(prediction.trend, 'HAUSSE');
      expect(prediction.confidence, 0.72);
      expect(prediction.technicalConfig, 'RSI neutre, MACD haussier.');

      final score = detail.score!;
      expect(score.day, DateTime(2026, 9, 3));
      expect(score.score, 72.5);
      expect(score.signal, 'BUY');
    });

    test('dégradation indépendante des sections en erreur', () {
      final detail = SymbolDetail.fromJson('NTLC', <String, dynamic>{
        'symbol': 'NTLC',
        'history': <String, dynamic>{'error': 'Historique indisponible.'},
        'profile': <String, dynamic>{'error': 'Fiche introuvable.'},
        'dividends': <String, dynamic>{'error': 'Timeout'},
        'news': <String, dynamic>{'error': 'Flux indisponible'},
        'prediction': <String, dynamic>{'error': 'modèle en cours'},
        'score': <String, dynamic>{},
      });

      expect(detail.history.error, 'Historique indisponible.');
      expect(detail.history.points, isEmpty);
      expect(detail.history.lastPrice, isNull);

      expect(detail.profileError, 'Fiche introuvable.');
      expect(detail.profile, isEmpty);

      expect(detail.dividendsError, 'Timeout');
      expect(detail.dividends, isEmpty);

      expect(detail.newsError, 'Flux indisponible');
      expect(detail.news, isEmpty);

      // Prévision en erreur → section cachée ; score vide → absent.
      expect(detail.prediction, isNull);
      expect(detail.score, isNull);
    });

    test('quote null (marché fermé) : repli sur le nom de la prédiction', () {
      final detail = SymbolDetail.fromJson('NTLC', <String, dynamic>{
        'symbol': 'NTLC',
        'quote': null,
        'history': <Map<String, dynamic>>[
          <String, dynamic>{'date': '2026-06-01', 'price': 6205.0},
        ],
        'prediction': <String, dynamic>{'company_name': 'ONATEL'},
      });

      expect(detail.quote, isNull);
      expect(detail.history.lastPrice, 6205.0);
      expect(detail.companyName, 'ONATEL');
    });

    test('quote {} et sections absentes : tout est toléré', () {
      final detail =
          SymbolDetail.fromJson('NTLC', <String, dynamic>{'quote': <String, dynamic>{}});

      expect(detail.quote, isNull);
      expect(detail.history.error, isNull);
      expect(detail.history.points, isEmpty);
      expect(detail.profile, isEmpty);
      expect(detail.dividends, isEmpty);
      expect(detail.news, isEmpty);
      expect(detail.prediction, isNull);
      expect(detail.score, isNull);
      expect(detail.companyName, isNull);
      // Le symbole demandé sert de repli quand la réponse n'en porte pas.
      expect(detail.symbol, 'NTLC');
    });

    test('historique : prix en chaîne française tolérés, points sans prix ignorés',
        () {
      final history = StockHistory.fromJson(<Map<String, dynamic>>[
        <String, dynamic>{'date': '2026-06-01', 'price': '6 205,5'},
        <String, dynamic>{'date': '2026-06-02'},
      ]);

      expect(history.error, isNull);
      expect(history.points, hasLength(1));
      expect(history.points.single.price, 6205.5);
    });

    test('dividendes/news acceptent aussi une liste brute', () {
      final detail = SymbolDetail.fromJson('NTLC', <String, dynamic>{
        'dividends': <Map<String, dynamic>>[
          <String, dynamic>{'symbol': 'NTLC', 'dividende': 150},
        ],
        'news': <Map<String, dynamic>>[
          <String, dynamic>{'title': 'Titre', 'url': 'https://example.com'},
        ],
      });

      expect(detail.dividendsError, isNull);
      expect(detail.dividends.single.dividende, 150.0);
      expect(detail.newsError, isNull);
      expect(detail.news.single.title, 'Titre');
    });
  });
}
