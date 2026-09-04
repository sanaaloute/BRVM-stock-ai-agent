import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/ui.dart';
import 'market_models.dart';
import 'market_providers.dart';
import 'market_repository.dart';

/// Lecteur in-app d'un article d'actualité (le site source bloque souvent
/// les navigateurs mobiles : le backend sert le contenu).
class ArticleScreen extends ConsumerWidget {
  const ArticleScreen({super.key, required this.url});

  /// URL (déjà décodée) de l'article à lire.
  final String url;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final article = ref.watch(articleProvider(url));
    return Scaffold(
      appBar: const KoraAppBar(title: Text('Actualité')),
      body: article.when(
        loading: () => const LoadingView(message: 'Chargement de l’article…'),
        error: (error, _) => ErrorView(
          message: error is ArticleFetchException
              ? error.message
              : 'Impossible de charger l’article.\n$error',
          onRetry: () => ref.invalidate(articleProvider(url)),
        ),
        data: (a) => _ArticleView(article: a, fallbackUrl: url),
      ),
    );
  }
}

class _ArticleView extends StatelessWidget {
  const _ArticleView({required this.article, required this.fallbackUrl});

  final NewsArticle article;
  final String fallbackUrl;

  Future<void> _openSource(BuildContext context) async {
    final raw = article.url ?? fallbackUrl;
    final uri = Uri.tryParse(raw);
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
    final colors = theme.colorScheme;
    final body = theme.textTheme.bodyMedium
        ?.copyWith(color: colors.onSurface, height: 1.4);
    final styleSheet = MarkdownStyleSheet.fromTheme(theme).copyWith(
      p: body,
      listBullet: body,
      h1: body?.copyWith(fontSize: 18, fontWeight: FontWeight.bold),
      h2: body?.copyWith(fontSize: 16, fontWeight: FontWeight.bold),
      h3: body?.copyWith(fontSize: 15, fontWeight: FontWeight.bold),
      a: body?.copyWith(
        color: colors.primary,
        decoration: TextDecoration.underline,
      ),
    );

    final text = article.text ?? '';
    final date = article.date;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: <Widget>[
        if (article.title != null)
          Text(
            article.title!,
            style: theme.textTheme.headlineSmall
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
        if (date != null && date.isNotEmpty) ...<Widget>[
          const SizedBox(height: 6),
          Text(
            date,
            style: theme.textTheme.bodySmall?.copyWith(color: colors.muted),
          ),
        ],
        const SizedBox(height: 16),
        if (text.isEmpty)
          Text(
            'Contenu indisponible.',
            style: body?.copyWith(color: colors.muted),
          )
        else
          MarkdownBody(
            data: text,
            styleSheet: styleSheet,
            onTapLink: (text, href, title) async {
              if (href == null) return;
              final uri = Uri.tryParse(href);
              if (uri == null) return;
              try {
                await launchUrl(uri, mode: LaunchMode.externalApplication);
              } catch (_) {
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                        content: Text('Impossible d’ouvrir le lien.')),
                  );
                }
              }
            },
          ),
        const SizedBox(height: 32),
        Center(
          child: TextButton.icon(
            onPressed: () => _openSource(context),
            icon: Icon(Icons.open_in_new,
                size: 16, color: colors.muted),
            label: Text(
              'Ouvrir la source dans le navigateur',
              style: theme.textTheme.bodySmall?.copyWith(color: colors.muted),
            ),
          ),
        ),
        const SizedBox(height: 16),
      ],
    );
  }
}
