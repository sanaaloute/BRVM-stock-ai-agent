import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import 'portfolio_models.dart';

enum _AllocationDimension { sgi, actions, sectors }

enum _AllocationMetric { value, dividends }

/// Regroupement des positions et dividendes pour une dimension de
/// répartition (SGI, symbole ou secteur).
class _AllocationGroup {
  const _AllocationGroup({
    required this.name,
    this.positionsCount = 0,
    this.quantity = 0,
    this.totalCostFcfa = 0,
    this.currentValueFcfa = 0,
    this.gainLossFcfa = 0,
    this.dividendsFcfa = 0,
    this.isOther = false,
  });

  final String name;
  final int positionsCount;
  final double quantity;
  final double totalCostFcfa;
  final double currentValueFcfa;
  final double gainLossFcfa;
  final double dividendsFcfa;

  /// Regroupement « Autres » (queue du classement) : légende réduite à la
  /// part en pourcentage, couleur grise fixe.
  final bool isOther;

  double? get gainLossPct =>
      totalCostFcfa > 0 ? gainLossFcfa / totalCostFcfa * 100 : null;
}

/// Accumulateur mutable utilisé pour construire les [_AllocationGroup].
class _GroupAccumulator {
  int positionsCount = 0;
  double quantity = 0;
  double totalCost = 0;
  double currentValue = 0;
  double gainLoss = 0;
  double dividends = 0;
}

class PortfolioAllocationChart extends StatefulWidget {
  const PortfolioAllocationChart({super.key, required this.data});

  final PortfolioData data;

  @override
  State<PortfolioAllocationChart> createState() =>
      _PortfolioAllocationChartState();
}

class _PortfolioAllocationChartState extends State<PortfolioAllocationChart> {
  _AllocationDimension _dimension = _AllocationDimension.sgi;
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

