import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/chat/chat_models.dart';
import 'package:brvm_mobile/features/chat/chat_providers.dart';
import 'package:brvm_mobile/features/chat/chat_repository.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeChatRepository extends ChatRepository {
  _FakeChatRepository() : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final List<({String query, String? threadId})> sent =
      <({String query, String? threadId})>[];
  List<HistoryMessage> history = <HistoryMessage>[];

  @override
  Future<ChatResponse> send(String query, {String? threadId}) async {
    sent.add((query: query, threadId: threadId));
    return ChatResponse(reply: 'Réponse', threadId: threadId ?? 'app:u1:serveur');
  }

  @override
  Future<List<HistoryMessage>> getMessages(String threadId) async => history;
}

/// Simule la résolution de l'auth : null (AuthLoading) puis 'u1'.
final _userIdFlip = StateProvider<String?>((ref) => null);

ProviderContainer _container(_FakeChatRepository repo) => ProviderContainer(
      overrides: <Override>[
        currentUserIdProvider.overrideWith((ref) => ref.watch(_userIdFlip)),
        chatRepositoryProvider.overrideWithValue(repo),
      ],
    );

void main() {
  test('nouvelle discussion : pas d’id avant l’auth, app:{userId} à l’envoi',
      () async {
    final repo = _FakeChatRepository();
    final container = _container(repo);
    addTearDown(container.dispose);
    final sub = container.listen(chatProvider('').notifier, (_, _) {});
    addTearDown(sub.close);
    final notifier = container.read(chatProvider('').notifier);

    // Auth non résolue à la construction : aucun id ne doit exister,
    // et surtout pas de thread « anonyme ».
    expect(notifier.state.threadId, isNull);

    // L'auth se résout avant le premier envoi (garanti par le routeur).
    container.read(_userIdFlip.notifier).state = 'u1';
    await notifier.send('Bonjour');

    expect(repo.sent, hasLength(1));
    expect(repo.sent.single.threadId, startsWith('app:u1:'));
    expect(repo.sent.single.threadId, isNot(contains('anonyme')));
    expect(notifier.state.threadId, repo.sent.single.threadId);
    expect(notifier.state.messages.last.text, 'Réponse');
  });

  test('envoi sans auth résolue : threadId null sur le réseau, id serveur adopté',
      () async {
    final repo = _FakeChatRepository();
    final container = _container(repo); // _userIdFlip reste null
    addTearDown(container.dispose);
    final sub = container.listen(chatProvider('').notifier, (_, _) {});
    addTearDown(sub.close);
    final notifier = container.read(chatProvider('').notifier);

    await notifier.send('Bonjour');

    expect(repo.sent.single.threadId, isNull);
    expect(notifier.state.threadId, 'app:u1:serveur');
  });

  test('thread préexistant « anonyme » régénéré à l’envoi', () async {
    final repo = _FakeChatRepository();
    final container = _container(repo);
    addTearDown(container.dispose);
    final sub =
        container.listen(chatProvider('app:anonyme:ancien').notifier, (_, _) {});
    addTearDown(sub.close);
    final notifier = container.read(chatProvider('app:anonyme:ancien').notifier);

    container.read(_userIdFlip.notifier).state = 'u1';
    await notifier.send('Suite');

    expect(repo.sent.single.threadId, startsWith('app:u1:'));
    expect(notifier.state.threadId, isNot('app:anonyme:ancien'));
  });

  test('thread existant : historique restauré, id conservé à l’envoi', () async {
    final repo = _FakeChatRepository()
      ..history = <HistoryMessage>[
        const HistoryMessage(fromUser: true, text: 'Question ?'),
        const HistoryMessage(fromUser: false, text: 'Réponse.'),
      ];
    final container = _container(repo);
    addTearDown(container.dispose);
    final sub = container.listen(chatProvider('app:u1:abc').notifier, (_, _) {});
    addTearDown(sub.close);
    final notifier = container.read(chatProvider('app:u1:abc').notifier);

    // Laisse _loadHistory (lancé à la construction) se résoudre.
    await Future<void>.delayed(const Duration(milliseconds: 20));

    expect(notifier.state.threadId, 'app:u1:abc');
    expect(notifier.state.messages, hasLength(2));
    expect(notifier.state.messages.first.fromUser, isTrue);
    expect(notifier.state.messages.last.fromUser, isFalse);

    container.read(_userIdFlip.notifier).state = 'u1';
    await notifier.send('Suite');

    expect(repo.sent.single.threadId, 'app:u1:abc');
    expect(notifier.state.threadId, 'app:u1:abc');
    expect(notifier.state.messages, hasLength(4));
  });
}
