import 'dart:convert';

import 'package:brvm_mobile/features/chat/chat_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ChatResponse.fromJson', () {
    test('réponse standard avec reply, thread_id et quota', () {
      final response = ChatResponse.fromJson(<String, dynamic>{
        'reply': 'Le palmarès du jour est disponible.',
        'thread_id': 'thread-123',
        'quota_remaining': 7,
      });

      expect(response.isError, isFalse);
      expect(response.displayText, 'Le palmarès du jour est disponible.');
      expect(response.threadId, 'thread-123');
      expect(response.quotaRemaining, 7);
      expect(response.imagesBase64, isEmpty);
    });

    test('erreur métier en HTTP 200 (champ error)', () {
      final response = ChatResponse.fromJson(<String, dynamic>{
        'error': 'Quota quotidien épuisé.',
        'quota_remaining': 0,
      });

      expect(response.isError, isTrue);
      expect(response.error, contains('Quota'));
      expect(response.displayText, isNull);
    });

    test('champ error vide ≠ erreur', () {
      final response = ChatResponse.fromJson(<String, dynamic>{
        'reply': 'OK',
        'error': '',
      });
      expect(response.isError, isFalse);
    });

    test('images_base64 décodées en base64 valide + légende', () {
      final pngBase64 = base64Encode(<int>[137, 80, 78, 71, 13, 10, 26, 10]);
      final response = ChatResponse.fromJson(<String, dynamic>{
        'reply': 'Voici le graphique :',
        'images_base64': <String>[pngBase64],
        'image_caption': 'Cours sur 30 jours',
      });

      expect(response.imagesBase64, hasLength(1));
      expect(base64Decode(response.imagesBase64.single),
          <int>[137, 80, 78, 71, 13, 10, 26, 10]);
      expect(response.imageCaption, 'Cours sur 30 jours');
    });

    test('image_base64 unique fusionnée dans imagesBase64', () {
      final response = ChatResponse.fromJson(<String, dynamic>{
        'image_base64': 'aGVsbG8=',
      });
      expect(response.imagesBase64, <String>['aGVsbG8=']);
    });

    test('clarification utilisée quand pas de reply', () {
      final response = ChatResponse.fromJson(<String, dynamic>{
        'clarification': 'De quel titre parlez-vous ?',
      });
      expect(response.displayText, 'De quel titre parlez-vous ?');
    });

    test('JSON minimal / champs manquants', () {
      final response = ChatResponse.fromJson(<String, dynamic>{});
      expect(response.isError, isFalse);
      expect(response.displayText, isNull);
      expect(response.threadId, isNull);
      expect(response.quotaRemaining, isNull);
    });
  });

  group('Conversation.fromJson', () {
    test('parse thread_id, titre et date', () {
      final conversation = Conversation.fromJson(<String, dynamic>{
        'thread_id': 't-9',
        'title': 'Analyse SONATEL',
        'last_seen': '2026-09-01T10:30:00',
      });
      expect(conversation.threadId, 't-9');
      expect(conversation.title, 'Analyse SONATEL');
      expect(conversation.lastSeen, DateTime(2026, 9, 1, 10, 30));
    });

    test('tolère les champs absents', () {
      final conversation = Conversation.fromJson(<String, dynamic>{});
      expect(conversation.threadId, '');
      expect(conversation.lastSeen, isNull);
    });
  });
}
