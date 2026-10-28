import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import 'portfolio_models.dart';

enum _AllocationMetric { value, dividends }

class PortfolioSgiChart extends StatefulWidget {
  const PortfolioSgiChart({super.key, required this.breakdown});

  final List<SgiSummary> breakdown;

  @override
  State<PortfolioSgiChart> createState() => _PortfolioSgiChartState();
}

class _PortfolioSgiChartState extends State<PortfolioSgiChart> {
  _AllocationMetric _metric = _AllocationMetric.value;

  static const _colors = <Color>[
    Color(0xFF0E9F6E),
    Color(0xFF3B82F6),
    Color(0xFFF59E0B),
    Color(0xFF8B5CF6),
    Color(0xFFEF4444),
    Color(0xFF14B8A6),
    Color(0xFF6366F1),
    Color(0xFFF97316),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Répartition par SGI', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: <Widget>[
                ChoiceChip(
                  label: const Text('Valeur'),
                  selected: _metric == _AllocationMetric.value,
                  onSelected: (_) =>
                      setState(() => _metric = _AllocationMetric.value),
                ),
                ChoiceChip(
                  label: const Text('Dividendes'),
                  selected: _metric == _AllocationMetric.dividends,
                  onSelected: (_) =>
                      setState(() => _metric = _AllocationMetric.dividends),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _buildContent(theme),
          ],
        ),
      ),
    );
  }

  Widget _buildContent(ThemeData theme) {
    final total = _total;
    if (total <= 0) {
      return Text(
        _metric == _AllocationMetric.value
            ? 'Aucune valeur de portefeuille à afficher.'
            : 'Aucun dividende enregistré.',
        style: theme.textTheme.bodyMedium,
      );
    }
    final sections = <PieChartSectionData>[
      // Les parts à zéro sont exclues : fl_chart empilerait leurs titres
      // « 0 % » à l'angle 0 et, selon la version, pourrait ne rien tracer.
      for (var i = 0; i < widget.breakdown.length; i++)
        if (_valueOf(widget.breakdown[i]) > 0)
          PieChartSectionData(
            value: _valueOf(widget.breakdown[i]),
            title:
                '${(_valueOf(widget.breakdown[i]) / total * 100).toStringAsFixed(0)}%',
            color: _colors[i % _colors.length],
            titleStyle: const TextStyle(
              color: Colors.white,
              fontSize: 12,
              fontWeight: FontWeight.bold,
            ),
          ),
    ];
    return Column(
      children: <Widget>[
        SizedBox(
          height: 210,
          child: PieChart(
            PieChartData(
              sections: sections,
              centerSpaceRadius: 34,
              sectionsSpace: 2,
            ),
          ),
        ),
        const SizedBox(height: 12),
        for (var i = 0; i < widget.breakdown.length; i++)
          _SgiSummaryRow(
            summary: widget.breakdown[i],
            color: _colors[i % _colors.length],
          ),
      ],
    );
  }

  double get _total => widget.breakdown.fold<double>(
    0,
    (sum, summary) => sum + _valueOf(summary),
  );

  double _valueOf(SgiSummary summary) {
    if (_metric == _AllocationMetric.dividends) return summary.dividendsFcfa;
    return summary.currentValueFcfa ?? 0;
  }
}

class _SgiSummaryRow extends StatelessWidget {
  const _SgiSummaryRow({required this.summary, required this.color});

  final SgiSummary summary;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            width: 10,
            height: 10,
            margin: const EdgeInsets.only(top: 5, right: 8),
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  summary.sgi,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                Text(
                  '${summary.positionsCount} position(s) · '
                  '${formatAmount(summary.quantity)} titres · '
                  '${formatFcfa(summary.currentValueFcfa)}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.muted,
                  ),
                ),
                Text(
                  '${formatSignedFcfa(summary.gainLossFcfa)} '
                  '(${formatPercent(summary.gainLossPct)}) · '
                  'Dividendes : ${formatFcfa(summary.dividendsFcfa)}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.muted,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
