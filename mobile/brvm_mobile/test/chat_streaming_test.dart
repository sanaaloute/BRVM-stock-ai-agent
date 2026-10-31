import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/chat/chat_models.dart';
import 'package:brvm_mobile/features/chat/chat_providers.dart';
import 'package:brvm_mobile/features/chat/chat_repository.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Flux SSE complet : statut + réflexion + tokens, puis réponse canonique.
class _StreamingChatRepository extends ChatRepository {
  _StreamingChatRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  @override
  Stream<ChatStreamEvent> sendStream(String query, {String? threadId}) async* {
    yield ChatStreamEvent.fromJson(const <String, dynamic>{
      'type': 'status',
      'label': 'Analyse des données…',
    });
    yield ChatStreamEvent.fromJson(const <String, dynamic>{
      'type': 'thinking',
      'delta': 'je vérifie ',
    });
    yield ChatStreamEvent.fromJson(const <String, dynamic>{
      'type': 'thinking',
      'delta': 'les chiffres',
    });
    yield ChatStreamEvent.fromJson(const <String, dynamic>{
      'type': 'token',
      'delta': 'Réponse ',
    });
    yield ChatStreamEvent.fromJson(const <String, dynamic>{
      'type': 'token',
      'delta': 'approximative',
    });
    yield ChatStreamEvent.fromJson(const <String, dynamic>{
      'type': 'final',
      'payload': <String, dynamic>{
        'reply': 'Réponse canonique.',
        'thread_id': 'app:u1:t1',
      },
    });
  }
}

/// SSE indisponible avant le premier événement : repli sur le POST classique.
class _FailingStreamChatRepository extends ChatRepository {
  _FailingStreamChatRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  int classicCalls = 0;

  @override
  Stream<ChatStreamEvent> sendStream(String query, {String? threadId}) async* {
    throw StateError('404: endpoint inconnu');
  }

  @override
  Future<ChatResponse> send(String query, {String? threadId}) async {
    classicCalls++;
    return ChatResponse(reply: 'Classique', threadId: 'app:u1:t1');
  }
}

/// Erreur métier portée par le flux (quota, etc.) : pas de repli classique.
class _ErrorStreamChatRepository extends ChatRepository {
  _ErrorStreamChatRepository()
      : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  int classicCalls = 0;

  @override
  Stream<ChatStreamEvent> sendStream(String query, {String? threadId}) async* {
    yield ChatStreamEvent.fromJson(const <String, dynamic>{
      'type': 'error',
      'error': 'Quota épuisé.',
    });
  }

  @override
  Future<ChatResponse> send(String query, {String? threadId}) async {
    classicCalls++;
    return ChatResponse(reply: 'Ne doit pas être appelé');
  }
}

ProviderContainer _container(ChatRepository repo) => ProviderContainer(
      overrides: <Override>[
        currentUserIdProvider.overrideWith((ref) => 'u1'),
        chatRepositoryProvider.overrideWithValue(repo),
      ],
    );

void main() {
  test(
      'streaming : la réponse canonique remplace les tokens, '
      'la réflexion est conservée', () async {
    final repo = _StreamingChatRepository();
    final container = _container(repo);
    addTearDown(container.dispose);
    final sub = container.listen(chatProvider('').notifier, (_, _) {});
    addTearDown(sub.close);
    final notifier = container.read(chatProvider('').notifier);

    await notifier.send('Question ?');

    final last = notifier.state.messages.last;
    expect(last.fromUser, isFalse);
    expect(last.text, 'Réponse canonique.');
    expect(last.thinking, 'je vérifie les chiffres');
    expect(last.streaming, isFalse);
    expect(notifier.state.isSending, isFalse);
    expect(notifier.state.threadId, 'app:u1:t1');
    expect(notifier.state.error, isNull);
  });

  test('repli classique quand le flux échoue avant tout événement', () async {
    final repo = _FailingStreamChatRepository();
    final container = _container(repo);
    addTearDown(container.dispose);
    final sub = container.listen(chatProvider('').notifier, (_, _) {});
    addTearDown(sub.close);
    final notifier = container.read(chatProvider('').notifier);

    await notifier.send('Question ?');

    expect(repo.classicCalls, 1);
    final last = notifier.state.messages.last;
    expect(last.text, 'Classique');
    expect(last.streaming, isFalse);
    expect(notifier.state.isSending, isFalse);
    expect(notifier.state.error, isNull);
  });

  test('erreur métier streamée : affichée telle quelle, sans repli', () async {
    final repo = _ErrorStreamChatRepository();
    final container = _container(repo);
    addTearDown(container.dispose);
    final sub = container.listen(chatProvider('').notifier, (_, _) {});
    addTearDown(sub.close);
    final notifier = container.read(chatProvider('').notifier);

    await notifier.send('Question ?');

    expect(repo.classicCalls, 0);
    expect(notifier.state.error, 'Quota épuisé.');
    expect(notifier.state.isSending, isFalse);
    // La bulle de streaming est retirée : seule la question reste.
    expect(notifier.state.messages, hasLength(1));
    expect(notifier.state.messages.single.fromUser, isTrue);
  });
}
