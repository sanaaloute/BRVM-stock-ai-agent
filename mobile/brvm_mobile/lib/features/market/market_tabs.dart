import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import '../watchlist/watchlist_providers.dart';
import 'market_models.dart';
import 'market_providers.dart';

/// Liste de suivi (watchlist) : onglet du marché.
class WatchlistTab extends ConsumerWidget {
  const WatchlistTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final watchlist = ref.watch(watchlistProvider);
    return Scaffold(
      body: watchlist.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(
          message: 'Impossible de charger votre liste de suivi.\n$error',
          onRetry: () => ref.invalidate(watchlistProvider),
        ),
        data: (entries) {
          if (entries.isEmpty) {
            return RefreshIndicator(
              onRefresh: () async => ref.invalidate(watchlistProvider),
              child: _WatchlistEmptyView(
                onAdd: () => _showAddDialog(context, ref),
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(watchlistProvider),
            child: ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              itemCount: entries.length,
              separatorBuilder: (_, _) => const Divider(height: 1, indent: 16),
              itemBuilder: (_, index) {
                final entry = entries[index];
                return Dismissible(
                  key: ValueKey('watchlist-${entry.symbol}'),
                  direction: DismissDirection.endToStart,
                  background: Container(
                    color: Theme.of(context).colorScheme.error,
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.only(right: 24),
                    child: const Icon(Icons.delete_outline, color: Colors.white),
                  ),
                  confirmDismiss: (_) async => _confirmRemove(context, entry.symbol),
                  onDismissed: (_) => ref
                      .read(watchlistProvider.notifier)
                      .remove(entry.symbol),
                  child: ListTile(
                    leading: const Icon(Icons.star),
                    title: Text(
                      entry.symbol,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    trailing: PriceText(entry.price),
                    onTap: () => context.push('/marche/symbol/${entry.symbol}'),
                  ),
                );
              },
            ),
          );
        },
      ),
      floatingActionButton: FloatingActionButton.small(
        heroTag: 'watchlist-fab',
        onPressed: () => _showAddDialog(context, ref),
        child: const Icon(Icons.add),
      ),
    );
  }

  Future<bool> _confirmRemove(BuildContext context, String symbol) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Retirer $symbol ?'),
        content: const Text('Ce titre sera retiré de votre liste de suivi.'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Retirer'),
          ),
        ],
      ),
    );
    return result ?? false;
  }

  Future<void> _showAddDialog(BuildContext context, WidgetRef ref) async {
    final symbols = ref
            .read(palmaresSymbolsProvider)
            .valueOrNull ??
        const <String>[];
    final controller = TextEditingController();
    final formKey = GlobalKey<FormState>();
    String? error;

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (context, setState) {
            return AlertDialog(
              title: const Text('Ajouter un titre'),
              content: Form(
                key: formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    if (symbols.isNotEmpty)
                      Autocomplete<String>(
                        optionsBuilder: (textEditingValue) {
                          final query = textEditingValue.text.toUpperCase();
                          if (query.isEmpty) return symbols;
                          return symbols
                              .where((s) => s.contains(query))
                              .toList();
                        },
                        onSelected: (value) => controller.text = value,
                        fieldViewBuilder: (context, fieldController, focusNode, _) {
                          // On réutilise le contrôleur externe pour la validation.
                          fieldController.text = controller.text;
                          fieldController.addListener(() {
                            controller.text = fieldController.text;
                          });
                          return TextFormField(
                            controller: fieldController,
                            focusNode: focusNode,
                            textCapitalization: TextCapitalization.characters,
                            decoration: const InputDecoration(
                              labelText: 'Symbole (ex. SONATEL)',
                              border: OutlineInputBorder(),
                            ),
                            validator: (value) {
                              final v = value?.trim() ?? '';
                              if (v.isEmpty) return 'Saisissez un symbole.';
                              if (!RegExp(r'^[A-Za-z0-9&.\- ]{1,15}$')
                                  .hasMatch(v)) {
                                return 'Symbole invalide.';
                              }
                              return null;
                            },
                          );
                        },
                      )
                    else
                      TextFormField(
                        controller: controller,
                        textCapitalization: TextCapitalization.characters,
                        decoration: const InputDecoration(
                          labelText: 'Symbole (ex. SONATEL)',
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) =>
                            (value == null || value.trim().isEmpty)
                                ? 'Saisissez un symbole.'
                                : null,
                      ),
                    if (error != null) FormError(message: error!),
                  ],
                ),
              ),
              actions: <Widget>[
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('Annuler'),
                ),
                FilledButton(
                  onPressed: () async {
                    if (!(formKey.currentState?.validate() ?? false)) return;
                    final symbol = controller.text.trim().toUpperCase();
                    final message = await ref
                        .read(watchlistProvider.notifier)
                        .add(symbol);
                    if (!dialogContext.mounted) return;
                    if (message == null) {
                      Navigator.of(dialogContext).pop();
                    } else {
                      setState(() => error = message);
                    }
                  },
                  child: const Text('Ajouter'),
                ),
              ],
            );
          },
        );
      },
    );
    controller.dispose();
  }
}

