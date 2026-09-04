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

  Future<void> deleteConversation(String threadId) async {
    await _api.delete('${AppConfig.apiPrefix}/conversations/$threadId');
  }
}
