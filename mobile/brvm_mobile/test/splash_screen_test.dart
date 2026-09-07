import 'package:brvm_mobile/app.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('SplashScreen : logo, titre et animation de chargement',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: SplashScreen()));

    expect(find.byIcon(Icons.candlestick_chart), findsOneWidget);
    expect(find.text('Kora Bourse'), findsOneWidget);
    // L'animation de progression doit être visible pendant la restauration
    // de la session.
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
