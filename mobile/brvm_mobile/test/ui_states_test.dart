import 'package:brvm_mobile/core/ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ErrorView / EmptyView', () {
    testWidgets('pas de crash dans une ListView (hauteur non bornée)',
        (tester) async {
      // Régression : BoxConstraints(minHeight: Infinity) crashait quand la vue
      // était enfant direct d'une ListView (ex. erreurs de l'écran Compte).
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ListView(
              children: <Widget>[
                const ErrorView(message: 'Erreur test'),
                const EmptyView(message: 'Vide'),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Erreur test'), findsOneWidget);
      expect(find.text('Vide'), findsOneWidget);
    });

    testWidgets('bornée : la vue occupe toute la hauteur disponible',
        (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: ErrorView(message: 'Erreur test')),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      final size = tester.getSize(find.byType(ErrorView));
      expect(size.height, greaterThan(500)); // viewport de test : 800x600
    });
  });
}
