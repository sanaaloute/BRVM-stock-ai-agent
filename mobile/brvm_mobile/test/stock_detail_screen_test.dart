import 'package:brvm_mobile/features/market/stock_detail_models.dart';
import 'package:brvm_mobile/features/market/stock_detail_providers.dart';
import 'package:brvm_mobile/features/market/stock_detail_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

/// Fiche volontairement « sale » : champs internes (source_url, phone,
/// address, fetched_at, peers) encore présents — l'UI ne doit jamais les
/// afficher, même si le backend les laisse passer.
Map<String, dynamic> _detailJson() => <String, dynamic>{
      'symbol': 'SNTS',
      'period': '3M',
      'quote': <String, dynamic>{
        'symbol': 'SNTS',
        'name': 'SONATEL',
        'cours_actuel': 36980.0,
        'variation_pct': 7.5,
      },
      'history': <String, dynamic>{'error': 'Hors test.'},
      'profile': <String, dynamic>{
        'symbol': 'SNTS',
        'source_url': 'https://www.sikafinance.com/marches/societe/SNTS.sn',
        'company_name': 'SONATEL',
        'code': 'SN0000000019 - SNTS',
        'presentation': 'Résumé réécrit par le backend.',
        'phone': '(+221) 33-839-12-00',
        'address': '6 Rue WAGANE DIOUF, Sénégal',
        'dirigeants':
            'Président du Conseil : Alioune NDIAYE Directeur Général : Brelotte BA',
        'nombre_titres': '100 000 000',
        'shareholders': <Map<String, dynamic>>[
          <String, dynamic>{'name': 'ORANGE', 'pct': '42,33'},
        ],
        'performance': <String, dynamic>{
          'chiffre_affaires': <String, dynamic>{
            '2024': '1 776 443',
            '2025': '1 923 122',
          },
        },
        'market': <String, dynamic>{
          'beta_1an': 1.31,
          'fetched_at': '2026-08-22T23:03:33+00:00',
          'ranges': <String, dynamic>{
            '1_semaine': <String, dynamic>{
              'plus_haut': 36980.0,
              'plus_bas': 31900.0,
              'variation_pct': 15.92,
            },
          },
          'dividend_history': <Map<String, dynamic>>[
            <String, dynamic>{
              'year': 2025,
              'montant': 1740.0,
              'rendement_pct': 7.25,
            },
          ],
        },
        'technical_analysis': <String, dynamic>{
          'signals': <Map<String, dynamic>>[
            <String, dynamic>{
              'group': 'tendance',
              'direction': 'up',
              'text':
                  'Les cours évoluent au-dessus de leur moyenne mobile à 20 jours.',
            },
            <String, dynamic>{
              'group': 'tendance',
              'direction': 'up',
              'text': 'Texte brut source à ne pas afficher.',
            },
            <String, dynamic>{
              'group': 'momentum',
              'direction': 'down',
              'text': 'Texte brut source à ne pas afficher.',
            },
          ],
          'fetched_at': '2026-08-22T23:03:33+00:00',
        },
        'sector': <String, dynamic>{
          'name': 'TELECOMMUNICATIONS',
          'peers': <Map<String, dynamic>>[
            <String, dynamic>{'symbol': 'ONTBF', 'name': 'ONATEL BF'},
          ],
          'fetched_at': '2026-08-22T23:03:16+00:00',
        },
      },
      'dividends': <String, dynamic>{'items': <Map<String, dynamic>>[]},
      'news': <String, dynamic>{'items': <Map<String, dynamic>>[]},
    };

void main() {
  setUpAll(() async => initializeDateFormatting('fr_FR'));

  testWidgets(
      'fiche : cartes séparées, tableaux structurés, aucun champ brut ni interne',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 6000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final detail = SymbolDetail.fromJson('SNTS', _detailJson());
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          stockDetailProvider.overrideWith((ref, symbol) async => detail),
          stockHistoryProvider.overrideWith(
            (ref, record) async => const StockHistory(error: 'Hors test.'),
          ),
        ],
        child: const MaterialApp(home: StockDetailScreen(symbol: 'SNTS')),
      ),
    );
    await tester.pumpAndSettle();

    // Trois cartes distinctes (plus de « Profil & Fondamentaux » fusionné).
    expect(find.text('Profil'), findsOneWidget);
    expect(find.text('Fondamentaux'), findsOneWidget);
    expect(find.text('Analyse technique'), findsOneWidget);
    expect(find.text('Profil & Fondamentaux'), findsNothing);

    // Champs internes jamais affichés.
    expect(find.textContaining('sikafinance.com'), findsNothing);
    expect(find.textContaining('33-839-12-00'), findsNothing);
    expect(find.textContaining('WAGANE'), findsNothing);
    expect(find.textContaining('2026-08-22'), findsNothing);
    expect(find.textContaining('ONTBF'), findsNothing);
    expect(find.textContaining('fetched_at'), findsNothing);
    // Aucune structure JSON brute.
    expect(find.textContaining('[{'), findsNothing);
    expect(find.textContaining('{name:'), findsNothing);

    // Profil : présentation réécrite + mention IA, direction, actionnaires.
    expect(find.text('Résumé réécrit par le backend.'), findsOneWidget);
    expect(
      find.text("Résumé rédigé par l'IA à partir de données publiques."),
      findsOneWidget,
    );
    expect(find.text('Direction'), findsOneWidget);
    expect(find.text('Président du Conseil'), findsOneWidget);
    expect(find.text('Alioune NDIAYE'), findsOneWidget);
    expect(find.text('Principaux actionnaires'), findsOneWidget);
    expect(find.text('ORANGE'), findsOneWidget);
    expect(find.text('42,33 %'), findsOneWidget);

    // Fondamentaux : tableau de performance, indicateurs, fourchettes,
    // dividendes annuels.
    expect(find.text('Performance financière'), findsOneWidget);
    expect(find.text("Chiffre d'affaires (MFCFA)"), findsOneWidget);
    expect(find.text('1 923 122'), findsOneWidget);
    expect(find.text('Indicateurs de marché'), findsOneWidget);
    expect(find.text('Bêta (1 an)'), findsOneWidget);
    expect(find.text('Fourchettes de cours'), findsOneWidget);
    expect(find.text('1 semaine'), findsOneWidget);
    expect(find.text('Dividendes par exercice'), findsOneWidget);
    expect(find.text('7,25 %'), findsOneWidget);

    // Analyse technique : synthèse, pas les textes sources.
    expect(find.text('Lecture globale'), findsOneWidget);
    expect(find.text('2 haussiers'), findsOneWidget);
    expect(find.text('1 baissier'), findsOneWidget);
    expect(find.text('Par famille de signaux'), findsOneWidget);
    expect(find.text('Haussier · 2/2'), findsOneWidget);
    expect(find.textContaining('moyenne mobile'), findsNothing);
    expect(find.textContaining('Texte brut source'), findsNothing);
  });
}
