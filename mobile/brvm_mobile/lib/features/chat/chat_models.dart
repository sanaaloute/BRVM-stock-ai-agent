import '../../core/json_utils.dart';

/// Réponse de POST /mobile/v1/chat.
/// Attention : les erreurs métier reviennent en HTTP 200 avec un champ
/// `error` — toujours vérifier [isError].
class ChatResponse {
  const ChatResponse({
    this.reply,
    this.imageBase64,
    this.rawImagesBase64 = const <String>[],
    this.imageCaption,
    this.clarification,
    this.quotaRemaining,
    this.threadId,
    this.error,
  });

  factory ChatResponse.fromJson(Map<String, dynamic> json) => ChatResponse(
        reply: asString(json['reply']),
        imageBase64: asString(json['image_base64']),
        rawImagesBase64: asStringList(json['images_base64']),
        imageCaption: asString(json['image_caption']),
        clarification: asString(json['clarification']),
        quotaRemaining: asInt(json['quota_remaining']),
        threadId: asString(json['thread_id']),
        error: asString(json['error']),
      );

  final String? reply;
  final String? imageBase64;
  final List<String> rawImagesBase64;
  final String? imageCaption;
  final String? clarification;
  final int? quotaRemaining;
  final String? threadId;
  final String? error;

  bool get isError => error != null && error!.isNotEmpty;

  /// Toutes les images de la réponse (champ unique + champ liste).
  List<String> get imagesBase64 => <String>[
        ?imageBase64,
        ...rawImagesBase64,
      ];

  /// Texte à afficher (clarification prioritaire si pas de réponse).
  String? get displayText => reply ?? clarification;
}

/// Conversation existante (tel que renvoyé par GET /mobile/v1/conversations).
class Conversation {
  const Conversation({
    required this.threadId,
    this.title,
    this.lastSeen,
  });

  factory Conversation.fromJson(Map<String, dynamic> json) {
    DateTime? parsed;
    final raw = json['last_seen'];
    if (raw is num) {
      // Backend epoch (seconds) — thread_activity.last_seen.
      parsed = DateTime.fromMillisecondsSinceEpoch((raw * 1000).round());
    } else if (raw is String) {
      parsed = DateTime.tryParse(raw);
    }
    return Conversation(
      threadId: asString(json['thread_id']) ?? '',
      title: asString(json['title']),
      lastSeen: parsed,
    );
  }

  final String threadId;
  final String? title;
  final DateTime? lastSeen;
}

/// Message d'historique (GET /conversations/{thread_id}/messages) :
/// simple texte + rôle, rejoué tel quel dans les bulles.
class HistoryMessage {
  const HistoryMessage({required this.fromUser, required this.text});

  factory HistoryMessage.fromJson(Map<String, dynamic> json) =>
      HistoryMessage(
        fromUser: (asString(json['role']) ?? '').toLowerCase() == 'user',
        text: asString(json['text']) ?? '',
      );

  final bool fromUser;
  final String text;
}

/// Avertissement IA ajouté en fin de réponse par le backend
/// (app/api/chat.py). L'historique le stocke dans chaque message : on le
/// retire à la restauration pour ne pas le répéter sur chaque bulle.
const aiDisclaimer =
    '⚠️ Attention : ce texte est généré par IA. Vérifiez les informations avant toute décision ou action.';

/// Retire l'avertissement IA terminal d'un message restauré.
/// Renvoie le texte inchangé s'il n'est pas présent ; peut renvoyer une
/// chaîne vide si le message ne contenait que l'avertissement (l'appelant
/// filtre alors le message).
String stripAiDisclaimer(String text) {
  final idx = text.lastIndexOf(aiDisclaimer);
  if (idx == -1) return text;
  return text.substring(0, idx).trimRight();
}

/// Message local affiché dans une bulle de chat.
class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.text,
    required this.fromUser,
    this.imagesBase64 = const <String>[],
    this.caption,
    this.createdAt,
  });

  final String id;
  final String text;
  final bool fromUser;
  final List<String> imagesBase64;
  final String? caption;
  final DateTime? createdAt;
}
