import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'chat_models.dart';
import 'chat_repository.dart';

final chatRepositoryProvider = Provider<ChatRepository>(
  (ref) => ChatRepository(ref.watch(apiClientProvider)),
);

final conversationsProvider = FutureProvider.autoDispose<List<Conversation>>(
  (ref) => ref.watch(chatRepositoryProvider).getConversations(),
);

/// Nouvel identifiant de conversation. Préfixé `app:{userId}` : le backend
/// vérifie la propriété par préfixe, donc l'id utilisateur est obligatoire.
String buildThreadId(String userId) {
  final time = DateTime.now().millisecondsSinceEpoch;
  final rand = Random.secure().nextInt(0x7fffffff).toRadixString(16);
  return 'app:$userId:$time-$rand';
}

/// Identifiant de l'utilisateur connecté, `null` tant que l'auth n'est pas
/// résolue. Lu au moment de l'envoi pour construire l'id de conversation
/// (jamais « anonyme » : un thread orphelin disparaîtrait de la liste).
final currentUserIdProvider = Provider<String?>((ref) {
  final auth = ref.watch(authStateProvider);
  return auth is AuthAuthenticated ? auth.user.id : null;
});

/// État d'une conversation de chat.
class ChatState {
  const ChatState({
    this.threadId,
    this.messages = const <ChatMessage>[],
    this.isSending = false,
    this.isLoadingHistory = false,
    this.error,
    this.quotaRemaining,
  });

  final String? threadId;
  final List<ChatMessage> messages;
  final bool isSending;
  final bool isLoadingHistory;
  final String? error;
  final int? quotaRemaining;

  ChatState copyWith({
    String? threadId,
    List<ChatMessage>? messages,
    bool? isSending,
    bool? isLoadingHistory,
    String? error,
    int? quotaRemaining,
  }) =>
      ChatState(
        threadId: threadId ?? this.threadId,
        messages: messages ?? this.messages,
        isSending: isSending ?? this.isSending,
        isLoadingHistory: isLoadingHistory ?? this.isLoadingHistory,
        error: error,
        quotaRemaining: quotaRemaining ?? this.quotaRemaining,
      );
}

/// Clé de la famille : '' ou préfixe 'new-' = conversation vierge
/// (le suffixe numéroté force un état neuf à chaque « Nouvelle discussion »),
/// sinon threadId existant dont on restaure l'historique.
final chatProvider = StateNotifierProvider.autoDispose
    .family<ChatNotifier, ChatState, String>(
  (ref, threadKey) => ChatNotifier(
    ref,
    threadKey.isEmpty || threadKey.startsWith('new-') ? null : threadKey,
  ),
);

/// Compteur incrémenté par « Nouvelle discussion » depuis l'historique :
/// l'écran de chat racine rebuild avec une nouvelle conversation vierge.
final chatEpochProvider = StateProvider<int>((ref) => 0);

class ChatNotifier extends StateNotifier<ChatState> {
  ChatNotifier(this._ref, String? initialThreadId)
      : super(ChatState(threadId: initialThreadId)) {
    // Thread existant : on restaure son historique. Pour une nouvelle
    // discussion, threadId reste null ici : l'id (préfixé app:{userId}) n'est
    // construit qu'au premier envoi, quand l'auth est garantie résolue —
    // sinon un id « anonyme » créerait un thread orphelin côté liste.
    if (initialThreadId != null) {
      _loadHistory(initialThreadId);
    }
  }

  final Ref _ref;
  int _localId = 0;

  String _nextId() => 'local-${++_localId}';

  /// Résout l'id utilisateur au moment de l'envoi et construit (ou
  /// régénère) l'identifiant de conversation. Sans authentification
  /// résolue, on laisse null : le backend crée le thread et renvoie son id.
  void _ensureThreadId() {
    final current = state.threadId;
    if (current != null && !current.startsWith('app:anonyme:')) return;
    final userId = _ref.read(currentUserIdProvider);
    if (userId == null || userId.isEmpty) return;
    state = state.copyWith(threadId: buildThreadId(userId));
  }

  Future<void> _loadHistory(String threadId) async {
    state = state.copyWith(isLoadingHistory: true);
    try {
      final history = await _ref
          .read(chatRepositoryProvider)
          .getMessages(threadId);
      final restored = <ChatMessage>[];
      for (var i = 0; i < history.length; i++) {
        final item = history[i];
        // L'avertissement IA n'est pas répété sur chaque bulle restaurée.
        final text =
            item.fromUser ? item.text : stripAiDisclaimer(item.text);
        if (text.trim().isEmpty) continue;
        restored.add(ChatMessage(
          id: 'hist-$i',
          text: text,
          fromUser: item.fromUser,
        ));
      }
      // Préfixe : si l'utilisateur a déjà envoyé un message pendant le
      // chargement, l'historique reste en tête.
      state = state.copyWith(
        messages: <ChatMessage>[...restored, ...state.messages],
        isLoadingHistory: false,
      );
    } catch (_) {
      // L'historique est un confort : la conversation continue sans.
      state = state.copyWith(isLoadingHistory: false);
    }
  }

  Future<void> send(String query) async {
    final trimmed = query.trim();
    if (trimmed.isEmpty || state.isSending) return;
    _ensureThreadId();

    final userMessage = ChatMessage(
      id: _nextId(),
      text: trimmed,
      fromUser: true,
      createdAt: DateTime.now(),
    );
    state = state.copyWith(
      messages: <ChatMessage>[...state.messages, userMessage],
      isSending: true,
      error: null,
    );

    try {
      final response = await _ref
          .read(chatRepositoryProvider)
          .send(trimmed, threadId: state.threadId);

      if (response.isError) {
        state = state.copyWith(
          isSending: false,
          error: response.error ?? 'Une erreur est survenue.',
        );
        return;
      }

      final aiMessage = ChatMessage(
        id: _nextId(),
        text: response.displayText ?? '',
        fromUser: false,
        imagesBase64: response.imagesBase64,
        caption: response.imageCaption,
        createdAt: DateTime.now(),
      );
      state = state.copyWith(
        messages: <ChatMessage>[...state.messages, aiMessage],
        isSending: false,
        threadId: response.threadId ?? state.threadId,
        quotaRemaining: response.quotaRemaining,
      );
      // La nouvelle conversation apparaît dans la liste.
      _ref.invalidate(conversationsProvider);
    } catch (e) {
      state = state.copyWith(
        isSending: false,
        error: 'Erreur réseau. Vérifiez votre connexion et réessayez.',
      );
    }
  }
}
