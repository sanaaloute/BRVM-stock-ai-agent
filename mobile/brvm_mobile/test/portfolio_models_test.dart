import 'package:brvm_mobile/features/portfolio/portfolio_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PortfolioData.fromJson (lots)', () {
    test('position avec 2 lots, current_price et gain_loss_pct nulls', () {
      final data = PortfolioData.fromJson(<String, dynamic>{
        'summary': <String, dynamic>{
          'total_cost_fcfa': 1000000.0,
          'total_value_fcfa': 1150000.0,
          'gain_loss_pct': 15.0,
          'positions_count': 1,
          'lots_count': 2,
        },
        'positions': <Map<String, dynamic>>[
          <String, dynamic>{
            'symbol': 'NTLC',
            'quantity': 25.0,
            'avg_buy_price': 40000.0,
            'total_cost': 1000000.0,
            'current_price': null,
            'gain_loss_pct': null,
            'lots': <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 1,
                'symbol': 'NTLC',
                'buy_price': 38000.0,
                'buy_date': '2026-01-15',
                'quantity': 10.0,
                'created_at': '2026-01-15T10:30:00',
              },
              <String, dynamic>{
                'id': 2,
                'symbol': 'NTLC',
                'buy_price': 42000.0,
                'buy_date': '2026-03-20',
                'quantity': 15.0,
                'created_at': '2026-03-20T14:00:00',
              },
            ],
          },
        ],
      });

      final summary = data.summary;
      expect(summary.totalCostFcfa, 1000000.0);
      expect(summary.totalValueFcfa, 1150000.0);
      expect(summary.gainLossPct, 15.0);
      expect(summary.positionsCount, 1);
      expect(summary.lotsCount, 2);

      expect(data.positions, hasLength(1));
      final position = data.positions.single;
      expect(position.symbol, 'NTLC');
      expect(position.quantity, 25.0);
      expect(position.avgBuyPrice, 40000.0);
      expect(position.totalCost, 1000000.0);
      expect(position.currentPrice, isNull);
      expect(position.gainLossPct, isNull);

      expect(position.lots, hasLength(2));
      final first = position.lots.first;
      expect(first.id, 1);
      expect(first.symbol, 'NTLC');
      expect(first.buyPrice, 38000.0);
      expect(first.buyDate, '2026-01-15');
      expect(first.quantity, 10.0);
      expect(first.invested, 380000.0);
      final second = position.lots.last;
      expect(second.id, 2);
      expect(second.buyPrice, 42000.0);
      expect(second.invested, 630000.0);
    });

    test('JSON minimal / sections manquantes', () {
      final data = PortfolioData.fromJson(<String, dynamic>{
        'summary': <String, dynamic>{},
        'positions': <Map<String, dynamic>>[
          <String, dynamic>{'symbol': 'ABJC'},
        ],
      });

      expect(data.summary.totalCostFcfa, isNull);
      expect(data.summary.lotsCount, isNull);
      final position = data.positions.single;
      expect(position.quantity, isNull);
      expect(position.avgBuyPrice, isNull);
      expect(position.currentPrice, isNull);
      expect(position.gainLossPct, isNull);
      expect(position.lots, isEmpty);
    });

    test('positions sans symbole filtrées', () {
      final data = PortfolioData.fromJson(<String, dynamic>{
        'positions': <Map<String, dynamic>>[
          <String, dynamic>{'symbol': ''},
          <String, dynamic>{'symbol': 'SONATEL'},
        ],
      });
      expect(data.positions, hasLength(1));
      expect(data.positions.single.symbol, 'SONATEL');
    });
  });
}
