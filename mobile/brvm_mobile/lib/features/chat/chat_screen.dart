import 'dart:convert';

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

    final quota = chat.quotaRemaining;
    return Scaffold(
      appBar: KoraAppBar(
        title: const Text('Kora'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Historique',
            icon: const Icon(Icons.history_outlined),
            onPressed: () => context.push('/chat/historique'),
          ),
        ],
        bottom: quota != null
            ? PreferredSize(
                preferredSize: const Size.fromHeight(18),
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(
                    'Quota restant : $quota',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              )
            : null,
      ),
      body: Column(
        children: <Widget>[
          Expanded(
            child: chat.isLoadingHistory && chat.messages.isEmpty
                ? const LoadingView(message: 'Chargement de la conversation…')
                : chat.messages.isEmpty
                    ? const _ChatHint()
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
                            return const _TypingIndicator();
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

class _ChatHint extends StatelessWidget {
  const _ChatHint();

  static const _suggestions = <String>[
    'Quel est le palmarès du jour ?',
    'Analyse-moi la action SONATEL',
    'Quelles sont les perspectives du secteur bancaire ?',
  ];

  @override
  Widget build(BuildContext context) {
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
            for (final suggestion in _suggestions)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: ActionChip(
                  label: Text(suggestion),
                  onPressed: () {
                    final state = context
                        .findAncestorStateOfType<_ChatScreenState>();
                    state?._inputController.text = suggestion;
                  },
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

class _TypingIndicator extends StatelessWidget {
  const _TypingIndicator();

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: colors.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const SizedBox(
              height: 16,
              width: 32,
              child: _Dots(),
            ),
            const SizedBox(height: 6),
            Text(
              'L’assistant analyse… (cela peut prendre quelques minutes)',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: colors.muted),
            ),
          ],
        ),
      ),
    );
  }
}

class _Dots extends StatefulWidget {
  const _Dots();

  @override
  State<_Dots> createState() => _DotsState();
}

class _DotsState extends State<_Dots> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: List<Widget>.generate(3, (i) {
            final offset = (_controller.value * 3 + i) % 3;
            final opacity = 0.3 + 0.7 * (1 - offset / 3);
            return Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Theme.of(context)
                    .colorScheme
                    .onSurface
                    .withValues(alpha: opacity),
              ),
            );
          }),
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
