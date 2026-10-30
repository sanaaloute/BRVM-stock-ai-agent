import 'package:brvm_mobile/features/alerts/alerts_providers.dart';
import 'package:brvm_mobile/features/alerts/alerts_screen.dart';
import 'package:brvm_mobile/features/market/market_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

class _FakeAlertsNotifier extends AlertsNotifier {
  _FakeAlertsNotifier([List<PriceAlert>? initial])
    : items = initial ?? <PriceAlert>[];

  List<PriceAlert> items;
  String? createdSymbol;
  double? createdTarget;
  String? updatedId;
  double? updatedTarget;
  String? updatedDirection;

  @override
  Future<List<PriceAlert>> build() async => items;

  @override
  Future<String?> create(
    String symbol,
    double targetPrice,
    String direction,
  ) async {
    createdSymbol = symbol;
    createdTarget = targetPrice;
    return null;
  }

  @override
  Future<String?> updateAlert(
    String id, {
    double? targetPrice,
    String? direction,
  }) async {
    updatedId = id;
    updatedTarget = targetPrice;
    updatedDirection = direction;
    items = <PriceAlert>[
      for (final alert in items)
        if (alert.id == id)
          PriceAlert(
            id: alert.id,
            symbol: alert.symbol,
            targetPrice: targetPrice ?? alert.targetPrice,
            direction: direction ?? alert.direction,
            notified: alert.notified,
          )
        else
          alert,
    ];
    ref.invalidateSelf();
    return null;
  }

  @override
  Future<void> delete(String id) async {
    items = items.where((alert) => alert.id != id).toList();
    ref.invalidateSelf();
  }
}

Widget _app(_FakeAlertsNotifier notifier) => ProviderScope(
      overrides: <Override>[
        alertsProvider.overrideWith(() => notifier),
        palmaresSymbolsProvider
            .overrideWithValue(const AsyncData<List<String>>(['SONATEL'])),
        quoteProvider.overrideWith((ref, symbol) async => 6200.0),
      ],
      child: const MaterialApp(home: AlertsScreen()),
    );

void main() {
  // formatFcfa (aide « Cours actuel ») exige les données fr_FR,
  // initialisées par l'app dans main().
  setUpAll(() async => initializeDateFormatting('fr_FR'));

  testWidgets('ouvrir le dialogue puis Annuler : aucune exception', (tester) async {
    await tester.pumpWidget(_app(_FakeAlertsNotifier()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nouvelle alerte'));
    await tester.pumpAndSettle();
    expect(find.text('Nouvelle alerte'), findsNWidgets(2)); // FAB + titre
    expect(find.byType(DropdownMenu<String>), findsOneWidget);

    // Rebuilds du dialogue (changement de direction) sans fuite d'écouteurs.
    await tester.tap(find.text('En dessous'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Au-dessus'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(TextButton, 'Annuler'));
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('créer une alerte : symbole + cours envoyés, dialogue fermé',
      (tester) async {
    final notifier = _FakeAlertsNotifier();
    await tester.pumpWidget(_app(notifier));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nouvelle alerte'));
    await tester.pumpAndSettle();

    // Sélection du symbole dans le menu déroulant (déclenche le cours actuel).
    await tester.tap(find.descendant(
      of: find.byType(DropdownMenu<String>),
      matching: find.byType(EditableText),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('SONATEL').last);
    await tester.pumpAndSettle();
    // Groupement français = espace fine insécable (U+202F) dans le nombre.
    final helper = find.textContaining('Cours actuel');
    expect(helper, findsOneWidget);
    expect(
      tester.widget<Text>(helper).data!.replaceAll('\u202F', ' '),
      'Cours actuel : 6 200 FCFA',
    );

    await tester.enterText(find.byKey(const Key('alert-price-field')), '5000');
    await tester.tap(find.widgetWithText(FilledButton, 'Créer'));
    await tester.pumpAndSettle();

    expect(notifier.createdSymbol, 'SONATEL');
    expect(notifier.createdTarget, 5000.0);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('champ symbole libre quand aucun symbole connu', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          alertsProvider.overrideWith(() => _FakeAlertsNotifier()),
          palmaresSymbolsProvider
              .overrideWithValue(const AsyncData<List<String>>([])),
        ],
        child: const MaterialApp(home: AlertsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nouvelle alerte'));
    await tester.pumpAndSettle();

    expect(find.byType(DropdownMenu<String>), findsNothing);
    expect(find.widgetWithText(TextFormField, ''), findsWidgets);
    expect(find.text('Symbole'), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, 'Annuler'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('chaque alerte a des boutons modifier/supprimer ; suppression confirmée',
      (tester) async {
    final notifier = _FakeAlertsNotifier(const <PriceAlert>[
      PriceAlert(
        id: '1',
        symbol: 'SONATEL',
        targetPrice: 6200,
        direction: 'above',
      ),
      PriceAlert(
        id: '2',
        symbol: 'NTLC',
        targetPrice: 14000,
        direction: 'below',
        notified: true,
      ),
    ]);
    await tester.pumpWidget(_app(notifier));
    await tester.pumpAndSettle();

    expect(find.byTooltip('Modifier l’alerte'), findsNWidgets(2));
    expect(find.byTooltip('Supprimer l’alerte'), findsNWidgets(2));
    expect(find.text('Déclenchée'), findsOneWidget);

    await tester.tap(find.byTooltip('Supprimer l’alerte').first);
    await tester.pumpAndSettle();
    expect(find.text('Supprimer cette alerte ?'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Supprimer'));
    await tester.pumpAndSettle();
    expect(find.text('SONATEL'), findsNothing);
    expect(find.text('NTLC'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('modifier une alerte : dialogue pré-rempli, update appelé',
      (tester) async {
    final notifier = _FakeAlertsNotifier(const <PriceAlert>[
      PriceAlert(
        id: '1',
        symbol: 'SONATEL',
        targetPrice: 6200,
        direction: 'above',
      ),
    ]);
    await tester.pumpWidget(_app(notifier));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Modifier l’alerte'));
    await tester.pumpAndSettle();

    // Mode édition : symbole fixe, cours cible pré-rempli, bouton dédié.
    expect(find.text('Modifier l’alerte'), findsOneWidget);
    expect(find.byType(DropdownMenu<String>), findsNothing);
    final priceField = tester.widget<TextFormField>(
      find.byKey(const Key('alert-price-field')),
    );
    expect(priceField.controller!.text, '6200.0');

    await tester.enterText(
      find.byKey(const Key('alert-price-field')),
      '5000',
    );
    await tester.tap(find.text('En dessous'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Enregistrer'));
    await tester.pumpAndSettle();

    expect(notifier.updatedId, '1');
    expect(notifier.updatedTarget, 5000.0);
    expect(notifier.updatedDirection, 'below');
    expect(find.byType(AlertDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
