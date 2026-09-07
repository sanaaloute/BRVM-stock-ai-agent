import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import 'predictions_models.dart';
import 'predictions_providers.dart';

enum _DirectionFilter { all, hausse, baisse, neutre }

/// Prévisions IA du jour : filtre par direction, tri par confiance
/// décroissante appliqués côté client.
class PredictionsTab extends ConsumerStatefulWidget {
  const PredictionsTab({super.key});

  @override
  ConsumerState<PredictionsTab> createState() => _PredictionsTabState();
}

class _PredictionsTabState extends ConsumerState<PredictionsTab> {
  _DirectionFilter _filter = _DirectionFilter.all;

  List<StockPrediction> _apply(List<StockPrediction> predictions) {
    final filtered = predictions.where((prediction) {
      switch (_filter) {
        case _DirectionFilter.hausse:
          if (prediction.direction != 'hausse') return false;
        case _DirectionFilter.baisse:
          if (prediction.direction != 'baisse') return false;
        case _DirectionFilter.neutre:
          if (prediction.direction != 'neutre') return false;
        case _DirectionFilter.all:
          break;
      }
      return true;
    }).toList();
    // Tri par confiance décroissante (le backend trie déjà ; on le garantit
    // côté client comme dans le palmarès).
    filtered.sort(
      (a, b) => (b.confidencePct ?? -double.infinity)
          .compareTo(a.confidencePct ?? -double.infinity),
    );
    return filtered;
  }

  @override
  Widget build(BuildContext context) {
    final predictions = ref.watch(predictionsProvider);
    return predictions.when(
      loading: () => const LoadingView(),
      error: (error, _) => ErrorView(
        message: 'Impossible de charger les prévisions.\n$error',
        onRetry: () => ref.invalidate(predictionsProvider),
      ),
      data: (feed) {
        final visible = _apply(feed.predictions);
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _PredictionsHeader(day: feed.day),
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
                      selected: _filter == _DirectionFilter.all,
                      onSelected: (_) =>
                          setState(() => _filter = _DirectionFilter.all),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      avatar: Icon(Icons.arrow_upward,
                          size: 14,
                          color: _filter == _DirectionFilter.hausse
                              ? Theme.of(context).colorScheme.gain
                              : null),
                      label: const Text('Hausse'),
                      showCheckmark: false,
                      selected: _filter == _DirectionFilter.hausse,
                      onSelected: (_) =>
                          setState(() => _filter = _DirectionFilter.hausse),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      avatar: Icon(Icons.arrow_downward,
                          size: 14,
                          color: _filter == _DirectionFilter.baisse
                              ? Theme.of(context).colorScheme.loss
                              : null),
                      label: const Text('Baisse'),
                      showCheckmark: false,
                      selected: _filter == _DirectionFilter.baisse,
                      onSelected: (_) =>
                          setState(() => _filter = _DirectionFilter.baisse),
                    ),
                  ),
                  FilterChip(
                    avatar: Icon(Icons.remove,
                        size: 14,
                        color: _filter == _DirectionFilter.neutre
                            ? Theme.of(context).colorScheme.neutral
                            : null),
                    label: const Text('Neutre'),
                    showCheckmark: false,
                    selected: _filter == _DirectionFilter.neutre,
                    onSelected: (_) =>
                        setState(() => _filter = _DirectionFilter.neutre),
                  ),
                ],
              ),
            ),
            Expanded(
              child: visible.isEmpty
                  ? EmptyView(
                      message: feed.predictions.isEmpty
                          ? 'Les prévisions seront disponibles après la '
                              'prochaine clôture.'
                          : 'Aucune prévision dans cette catégorie.',
                      icon: Icons.auto_graph_outlined,
                      onRetry: feed.predictions.isEmpty
                          ? () => ref.invalidate(predictionsProvider)
                          : null,
                    )
                  : RefreshIndicator(
                      onRefresh: () async =>
                          ref.invalidate(predictionsProvider),
                      child: ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: visible.length,
                        separatorBuilder: (_, _) =>
                            const Divider(height: 1, indent: 16),
                        itemBuilder: (_, index) =>
                            _PredictionTile(prediction: visible[index]),
                      ),
                    ),
            ),
          ],
        );
      },
    );
  }
}

/// En-tête de l'onglet : jour de calcul + avertissement « indicatif »
/// toujours visible.
class _PredictionsHeader extends StatelessWidget {
  const _PredictionsHeader({this.day});

