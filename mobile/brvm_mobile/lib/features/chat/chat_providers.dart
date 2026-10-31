import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'chat_models.dart';
import 'chat_repository.dart';

final chatRepositoryProvider = Provider<ChatRepository>(
  (ref) => ChatRepository(ref.watch(apiClientProvider)),
);

final conversationsProvider = FutureProvider.autoDispose<List<Conversation>>(
  (ref) {
    // Changement de compte → rechargement automatique (pas de cache croisé).
    ref.watch(currentUserIdProvider);
    return ref.watch(chatRepositoryProvider).getConversations();
  },
);

/// Nouvel identifiant de conversation. Préfixé `app:{userId}` : le backend
/// vérifie la propriété par préfixe, donc l'id utilisateur est obligatoire.
String buildThreadId(String userId) {
  final time = DateTime.now().millisecondsSinceEpoch;
  final rand = Random.secure().nextInt(0x7fffffff).toRadixString(16);
  return 'app:$userId:$time-$rand';
}

/// État d'une conversation de chat.
class ChatState {
  const ChatState({
    this.threadId,
    this.messages = const <ChatMessage>[],
    this.isSending = false,
    this.isLoadingHistory = false,
    this.error,
    this.status,
  });

  final String? threadId;
  final List<ChatMessage> messages;
  final bool isSending;
  final bool isLoadingHistory;
  final String? error;

  /// Agent en cours côté serveur (événements `status` du flux SSE, libellé
  /// français prêt à afficher). Null hors streaming.
  final String? status;

  ChatState copyWith({
    String? threadId,
    List<ChatMessage>? messages,
    bool? isSending,
    bool? isLoadingHistory,
    String? error,
    String? status,
    bool clearStatus = false,
  }) =>
      ChatState(
        threadId: threadId ?? this.threadId,
        messages: messages ?? this.messages,
        isSending: isSending ?? this.isSending,
        isLoadingHistory: isLoadingHistory ?? this.isLoadingHistory,
        error: error,
        status: clearStatus ? null : (status ?? this.status),
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

/// Questions suggérées sur une conversation vierge. Rechargées à chaque
/// nouvelle session (epoch) et à chaque changement de compte ; le backend
/// les génère à partir des données de marché du jour.
final chatSuggestionsProvider = FutureProvider.autoDispose<List<String>>(
  (ref) {
    ref.watch(chatEpochProvider);
    ref.watch(currentUserIdProvider);
    return ref.watch(chatRepositoryProvider).getSuggestions();
  },
);

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
    // Bulle d'attente progressive : pensées + réponse s'y affichent en direct.
    final placeholder = ChatMessage(
      id: _nextId(),
      text: '',
      fromUser: false,
      streaming: true,
      createdAt: DateTime.now(),
    );
    state = state.copyWith(
      messages: <ChatMessage>[...state.messages, userMessage, placeholder],
      isSending: true,
      error: null,
      clearStatus: true,
    );

    final repo = _ref.read(chatRepositoryProvider);
    // La requête n'est réellement consommée côté serveur qu'au premier
    // événement : avant ça, une erreur (404 vieux serveur, réseau) retombe
    // sans risque sur le POST classique.
    var gotEvent = false;
    try {
      await for (final event
          in repo.sendStream(trimmed, threadId: state.threadId)) {
        gotEvent = true;
        switch (event.type) {
          case ChatStreamEventType.status:
            state = state.copyWith(status: event.label);
          case ChatStreamEventType.thinking:
            _growPlaceholder(placeholder.id, thinkingDelta: event.delta ?? '');
          case ChatStreamEventType.token:
            _growPlaceholder(placeholder.id, textDelta: event.delta ?? '');
          case ChatStreamEventType.finalPayload:
            _finishStream(placeholder.id, event.response!);
            // La nouvelle conversation apparaît dans la liste.
            _ref.invalidate(conversationsProvider);
            return;
          case ChatStreamEventType.error:
            _failStream(
              placeholder.id,
              event.error ?? 'Une erreur est survenue.',
            );
            return;
        }
      }
      // Flux terminé sans événement `final`.
      if (!gotEvent) {
        await _sendClassic(repo, trimmed, placeholderId: placeholder.id);
      } else {
        _failStream(
          placeholder.id,
          'Erreur réseau. Vérifiez votre connexion et réessayez.',
        );
      }
    } catch (_) {
      if (!gotEvent) {
        await _sendClassic(repo, trimmed, placeholderId: placeholder.id);
      } else {
        _failStream(
          placeholder.id,
          'Erreur réseau. Vérifiez votre connexion et réessayez.',
        );
      }
    }
  }

  /// Chemin historique (POST JSON simple) : secours quand le serveur ne
  /// connaît pas /chat/stream ou que la connexion SSE échoue avant le
  /// premier événement.
  Future<void> _sendClassic(
    ChatRepository repo,
    String trimmed, {
    required String placeholderId,
  }) async {
    _dropPlaceholder(placeholderId);
    try {
      final response = await repo.send(trimmed, threadId: state.threadId);

      if (response.isError) {
        state = state.copyWith(
          isSending: false,
          error: response.error ?? 'Une erreur est survenue.',
          clearStatus: true,
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
        clearStatus: true,
      );
      // La nouvelle conversation apparaît dans la liste.
      _ref.invalidate(conversationsProvider);
    } catch (e) {
      state = state.copyWith(
        isSending: false,
        error: 'Erreur réseau. Vérifiez votre connexion et réessayez.',
        clearStatus: true,
      );
    }
  }

  void _growPlaceholder(String id, {String? textDelta, String? thinkingDelta}) {
    _updatePlaceholder(
      id,
      (m) => m.copyWith(
        text: m.text + (textDelta ?? ''),
        thinking: (m.thinking ?? '') + (thinkingDelta ?? ''),
      ),
    );
  }

  /// Remplace la bulle progressive par la réponse canonique (le texte
  /// streamé était une approximation — le payload final fait foi). La
  /// réflexion accumulée reste visible, repliée.
  void _finishStream(String placeholderId, ChatResponse response) {
    _updatePlaceholder(
      placeholderId,
      (m) => m.copyWith(
        text: response.displayText ?? '',
        imagesBase64: response.imagesBase64,
        caption: response.imageCaption,
        streaming: false,
      ),
    );
    state = state.copyWith(
      isSending: false,
      threadId: response.threadId ?? state.threadId,
      clearStatus: true,
    );
  }

  void _failStream(String placeholderId, String message) {
    _dropPlaceholder(placeholderId);
    state = state.copyWith(
      isSending: false,
      error: message,
      clearStatus: true,
    );
  }

  void _dropPlaceholder(String id) {
    state = state.copyWith(
      messages: state.messages.where((m) => m.id != id).toList(),
    );
  }

  void _updatePlaceholder(String id, ChatMessage Function(ChatMessage) update) {
    final messages = List<ChatMessage>.of(state.messages);
    final index = messages.indexWhere((m) => m.id == id);
    if (index == -1) return;
    messages[index] = update(messages[index]);
    state = state.copyWith(messages: messages);
  }
}
