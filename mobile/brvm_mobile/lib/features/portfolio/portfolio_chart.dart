import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import 'portfolio_models.dart';
import 'portfolio_providers.dart';

enum _HistoryMetric { value, gainLoss, dividends }

class PortfolioHistoryChart extends ConsumerStatefulWidget {
  const PortfolioHistoryChart({super.key});

  @override
  ConsumerState<PortfolioHistoryChart> createState() =>
      _PortfolioHistoryChartState();
}

class _PortfolioHistoryChartState extends ConsumerState<PortfolioHistoryChart> {
  int _days = 90;
  _HistoryMetric _metric = _HistoryMetric.value;

  @override
  Widget build(BuildContext context) {
    final query = (days: _days, sgi: ref.watch(portfolioSgiFilterProvider));
    final history = ref.watch(portfolioHistoryProvider(query));
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              'Évolution du portefeuille',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                for (final entry in <(int, String)>[
                  (30, '1M'),
                  (90, '3M'),
                  (180, '6M'),
                  (365, '1A'),
                ])
                  ChoiceChip(
                    label: Text(entry.$2),
                    selected: _days == entry.$1,
                    onSelected: (_) => setState(() => _days = entry.$1),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: <Widget>[
                ChoiceChip(
                  label: const Text('Valeur'),
                  selected: _metric == _HistoryMetric.value,
                  onSelected: (_) =>
                      setState(() => _metric = _HistoryMetric.value),
                ),
                ChoiceChip(
                  label: const Text('Gain/Perte'),
                  selected: _metric == _HistoryMetric.gainLoss,
                  onSelected: (_) =>
                      setState(() => _metric = _HistoryMetric.gainLoss),
                ),
                ChoiceChip(
                  label: const Text('Dividendes'),
                  selected: _metric == _HistoryMetric.dividends,
                  onSelected: (_) =>
                      setState(() => _metric = _HistoryMetric.dividends),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 240,
              child: history.when(
                loading: () => const LoadingView(),
                error: (error, _) => ErrorView(
                  message: 'Impossible de charger l’historique.\n$error',
                  onRetry: () =>
                      ref.invalidate(portfolioHistoryProvider(query)),
                ),
                data: (points) {
                  if (points.isEmpty) {
                    return const EmptyView(
                      message:
                          'Pas assez de données pour afficher l’évolution.',
                      icon: Icons.show_chart,
                    );
                  }
                  return _HistoryLineChart(points: points, metric: _metric);
                },
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Estimation basée sur les lots et les clôtures disponibles.',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.muted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HistoryLineChart extends StatelessWidget {
  const _HistoryLineChart({required this.points, required this.metric});

  final List<PortfolioHistoryPoint> points;
  final _HistoryMetric metric;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final caption = Theme.of(context).textTheme.labelSmall?.copyWith(
      color: colors.muted,
      fontSize: 10,
      fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
    );
    final visible = points.where((point) => point.day != null).toList();
    if (visible.isEmpty) return const SizedBox.shrink();

    double valueOf(PortfolioHistoryPoint point) {
      if (metric == _HistoryMetric.value) return point.totalValueFcfa!;
      if (metric == _HistoryMetric.gainLoss) return point.gainLossFcfa!;
      return point.dividendsFcfa;
    }

    final values = visible.map(valueOf).toList();
    var minY = values.reduce(math.min);
    var maxY = values.reduce(math.max);
    final range = maxY - minY;
    final pad = range <= 0 ? math.max(1.0, maxY.abs() * 0.02) : range * 0.08;
    minY -= pad;
    maxY += pad;
    final yInterval = math.max(1.0, (maxY - minY) / 3);
    final mainColor = switch (metric) {
      _HistoryMetric.gainLoss when values.last < 0 => colors.loss,
      _HistoryMetric.dividends => colors.tertiary,
      _ => colors.primary,
    };
    final spots = <FlSpot>[
      for (var i = 0; i < visible.length; i++) FlSpot(i.toDouble(), values[i]),
    ];
    final costSpots = <FlSpot>[
      for (var i = 0; i < visible.length; i++)
        FlSpot(i.toDouble(), visible[i].totalCostFcfa!),
    ];
    final bars = <LineChartBarData>[
      LineChartBarData(
        spots: spots,
        isCurved: true,
        curveSmoothness: 0.22,
        color: mainColor,
        barWidth: 2.4,
        isStrokeCapRound: true,
        dotData: const FlDotData(show: false),
        belowBarData: BarAreaData(
          show: true,
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              mainColor.withValues(alpha: 0.24),
              mainColor.withValues(alpha: 0.02),
            ],
          ),
        ),
      ),
      if (metric == _HistoryMetric.value)
        LineChartBarData(
          spots: costSpots,
          isCurved: true,
          curveSmoothness: 0.22,
          color: colors.muted,
          barWidth: 1.4,
          dashArray: <int>[5, 4],
          dotData: const FlDotData(show: false),
        ),
    ];

    String dateLabel(DateTime day) {
      final month = day.month.toString().padLeft(2, '0');
      return '${day.day.toString().padLeft(2, '0')}/$month';
    }

    final xTickCount = math.min(5, visible.length);
    final xTickInterval = xTickCount > 1
        ? (visible.length - 1) / (xTickCount - 1)
        : 1.0;
    final xTickIndexes = <int>{
      for (var i = 0; i < xTickCount; i++) (i * xTickInterval).round(),
    };

    return LineChart(
      LineChartData(
        minX: 0,
        maxX: visible.length == 1 ? 1 : (visible.length - 1).toDouble(),
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
          leftTitles: const AxisTitles(
            sideTitles: SideTitles(showTitles: false),
          ),
          topTitles: const AxisTitles(
            sideTitles: SideTitles(showTitles: false),
          ),
          rightTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 56,
              interval: yInterval,
              getTitlesWidget: (value, meta) => Padding(
                padding: const EdgeInsets.only(left: 4),
                child: Text(formatCompactAmount(value), style: caption),
              ),
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 26,
              interval: xTickInterval,
              getTitlesWidget: (value, meta) {
                final index = value.round();
                if (index < 0 ||
                    index >= visible.length ||
                    !xTickIndexes.contains(index)) {
                  return const SizedBox.shrink();
                }
                return Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(dateLabel(visible[index].day!), style: caption),
                );
              },
            ),
          ),
        ),
        lineTouchData: LineTouchData(
          handleBuiltInTouches: true,
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => colors.surfaceContainerHighest,
            getTooltipItems: (touchedSpots) => touchedSpots.map((spot) {
              final index = spot.x.round();
              final date = index >= 0 && index < visible.length
                  ? visible[index].day!
                  : null;
              return LineTooltipItem(
                '${formatFcfa(spot.y)}${date == null ? '' : '\n${dateLabel(date)}'}',
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
        lineBarsData: bars,
      ),
    );
  }
}
