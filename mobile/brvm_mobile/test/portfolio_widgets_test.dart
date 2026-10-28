import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/format.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/core/ui.dart';
import 'package:brvm_mobile/features/market/market_models.dart';
import 'package:brvm_mobile/features/market/market_providers.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_chart.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_import_dialog.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_models.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_providers.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_screen.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_sgi_chart.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeRepository extends PortfolioRepository {
  _FakeRepository({this._history, this.positions})
    : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final List<PortfolioHistoryPoint>? _history;
  final List<Position>? positions;

  @override
  Future<PortfolioData> get({String? sgi}) async {
    return PortfolioData(
      summary: const PortfolioSummary(
        totalCostFcfa: 660000,
        totalValueFcfa: 191100,
        gainLossFcfa: -468900,
        gainLossPct: -71.05,
        dividendsFcfa: 1000,
        totalGainLossFcfa: -467900,
        totalGainLossPct: -70.89,
        positionsCount: 2,
        lotsCount: 2,
      ),
      positions: positions ?? const <Position>[
        Position(
          symbol: 'NTLC',
          sgi: 'PHOENIX CAPITAL MANAGEMENT',
          quantity: 8,
          totalCost: 400000,
          currentValueFcfa: 117600,
          gainLossFcfa: -282400,
          gainLossPct: -70.6,
        ),
        Position(
          symbol: 'NTLC',
          sgi: 'BSIC Capital SA',
          quantity: 5,
          totalCost: 260000,
          currentValueFcfa: 73500,
          gainLossFcfa: -186500,
          gainLossPct: -71.73,
        ),
      ],
      sgiBreakdown: const <SgiSummary>[
        SgiSummary(
          sgi: 'PHOENIX CAPITAL MANAGEMENT',
          positionsCount: 1,
          quantity: 8,
          totalCostFcfa: 400000,
          currentValueFcfa: 117600,
          gainLossFcfa: -282400,
          gainLossPct: -70.6,
          dividendsFcfa: 1000,
        ),
        SgiSummary(
          sgi: 'BSIC Capital SA',
          positionsCount: 1,
          quantity: 5,
          totalCostFcfa: 260000,
          currentValueFcfa: 73500,
          gainLossFcfa: -186500,
          gainLossPct: -71.73,
          dividendsFcfa: 0,
        ),
      ],
    );
  }

  @override
  Future<List<PortfolioHistoryPoint>> getHistory(
    int days, {
    String? sgi,
  }) async {
    if (_history != null) return _history;
    return <PortfolioHistoryPoint>[
      PortfolioHistoryPoint(
        day: DateTime(2026, 1, 1),
        totalCostFcfa: 100000,
        totalValueFcfa: 100000,
        gainLossFcfa: 0,
        dividendsFcfa: 0,
        gainLossPct: 0,
      ),
      PortfolioHistoryPoint(
        day: DateTime(2026, 2, 1),
        totalCostFcfa: 100000,
        totalValueFcfa: 112000,
        gainLossFcfa: 12000,
        dividendsFcfa: 0,
        gainLossPct: 12,
      ),
    ];
  }
}