/// État vide de la liste de suivi : explication + bouton d'ajout.
class _WatchlistEmptyView extends StatelessWidget {
  const _WatchlistEmptyView({required this.onAdd});

  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(Icons.star_outline, size: 48, color: colors.muted),
                  const SizedBox(height: 12),
                  Text(
                    'Votre liste de suivi est vide.',
                    style: theme.textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Suivez des actions pour les retrouver ici.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(color: colors.muted),
                  ),
                  const SizedBox(height: 16),
                  FilledButton.tonalIcon(
                    onPressed: onAdd,
                    icon: const Icon(Icons.star_outline),
                    label: const Text('Ajouter un titre'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Courtiers agréés : onglet du marché — recherche par nom + filtre pays.
class BrokersTab extends ConsumerStatefulWidget {
  const BrokersTab({super.key});

  @override
  ConsumerState<BrokersTab> createState() => _BrokersTabState();
}

class _BrokersTabState extends ConsumerState<BrokersTab> {
  final _searchController = TextEditingController();
  String _query = '';
  String? _country;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<BrokerEntry> _apply(List<BrokerEntry> brokers) {
    final query = normalizeForSearch(_query.trim());
    return brokers.where((broker) {
      if (_country != null && broker.country != _country) return false;
      if (query.isEmpty) return true;
      return broker.name != null &&
          normalizeForSearch(broker.name!).contains(query);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final brokers = ref.watch(brokersProvider);
    return brokers.when(
      loading: () => const LoadingView(),
      error: (error, _) => ErrorView(
        message: 'Impossible de charger les SGI.\n$error',
        onRetry: () => ref.invalidate(brokersProvider),
      ),
      data: (all) {
        final countries = all
            .map((b) => b.country)
            .whereType<String>()
            .toSet()
            .toList()
          ..sort();
        // Pays sélectionné disparu de la liste (rechargement) : réinitialise.
        if (_country != null && !countries.contains(_country)) {
          _country = null;
        }
        final visible = _apply(all);
        return Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: TextField(
                controller: _searchController,
                onChanged: (value) => setState(() => _query = value),
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  hintText: 'Rechercher une SGI…',
                  prefixIcon: const Icon(Icons.search),
                  isDense: true,
                  suffixIcon: _query.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.clear),
                          tooltip: 'Effacer',
                          onPressed: () {
                            _searchController.clear();
                            setState(() => _query = '');
                          },
                        ),
                ),
              ),
            ),
            if (countries.isNotEmpty)
              SizedBox(
                height: 48,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  children: <Widget>[
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: const Text('Tous'),
                        showCheckmark: false,
                        selected: _country == null,
                        onSelected: (_) => setState(() => _country = null),
                      ),
                    ),
                    for (final country in countries)
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: FilterChip(
                          label: Text(country),
                          showCheckmark: false,
                          selected: _country == country,
                          onSelected: (_) =>
                              setState(() => _country = country),
                        ),
                      ),
                  ],
                ),
              ),
            Expanded(
              child: visible.isEmpty
                  ? EmptyView(
                      message: all.isEmpty
                          ? 'Aucune donnée SGI disponible. Réessayez.'
                          : 'Aucune SGI ne correspond à votre recherche.',
                      icon: Icons.business_outlined,
                      onRetry: all.isEmpty
                          ? () => ref.invalidate(brokersProvider)
                          : null,
                    )
                  : RefreshIndicator(
                      onRefresh: () async => ref.invalidate(brokersProvider),
                      child: ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: visible.length,
                        separatorBuilder: (_, _) =>
                            const Divider(height: 1, indent: 16),
                        itemBuilder: (_, index) {
                          final broker = visible[index];
                          final theme = Theme.of(context);
                          final name = broker.name ?? 'Courtier';
                          final location = <String>[
                            if (broker.country != null) broker.country!,
                            if (broker.phone != null) broker.phone!,
                          ].join(' · ');
                          return ListTile(
                            leading: const Icon(Icons.business_outlined),
                            title: Text(name),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                if (location.isNotEmpty) Text(location),
                                if (broker.note != null)
                                  Text(
                                    broker.note!,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: theme.textTheme.bodySmall?.copyWith(
                                        color: theme.colorScheme.muted),
                                  ),
                              ],
                            ),
                            isThreeLine:
                                broker.note != null && location.isNotEmpty,
                            trailing: broker.id != null
                                ? Icon(Icons.chevron_right,
                                    color: theme.colorScheme.muted)
                                : null,
                            // La fiche détail (in-app) porte les actions
                            // appel / site web.
                            onTap: broker.id != null
                                ? () =>
                                    context.push('/marche/courtier/${broker.id}')
                                : null,
                          );
                        },
                      ),
                    ),
            ),
          ],
        );
      },
    );
  }
}

