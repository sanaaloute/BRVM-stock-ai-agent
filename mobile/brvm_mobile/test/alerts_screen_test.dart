import 'package:brvm_mobile/features/alerts/alerts_providers.dart';
import 'package:brvm_mobile/features/alerts/alerts_screen.dart';
import 'package:brvm_mobile/features/market/market_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

class _FakeAlertsNotifier extends AlertsNotifier {
  String? createdSymbol;
  double? createdTarget;

  @override
  Future<List<PriceAlert>> build() async => <PriceAlert>[];

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
}
