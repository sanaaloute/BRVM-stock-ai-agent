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

  group('SGI import, amounts, and history models', () {
    test('parses gain/loss amounts and history points', () {
      final data = PortfolioData.fromJson(<String, dynamic>{
        'summary': <String, dynamic>{
          'total_cost_fcfa': 100000.0,
          'total_value_fcfa': 112000.0,
          'gain_loss_fcfa': 12000.0,
          'gain_loss_pct': 12.0,
          'dividends_fcfa': 2000.0,
          'total_gain_loss_fcfa': 14000.0,
          'total_gain_loss_pct': 14.0,
        },
        'positions': <Map<String, dynamic>>[
          <String, dynamic>{
            'symbol': 'NTLC',
            'current_price': 56000.0,
            'current_value_fcfa': 112000.0,
            'gain_loss_fcfa': 12000.0,
            'gain_loss_pct': 12.0,
          },
        ],
      });
      expect(data.summary.gainLossFcfa, 12000.0);
      expect(data.summary.dividendsFcfa, 2000.0);
      expect(data.summary.totalGainLossFcfa, 14000.0);
      expect(data.summary.totalGainLossPct, 14.0);
      expect(data.positions.single.currentValueFcfa, 112000.0);
      expect(data.positions.single.gainLossFcfa, 12000.0);

      final point = PortfolioHistoryPoint.fromJson(<String, dynamic>{
        'day': '2026-03-01',
        'total_cost_fcfa': 100000.0,
        'total_value_fcfa': 112000.0,
        'gain_loss_fcfa': 12000.0,
        'gain_loss_pct': 12.0,
      });
      expect(point.day, DateTime(2026, 3, 1));
      expect(point.totalValueFcfa, 112000.0);
      expect(point.gainLossFcfa, 12000.0);
    });

    test('parses SGI import preview and serializes transactions', () {
      final preview = SgiImportPreview.fromJson(<String, dynamic>{
        'content_hash': 'a' * 64,
        'transactions': <Map<String, dynamic>>[
          <String, dynamic>{
            'symbol': 'NTLC',
            'side': 'sell',
            'date': '2026-02-01',
            'quantity': 3.0,
            'price': 52000.0,
          },
        ],
        'warnings': <String>['warning'],
      });
      expect(preview.contentHash, hasLength(64));
      expect(preview.warnings, <String>['warning']);
      expect(preview.transactions.single.sideLabel, 'Vente');
      expect(preview.transactions.single.toJson()['side'], 'sell');
    });

    test('parses SGI breakdown and dividend history', () {
      final data = PortfolioData.fromJson(<String, dynamic>{
        'summary': <String, dynamic>{},
        'positions': <Map<String, dynamic>>[],
        'sgi_breakdown': <Map<String, dynamic>>[
          <String, dynamic>{
            'sgi': 'PHOENIX CAPITAL MANAGEMENT',
            'positions_count': 2,
            'quantity': 12.5,
            'total_cost_fcfa': 100000.0,
            'current_value_fcfa': 112000.0,
            'gain_loss_fcfa': 12000.0,
            'gain_loss_pct': 12.0,
            'dividends_fcfa': 5000.0,
          },
        ],
      });
      final summary = data.sgiBreakdown.single;
      expect(summary.positionsCount, 2);
      expect(summary.quantity, 12.5);
      expect(summary.currentValueFcfa, 112000.0);
      expect(summary.dividendsFcfa, 5000.0);

      final point = PortfolioHistoryPoint.fromJson(<String, dynamic>{
        'day': '2026-03-01',
        'total_cost_fcfa': 100000.0,
        'total_value_fcfa': 112000.0,
        'gain_loss_fcfa': 12000.0,
        'gain_loss_pct': 12.0,
        'dividends_fcfa': 5000.0,
      });
      expect(point.dividendsFcfa, 5000.0);

      final transaction = SgiTransaction.fromJson(<String, dynamic>{
        'symbol': 'NTLC',
        'side': 'dividend',
        'date': '2026-02-15',
        'quantity': 0,
        'price': 0,
        'amount': 5000.0,
        'sgi': 'PHOENIX CAPITAL MANAGEMENT',
      });
      expect(transaction.sideLabel, 'Dividende');
      expect(transaction.amount, 5000.0);
      expect(transaction.sgi, 'PHOENIX CAPITAL MANAGEMENT');
    });
  });
}
