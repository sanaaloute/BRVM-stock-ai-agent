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
    this.clarification = false,
    this.quotaRemaining,
    this.threadId,
    this.error,
  });

  factory ChatResponse.fromJson(Map<String, dynamic> json) => ChatResponse(
        reply: asString(json['reply']),
        imageBase64: asString(json['image_base64']),
        rawImagesBase64: asStringList(json['images_base64']),
        imageCaption: asString(json['image_caption']),
        // Booléen côté backend (app/api/chat.py) : le texte de clarification
        // voyage dans `reply`, ce champ ne fait que marquer le type de tour.
        clarification: asBool(json['clarification']),
        quotaRemaining: asInt(json['quota_remaining']),
        threadId: asString(json['thread_id']),
        error: asString(json['error']),
      );

  final String? reply;
  final String? imageBase64;
  final List<String> rawImagesBase64;
  final String? imageCaption;
  final bool clarification;
  final int? quotaRemaining;
  final String? threadId;
  final String? error;

  bool get isError => error != null && error!.isNotEmpty;

  /// Toutes les images de la réponse. Le champ liste prime : le serveur y
  /// met TOUTES les images et duplique la première dans `image_base64` pour
  /// les vieux clients — fusionner les deux afficherait la même image deux
  /// fois. Le champ unique ne sert que de repli (anciennes réponses).
  List<String> get imagesBase64 => rawImagesBase64.isNotEmpty
      ? rawImagesBase64
      : <String>[?imageBase64];

  /// Texte à afficher (les clarifications arrivent aussi dans `reply`).
  String? get displayText => reply;
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
    this.thinking,
    this.streaming = false,
    this.createdAt,
  });

  ChatMessage copyWith({
    String? text,
    String? thinking,
    bool? streaming,
    List<String>? imagesBase64,
    String? caption,
  }) =>
      ChatMessage(
        id: id,
        text: text ?? this.text,
        fromUser: fromUser,
        imagesBase64: imagesBase64 ?? this.imagesBase64,
        caption: caption ?? this.caption,
        thinking: thinking ?? this.thinking,
        streaming: streaming ?? this.streaming,
        createdAt: createdAt,
      );

  final String id;
  final String text;
  final bool fromUser;
  final List<String> imagesBase64;
  final String? caption;

  /// Raisonnement du modèle (événements `thinking` du flux SSE) : affiché
  /// replié dans la bulle, jamais mélangé à la réponse finale.
  final String? thinking;

  /// Vrai tant que la réponse est en cours de streaming (bulle progressive).
  final bool streaming;

  final DateTime? createdAt;
}

/// Types d'événements du flux SSE (POST /mobile/v1/chat/stream).
enum ChatStreamEventType { status, thinking, token, finalPayload, error }

/// Un événement du flux SSE de chat :
/// - status : quel agent travaille ([label] en français) ;
/// - thinking : fragment de raisonnement (à afficher replié) ;
/// - token : fragment de la réponse ;
/// - finalPayload : réponse canonique complète (remplace le texte progressif) ;
/// - error : message d'erreur prêt à afficher.
class ChatStreamEvent {
  const ChatStreamEvent._(
    this.type, {
    this.delta,
    this.label,
    this.response,
    this.error,
  });

  factory ChatStreamEvent.fromJson(Map<String, dynamic> json) {
    // Les deltas sont pris BRUTS (pas de asString : les espaces et sauts de
    // ligne portent le texte streamé, il ne faut rien rogner).
    final delta = json['delta'];
    switch ((asString(json['type']) ?? '').toLowerCase()) {
      case 'status':
        return ChatStreamEvent._(
          ChatStreamEventType.status,
          label: asString(json['label']),
        );
      case 'thinking':
        return ChatStreamEvent._(
          ChatStreamEventType.thinking,
          delta: delta is String ? delta : null,
        );
      case 'token':
        return ChatStreamEvent._(
          ChatStreamEventType.token,
          delta: delta is String ? delta : null,
        );
      case 'final':
        return ChatStreamEvent._(
          ChatStreamEventType.finalPayload,
          response: ChatResponse.fromJson(asMap(json['payload'])),
        );
      default:
        return ChatStreamEvent._(
          ChatStreamEventType.error,
          error: asString(json['error']) ?? 'Une erreur est survenue.',
        );
    }
  }

  final ChatStreamEventType type;
  final String? delta;
  final String? label;
  final ChatResponse? response;
  final String? error;
}