  final DateTime? day;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (day != null)
            Text(
              'Prévisions après la clôture du ${formatDate(day)}',
              style: theme.textTheme.titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
          if (day != null) const SizedBox(height: 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.only(top: 1),
                child: Icon(Icons.info_outline, size: 14, color: colors.muted),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  "À titre indicatif — ceci n'est pas un conseil en "
                  'investissement',
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: colors.muted),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PredictionTile extends StatelessWidget {
  const _PredictionTile({required this.prediction});

  final StockPrediction prediction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final stats = <String>[
      if (prediction.confidencePct != null)
        'Confiance ${formatAmount(prediction.confidencePct)} %',
      if (prediction.expectedMovePct != null)
        '±${formatAmount(prediction.expectedMovePct)} %',
    ].join(' · ');
    return ListTile(
      title: Row(
        children: <Widget>[
          Flexible(
            child: Text(
              prediction.symbol,
              style: const TextStyle(fontWeight: FontWeight.bold),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          _DirectionChip(prediction.direction),
        ],
      ),
      // Le nom est renvoyé par le backend ; sinon pas de sous-titre.
      subtitle: prediction.name != null
          ? Text(prediction.name!, maxLines: 1, overflow: TextOverflow.ellipsis)
          : null,
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: <Widget>[
          PriceText(prediction.price, style: const TextStyle(fontSize: 15)),
          if (stats.isNotEmpty) ...<Widget>[
            const SizedBox(height: 4),
            Text(
              stats,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.muted,
                fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
              ),
            ),
          ],
        ],
      ),
      onTap: () {
        // Le routeur est capturé avant l'ouverture de la fiche modale :
        // le contexte de la tuile ne doit pas être utilisé après fermeture.
        final router = GoRouter.of(context);
        showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          showDragHandle: true,
          builder: (sheetContext) => _PredictionDetailSheet(
            symbol: prediction.symbol,
            onOpenStock: () {
              Navigator.of(sheetContext).pop();
              router.push('/marche/symbol/${prediction.symbol}');
            },
          ),
        );
      },
    );
  }
}

/// Pastille de direction : ▲ Hausse (vert) / ▼ Baisse (rouge) /
/// Neutre (gris) — mêmes couleurs que [VariationChip].
class _DirectionChip extends StatelessWidget {
  const _DirectionChip(this.direction);

  final String? direction;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final (color, label, icon) = switch (direction) {
      'hausse' => (colors.gain, 'Hausse', Icons.arrow_upward),
      'baisse' => (colors.loss, 'Baisse', Icons.arrow_downward),
      _ => (colors.neutral, 'Neutre', Icons.remove),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 3),
          Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: color,
                  fontWeight: FontWeight.w600,
                ),
          ),
        ],
      ),
    );
  }
}

/// Fiche modale : détail complet d'une prévision (explication, objectifs,
/// score, signal) chargé via [predictionDetailProvider].
class _PredictionDetailSheet extends ConsumerWidget {
  const _PredictionDetailSheet({required this.symbol, required this.onOpenStock});

  final String symbol;
  final VoidCallback onOpenStock;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(predictionDetailProvider(symbol));
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          bottom: 20 + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: detail.when(
          loading: () => const SizedBox(height: 200, child: LoadingView()),
          error: (error, _) => SizedBox(
            height: 240,
            child: ErrorView(
              message: 'Impossible de charger la prévision.\n$error',
              onRetry: () => ref.invalidate(predictionDetailProvider(symbol)),
            ),
          ),
          data: (prediction) => ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: MediaQuery.sizeOf(context).height * 0.8,
            ),
            child: SingleChildScrollView(
              child: _PredictionDetailBody(
                prediction: prediction,
                onOpenStock: onOpenStock,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PredictionDetailBody extends StatelessWidget {
  const _PredictionDetailBody({
    required this.prediction,
    required this.onOpenStock,
  });

  final StockPrediction prediction;
  final VoidCallback onOpenStock;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Row(
          children: <Widget>[
            Flexible(
              child: Text(
                prediction.symbol,
                style: theme.textTheme.titleLarge
                    ?.copyWith(fontWeight: FontWeight.bold),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 8),
            _DirectionChip(prediction.direction),
          ],
        ),
        if (prediction.name != null) ...<Widget>[
          const SizedBox(height: 2),
          Text(
            prediction.name!,
            style: theme.textTheme.bodyMedium?.copyWith(color: colors.muted),
          ),
        ],
        if (prediction.day != null) ...<Widget>[
          const SizedBox(height: 4),
          Text(
            'Prévision après la clôture du ${formatDate(prediction.day)}',
            style: theme.textTheme.labelMedium?.copyWith(color: colors.muted),
          ),
        ],
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[
            StatChip(
              label: 'Cours',
              value: formatFcfa(prediction.price),
            ),
            StatChip(
              label: 'Confiance',
              value: prediction.confidencePct == null
                  ? '—'
                  : '${formatAmount(prediction.confidencePct)} %',
            ),
            StatChip(
              label: 'Variation attendue',
              value: prediction.expectedMovePct == null
                  ? '—'
                  : '±${formatAmount(prediction.expectedMovePct)} %',
            ),
            StatChip(label: 'Cible basse', value: formatFcfa(prediction.targetLow)),
            StatChip(label: 'Cible haute', value: formatFcfa(prediction.targetHigh)),
            StatChip(label: 'Score', value: formatAmount(prediction.score)),
            StatChip(label: 'Signal', value: prediction.signal ?? '—'),
          ],
        ),
        if (prediction.explanation != null) ...<Widget>[
          const SizedBox(height: 16),
          Text(
            'Analyse',
            style: theme.textTheme.titleSmall
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 6),
          Text(prediction.explanation!, style: theme.textTheme.bodyMedium),
        ],
        const SizedBox(height: 12),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.only(top: 1),
              child: Icon(Icons.info_outline, size: 14, color: colors.muted),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                "À titre indicatif — ceci n'est pas un conseil en "
                'investissement',
                style:
                    theme.textTheme.bodySmall?.copyWith(color: colors.muted),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: onOpenStock,
            icon: const Icon(Icons.open_in_new),
            label: const Text('Voir la fiche'),
          ),
        ),
      ],
    );
  }
}