  String get _title => switch (_dimension) {
    _AllocationDimension.sgi => 'Répartition par SGI',
    _AllocationDimension.actions => 'Répartition par actions',
    _AllocationDimension.sectors => 'Répartition par secteur',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(_title, style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: <Widget>[
                ChoiceChip(
                  label: const Text('SGI'),
                  selected: _dimension == _AllocationDimension.sgi,
                  onSelected: (_) =>
                      setState(() => _dimension = _AllocationDimension.sgi),
                ),
                ChoiceChip(
                  label: const Text('Actions'),
                  selected: _dimension == _AllocationDimension.actions,
                  onSelected: (_) =>
                      setState(() => _dimension = _AllocationDimension.actions),
                ),
                ChoiceChip(
                  label: const Text('Secteurs'),
                  selected: _dimension == _AllocationDimension.sectors,
                  onSelected: (_) =>
                      setState(() => _dimension = _AllocationDimension.sectors),
                ),
              ],
            ),
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

  List<_AllocationGroup> get _groups {
    if (_dimension == _AllocationDimension.sgi) {
      return <_AllocationGroup>[
        for (final summary in widget.data.sgiBreakdown)
          _AllocationGroup(
            name: summary.sgi,
            positionsCount: summary.positionsCount,
            quantity: summary.quantity,
            totalCostFcfa: summary.totalCostFcfa ?? 0,
            currentValueFcfa: summary.currentValueFcfa ?? 0,
            gainLossFcfa: summary.gainLossFcfa ?? 0,
            dividendsFcfa: summary.dividendsFcfa,
          ),
      ];
    }
    return _groupsFromPositions(
      positionKey: _dimension == _AllocationDimension.actions
          ? (position) => position.symbol
          : (position) => _sectorLabel(position.sector),
      dividendKey: _dimension == _AllocationDimension.actions
          ? (dividend) => dividend.symbol
          : (dividend) => _sectorLabel(dividend.sector),
    );
  }

  static String _sectorLabel(String? sector) {
    final label = (sector ?? '').trim();
    return label.isEmpty ? 'Autres' : label;
  }

  List<_AllocationGroup> _groupsFromPositions({
    required String Function(Position) positionKey,
    required String Function(DividendEntry) dividendKey,
  }) {
    final accumulators = <String, _GroupAccumulator>{};
    for (final position in widget.data.positions) {
      final group = accumulators.putIfAbsent(
        positionKey(position),
        _GroupAccumulator.new,
      );
      group.positionsCount += 1;
      group.quantity += position.quantity ?? 0;
      group.totalCost += position.totalCost ?? 0;
      // Comme la répartition SGI : à défaut de cours, repli sur le coût.
      group.currentValue +=
          position.currentValueFcfa ?? position.totalCost ?? 0;
      group.gainLoss += position.gainLossFcfa ?? 0;
    }
    // Un groupe sans position courante mais avec des dividendes doit
    // apparaître (vue « Dividendes »), comme pour les SGI.
    for (final dividend in widget.data.dividends) {
      final group = accumulators.putIfAbsent(
        dividendKey(dividend),
        _GroupAccumulator.new,
      );
      group.dividends += dividend.amount ?? 0;
    }
    final groups = <_AllocationGroup>[
      for (final entry in accumulators.entries)
        _AllocationGroup(
          name: entry.key,
          positionsCount: entry.value.positionsCount,
          quantity: entry.value.quantity,
          totalCostFcfa: entry.value.totalCost,
          currentValueFcfa: entry.value.currentValue,
          gainLossFcfa: entry.value.gainLoss,
          dividendsFcfa: entry.value.dividends,
        ),
    ];
    groups.sort((a, b) => b.currentValueFcfa.compareTo(a.currentValueFcfa));
    return groups;
  }

  double _valueOf(_AllocationGroup group) {
    if (_metric == _AllocationMetric.dividends) return group.dividendsFcfa;
    return group.currentValueFcfa;
  }

  /// Vue « Actions » : au-delà de 8 sociétés, top 8 + une part « Autres »
  /// agrégeant le reste — sinon le camembert devient illisible. Le tri suit
  /// la métrique affichée (valeur ou dividendes).
  static const int _maxActionSlices = 8;

  List<_AllocationGroup> _visibleGroups(List<_AllocationGroup> groups) {
    if (_dimension != _AllocationDimension.actions ||
        groups.length <= _maxActionSlices) {
      return groups;
    }
    final sorted = List<_AllocationGroup>.of(groups)
      ..sort((a, b) => _valueOf(b).compareTo(_valueOf(a)));
    final top = sorted.take(_maxActionSlices).toList();
    final rest = sorted.skip(_maxActionSlices).toList();
    final otherValue = rest.fold<double>(0, (sum, g) => sum + _valueOf(g));
    // Rien à regrouper si le reste est nul dans la métrique affichée.
    if (otherValue <= 0) return top;
    return <_AllocationGroup>[
      ...top,
      _AllocationGroup(
        name: 'Autres',
        isOther: true,
        positionsCount: rest.fold<int>(0, (sum, g) => sum + g.positionsCount),
        quantity: rest.fold<double>(0, (sum, g) => sum + g.quantity),
        totalCostFcfa: rest.fold<double>(0, (sum, g) => sum + g.totalCostFcfa),
        currentValueFcfa:
            rest.fold<double>(0, (sum, g) => sum + g.currentValueFcfa),
        gainLossFcfa: rest.fold<double>(0, (sum, g) => sum + g.gainLossFcfa),
        dividendsFcfa: rest.fold<double>(0, (sum, g) => sum + g.dividendsFcfa),
      ),
    ];
  }

  Color _colorFor(int index, _AllocationGroup group) =>
      group.isOther ? Colors.grey.shade500 : _colors[index % _colors.length];

  Widget _buildContent(ThemeData theme) {
    final allGroups = _groups;
    final total =
        allGroups.fold<double>(0, (sum, group) => sum + _valueOf(group));
    if (total <= 0) {
      return Text(
        _metric == _AllocationMetric.value
            ? 'Aucune valeur de portefeuille à afficher.'
            : 'Aucun dividende enregistré.',
        style: theme.textTheme.bodyMedium,
      );
    }
    final groups = _visibleGroups(allGroups);
    final sections = <PieChartSectionData>[
      // Les parts à zéro sont exclues : fl_chart empilerait leurs titres
      // « 0 % » à l'angle 0 et, selon la version, pourrait ne rien tracer.
      for (var i = 0; i < groups.length; i++)
        if (_valueOf(groups[i]) > 0)
          PieChartSectionData(
            value: _valueOf(groups[i]),
            title:
                '${(_valueOf(groups[i]) / total * 100).toStringAsFixed(0)}%',
            color: _colorFor(i, groups[i]),
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
        for (var i = 0; i < groups.length; i++)
          groups[i].isOther
              ? _OtherRow(
                  name: groups[i].name,
                  percent: _valueOf(groups[i]) / total * 100,
                  color: _colorFor(i, groups[i]),
                )
              : _AllocationRow(
                  group: groups[i],
                  color: _colorFor(i, groups[i]),
                ),
      ],
    );
  }
}

/// Ligne « Autres » de la vue Actions : nom + part en pourcentage, sans le
/// détail chiffré des autres lignes.
class _OtherRow extends StatelessWidget {
  const _OtherRow({
    required this.name,
    required this.percent,
    required this.color,
  });

  final String name;
  final double percent;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: <Widget>[
          Container(
            width: 10,
            height: 10,
            margin: const EdgeInsets.only(right: 8),
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          Expanded(
            child: Text(
              name,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          Text(
            '${percent.toStringAsFixed(0)} %',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.muted,
            ),
          ),
        ],
      ),
    );
  }
}

class _AllocationRow extends StatelessWidget {
  const _AllocationRow({required this.group, required this.color});

  final _AllocationGroup group;
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
                  group.name,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                Text(
                  '${group.positionsCount} position(s) · '
                  '${formatAmount(group.quantity)} titres · '
                  '${formatFcfa(group.currentValueFcfa)}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.muted,
                  ),
                ),
                Text(
                  '${formatSignedFcfa(group.gainLossFcfa)} '
                  '(${formatPercent(group.gainLossPct)}) · '
                  'Dividendes : ${formatFcfa(group.dividendsFcfa)}',
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
