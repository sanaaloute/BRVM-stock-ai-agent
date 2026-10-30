import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/format.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/core/ui.dart';
import 'package:brvm_mobile/features/market/market_models.dart';
import 'package:brvm_mobile/features/market/market_providers.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_allocation_chart.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_chart.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_import_dialog.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_models.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_providers.dart';
import 'package:brvm_mobile/features/portfolio/portfolio_screen.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeRepository extends PortfolioRepository {
  _FakeRepository({this._history, this.positions, List<DividendEntry>? dividends})
    : dividends =
          dividends ??
          <DividendEntry>[
            const DividendEntry(
              id: 1,
              symbol: 'NTLC',
              sgi: 'PHOENIX CAPITAL MANAGEMENT',
              sector: 'Agroalimentaire',
              amount: 1000,
              paymentDate: '2026-01-20',
            ),
            const DividendEntry(
              id: 2,
              symbol: 'SNTS',
              sgi: 'BSIC Capital SA',
              sector: 'Télécommunications',
              amount: 500,
              paymentDate: '2026-02-10',
            ),
          ],
      super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final List<PortfolioHistoryPoint>? _history;
  final List<Position>? positions;
  List<DividendEntry> dividends;

  @override
  Future<PortfolioData> get({String? sgi}) async {
    return PortfolioData(
      summary: const PortfolioSummary(
        totalCostFcfa: 760000,
        totalValueFcfa: 311100,
        gainLossFcfa: -448900,
        gainLossPct: -59.07,
        dividendsFcfa: 1500,
        totalGainLossFcfa: -447400,
        totalGainLossPct: -58.87,
        positionsCount: 3,
        lotsCount: 2,
      ),
      positions: positions ?? const <Position>[
        Position(
          symbol: 'NTLC',
          sgi: 'PHOENIX CAPITAL MANAGEMENT',
          sector: 'Agroalimentaire',
          quantity: 8,
          totalCost: 400000,
          currentValueFcfa: 117600,
          gainLossFcfa: -282400,
          gainLossPct: -70.6,
        ),
        Position(
          symbol: 'NTLC',
          sgi: 'BSIC Capital SA',
          sector: 'Agroalimentaire',
          quantity: 5,
          totalCost: 260000,
          currentValueFcfa: 73500,
          gainLossFcfa: -186500,
          gainLossPct: -71.73,
        ),
        Position(
          symbol: 'SNTS',
          sgi: 'BSIC Capital SA',
          sector: 'Télécommunications',
          quantity: 10,
          totalCost: 100000,
          currentValueFcfa: 120000,
          gainLossFcfa: 20000,
          gainLossPct: 20,
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
          positionsCount: 2,
          quantity: 15,
          totalCostFcfa: 360000,
          currentValueFcfa: 193500,
          gainLossFcfa: -166500,
          gainLossPct: -46.25,
          dividendsFcfa: 500,
        ),
      ],
      dividends: dividends,
    );
  }

  @override
  Future<String?> updateDividend(
    int dividendId, {
    double? amount,
    String? paymentDate,
    String? sgi,
  }) async {
    dividends = <DividendEntry>[
      for (final dividend in dividends)
        if (dividend.id == dividendId)
          DividendEntry(
            id: dividend.id,
            symbol: dividend.symbol,
            sgi: sgi ?? dividend.sgi,
            sector: dividend.sector,
            amount: amount ?? dividend.amount,
            paymentDate: paymentDate ?? dividend.paymentDate,
          )
        else
          dividend,
    ];
    return null;
  }

  @override
  Future<void> deleteDividend(int dividendId) async {
    dividends = dividends
        .where((dividend) => dividend.id != dividendId)
        .toList();
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
  // find.byType(SegmentedButton) chercherait SegmentedButton<dynamic> et
  // raterait SegmentedButton<_PortfolioTab> : on passe par un prédicat.
  Finder segmentedTab(String label) => find.descendant(
    of: find.byWidgetPredicate((widget) => widget is SegmentedButton),
    matching: find.text(label),
  );

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

  testWidgets('allocation chart shows SGI pie and per-SGI totals', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PortfolioAllocationChart(
          data: PortfolioData(
            summary: const PortfolioSummary(),
            positions: const <Position>[],
            sgiBreakdown: const <SgiSummary>[
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
      ),
    );
    expect(find.text('Répartition par SGI'), findsOneWidget);
    expect(find.text('SGI'), findsOneWidget);
    expect(find.text('Actions'), findsOneWidget);
    expect(find.text('Secteurs'), findsOneWidget);
    expect(find.text('Valeur'), findsOneWidget);
    expect(find.text('Dividendes'), findsOneWidget);
    expect(find.text('PHOENIX CAPITAL MANAGEMENT'), findsOneWidget);
    expect(find.textContaining('1 position(s)'), findsOneWidget);
    expect(find.textContaining('5\u202f000'), findsOneWidget);
  });

  testWidgets('allocation chart dividends view plots dividend shares', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PortfolioAllocationChart(
          data: PortfolioData(
            summary: const PortfolioSummary(),
            positions: const <Position>[],
            sgiBreakdown: const <SgiSummary>[
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

  testWidgets('allocation chart switches to actions and sectors views', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PortfolioAllocationChart(
          data: PortfolioData(
            summary: const PortfolioSummary(),
            positions: const <Position>[
              Position(
                symbol: 'NTLC',
                sgi: 'PHOENIX CAPITAL MANAGEMENT',
                sector: 'Agroalimentaire',
                quantity: 8,
                totalCost: 400000,
                currentValueFcfa: 117600,
                gainLossFcfa: -282400,
                gainLossPct: -70.6,
              ),
              Position(
                symbol: 'NTLC',
                sgi: 'BSIC Capital SA',
                sector: 'Agroalimentaire',
                quantity: 5,
                totalCost: 260000,
                currentValueFcfa: 73500,
                gainLossFcfa: -186500,
                gainLossPct: -71.73,
              ),
              Position(
                symbol: 'SNTS',
                sgi: 'BSIC Capital SA',
                sector: 'Télécommunications',
                quantity: 10,
                totalCost: 100000,
                currentValueFcfa: 120000,
                gainLossFcfa: 20000,
                gainLossPct: 20,
              ),
            ],
            sgiBreakdown: const <SgiSummary>[],
            dividends: const <DividendEntry>[
              DividendEntry(
                id: 1,
                symbol: 'NTLC',
                sgi: 'PHOENIX CAPITAL MANAGEMENT',
                sector: 'Agroalimentaire',
                amount: 1000,
                paymentDate: '2026-01-20',
              ),
              DividendEntry(
                id: 2,
                symbol: 'SNTS',
                sgi: 'BSIC Capital SA',
                sector: 'Télécommunications',
                amount: 500,
                paymentDate: '2026-02-10',
              ),
            ],
          ),
        ),
      ),
    );

    // Vue « Actions » : les deux positions NTLC (SGI différentes)
    // fusionnent en une seule part par société.
    await tester.tap(find.text('Actions'));
    await tester.pumpAndSettle();
    expect(find.text('Répartition par actions'), findsOneWidget);
    PieChart pie = tester.widget<PieChart>(find.byType(PieChart));
    expect(pie.data.sections, hasLength(2));
    expect(find.text('NTLC'), findsOneWidget);
    expect(find.text('SNTS'), findsOneWidget);
    expect(find.textContaining('2 position(s)'), findsOneWidget);

    // Vue « Secteurs » : regroupement par secteur d'activité.
    await tester.tap(find.text('Secteurs'));
    await tester.pumpAndSettle();
    expect(find.text('Répartition par secteur'), findsOneWidget);
    pie = tester.widget<PieChart>(find.byType(PieChart));
    expect(pie.data.sections, hasLength(2));
    expect(find.text('Agroalimentaire'), findsOneWidget);
    expect(find.text('Télécommunications'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('actions view folds companies beyond the top 8 into Autres', (
    tester,
  ) async {
    // 10 sociétés : valeurs 1000, 900, …, 100 (total 5500).
    final positions = <Position>[
      for (var i = 1; i <= 10; i++)
        Position(
          symbol: 'C${i.toString().padLeft(2, '0')}',
          sgi: 'BSIC Capital SA',
          quantity: 1,
          totalCost: (1100 - i * 100).toDouble(),
          currentValueFcfa: (1100 - i * 100).toDouble(),
        ),
    ];
    await tester.pumpWidget(
      MaterialApp(
        // Défilement comme dans l'écran portefeuille (la carte est plus
        // haute que le viewport de test avec 9 lignes de légende).
        home: Scaffold(
          body: SingleChildScrollView(
            child: PortfolioAllocationChart(
              data: PortfolioData(
                summary: const PortfolioSummary(),
                positions: positions,
                sgiBreakdown: const <SgiSummary>[],
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Actions'));
    await tester.pumpAndSettle();

    // 8 premières parts + « Autres » (200 + 100 = 300, gris fixe).
    final pie = tester.widget<PieChart>(find.byType(PieChart));
    expect(pie.data.sections, hasLength(9));
    expect(pie.data.sections.last.value, 300);
    expect(pie.data.sections.last.color, Colors.grey.shade500);

    // Légende : les 8 premières sociétés, puis « Autres » avec juste le %.
    expect(find.text('C01'), findsOneWidget);
    expect(find.text('C08'), findsOneWidget);
    expect(find.text('C09'), findsNothing);
    expect(find.text('C10'), findsNothing);
    expect(find.text('Autres'), findsOneWidget);
    expect(find.text('5 %'), findsOneWidget);
    expect(tester.takeException(), isNull);
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

  testWidgets('holdings card switches between positions and dividends', (
    tester,
  ) async {
    // Grande surface : toute la page est visible sans défilement.
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 3200);
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

    // Onglet Positions par défaut : les filtres gains/pertes sont visibles
    // (« Tous » existe aussi dans le filtre SGI de l'AppBar → on cible les
    // ChoiceChip de la carte).
    expect(find.widgetWithText(ChoiceChip, 'Tous'), findsOneWidget);
    expect(find.widgetWithText(ChoiceChip, 'Gains'), findsOneWidget);
    expect(find.widgetWithText(ChoiceChip, 'Pertes'), findsOneWidget);

    // Bascule vers Dividendes : les filtres disparaissent et les
    // dividendes sont listés avec leurs actions.
    await tester.tap(segmentedTab('Dividendes'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(ChoiceChip, 'Tous'), findsNothing);
    expect(find.widgetWithText(ChoiceChip, 'Gains'), findsNothing);
    expect(find.widgetWithText(ChoiceChip, 'Pertes'), findsNothing);
    expect(find.text('Payé le 2026-01-20'), findsOneWidget);
    expect(find.text('Payé le 2026-02-10'), findsOneWidget);
    expect(find.byTooltip('Modifier le dividende'), findsNWidgets(2));
    expect(find.byTooltip('Supprimer le dividende'), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('dividend edit dialog opens from the holdings card', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 3200);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          brokersProvider.overrideWith((ref) async => <BrokerEntry>[]),
          portfolioRepositoryProvider.overrideWithValue(_FakeRepository()),
        ],
        child: const MaterialApp(home: PortfolioScreen()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(segmentedTab('Dividendes'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Modifier le dividende').first);
    await tester.pumpAndSettle();

    expect(find.text('Modifier le dividende NTLC'), findsOneWidget);
    expect(find.text('Montant du dividende (FCFA)'), findsOneWidget);
    expect(find.textContaining('Date de paiement'), findsOneWidget);
    expect(find.text('Enregistrer'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('dividend deletion asks for confirmation', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 3200);
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

    await tester.tap(segmentedTab('Dividendes'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Supprimer le dividende').first);
    await tester.pumpAndSettle();
    expect(find.text('Supprimer ce dividende ?'), findsOneWidget);

    await tester.tap(find.text('Supprimer'));
    await tester.pumpAndSettle();
    // Le dividende NTLC est retiré ; celui de SNTS reste affiché.
    expect(find.text('Payé le 2026-01-20'), findsNothing);
    expect(find.text('Payé le 2026-02-10'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
