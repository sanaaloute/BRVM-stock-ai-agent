import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import '../predictions/predictions_tab.dart';
import 'market_models.dart';
import 'market_providers.dart';
import 'market_tabs.dart';

/// Onglet « Marché » : actions (palmarès), prévisions IA, liste de suivi,
/// SGI et actualités.
class MarketScreen extends StatelessWidget {
  const MarketScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 5,
      child: Scaffold(
        appBar: const KoraAppBar(
          title: Text('Le Marché'),
          bottom: TabBar(
            isScrollable: true,
            // Material 3 décale les TabBar scrollables de 52 dp au départ
            // (TabAlignment.startOffset) : forcer l'alignement à gauche.
            tabAlignment: TabAlignment.start,
            padding: EdgeInsets.zero,
            tabs: <Widget>[
              Tab(text: 'Actions', icon: Icon(Icons.leaderboard_outlined)),
              Tab(text: 'Prévisions', icon: Icon(Icons.auto_graph_outlined)),
              Tab(text: 'Suivi', icon: Icon(Icons.star_outline)),
              Tab(text: 'SGI', icon: Icon(Icons.business_outlined)),
              Tab(text: 'Actualités', icon: Icon(Icons.newspaper_outlined)),
            ],
          ),
        ),
        body: const TabBarView(
          children: <Widget>[
            PalmaresTab(),
            PredictionsTab(),
            WatchlistTab(),
            BrokersTab(),
            NewsTab(),
          ],
        ),
      ),
    );
  }
}

enum _VariationFilter { all, up, down }

enum _PalmaresSort { alpha, variation, price }

/// Palmarès : recherche, filtre de variation et tri appliqués côté client.
class PalmaresTab extends ConsumerStatefulWidget {
  const PalmaresTab({super.key});

  @override
  ConsumerState<PalmaresTab> createState() => _PalmaresTabState();
}

class _PalmaresTabState extends ConsumerState<PalmaresTab> {
  final _searchController = TextEditingController();
  String _query = '';
  _VariationFilter _filter = _VariationFilter.all;
  _PalmaresSort _sort = _PalmaresSort.alpha;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<PalmaresStock> _apply(List<PalmaresStock> stocks) {
    final query = normalizeForSearch(_query.trim());
    final filtered = stocks.where((stock) {
      switch (_filter) {
        case _VariationFilter.up:
          if ((stock.variationPct ?? 0) <= 0) return false;
        case _VariationFilter.down:
          if ((stock.variationPct ?? 0) >= 0) return false;
        case _VariationFilter.all:
          break;
      }
      if (query.isEmpty) return true;
      return normalizeForSearch(stock.symbol).contains(query) ||
          (stock.name != null && normalizeForSearch(stock.name!).contains(query));
    }).toList();
    switch (_sort) {
      case _PalmaresSort.alpha:
        filtered.sort((a, b) => a.symbol.compareTo(b.symbol));
      case _PalmaresSort.variation:
        filtered.sort(
          (a, b) => (b.variationPct ?? -double.infinity)
              .compareTo(a.variationPct ?? -double.infinity),
        );
      case _PalmaresSort.price:
        filtered.sort(
          (a, b) => (b.coursActuel ?? -double.infinity)
              .compareTo(a.coursActuel ?? -double.infinity),
        );
    }
    return filtered;
  }

  @override
  Widget build(BuildContext context) {
    final palmares = ref.watch(palmaresProvider);
    return palmares.when(
      loading: () => const LoadingView(),
      error: (error, _) => ErrorView(
        message: 'Impossible de charger le palmarès.\n$error',
        onRetry: () => ref.invalidate(palmaresProvider),
      ),
      data: (stocks) {
        final visible = _apply(stocks);
        return Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: TextField(
                controller: _searchController,
                onChanged: (value) => setState(() => _query = value),
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  hintText: 'Rechercher un titre ou une société…',
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
            SizedBox(
              height: 48,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                children: <Widget>[
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      label: const Text('Toutes'),
                      showCheckmark: false,
                      selected: _filter == _VariationFilter.all,
                      onSelected: (_) =>
                          setState(() => _filter = _VariationFilter.all),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      avatar: Icon(Icons.arrow_upward,
                          size: 14,
                          color: _filter == _VariationFilter.up
                              ? Theme.of(context).colorScheme.gain
                              : null),
                      label: const Text('En hausse'),
                      showCheckmark: false,
                      selected: _filter == _VariationFilter.up,
                      onSelected: (_) =>
                          setState(() => _filter = _VariationFilter.up),
                    ),
                  ),
                  FilterChip(
                    avatar: Icon(Icons.arrow_downward,
                        size: 14,
                        color: _filter == _VariationFilter.down
                            ? Theme.of(context).colorScheme.loss
                            : null),
                    label: const Text('En baisse'),
                    showCheckmark: false,
                    selected: _filter == _VariationFilter.down,
                    onSelected: (_) =>
                        setState(() => _filter = _VariationFilter.down),
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 10),
                    child: VerticalDivider(width: 24),
                  ),
                  for (final sort in _PalmaresSort.values)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        avatar: Icon(switch (sort) {
                          _PalmaresSort.alpha => Icons.sort_by_alpha,
                          _PalmaresSort.variation => Icons.percent,
                          _PalmaresSort.price => Icons.payments_outlined,
                        }, size: 14),
                        label: Text(switch (sort) {
                          _PalmaresSort.alpha => 'A→Z',
                          _PalmaresSort.variation => 'Variation %',
                          _PalmaresSort.price => 'Cours',
                        }),
                        showCheckmark: false,
                        selected: _sort == sort,
                        onSelected: (_) => setState(() => _sort = sort),
                      ),
                    ),
                ],
              ),
            ),
            Expanded(
              child: visible.isEmpty
                  ? EmptyView(
                      message: stocks.isEmpty
                          ? 'Aucune cotation disponible pour le moment.'
                          : 'Aucun titre ne correspond à votre recherche.',
                      icon: Icons.leaderboard_outlined,
                      onRetry: stocks.isEmpty
                          ? () => ref.invalidate(palmaresProvider)
                          : null,
                    )
                  : RefreshIndicator(
                      onRefresh: () async => ref.invalidate(palmaresProvider),
                      child: ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: visible.length,
                        separatorBuilder: (_, _) =>
                            const Divider(height: 1, indent: 16),
                        itemBuilder: (_, index) =>
                            PalmaresTile(stock: visible[index]),
                      ),
                    ),
            ),
          ],
        );
      },
    );
  }
}

class PalmaresTile extends StatelessWidget {
  const PalmaresTile({super.key, required this.stock});

  final PalmaresStock stock;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(
        stock.symbol,
        style: const TextStyle(fontWeight: FontWeight.bold),
      ),
      // Le nom est renvoyé par le backend ; sinon pas de sous-titre
      // (aucune table symbole → nom n'existe pas côté client).
      subtitle: stock.name != null ? Text(stock.name!) : null,
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: <Widget>[
          PriceText(stock.coursActuel, style: const TextStyle(fontSize: 15)),
          const SizedBox(height: 4),
          VariationChip(stock.variationPct),
        ],
      ),
      onTap: () => context.push('/marche/symbol/${stock.symbol}'),
    );
  }
}
