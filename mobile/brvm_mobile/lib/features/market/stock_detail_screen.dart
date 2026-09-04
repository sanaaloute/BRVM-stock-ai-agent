import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/format.dart';
import '../../core/json_utils.dart';
import '../../core/ui.dart';
import 'stock_detail_models.dart';
import 'stock_detail_providers.dart';

/// Fiche investisseur d'un titre : cotation, graphique, score IA, profil,
/// dividendes, actualités et prévision technique. Chaque section se dégrade
/// indépendamment (marché fermé, section en erreur…).
class StockDetailScreen extends ConsumerStatefulWidget {
  const StockDetailScreen({super.key, required this.symbol});

  final String symbol;

  @override
  ConsumerState<StockDetailScreen> createState() => _StockDetailScreenState();
}

class _StockDetailScreenState extends ConsumerState<StockDetailScreen> {
  String _period = '3M';

  Future<void> _refresh() async {
    ref.invalidate(stockDetailProvider(widget.symbol));
    ref.invalidate(stockHistoryProvider((widget.symbol, _period)));
  }

  @override
  Widget build(BuildContext context) {
    final detail = ref.watch(stockDetailProvider(widget.symbol));
    return Scaffold(
      appBar: KoraAppBar(title: Text(widget.symbol)),
      body: detail.when(
        loading: () => const LoadingView(message: 'Chargement des données…'),
        error: (error, _) => ErrorView(
          message: 'Impossible de charger la fiche de ${widget.symbol}.\n$error',
          onRetry: _refresh,
        ),
        data: (d) => RefreshIndicator(
          onRefresh: _refresh,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: <Widget>[
              SliverPadding(
                padding: const EdgeInsets.all(16),
                sliver: SliverList(
                  delegate: SliverChildListDelegate(<Widget>[
                    _HeaderCard(detail: d),
                    const SizedBox(height: 12),
                    _ChartCard(
                      symbol: widget.symbol,
                      period: _period,
                      onPeriodChanged: (p) => setState(() => _period = p),
                    ),
                    if (d.prediction != null) ...<Widget>[
                      const SizedBox(height: 12),
                      _PredictionCard(prediction: d.prediction!),
                    ],
                    if (d.score != null) ...<Widget>[
                      const SizedBox(height: 12),
                      _ScoreCard(score: d.score!),
                    ],
                    const SizedBox(height: 12),
                    _ProfileCard(detail: d),
                    const SizedBox(height: 12),
                    _DividendsCard(detail: d),
                    const SizedBox(height: 12),
                    _NewsCard(detail: d),
                    const SizedBox(height: 24),
                  ]),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// En-tête : symbole, nom, cours, variation et statistiques clés.
class _HeaderCard extends StatelessWidget {
  const _HeaderCard({required this.detail});

  final SymbolDetail detail;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final quote = detail.quote;
    final price = quote?.coursActuel ??
        quote?.coursVeille ??
        detail.history.lastPrice;
    // Marché fermé : pas de cours du jour (on affiche le dernier connu).
    final closed = quote == null || quote.coursActuel == null;

    final base = theme.cardTheme.color ?? colors.surface;
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        border:
            Border.all(color: colors.outlineVariant.withValues(alpha: 0.75)),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            Color.alphaBlend(colors.primary.withValues(alpha: 0.10), base),
            base,
          ],
        ),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      detail.symbol,
                      style: theme.textTheme.headlineMedium
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    if (detail.companyName != null) ...<Widget>[
                      const SizedBox(height: 2),
                      Text(
                        detail.companyName!,
                        style: theme.textTheme.bodyMedium
                            ?.copyWith(color: colors.muted),
                      ),
                    ],
                  ],
                ),
              ),
              VariationChip(quote?.variationPct),
            ],
          ),
          const SizedBox(height: 12),
          PriceText(price, style: theme.textTheme.headlineSmall),
          if (closed) ...<Widget>[
            const SizedBox(height: 4),
            Text(
              'Marché fermé — dernier cours connu',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colors.muted),
            ),
          ],
          if (quote != null &&
              (quote.volume != null || quote.capitalisation != null)) ...<Widget>[
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                if (quote.volume != null)
                  StatChip(label: 'Volume', value: formatCompactAmount(quote.volume)),
                if (quote.capitalisation != null)
                  StatChip(
                    label: 'Capitalisation',
                    value: formatCompactFcfa(quote.capitalisation),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// Graphique des cours + sélecteur de période. Seul ce bloc se recharge
/// quand on change de période.
class _ChartCard extends ConsumerWidget {
  const _ChartCard({
    required this.symbol,
    required this.period,
    required this.onPeriodChanged,
  });

  final String symbol;
  final String period;
  final ValueChanged<String> onPeriodChanged;

  static const _periods = <String>['1M', '3M', '6M', '1A', 'MAX'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(stockHistoryProvider((symbol, period)));
    return _CardSection(
      title: 'Cours',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              for (final p in _periods)
                _PeriodChip(
                  label: p,
                  selected: p == period,
                  onTap: () => onPeriodChanged(p),
                ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 230,
            child: history.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => _InlineMessage(
                icon: Icons.cloud_off_outlined,
                text: 'Historique indisponible pour le moment.',
              ),
              data: (h) {
                if (h.error != null || h.points.length < 2) {
                  return const _InlineMessage(
                    icon: Icons.show_chart,
                    text: 'Pas assez de données sur cette période.',
                  );
                }
                return _PriceChart(points: h.points, period: period);
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _PeriodChip extends StatelessWidget {
  const _PeriodChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final color = selected ? colors.primary : colors.muted;
    return InkWell(
      borderRadius: BorderRadius.circular(999),
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(999),
          color: selected
              ? colors.primary.withValues(alpha: 0.16)
              : colors.surfaceContainerHighest.withValues(alpha: 0.5),
          border: Border.all(
            color: selected
                ? colors.primary.withValues(alpha: 0.5)
                : colors.outlineVariant.withValues(alpha: 0.6),
          ),
        ),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: color,
                fontWeight: FontWeight.w700,
                fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
              ),
        ),
      ),
    );
  }
}

class _PriceChart extends StatelessWidget {
  const _PriceChart({required this.points, required this.period});

  final List<PricePoint> points;
  final String period;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final caption = Theme.of(context).textTheme.labelSmall?.copyWith(
          color: colors.muted,
          fontSize: 10,
          fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
        );

    final prices = points.map((p) => p.price!).toList();
    var minY = prices.reduce(math.min);
    var maxY = prices.reduce(math.max);
    final range = maxY - minY;
    final pad = range <= 0 ? math.max(1.0, maxY.abs() * 0.02) : range * 0.08;
    minY -= pad;
    maxY += pad;
    final yInterval = _niceInterval(range <= 0 ? pad * 2 : range);

    // Hausse si le dernier cours visible >= au premier, baisse sinon.
    final up = prices.last >= prices.first;
    final lineColor = up ? colors.gain : colors.loss;

    final spots = <FlSpot>[
      for (var i = 0; i < points.length; i++)
        FlSpot(i.toDouble(), points[i].price!),
    ];

    String dateLabel(DateTime d) {
      String two(int v) => v.toString().padLeft(2, '0');
      return switch (period) {
        '1M' || '3M' => '${two(d.day)}/${two(d.month)}',
        '6M' || '1A' => '${two(d.month)}/${two(d.year % 100)}',
        _ => '${d.year}',
      };
    }

    return LineChart(
      LineChartData(
        minX: 0,
        maxX: (points.length - 1).toDouble(),
        minY: minY,
        maxY: maxY,
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: yInterval,
          getDrawingHorizontalLine: (value) => FlLine(
            color: colors.outline.withValues(alpha: 0.12),
            strokeWidth: 1,
          ),
        ),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          topTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 48,
              interval: yInterval,
              getTitlesWidget: (value, meta) => Padding(
                padding: const EdgeInsets.only(left: 4),
                child: Text(
                  formatCompactAmount(value),
                  style: caption,
                  textAlign: TextAlign.left,
                ),
              ),
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 24,
              interval: math.max(1, (points.length / 4).floor()).toDouble(),
              getTitlesWidget: (value, meta) {
                final i = value.round();
                if (i < 0 || i >= points.length) {
                  return const SizedBox.shrink();
                }
                final d = points[i].date;
                return Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(d == null ? '' : dateLabel(d), style: caption),
                );
              },
            ),
          ),
        ),
        lineTouchData: LineTouchData(
          handleBuiltInTouches: true,
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => colors.surfaceContainerHighest,
            getTooltipItems: (touchedSpots) => touchedSpots.map((s) {
              final i = s.x.round();
              final d = (i >= 0 && i < points.length)
                  ? points[i].date
                  : null;
              final date = d == null
                  ? ''
                  : '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';
              return LineTooltipItem(
                '${formatFcfa(s.y)}${date.isEmpty ? '' : '\n$date'}',
                TextStyle(
                  color: colors.onSurface,
                  fontWeight: FontWeight.bold,
                  fontSize: 12,
                  fontFeatures: const <FontFeature>[
                    FontFeature.tabularFigures(),
                  ],
                ),
              );
            }).toList(),
          ),
        ),
        lineBarsData: <LineChartBarData>[
          LineChartBarData(
            spots: spots,
            isCurved: true,
            curveSmoothness: 0.22,
            color: lineColor,
            barWidth: 2.4,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  lineColor.withValues(alpha: 0.28),
                  lineColor.withValues(alpha: 0.02),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Intervalle « rond » pour l'axe des prix (~3 graduations).
  double _niceInterval(double range) {
    if (range <= 0) return 1;
    final rough = range / 3;
    final exp = (math.log(rough) / math.ln10).floor();
    final base = math.pow(10, exp).toDouble();
    for (final m in const <double>[1, 2, 2.5, 5, 10]) {
      if (base * m >= rough) return base * m;
    }
    return base * 10;
  }
}

/// Score & signal du jour.
class _ScoreCard extends StatelessWidget {
  const _ScoreCard({required this.score});

  final AiScore score;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final value = (score.score ?? 0).clamp(0, 100).toDouble();
    final signal = score.signal?.toUpperCase();
    final signalColor = signal == 'BUY'
        ? colors.gain
        : (signal == 'SELL' ? colors.loss : colors.muted);

    return _CardSection(
      title: 'Score & Signal',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              Text(
                formatAmount(value),
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: signalColor,
                  fontFeatures: const <FontFeature>[
                    FontFeature.tabularFigures(),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(left: 4, bottom: 6),
                child: Text('/ 100',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: colors.muted)),
              ),
              const Spacer(),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: signalColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(999),
                  border:
                      Border.all(color: signalColor.withValues(alpha: 0.4)),
                ),
                child: Text(
                  signal ?? 'NEUTRE',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: signalColor,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: value / 100,
              minHeight: 8,
              color: signalColor,
              backgroundColor: colors.outline.withValues(alpha: 0.15),
            ),
          ),
          if (score.day != null) ...<Widget>[
            const SizedBox(height: 8),
            Text(
              'Au ${formatDate(score.day)}',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colors.muted),
            ),
          ],
        ],
      ),
    );
  }
}

