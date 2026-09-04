import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/ui.dart';
import 'market_models.dart';
import 'market_providers.dart';
import 'market_repository.dart';

/// Fiche détaillée d'un courtier agréé (SGI) : conditions, présence
/// régionale et contacts (appel / site web en un geste).
class BrokerDetailScreen extends ConsumerWidget {
  const BrokerDetailScreen({super.key, required this.id});

  final int id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final broker = ref.watch(brokerProvider(id));
    return Scaffold(
      appBar: const KoraAppBar(title: Text('SGI')),
      body: broker.when(
        loading: () => const LoadingView(message: 'Chargement de la SGI…'),
        error: (error, _) {
          // 404 : la SGI n'existe pas (ou plus).
          if (error is BrokerNotFoundException) {
            return const EmptyView(
              message: 'SGI introuvable.',
              icon: Icons.business_outlined,
            );
          }
          return ErrorView(
            message: 'Impossible de charger la SGI.\n$error',
            onRetry: () => ref.invalidate(brokerProvider(id)),
          );
        },
        data: (b) => _BrokerView(broker: b),
      ),
    );
  }
}

class _BrokerView extends StatelessWidget {
  const _BrokerView({required this.broker});

  final BrokerEntry broker;

  Future<void> _open(BuildContext context, Uri uri, String errorMessage) async {
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(errorMessage)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;

    final location = <String>[
      if (broker.country != null) broker.country!,
      if (broker.countryCode != null) broker.countryCode!,
    ].join(' · ');

    final hasConditions = broker.minAmount != null ||
        broker.note != null ||
        broker.info != null ||
        broker.detailText != null ||
        broker.otherCountries.isNotEmpty;
    final hasContact = broker.address != null ||
        broker.phone != null ||
        broker.email != null ||
        broker.url != null;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: <Widget>[
        // En-tête : nom + pays.
        Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border:
                Border.all(color: colors.outlineVariant.withValues(alpha: 0.75)),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: <Color>[
                Color.alphaBlend(colors.primary.withValues(alpha: 0.10),
                    theme.cardTheme.color ?? colors.surface),
                theme.cardTheme.color ?? colors.surface,
              ],
            ),
          ),
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                broker.name ?? 'Courtier',
                style: theme.textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              if (location.isNotEmpty) ...<Widget>[
                const SizedBox(height: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: colors.surfaceContainerHighest
                        .withValues(alpha: 0.55),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                        color: colors.outlineVariant.withValues(alpha: 0.6)),
                  ),
                  child: Text(
                    location,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: colors.muted,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
        if (broker.phone != null || broker.url != null) ...<Widget>[
          const SizedBox(height: 12),
          Row(
            children: <Widget>[
              if (broker.phone != null) ...<Widget>[
                Expanded(
                  child: FilledButton.tonalIcon(
                    onPressed: () => _open(
                      context,
                      Uri.parse('tel:${broker.phone}'),
                      'Impossible de lancer l’appel.',
                    ),
                    icon: const Icon(Icons.call_outlined),
                    label: const Text('Appeler'),
                  ),
                ),
                if (broker.url != null) const SizedBox(width: 12),
              ],
              if (broker.url != null)
                Expanded(
                  child: FilledButton.tonalIcon(
                    onPressed: () {
                      final raw = broker.url!;
                      final uri = Uri.tryParse(raw);
                      if (uri == null) return;
                      _open(
                        context,
                        uri.scheme.isEmpty
                            ? Uri.parse('https://$raw')
                            : uri,
                        'Impossible d’ouvrir le site web.',
                      );
                    },
                    icon: const Icon(Icons.open_in_new),
                    label: const Text('Site web'),
                  ),
                ),
            ],
          ),
        ],
        if (hasConditions) ...<Widget>[
          const SizedBox(height: 12),
          _CardSection(
            title: 'Conditions & informations',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                if (broker.minAmount != null)
                  _InfoRow(label: 'Montant minimum', value: broker.minAmount!),
                if (broker.note != null)
                  _InfoRow(label: 'Note', value: broker.note!),
                if (broker.info != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Text(
                      broker.info!,
                      style: theme.textTheme.bodyMedium?.copyWith(height: 1.5),
                    ),
                  ),
                if (broker.detailText != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Text(
                      broker.detailText!,
                      style: theme.textTheme.bodyMedium?.copyWith(height: 1.5),
                    ),
                  ),
                if (broker.otherCountries.isNotEmpty)
                  _InfoRow(
                    label: 'Aussi présent en',
                    value: broker.otherCountries.join(' · '),
                  ),
              ],
            ),
          ),
        ],
        if (hasContact) ...<Widget>[
          const SizedBox(height: 12),
          _CardSection(
            title: 'Contact',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                if (broker.address != null)
                  _ContactRow(
                    icon: Icons.place_outlined,
                    text: broker.address!,
                    multiLine: true,
                  ),
                if (broker.phone != null)
                  _ContactRow(
                    icon: Icons.call_outlined,
                    text: broker.phone!,
                    onTap: () => _open(
                      context,
                      Uri.parse('tel:${broker.phone}'),
                      'Impossible de lancer l’appel.',
                    ),
                  ),
                if (broker.email != null)
                  _ContactRow(
                    icon: Icons.mail_outline,
                    text: broker.email!,
                    onTap: () => _open(
                      context,
                      Uri.parse('mailto:${broker.email}'),
                      'Impossible d’ouvrir la messagerie.',
                    ),
                  ),
                if (broker.url != null)
                  _ContactRow(
                    icon: Icons.language,
                    text: broker.url!,
                    trailing: const Icon(Icons.open_in_new, size: 16),
                    onTap: () {
                      final raw = broker.url!;
                      final uri = Uri.tryParse(raw);
                      if (uri == null) return;
                      _open(
                        context,
                        uri.scheme.isEmpty
                            ? Uri.parse('https://$raw')
                            : uri,
                        'Impossible d’ouvrir le site web.',
                      );
                    },
                  ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 24),
      ],
    );
  }
}

/// Carte de section (titre accentué + contenu).
class _CardSection extends StatelessWidget {
  const _CardSection({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              title,
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w700,
                color: theme.colorScheme.primary,
              ),
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

/// Ligne libellé / valeur alignée.
class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            flex: 2,
            child: Text(
              label,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.muted),
            ),
          ),
          Expanded(
            flex: 3,
            child: Text(value, style: theme.textTheme.bodyMedium),
          ),
        ],
      ),
    );
  }
}

/// Ligne de contact avec icône ; `onTap` rend la ligne tappable
/// (téléphone, e-mail, site web).
class _ContactRow extends StatelessWidget {
  const _ContactRow({
    required this.icon,
    required this.text,
    this.multiLine = false,
    this.trailing,
    this.onTap,
  });

  final IconData icon;
  final String text;
  final bool multiLine;
  final Widget? trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final row = Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment:
            multiLine ? CrossAxisAlignment.start : CrossAxisAlignment.center,
        children: <Widget>[
          Icon(icon, size: 18, color: colors.muted),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              text,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: onTap != null ? null : colors.muted),
            ),
          ),
          if (trailing != null) ...<Widget>[
            const SizedBox(width: 8),
            trailing!,
          ],
        ],
      ),
    );
    if (onTap == null) return row;
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: row,
    );
  }
}