void main() {
  test('signed FCFA formatting includes amounts and signs', () {
    expect(formatSignedFcfa(12000), '+12\u202f000 FCFA');
    expect(formatSignedFcfa(-500), '-500 FCFA');
    expect(formatSignedFcfa(null), '—');
  });

  testWidgets('SGI import dialog explains preview and privacy', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: SgiImportDialog())),
    );
    expect(find.text('Importer un document SGI'), findsOneWidget);
    expect(find.textContaining('n’est pas conservé'), findsOneWidget);
    expect(find.text('Choisir le document'), findsOneWidget);
    expect(find.text('Annuler'), findsOneWidget);
  });

  testWidgets('portfolio history chart shows range and metric controls', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          portfolioRepositoryProvider.overrideWithValue(_FakeRepository()),
        ],
        child: const MaterialApp(home: PortfolioHistoryChart()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Évolution du portefeuille'), findsOneWidget);
    expect(find.text('1M'), findsOneWidget);
    expect(find.text('3M'), findsOneWidget);
    expect(find.text('6M'), findsOneWidget);
    expect(find.text('1A'), findsOneWidget);
    expect(find.text('Valeur'), findsOneWidget);
    expect(find.text('Gain/Perte'), findsOneWidget);
    expect(find.text('Dividendes'), findsOneWidget);
  });

  testWidgets('portfolio history chart date labels do not overlap', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 800);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    final points = List<PortfolioHistoryPoint>.generate(
      14,
      (index) => PortfolioHistoryPoint(
        day: DateTime(2026, 1, index + 1),
        totalCostFcfa: 100000,
        totalValueFcfa: 100000 + index * 1000,
        gainLossFcfa: index * 1000,
        dividendsFcfa: 0,
        gainLossPct: index.toDouble(),
      ),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          portfolioRepositoryProvider.overrideWithValue(
            _FakeRepository(history: points),
          ),
        ],
        child: const MaterialApp(home: PortfolioHistoryChart()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    final labels = tester
        .widgetList<Text>(find.byType(Text))
        .where((text) => RegExp(r'^\d{2}/\d{2}$').hasMatch(text.data ?? ''))
        .toList();
    expect(labels.length, greaterThan(1));
    expect(labels.length, lessThanOrEqualTo(5));
    final rectangles = labels
        .map((label) => tester.getRect(find.byWidget(label)))
        .toList();
    for (var i = 0; i < rectangles.length; i++) {
      for (var j = i + 1; j < rectangles.length; j++) {
        expect(
          rectangles[i].overlaps(rectangles[j]),
          isFalse,
          reason: '${labels[i].data} overlaps ${labels[j].data}',
        );
      }
    }
  });

  testWidgets('portfolio layout handles large amounts on narrow screens', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 800);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          portfolioRepositoryProvider.overrideWithValue(_FakeRepository()),
        ],
        child: const MaterialApp(home: PortfolioScreen()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Valeur actuelle'), findsOneWidget);
    expect(find.text('Performance globale'), findsOneWidget);
    expect(find.text('Évolution du portefeuille'), findsOneWidget);
    expect(find.byTooltip('Importer un document SGI'), findsOneWidget);
    expect(find.byTooltip('Ajouter une opération'), findsOneWidget);
    expect(find.byType(FloatingActionButton), findsNothing);

    final totalY = tester.getTopLeft(find.text('Valeur actuelle')).dy;
    final performanceY = tester.getTopLeft(find.text('Performance globale')).dy;
    final costY = tester.getTopLeft(find.text('Coût d’achat')).dy;
    final latentY = tester.getTopLeft(find.text('Gain/Perte latent(e)')).dy;
    final dividendsY = tester.getTopLeft(find.text('Dividendes perçus')).dy;
    final positionsY = tester.getTopLeft(find.text('Positions').first).dy;
    expect(performanceY, greaterThan(totalY));
    expect(costY, greaterThan(performanceY));
    expect(latentY, greaterThan(costY));
    expect(dividendsY, greaterThan(latentY));
    expect(positionsY, greaterThan(dividendsY));
    expect(tester.takeException(), isNull);
  });

  testWidgets('position form SGI dropdown sorts and labels broker names', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 800);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    const longName =
        'PHOENIX CAPITAL MANAGEMENT - DIRECTION REGIONALE DES OPERATIONS';
    const alphaName = 'ALPHA INVESTMENT (AIA)';

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          brokersProvider.overrideWith(
            (ref) async => <BrokerEntry>[
              BrokerEntry(raw: const <String, dynamic>{}, name: longName),
              BrokerEntry(raw: const <String, dynamic>{}, name: alphaName),
            ],
          ),
        ],
        child: const MaterialApp(home: PositionFormScreen()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.takeException(), isNull);

    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    expect(find.text('AIA'), findsOneWidget);
    expect(find.text('ALPHA INVESTMENT'), findsOneWidget);
    expect(find.text('PCMDRO'), findsOneWidget);
    expect(find.text(longName), findsOneWidget);
    final alphaY = tester.getTopLeft(find.text('AIA')).dy;
    final longY = tester.getTopLeft(find.text('PCMDRO')).dy;
    expect(alphaY, lessThan(longY));

    await tester.tap(find.text('AIA'));
    await tester.pumpAndSettle();
    expect(find.text('AIA'), findsOneWidget);
    expect(find.text('ALPHA INVESTMENT'), findsNothing);
    expect(find.text('PCMDRO'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('position form switches to dividend entry', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 800);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          brokersProvider.overrideWith((ref) async => <BrokerEntry>[]),
        ],
        child: const MaterialApp(home: PositionFormScreen()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Prix d’achat (FCFA)'), findsOneWidget);
    expect(find.text('Quantité'), findsOneWidget);

    await tester.tap(find.text('Dividende'));
    await tester.pumpAndSettle();
    expect(find.text('Montant du dividende (FCFA)'), findsOneWidget);
    expect(find.text('Date de paiement'), findsOneWidget);
    expect(find.text('Ajouter le dividende'), findsOneWidget);
    expect(find.text('Prix d’achat (FCFA)'), findsNothing);
    expect(find.text('Quantité'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('SGI allocation chart shows pie and per-SGI totals', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PortfolioSgiChart(
          breakdown: <SgiSummary>[
            SgiSummary(
              sgi: 'PHOENIX CAPITAL MANAGEMENT',
              positionsCount: 1,
              quantity: 12,
              totalCostFcfa: 100000,
              currentValueFcfa: 112000,
              gainLossFcfa: 12000,
              gainLossPct: 12,
              dividendsFcfa: 5000,
            ),
          ],
        ),
      ),
    );
    expect(find.text('Répartition par SGI'), findsOneWidget);
    expect(find.text('Valeur'), findsOneWidget);
    expect(find.text('Dividendes'), findsOneWidget);
    expect(find.text('PHOENIX CAPITAL MANAGEMENT'), findsOneWidget);
    expect(find.textContaining('1 position(s)'), findsOneWidget);
    expect(find.textContaining('5\u202f000'), findsOneWidget);
  });

  testWidgets('SGI allocation chart dividends view plots dividend shares', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PortfolioSgiChart(
          breakdown: <SgiSummary>[
            SgiSummary(
              sgi: 'PHOENIX CAPITAL MANAGEMENT',
              positionsCount: 1,
              quantity: 12,
              totalCostFcfa: 100000,
              currentValueFcfa: 112000,
              gainLossFcfa: 12000,
              gainLossPct: 12,
              dividendsFcfa: 5000,
            ),
            SgiSummary(
              sgi: 'BSIC Capital SA',
              positionsCount: 1,
              quantity: 5,
              totalCostFcfa: 60000,
              currentValueFcfa: 70000,
              gainLossFcfa: 10000,
              gainLossPct: 16.67,
              dividendsFcfa: 0,
            ),
          ],
        ),
      ),
    );

    // Vue « Valeur » : deux parts, une par courtier.
    PieChart pie = tester.widget<PieChart>(find.byType(PieChart));
    expect(pie.data.sections, hasLength(2));

    await tester.tap(find.text('Dividendes'));
    await tester.pumpAndSettle();

    // Vue « Dividendes » : seul PHOENIX verse des dividendes — la part à
    // zéro de BSIC est exclue au lieu d'empiler une étiquette « 0 % ».
    expect(find.text('Aucun dividende enregistré.'), findsNothing);
    pie = tester.widget<PieChart>(find.byType(PieChart));
    expect(pie.data.sections, hasLength(1));
    expect(pie.data.sections.single.value, 5000);
    expect(pie.data.sections.single.title, '100%');
  });

  testWidgets('edit lot dialog fits when the keyboard shrinks it', (
    tester,
  ) async {
    // Grande surface : tout le contenu est visible sans défilement.
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 3200);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetViewInsets);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          brokersProvider.overrideWith(
            (ref) async => <BrokerEntry>[
              BrokerEntry(
                raw: const <String, dynamic>{},
                name: 'PHOENIX CAPITAL MANAGEMENT',
              ),
            ],
          ),
          portfolioRepositoryProvider.overrideWithValue(
            _FakeRepository(
              positions: const <Position>[
                Position(
                  symbol: 'NTLC',
                  sgi: 'PHOENIX CAPITAL MANAGEMENT',
                  quantity: 8,
                  totalCost: 400000,
                  currentValueFcfa: 117600,
                  gainLossFcfa: -282400,
                  gainLossPct: -70.6,
                  lots: <Lot>[
                    Lot(
                      id: 1,
                      symbol: 'NTLC',
                      sgi: 'PHOENIX CAPITAL MANAGEMENT',
                      buyPrice: 50000,
                      buyDate: '2026-01-15',
                      quantity: 8,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
        child: const MaterialApp(home: PortfolioScreen()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.takeException(), isNull);

    // Déplier la position puis ouvrir le dialogue de modification du lot.
    await tester.tap(find.byIcon(Icons.expand_more));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.edit_outlined));
    await tester.pumpAndSettle();
    expect(find.textContaining('Modifier le lot'), findsOneWidget);

    // Clavier ouvert sur un écran court : le dialogue perd la moitié de sa
    // hauteur — le contenu doit défiler (scrollable) au lieu de déborder
    // (« BOTTOM OVERFLOWED » sur le bouton de date).
    tester.view.physicalSize = const Size(360, 800);
    tester.view.viewInsets = FakeViewPadding(bottom: 320);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Enregistrer'), findsOneWidget);
  });

  testWidgets('portfolio app bar hosts the SGI filter dropdown', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 800);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          portfolioRepositoryProvider.overrideWithValue(_FakeRepository()),
        ],
        child: const MaterialApp(home: PortfolioScreen()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.takeException(), isNull);

    // Le filtre SGI vit dans la barre d'action, à gauche du bouton d'import.
    final appBar = find.byType(KoraAppBar);
    expect(
      find.descendant(of: appBar, matching: find.text('SGI')),
      findsOneWidget,
    );
    final sgiLabelX = tester.getTopLeft(
      find.descendant(of: appBar, matching: find.text('SGI')),
    ).dx;
    final importX = tester.getTopLeft(
      find.byTooltip('Importer un document SGI'),
    ).dx;
    expect(sgiLabelX, lessThan(importX));

    // Ouvrir le menu : tous les courtiers du portefeuille y figurent.
    await tester.tap(find.byType(DropdownButton<String?>));
    await tester.pumpAndSettle();
    expect(find.text('Tous les SGI'), findsOneWidget);
    expect(find.text('PHOENIX CAPITAL MANAGEMENT'), findsWidgets);
    expect(find.text('BSIC Capital SA'), findsOneWidget);

    // Choisir un courtier met à jour le filtre global.
    await tester.tap(find.text('BSIC Capital SA').last);
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(
      tester.element(find.byType(PortfolioScreen)),
    );
    expect(container.read(portfolioSgiFilterProvider), 'BSIC Capital SA');
    expect(tester.takeException(), isNull);
  });
}
