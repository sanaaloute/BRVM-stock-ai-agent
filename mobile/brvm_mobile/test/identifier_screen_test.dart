import 'package:brvm_mobile/features/auth/identifier_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('affiche une erreur quand l’identifiant est invalide',
      (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: IdentifierScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('identifier-field')),
      'pas-un-identifiant',
    );
    await tester.tap(find.byKey(const Key('identifier-submit')));
    await tester.pump();

    expect(find.textContaining('Format invalide'), findsOneWidget);
  });

  testWidgets('affiche une erreur quand le champ est vide', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: IdentifierScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('identifier-submit')));
    await tester.pump();

    expect(find.textContaining('Veuillez saisir'), findsOneWidget);
  });
}
