import 'dart:async';

import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/chat/chat_models.dart';
import 'package:brvm_mobile/features/chat/chat_providers.dart';
import 'package:brvm_mobile/features/chat/chat_repository.dart';
import 'package:brvm_mobile/features/chat/chat_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Réponse qui n'arrive jamais : l'indicateur d'attente reste affiché.
class _NeverCompletingChatRepository extends ChatRepository {
  _NeverCompletingChatRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  @override
  Future<ChatResponse> send(String query, {String? threadId}) =>
      Completer<ChatResponse>().future;

  @override
  Stream<ChatStreamEvent> sendStream(String query, {String? threadId}) async* {
    // Jamais émis, jamais terminé : la bulle de streaming reste vide et
    // l'indicateur d'attente affiché.
    await Completer<void>().future;
  }

  @override
  Future<List<String>> getSuggestions() async => <String>[];
}

void main() {
  testWidgets(
      'attente : messages rotatifs, compteur de secondes, puis messages '
      'patience après 45 s', (tester) async {
    final repo = _NeverCompletingChatRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          currentUserIdProvider.overrideWith((ref) => 'u1'),
          chatRepositoryProvider.overrideWithValue(repo),
        ],
        child: const MaterialApp(home: ChatScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('chat-input')), 'Bonjour');
    await tester.tap(find.byKey(const Key('chat-send')));
    await tester.pump();

    // Premier message + compteur à zéro ; l'ancien texte statique a disparu.
    expect(find.text('Kora consulte le palmarès du jour…'), findsOneWidget);
    expect(find.text('0 s'), findsOneWidget);
    expect(find.textContaining('cela peut prendre'), findsNothing);

    // Rotation toutes les 3 s (400 ms de plus pour finir la transition).
    await tester.pump(const Duration(seconds: 4));
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('4 s'), findsOneWidget);
    expect(find.text('Analyse des tendances du marché…'), findsOneWidget);
    expect(find.text('Kora consulte le palmarès du jour…'), findsNothing);

    // Au-delà de 45 s, le ton « patience » prend le relais.
    await tester.pump(const Duration(seconds: 45));
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Les bonnes analyses demandent un peu de temps…'),
        findsOneWidget);
  });
}