/// Profil & fondamentaux : la fiche société (JSON arbitraire) est aplatie
/// sur un niveau et rendue en paires libellé/valeur.
class _ProfileCard extends StatelessWidget {
  const _ProfileCard({required this.detail});

  final SymbolDetail detail;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (detail.profileError != null) {
      return _CardSection(
        title: 'Profil & Fondamentaux',
        child: Text(
          'Profil indisponible pour le moment.',
          style: theme.textTheme.bodyMedium
              ?.copyWith(color: theme.colorScheme.muted),
        ),
      );
    }
    final rows = _flattenProfile(detail.profile);
    return _CardSection(
      title: 'Profil & Fondamentaux',
      child: rows.isEmpty
          ? Text(
              'Aucune information disponible.',
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.muted),
            )
          : Column(
              children: <Widget>[
                for (final row in rows)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Expanded(
                          flex: 2,
                          child: Text(
                            row.label,
                            style: theme.textTheme.bodySmall
                                ?.copyWith(color: theme.colorScheme.muted),
                          ),
                        ),
                        Expanded(
                          flex: 3,
                          child: Text(
                            row.value,
                            style: theme.textTheme.bodyMedium,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }

  List<({String label, String value})> _flattenProfile(
    Map<String, dynamic> profile,
  ) {
    final rows = <({String label, String value})>[];
    for (final entry in profile.entries) {
      final value = entry.value;
      if (value is Map) {
        // Aplatissement d'un niveau : les clés enfants portent le libellé.
        for (final child in asMap(value).entries) {
          final text = _stringify(child.value);
          if (text == null) continue;
          rows.add((label: _label(child.key), value: text));
        }
      } else {
        final text = _stringify(value);
        if (text == null) continue;
        rows.add((label: _label(entry.key), value: text));
      }
    }
    return rows;
  }

  /// Libellés français connus ; repli : clé brute humanisée.
  static const _labels = <String, String>{
    'nom': 'Nom',
    'name': 'Nom',
    'raison_sociale': 'Raison sociale',
    'symbole': 'Symbole',
    'symbol': 'Symbole',
    'secteur': 'Secteur',
    'secteur_activite': "Secteur d'activité",
    'activites': 'Activités',
    'description': 'Présentation',
    'capitalisation': 'Capitalisation',
    'capitalisation_boursiere': 'Capitalisation boursière',
    'per': 'PER',
    'PER': 'PER',
    'beta': 'Bêta',
    'dividende': 'Dividende',
    'rendement_dividende': 'Rendement du dividende',
    'rendement': 'Rendement',
    'date_incorporation': "Date d'incorporation",
    'date_introduction': "Date d'introduction",
    'introduction': "Date d'introduction",
    'site_web': 'Site web',
    'siege': 'Siège',
    'effectif': 'Effectif',
    'chiffre_affaires': "Chiffre d'affaires",
    'resultat_net': 'Résultat net',
    'francs': 'Francs',
    'cours': 'Cours',
    'cours_actuel': 'Cours actuel',
    'dirigeants': 'Dirigeants',
    'telephone': 'Téléphone',
    'fax': 'Fax',
  };

  String _label(String key) {
    final known = _labels[key] ?? _labels[key.toLowerCase()];
    if (known != null) return known;
    final cleaned = key.replaceAll('_', ' ').trim();
    if (cleaned.isEmpty) return key;
    return cleaned[0].toUpperCase() + cleaned.substring(1);
  }

  String? _stringify(dynamic value) {
    if (value == null) return null;
    if (value is bool) return value ? 'Oui' : 'Non';
    if (value is num) return formatAmount(value.toDouble());
    final text = value.toString().trim();
    return text.isEmpty ? null : text;
  }
}

/// Libellés des dividendes versés.
class _DividendsCard extends StatelessWidget {
  const _DividendsCard({required this.detail});

  final SymbolDetail detail;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Widget body;
    if (detail.dividendsError != null) {
      body = Text('Dividendes indisponibles pour le moment.',
          style: theme.textTheme.bodyMedium
              ?.copyWith(color: theme.colorScheme.muted));
    } else if (detail.dividends.isEmpty) {
      body = Text('Aucun dividende récent.',
          style: theme.textTheme.bodyMedium
              ?.copyWith(color: theme.colorScheme.muted));
    } else {
      body = Column(
        children: <Widget>[
          for (final item in detail.dividends)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          item.symbol ?? item.company ?? 'Dividende',
                          style: theme.textTheme.bodyMedium
                              ?.copyWith(fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          <String>[
                            if (item.rendement != null)
                              'Rendement ${formatPercent(item.rendement)}',
                            if (item.exDividende != null)
                              'Ex-dividende ${item.exDividende}',
                            if (item.datePaiement != null)
                              'Paiement ${item.datePaiement}',
                          ].join(' · '),
                          style: theme.textTheme.bodySmall
                              ?.copyWith(color: theme.colorScheme.muted),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    formatFcfa(item.dividende),
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      fontFeatures: const <FontFeature>[
                        FontFeature.tabularFigures(),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      );
    }
    return _CardSection(title: 'Dividendes', child: body);
  }
}

/// Actualités du titre (ouverture du lien dans le navigateur).
class _NewsCard extends StatelessWidget {
  const _NewsCard({required this.detail});

  final SymbolDetail detail;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Widget body;
    if (detail.newsError != null) {
      body = Text('Actualités indisponibles pour le moment.',
          style: theme.textTheme.bodyMedium
              ?.copyWith(color: theme.colorScheme.muted));
    } else if (detail.news.isEmpty) {
      body = Text('Aucune actualité récente.',
          style: theme.textTheme.bodyMedium
              ?.copyWith(color: theme.colorScheme.muted));
    } else {
      body = Column(
        children: <Widget>[
          for (final item in detail.news)
            InkWell(
              borderRadius: BorderRadius.circular(10),
              onTap: item.url != null ? () => _openUrl(context, item.url!) : null,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          if (item.date != null)
                            Text(
                              item.date!,
                              style: theme.textTheme.labelSmall?.copyWith(
                                  color: theme.colorScheme.muted),
                            ),
                          Text(
                            item.title ?? 'Actualité',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodyMedium,
                          ),
                          if (item.snippet != null) ...<Widget>[
                            const SizedBox(height: 2),
                            Text(
                              item.snippet!,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.muted),
                            ),
                          ],
                        ],
                      ),
                    ),
                    if (item.url != null)
                      Padding(
                        padding: const EdgeInsets.only(left: 8),
                        child: Icon(
                          Icons.open_in_new,
                          size: 16,
                          color: theme.colorScheme.muted,
                        ),
                      ),
                  ],
                ),
              ),
            ),
        ],
      );
    }
    return _CardSection(title: 'Actualités', child: body);
  }

  Future<void> _openUrl(BuildContext context, String raw) async {
    final url = Uri.tryParse(raw);
    if (url == null) return;
    try {
      await launchUrl(url, mode: LaunchMode.externalApplication);
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Impossible d’ouvrir le lien.')),
        );
      }
    }
  }
}

