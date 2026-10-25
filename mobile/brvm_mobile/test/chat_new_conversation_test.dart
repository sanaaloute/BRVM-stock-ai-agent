import 'package:brvm_mobile/app.dart';
import 'package:brvm_mobile/core/api_client.dart';
import 'package:brvm_mobile/core/models/auth_user.dart';
import 'package:brvm_mobile/core/providers.dart';
import 'package:brvm_mobile/core/token_storage.dart';
import 'package:brvm_mobile/features/chat/chat_models.dart';
import 'package:brvm_mobile/features/chat/chat_providers.dart';
import 'package:brvm_mobile/features/chat/chat_repository.dart';
import 'package:brvm_mobile/features/chat/chat_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeChatRepository extends ChatRepository {
  _FakeChatRepository() : super(ApiClient(TokenStorage(MemoryKeyValueStore())));

  final List<String?> sentThreadIds = <String?>[];
  List<String> suggestions = <String>[];
  bool suggestionsFail = false;

  @override
  Future<ChatResponse> send(String query, {String? threadId}) async {
    sentThreadIds.add(threadId);
    return ChatResponse(reply: 'Réponse', threadId: threadId ?? 'app:u1:serveur');
  }

  @override
  Future<List<Conversation>> getConversations() async => <Conversation>[
        for (final id in sentThreadIds.whereType<String>())
          Conversation(threadId: id, title: 'Conv $id', lastSeen: DateTime.now()),
      ];

  @override
  Future<List<HistoryMessage>> getMessages(String threadId) async =>
      <HistoryMessage>[];

  @override
  Future<List<String>> getSuggestions() async {
    if (suggestionsFail) throw StateError('offline');
    return suggestions;
  }
}

Future<void> _pumpApp(WidgetTester tester, _FakeChatRepository repo) async {
  final storage = TokenStorage(MemoryKeyValueStore());
  await storage.saveSession(
    const AuthSession(
      user: AuthUser(id: 'u1', email: 't@t.ci', hasTelegram: false),
      accessToken: 'at',
      accessExpiresIn: 900,
      refreshToken: 'rt',
      refreshExpiresIn: 1209600,
      tokenType: 'Bearer',
    ),
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        storageProvider.overrideWithValue(storage),
        chatRepositoryProvider.overrideWithValue(repo),
      ],
      child: const KoraApp(),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _send(WidgetTester tester, String text) async {
  await tester.enterText(find.byKey(const Key('chat-input')), text);
  await tester.tap(find.byKey(const Key('chat-send')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('historique → « Nouvelle discussion » → nouveau thread réseau',
      (tester) async {
    final repo = _FakeChatRepository();
    await _pumpApp(tester, repo);

    await _send(tester, 'Un');
    expect(repo.sentThreadIds, hasLength(1));
    final first = repo.sentThreadIds.single;
    expect(first, startsWith('app:u1:'));

    await tester.tap(find.byTooltip('Historique'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Nouvelle discussion'));
    await tester.pumpAndSettle();

    await _send(tester, 'Deux');
    expect(repo.sentThreadIds, hasLength(2));
    expect(repo.sentThreadIds[1], startsWith('app:u1:'));
    expect(repo.sentThreadIds[1], isNot(first));
  });

  testWidgets('bouton AppBar « Nouvelle discussion » sur /chat → session vierge',
      (tester) async {
    final repo = _FakeChatRepository();
    await _pumpApp(tester, repo);

    await _send(tester, 'Un');
    final first = repo.sentThreadIds.single;

    await tester.tap(find.byKey(const Key('chat-new')));
    await tester.pumpAndSettle();

    // Page vierge : les bulles ont disparu, le hint est revenu.
    expect(find.text('Un'), findsNothing);
    expect(find.text('Posez votre question…'), findsOneWidget);

    await _send(tester, 'Deux');
    expect(repo.sentThreadIds, hasLength(2));
    expect(repo.sentThreadIds[1], isNot(first));
  });

  testWidgets(
      'bouton AppBar depuis un fil existant → retour à une page vierge',
      (tester) async {
    final repo = _FakeChatRepository();
    await _pumpApp(tester, repo);

    await _send(tester, 'Un');
    final first = repo.sentThreadIds.single as String;

    // Ouvre le fil depuis l'historique.
    await tester.tap(find.byTooltip('Historique'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Conv $first'));
    await tester.pumpAndSettle();

    // Nouveau départ depuis le fil : nouveau thread au prochain envoi.
    await tester.tap(find.byKey(const Key('chat-new')));
    await tester.pumpAndSettle();
    await _send(tester, 'Deux');

    expect(repo.sentThreadIds, hasLength(2));
    expect(repo.sentThreadIds[1], isNot(first));
    expect(repo.sentThreadIds[1], startsWith('app:u1:'));
  });

  testWidgets('suggestions dynamiques affichées ; toucher remplit la saisie',
      (tester) async {
    final repo = _FakeChatRepository()
      ..suggestions = <String>['Question dynamique A', 'Question dynamique B'];
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

    expect(find.text('Question dynamique A'), findsOneWidget);
    expect(find.text('Question dynamique B'), findsOneWidget);

    await tester.tap(find.text('Question dynamique B'));
    await tester.pump();
    final field =
        tester.widget<TextField>(find.byKey(const Key('chat-input')));
    expect(field.controller?.text, 'Question dynamique B');
  });

  testWidgets('suggestions : secours statique si le serveur échoue',
      (tester) async {
    final repo = _FakeChatRepository()..suggestionsFail = true;
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

    expect(find.text('Quel est le palmarès du jour ?'), findsOneWidget);
    expect(find.byType(ActionChip), findsNWidgets(3));
  });

  testWidgets('pas de texte de quota dans l’AppBar', (tester) async {
    final repo = _FakeChatRepository();
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

    expect(find.textContaining('Quota'), findsNothing);
  });
}
