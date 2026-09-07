import 'package:brvm_mobile/features/predictions/predictions_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PredictionsFeed.fromJson', () {
    test('enveloppe complète du contrat (jour + liste triée)', () {
      final feed = PredictionsFeed.fromJson(<String, dynamic>{
        'day': '2026-09-07',
        'predictions': <Map<String, dynamic>>[
          <String, dynamic>{
            'symbol': 'NTLC',
            'name': 'Nestlé CI',
            'price': 1234.0,
            'direction': 'hausse',
            'confidence_pct': 78.0,
            'expected_move_pct': 2.4,
            'score': 66.5,
            'signal': 'Achat',
          },
          <String, dynamic>{
            'symbol': 'SGBC',
            'direction': 'baisse',
            'confidence_pct': 61,
          },
        ],
      });

      expect(feed.day, DateTime(2026, 9, 7));
      expect(feed.predictions, hasLength(2));
      final first = feed.predictions.first;
      expect(first.symbol, 'NTLC');
      expect(first.name, 'Nestlé CI');
      expect(first.price, 1234.0);
      expect(first.direction, 'hausse');
      expect(first.confidencePct, 78.0);
      expect(first.expectedMovePct, 2.4);
      expect(first.score, 66.5);
      expect(first.signal, 'Achat');
      expect(feed.predictions.last.confidencePct, 61.0);
    });

    test('pas encore calculé : day null + liste vide', () {
      final feed = PredictionsFeed.fromJson(<String, dynamic>{
        'day': null,
        'predictions': <Map<String, dynamic>>[],
      });
      expect(feed.day, isNull);
      expect(feed.predictions, isEmpty);
    });

    test('réponse vide ou partielle tolérée', () {
      final feed = PredictionsFeed.fromJson(<String, dynamic>{});
      expect(feed.day, isNull);
      expect(feed.predictions, isEmpty);

      // Entrées sans symbole filtrées, direction normalisée.
      final messy = PredictionsFeed.fromJson(<String, dynamic>{
        'day': '',
        'predictions': <Map<String, dynamic>>[
          <String, dynamic>{'name': 'Sans symbole'},
          <String, dynamic>{'symbol': 'TTLC', 'direction': 'HAUSSE'},
        ],
      });
      expect(messy.day, isNull);
      expect(messy.predictions, hasLength(1));
      expect(messy.predictions.single.direction, 'hausse');
    });
  });

  group('StockPrediction.fromJson', () {
    test('détail complet (cibles, explication, métriques)', () {
      final prediction = StockPrediction.fromJson(<String, dynamic>{
        'symbol': 'NTLC',
        'name': 'Nestlé CI',
        'price': 1234.0,
        'direction': 'neutre',
        'confidence_pct': 55.0,
        'expected_move_pct': 1.1,
        'score': 50.0,
        'signal': 'Conserver',
        'day': '2026-09-07',
        'target_low': 1220.4,
        'target_high': 1247.6,
        'explanation': 'Tendance stable.\nSupports proches.',
        'details': <String, dynamic>{'rsi14': 52.3},
      });

      expect(prediction.symbol, 'NTLC');
      expect(prediction.direction, 'neutre');
      expect(prediction.day, DateTime(2026, 9, 7));
      expect(prediction.targetLow, 1220.4);
      expect(prediction.targetHigh, 1247.6);
      expect(prediction.explanation, contains('Tendance stable.'));
      expect(prediction.details, isNotNull);
      expect(prediction.details!['rsi14'], 52.3);
    });

    test('clés optionnelles absentes tolérées', () {
      final minimal = StockPrediction.fromJson(
          <String, dynamic>{'symbol': 'SNTS'});
      expect(minimal.symbol, 'SNTS');
      expect(minimal.name, isNull);
      expect(minimal.price, isNull);
      expect(minimal.direction, isNull);
      expect(minimal.confidencePct, isNull);
      expect(minimal.expectedMovePct, isNull);
      expect(minimal.score, isNull);
      expect(minimal.signal, isNull);
      expect(minimal.day, isNull);
      expect(minimal.targetLow, isNull);
      expect(minimal.targetHigh, isNull);
      expect(minimal.explanation, isNull);
      // details absent ou vide → null (pas de carte vide).
      expect(minimal.details, isNull);

      final emptyDetails = StockPrediction.fromJson(<String, dynamic>{
        'symbol': 'SNTS',
        'details': <String, dynamic>{},
      });
      expect(emptyDetails.details, isNull);
    });
  });
}
