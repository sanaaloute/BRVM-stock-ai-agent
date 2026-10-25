import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/ui.dart';
import 'chat_models.dart';
import 'chat_providers.dart';

/// Écran de conversation avec l'assistant IA.
///
/// L'appel peut prendre jusqu'à 5 minutes : un indicateur de saisie
/// (et un message de progression) est affiché pendant l'attente.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key, this.threadId});

  /// `null` pour une nouvelle conversation.
  final String? threadId;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();

  /// Clé de la famille chatProvider. Conversation vierge : dépend de
  /// [chatEpochProvider] pour renaître vierge à chaque « Nouvelle
  /// discussion »; conversation existante : son threadId.
  late String _threadKey;

  @override
  void dispose() {
    _inputController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
      }
    });
  }

  Future<void> _send() async {
    final text = _inputController.text;
    if (text.trim().isEmpty) return;
    _inputController.clear();
    await ref.read(chatProvider(_threadKey).notifier).send(text);
    _scrollToBottom();
  }

  /// Nouvelle conversation : l'epoch force une session vierge sur l'écran
  /// racine ; depuis le fil d'une conversation existante, on y revient.
  void _newConversation() {
    ref.read(chatEpochProvider.notifier).state++;
    if (widget.threadId != null && widget.threadId != 'nouveau') {
      context.go('/chat');
    }
  }

  @override
  Widget build(BuildContext context) {
    // Conversation vierge : une nouvelle « session » par epoch, pour que
    // « Nouvelle discussion » (depuis l'historique) reparte à zéro.
    final epoch = ref.watch(chatEpochProvider);
    _threadKey = (widget.threadId == null || widget.threadId == 'nouveau')
        ? 'new-$epoch'
        : widget.threadId!;

    final chat = ref.watch(chatProvider(_threadKey));

    ref.listen(chatProvider(_threadKey), (_, _) => _scrollToBottom());

    return Scaffold(
      appBar: KoraAppBar(
        title: const Text('Kora'),
        actions: <Widget>[
          IconButton(
            key: const Key('chat-new'),
            tooltip: 'Nouvelle discussion',
            icon: const Icon(Icons.add_comment_outlined),
            onPressed: _newConversation,
          ),
          IconButton(
            tooltip: 'Historique',
            icon: const Icon(Icons.history_outlined),
            onPressed: () => context.push('/chat/historique'),
          ),
        ],
      ),
      body: Column(
        children: <Widget>[
          Expanded(
            child: chat.isLoadingHistory && chat.messages.isEmpty
                ? const LoadingView(message: 'Chargement de la conversation…')
                : chat.messages.isEmpty
                    ? _ChatHint(
                        onSuggestion: (s) => _inputController.text = s,
                      )
                    : ListView.builder(
                        controller: _scrollController,
                        padding: const EdgeInsets.all(12),
                        itemCount: chat.messages.length +
                            (chat.isSending ? 1 : 0) +
                            (chat.error != null ? 1 : 0),
                        itemBuilder: (context, index) {
                          if (index < chat.messages.length) {
                            return _MessageBubble(message: chat.messages[index]);
                          }
                          if (chat.isSending) {
                            return const _WaitingIndicator();
                          }
                          return _ErrorBubble(message: chat.error!);
                        },
                      ),
          ),
          const Divider(height: 1),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: TextField(
                      key: const Key('chat-input'),
                      controller: _inputController,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                      minLines: 1,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        hintText: 'Posez votre question…',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    key: const Key('chat-send'),
                    onPressed: chat.isSending ? null : _send,
                    icon: const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ChatHint extends ConsumerWidget {
  const _ChatHint({required this.onSuggestion});

  /// Remplit le champ de saisie avec la suggestion touchée.
  final ValueChanged<String> onSuggestion;

  /// Secours pendant le chargement ou si le serveur ne répond pas.
  static const _fallback = <String>[
    'Quel est le palmarès du jour ?',
    'Analyse-moi l\'action SONATEL',
    'Quelles sont les perspectives du secteur bancaire ?',
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final fetched = ref.watch(chatSuggestionsProvider).valueOrNull;
    final suggestions =
        (fetched == null || fetched.isEmpty) ? _fallback : fetched;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.smart_toy_outlined,
                size: 56, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 12),
            Text(
              'Posez vos questions à Kora : cotations, analyses, conseils…',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 20),
            for (final suggestion in suggestions)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: ActionChip(
                  label: Text(suggestion),
                  onPressed: () => onSuggestion(suggestion),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final alignment =
        message.fromUser ? Alignment.centerRight : Alignment.centerLeft;
    final bubbleColor = message.fromUser ? colors.primary : colors.surfaceContainerHighest;
    final textColor = message.fromUser ? colors.onPrimary : colors.onSurface;

    final images = message.imagesBase64
        .map((raw) {
          try {
            return Image.memory(
              base64Decode(raw),
              fit: BoxFit.contain,
              errorBuilder: (_, _, _) => const Icon(Icons.broken_image),
            );
          } catch (_) {
            return const Icon(Icons.broken_image);
          }
        })
        .toList();

    return Align(
      alignment: alignment,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.82,
        ),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(message.fromUser ? 16 : 4),
            bottomRight: Radius.circular(message.fromUser ? 4 : 16),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            if (message.text.isNotEmpty)
              message.fromUser
                  ? Text(message.text, style: TextStyle(color: textColor))
                  : _AssistantMarkdown(text: message.text, color: textColor),
            for (final image in images) ...<Widget>[
              const SizedBox(height: 8),
              ClipRRect(borderRadius: BorderRadius.circular(8), child: image),
            ],
            if (message.caption != null && images.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  message.caption!,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: textColor.withValues(alpha: 0.8)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Texte markdown de l'assistant (réponses live comme historique restauré) :
/// gras, listes, liens cliquables ; la couleur suit la bulle.
class _AssistantMarkdown extends StatelessWidget {
  const _AssistantMarkdown({required this.text, required this.color});

  final String text;
  final Color color;

  Future<void> _openLink(BuildContext context, String? href) async {
    if (href == null) return;
    final uri = Uri.tryParse(href);
    if (uri == null) return;
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Impossible d’ouvrir le lien.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final base = theme.textTheme.bodyMedium?.copyWith(color: color);
    final styleSheet =
        MarkdownStyleSheet.fromTheme(theme).copyWith(
      p: base,
      listBullet: base,
      h1: base?.copyWith(fontSize: 18, fontWeight: FontWeight.bold),
      h2: base?.copyWith(fontSize: 16, fontWeight: FontWeight.bold),
      h3: base?.copyWith(fontSize: 15, fontWeight: FontWeight.bold),
      blockquote: base?.copyWith(color: color.withValues(alpha: 0.8)),
      blockquoteDecoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        border: Border(
          left: BorderSide(color: color.withValues(alpha: 0.3), width: 3),
        ),
      ),
      a: base?.copyWith(
        color: theme.colorScheme.primary,
        decoration: TextDecoration.underline,
      ),
      tableBody: base,
      tableHead: base?.copyWith(fontWeight: FontWeight.bold),
    );
    return MarkdownBody(
      data: text,
      styleSheet: styleSheet,
      onTapLink: (text, href, title) => _openLink(context, href),
    );
  }
}

/// Indicateur d'attente de la réponse : mini-graphique animé (barres qui
/// pulsent comme un cours), messages rotatifs (progression + humour) et
/// compteur de secondes. Au-delà de ~45 s, les messages reconnaissent
/// l'attente sans l'ancien libellé « cela peut prendre quelques minutes ».
class _WaitingIndicator extends StatefulWidget {
  const _WaitingIndicator();

  @override
  State<_WaitingIndicator> createState() => _WaitingIndicatorState();
}

class _WaitingIndicatorState extends State<_WaitingIndicator>
    with SingleTickerProviderStateMixin {
  static const _messages = <String>[
    'Kora consulte le palmarès du jour…',
    'Analyse des tendances du marché…',
    'Le marché réfléchit, et vous ?',
    'On secoue les données pour qu’elles parlent…',
    'Recherche des chiffres qui comptent…',
    'La BRVM n’a jamais été aussi lue…',
  ];

  static const _patientMessages = <String>[
    'Encore un instant, la réponse arrive…',
    'Les bonnes analyses demandent un peu de temps…',
    'On y est presque…',
  ];

  late final AnimationController _barsController;
  late final Timer _ticker;
  int _elapsed = 0;

  @override
  void initState() {
    super.initState();
    _barsController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat();
    // Un tick par seconde : fait tourner les messages (toutes les 3 s) et le
    // compteur. Le compteur interne (et non DateTime.now) garde le widget
    // testable avec le temps simulé de flutter_test.
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _elapsed++);
    });
  }

  @override
  void dispose() {
    _barsController.dispose();
    _ticker.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final messages = _elapsed >= 45 ? _patientMessages : _messages;
    final message = messages[(_elapsed ~/ 3) % messages.length];
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: colors.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _MarketBars(animation: _barsController),
            const SizedBox(width: 14),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 350),
                    transitionBuilder: (child, animation) => FadeTransition(
                      opacity: animation,
                      child: SlideTransition(
                        position: Tween<Offset>(
                          begin: const Offset(0, 0.3),
                          end: Offset.zero,
                        ).animate(animation),
                        child: child,
                      ),
                    ),
                    child: Text(
                      message,
                      key: ValueKey<String>(message),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '$_elapsed s',
                    style: Theme.of(context)
                        .textTheme
                        .labelSmall
                        ?.copyWith(color: colors.muted),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Mini-graphique animé : des barres qui montent et descendent comme un
/// cours de bourse (la dernière en doré, accent de la palette).
class _MarketBars extends StatelessWidget {
  const _MarketBars({required this.animation});

  final Animation<double> animation;

  static const _barCount = 7;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return AnimatedBuilder(
      animation: animation,
      builder: (context, _) {
        return SizedBox(
          height: 30,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: List<Widget>.generate(_barCount, (i) {
              final phase = animation.value * 2 * math.pi + i * 0.65;
              final level = 0.5 + 0.5 * math.sin(phase); // 0..1
              return Padding(
                padding: EdgeInsets.only(left: i == 0 ? 0 : 3.5),
                child: Container(
                  width: 5.5,
                  height: 7 + level * 23,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(2.5),
                    color: (i == _barCount - 1
                            ? colors.secondary
                            : colors.primary)
                        .withValues(alpha: 0.45 + 0.55 * level),
                  ),
                ),
              );
            }),
          ),
        );
      },
    );
  }
}

class _ErrorBubble extends StatelessWidget {
  const _ErrorBubble({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: colors.errorContainer,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.error_outline, size: 18, color: colors.onErrorContainer),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                message,
                style: TextStyle(color: colors.onErrorContainer),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
