import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import 'chat_providers.dart';

/// Liste des conversations passées avec l'assistant.
class ConversationsScreen extends ConsumerWidget {
  const ConversationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final conversations = ref.watch(conversationsProvider);
    return Scaffold(
      appBar: const KoraAppBar(title: Text('Kora')),
      body: conversations.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(
          message: 'Impossible de charger les conversations.\n$error',
          onRetry: () => ref.invalidate(conversationsProvider),
        ),
        data: (items) {
          if (items.isEmpty) {
            return const EmptyView(
              message: 'Aucune conversation.\nPosez votre première question à l’assistant !',
              icon: Icons.chat_bubble_outline,
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(conversationsProvider),
            child: ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              itemCount: items.length,
              separatorBuilder: (_, _) => const Divider(height: 1, indent: 16),
              itemBuilder: (_, index) {
                final conversation = items[index];
                return ListTile(
                  leading: const Icon(Icons.forum_outlined),
                  title: Text(
                    conversation.title ?? 'Conversation',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(formatRelativeTime(conversation.lastSeen)),
                  trailing: IconButton(
                    icon: const Icon(Icons.delete_outline),
                    tooltip: 'Supprimer',
                    onPressed: () =>
                        _confirmDelete(context, ref, conversation.threadId),
                  ),
                  onTap: () =>
                      context.push('/chat/thread/${conversation.threadId}'),
                );
              },
            ),
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'chat-new',
        onPressed: () {
          // L'écran de chat sous-jacent renaît sur une conversation vierge.
          ref.read(chatEpochProvider.notifier).state++;
          if (context.canPop()) {
            context.pop();
          } else {
            context.go('/chat');
          }
        },
        icon: const Icon(Icons.add),
        label: const Text('Nouvelle discussion'),
      ),
    );
  }

  Future<void> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    String threadId,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Supprimer la conversation ?'),
        content: const Text('Cette action est définitive.'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      try {
        await ref
            .read(chatRepositoryProvider)
            .deleteConversation(threadId);
        ref.invalidate(conversationsProvider);
      } catch (_) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Suppression impossible.')),
          );
        }
      }
    }
  }
}
