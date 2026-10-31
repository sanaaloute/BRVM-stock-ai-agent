import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/json_utils.dart';
import 'chat_models.dart';

/// Délai maximal du chat : la réponse de l'IA peut mettre jusqu'à 5 min.
const Duration chatTimeout = Duration(minutes: 5);

class ChatRepository {
  ChatRepository(this._api);

  final ApiClient _api;

  Future<ChatResponse> send(String query, {String? threadId}) async {
    final response = await _api.post(
      '${AppConfig.apiPrefix}/chat',
      data: <String, dynamic>{
        'query': query,
        'thread_id': ?threadId,
      },
      timeout: chatTimeout,
    );
    return ChatResponse.fromJson(asMap(response.data));
  }

  /// Version SSE de [send] : événements `status` / `thinking` / `token` en
  /// direct, puis un événement `final` avec la réponse canonique. Lève une
  /// exception si la connexion échoue avant le premier événement (l'appelant
  /// retombe alors sur [send]).
  Stream<ChatStreamEvent> sendStream(String query, {String? threadId}) async* {
    final response = await _api.dio.post<ResponseBody>(
      '${AppConfig.apiPrefix}/chat/stream',
      data: <String, dynamic>{
        'query': query,
        'thread_id': ?threadId,
      },
      options: Options(
        responseType: ResponseType.stream,
        headers: <String, dynamic>{'Accept': 'text/event-stream'},
        receiveTimeout: chatTimeout,
        sendTimeout: chatTimeout,
      ),
    );
    final body = response.data;
    if (body == null) return;

    String buffer = '';
    await for (final chunk
        in body.stream.cast<List<int>>().transform(utf8.decoder)) {
      buffer += chunk;
      // Les événements SSE sont séparés par une ligne vide.
      int sep;
      while ((sep = buffer.indexOf('\n\n')) != -1) {
        final rawEvent = buffer.substring(0, sep);
        buffer = buffer.substring(sep + 2);
        final dataLines = <String>[];
        for (final line in rawEvent.split('\n')) {
          if (line.startsWith('data:')) {
            dataLines.add(line.substring(5).trimLeft());
          }
        }
        if (dataLines.isEmpty) continue; // commentaire keepalive
        try {
          yield ChatStreamEvent.fromJson(asMap(jsonDecode(dataLines.join('\n'))));
        } catch (_) {
          // Événement mal formé : on l'ignore plutôt que casser le flux.
        }
      }
    }
  }

  Future<List<Conversation>> getConversations() async {
    final response = await _api.get('${AppConfig.apiPrefix}/conversations');
    return asMapList(asMap(response.data)['conversations'])
        .map(Conversation.fromJson)
        .where((c) => c.threadId.isNotEmpty)
        .toList();
  }

  /// Historique d'une conversation (jusqu'aux 50 derniers messages).
  Future<List<HistoryMessage>> getMessages(String threadId) async {
    final response = await _api
        .get('${AppConfig.apiPrefix}/conversations/$threadId/messages');
    return asMapList(asMap(response.data)['messages'])
        .map(HistoryMessage.fromJson)
        .toList();
  }

  /// Questions suggérées pour une conversation vierge (générées côté
  /// serveur à partir des données de marché du jour).
  Future<List<String>> getSuggestions() async {
    final response = await _api.get('${AppConfig.apiPrefix}/chat/suggestions');
    return asStringList(asMap(response.data)['suggestions']);
  }

  Future<void> deleteConversation(String threadId) async {
    await _api.delete('${AppConfig.apiPrefix}/conversations/$threadId');
  }
}
