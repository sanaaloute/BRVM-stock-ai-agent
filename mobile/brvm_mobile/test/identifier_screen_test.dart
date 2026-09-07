import 'package:brvm_mobile/features/auth/identifier_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> pumpScreen(WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: IdentifierScreen()),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> switchToRegister(WidgetTester tester) async {
    await tester.tap(find.text('Créer un compte'));
    await tester.pumpAndSettle();
  }

  testWidgets('affiche une erreur quand l’identifiant est invalide',
      (tester) async {
    await pumpScreen(tester);

    await tester.enterText(
      find.byKey(const Key('identifier-field')),
      'pas-un-identifiant',
    );
    await tester.enterText(find.byKey(const Key('password-field')), 'password1');
    await tester.tap(find.byKey(const Key('auth-submit')));
    await tester.pump();

    expect(find.textContaining('Format invalide'), findsOneWidget);
  });

  testWidgets('affiche une erreur quand le champ est vide', (tester) async {
    await pumpScreen(tester);

    await tester.tap(find.byKey(const Key('auth-submit')));
    await tester.pump();

    expect(find.textContaining('Veuillez saisir'), findsOneWidget);
  });

  testWidgets('inscription : mot de passe trop court rejeté côté client',
      (tester) async {
    await pumpScreen(tester);
    await switchToRegister(tester);

    // Aide affichée en mode inscription.
    expect(find.textContaining('6 caractères minimum'), findsOneWidget);

    await tester.enterText(
      find.byKey(const Key('identifier-field')),
      'trader@brvm.ci',
    );
    await tester.enterText(find.byKey(const Key('password-field')), 'abc');
    await tester.enterText(find.byKey(const Key('confirm-field')), 'abc');
    await tester.ensureVisible(find.byKey(const Key('auth-submit')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('auth-submit')));
    await tester.pump();

    expect(
      find.text('Le mot de passe doit contenir au moins 6 caractères.'),
      findsOneWidget,
    );
  });

  testWidgets('inscription : confirmation différente rejetée', (tester) async {
    await pumpScreen(tester);
    await switchToRegister(tester);

    await tester.enterText(
      find.byKey(const Key('identifier-field')),
      'trader@brvm.ci',
    );
    await tester.enterText(find.byKey(const Key('password-field')), 'password1');
    await tester.enterText(find.byKey(const Key('confirm-field')), 'password2');
    await tester.ensureVisible(find.byKey(const Key('auth-submit')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('auth-submit')));
    await tester.pump();

    expect(find.textContaining('ne correspondent pas'), findsOneWidget);
  });

  testWidgets('le champ de confirmation n’apparaît qu’en mode inscription',
      (tester) async {
    await pumpScreen(tester);

    expect(find.byKey(const Key('confirm-field')), findsNothing);
    expect(find.text('Se connecter'), findsOneWidget);

    await switchToRegister(tester);

    expect(find.byKey(const Key('confirm-field')), findsOneWidget);
    expect(find.text('Créer mon compte'), findsOneWidget);
  });
}
