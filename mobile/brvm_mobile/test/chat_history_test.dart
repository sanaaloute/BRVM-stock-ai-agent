import 'package:brvm_mobile/features/chat/chat_models.dart';
import 'package:brvm_mobile/features/chat/chat_providers.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('HistoryMessage.fromJson', () {
    test('role user / assistant', () {
      final user = HistoryMessage.fromJson(<String, dynamic>{
        'role': 'user',
        'text': 'Analyse-moi SONATEL',
      });
      expect(user.fromUser, isTrue);
      expect(user.text, 'Analyse-moi SONATEL');

      final assistant = HistoryMessage.fromJson(<String, dynamic>{
        'role': 'assistant',
        'text': 'Voici une analyse détaillée…',
      });
      expect(assistant.fromUser, isFalse);
      expect(assistant.text, 'Voici une analyse détaillée…');
    });

    test('role insensible à la casse ; champs manquants tolérés', () {
      final upper = HistoryMessage.fromJson(<String, dynamic>{
        'role': 'USER',
        'text': 'Bonjour',
      });
      expect(upper.fromUser, isTrue);

      final minimal = HistoryMessage.fromJson(<String, dynamic>{});
      expect(minimal.fromUser, isFalse);
      expect(minimal.text, '');
    });
  });

  group('buildThreadId', () {
    test('préfixe app:{userId} (propriété vérifiée par le backend)', () {
      final id = buildThreadId('user-123');
      expect(id.startsWith('app:user-123:'), isTrue);
    });

    test('identifiants distincts à chaque appel', () {
      final a = buildThreadId('u1');
      final b = buildThreadId('u1');
      expect(a, isNot(b));
    });
  });

  group('stripAiDisclaimer', () {
    test('retire l’avertissement terminal (littéral backend exact)', () {
      const disclaimer =
          '⚠️ Attention : ce texte est généré par IA. Vérifiez les informations avant toute décision ou action.';
      const message = '**Valorisation**\n\n- Point 1\n\n$disclaimer';
      expect(stripAiDisclaimer(message), '**Valorisation**\n\n- Point 1');
    });

    test('constante synchronisée avec le littéral', () {
      expect(
        aiDisclaimer,
        '⚠️ Attention : ce texte est généré par IA. Vérifiez les informations avant toute décision ou action.',
      );
    });

    test('texte sans avertissement inchangé', () {
      expect(stripAiDisclaimer('Bonjour, voici le palmarès.'), 'Bonjour, voici le palmarès.');
      expect(stripAiDisclaimer(''), '');
    });

    test('message réduit à l’avertissement → chaîne vide (filtré à l’affichage)', () {
      expect(stripAiDisclaimer('⚠️ Attention : ce texte est généré par IA. Vérifiez les informations avant toute décision ou action.'), '');
    });

    test('espaces / sauts de ligne résiduels après coupe trimmés', () {
      final result = stripAiDisclaimer(
        'Réponse.\n\n\n⚠️ Attention : ce texte est généré par IA. Vérifiez les informations avant toute décision ou action.\n',
      );
      expect(result, 'Réponse.');
    });
  });
}
