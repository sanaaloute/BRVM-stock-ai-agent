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

    testWidgets(
      'remplace les détails techniques de connexion par un message simple',
      (tester) async {
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: ErrorView(
                message:
                    'Digest indisponible.\n'
                    'DioException [connection error]: Failed host lookup: '
                    'kbourse.neobytech.net',
                onRetry: _noop,
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.textContaining('Digest indisponible.'), findsOneWidget);
        expect(find.textContaining('Vérifiez votre connexion'), findsOneWidget);
        expect(find.textContaining('Failed host lookup'), findsNothing);
        expect(find.textContaining('DioException'), findsNothing);
        expect(find.text('Réessayer'), findsOneWidget);
      },
    );

    testWidgets(
      'conseille de réessayer quand le service est temporairement indisponible',
      (tester) async {
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: ErrorView(
                message:
                    'Quota indisponible.\nDioException [bad response]: 524',
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(
          find.textContaining('Service temporairement indisponible'),
          findsOneWidget,
        );
        expect(find.textContaining('524'), findsNothing);
      },
    );
  });
}

void _noop() {}