/// Actualités : onglet du marché.
class NewsTab extends ConsumerWidget {
  const NewsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final news = ref.watch(newsProvider);
    return news.when(
      loading: () => const LoadingView(),
      error: (error, _) => ErrorView(
        message: 'Impossible de charger les actualités.\n$error',
        onRetry: () => ref.invalidate(newsProvider),
      ),
      data: (feed) {
        // Section en erreur sans aucun item : erreur + réessai.
        if (feed.items.isEmpty && feed.error != null) {
          return ErrorView(
            message: feed.error!,
            onRetry: () => ref.invalidate(newsProvider),
          );
        }
        if (feed.items.isEmpty) {
          return const EmptyView(
            message: 'Aucune actualité pour le moment.',
            icon: Icons.newspaper_outlined,
          );
        }
        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(newsProvider),
          child: ListView.builder(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.symmetric(vertical: 8),
            itemCount: feed.items.length + (feed.warning != null ? 1 : 0),
            itemBuilder: (context, index) {
              if (feed.warning != null && index == 0) {
                return _NewsWarningBanner(warning: feed.warning!);
              }
              final item = feed.items[index - (feed.warning != null ? 1 : 0)];
              final theme = Theme.of(context);
              return ListTile(
                leading: const Icon(Icons.article_outlined),
                title: Text(item.title ?? 'Actualité'),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    if (item.date != null)
                      Text(
                        item.date!,
                        style: theme.textTheme.labelSmall
                            ?.copyWith(color: theme.colorScheme.muted),
                      ),
                    if (item.summary != null)
                      Text(
                        item.summary!,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: theme.colorScheme.muted),
                      ),
                  ],
                ),
                isThreeLine: item.summary != null,
                // Lecture in-app : le lecteur d'article (le site source
                // bloque souvent les navigateurs mobiles).
                onTap: item.url != null
                    ? () => context.push(Uri(
                          path: '/marche/actualite',
                          queryParameters: <String, String>{'url': item.url!},
                        ).toString())
                    : null,
              );
            },
          ),
        );
      },
    );
  }
}

/// Bannière d'avertissement (source de repli) en tête de liste.
class _NewsWarningBanner extends StatelessWidget {
  const _NewsWarningBanner({required this.warning});

  final String warning;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.outlineVariant.withValues(alpha: 0.6)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Icon(Icons.info_outline, size: 16, color: colors.muted),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              warning,
              style: theme.textTheme.bodySmall?.copyWith(color: colors.muted),
            ),
          ),
        ],
      ),
    );
  }
}