/// Prévision technique (IA) : tendance, confiance, configuration.
class _PredictionCard extends StatelessWidget {
  const _PredictionCard({required this.prediction});

  final PredictionInfo prediction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final trend = prediction.trend;
    final trendText = trend?.toUpperCase() ?? '—';
    final trendColor = _trendColor(trend, colors);
    final confidence = prediction.confidence;
    final confidenceText = confidence == null
        ? null
        : confidence <= 1
            ? formatPercent(confidence * 100)
            : formatPercent(confidence);

    return _CardSection(
      title: 'Prévision technique',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: _InfoRow(
                  label: 'Tendance',
                  value: trendText,
                  valueColor: trendColor,
                ),
              ),
              if (confidenceText != null)
                _InfoRow(
                  label: 'Confiance',
                  value: confidenceText,
                  alignEnd: true,
                ),
            ],
          ),
          if (prediction.technicalConfig != null) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              prediction.technicalConfig!,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colors.muted, height: 1.5),
            ),
          ],
        ],
      ),
    );
  }

  Color _trendColor(String? trend, ColorScheme colors) {
    if (trend == null) return colors.muted;
    final t = trend.toUpperCase();
    if (t.contains('HAUSSE') || t.contains('UP') || t.contains('BULLISH') ||
        t.contains('RISE')) {
      return colors.gain;
    }
    if (t.contains('BAISSE') || t.contains('DOWN') || t.contains('BEARISH') ||
        t.contains('FALL')) {
      return colors.loss;
    }
    return colors.muted;
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.label,
    required this.value,
    this.valueColor,
    this.alignEnd = false,
  });

  final String label;
  final String value;
  final Color? valueColor;
  final bool alignEnd;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment:
          alignEnd ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          label,
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.muted),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
            color: valueColor,
            fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}

/// Carte de section standard : titre + contenu, marge basse gérée par
/// l'écran.
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

class _InlineMessage extends StatelessWidget {
  const _InlineMessage({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 32, color: colors.muted),
          const SizedBox(height: 8),
          Text(
            text,
            textAlign: TextAlign.center,
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: colors.muted),
          ),
        ],
      ),
    );
  }
}
