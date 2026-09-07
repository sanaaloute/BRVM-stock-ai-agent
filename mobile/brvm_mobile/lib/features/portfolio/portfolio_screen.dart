import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import '../market/market_providers.dart';
import 'portfolio_models.dart';
import 'portfolio_providers.dart';

/// Onglet « Portefeuille » : valorisation agrégée des positions, chaque
/// position regroupant ses lignes d'achat (lots).
class PortfolioScreen extends ConsumerWidget {
  const PortfolioScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final portfolio = ref.watch(portfolioProvider);
    return Scaffold(
      appBar: const KoraAppBar(title: Text('Portefeuille')),
      body: portfolio.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(
          message: 'Impossible de charger votre portefeuille.\n$error',
          onRetry: () => ref.invalidate(portfolioProvider),
        ),
        data: (data) {
          if (data.positions.isEmpty) {
            return RefreshIndicator(
              onRefresh: () async => ref.invalidate(portfolioProvider),
              child: const EmptyView(
                message: 'Votre portefeuille est vide.',
                icon: Icons.pie_chart_outline,
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(portfolioProvider),
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              children: <Widget>[
                _SummaryCard(summary: data.summary),
                const SizedBox(height: 16),
                Text(
                  'Positions',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                ...data.positions.map(
                  (position) => _PositionCard(position: position),
                ),
              ],
            ),
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'portfolio-fab',
        onPressed: () => context.push('/portefeuille/form'),
        icon: const Icon(Icons.add),
        label: const Text('Ajouter un achat'),
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.summary});

  final PortfolioSummary summary;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final variation = summary.gainLossPct;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Valeur totale', style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            PriceText(
              summary.totalValueFcfa,
              style: theme.textTheme.headlineSmall,
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: <Widget>[
                _SummaryItem(
                  label: 'Coût d’achat',
                  value: formatFcfa(summary.totalCostFcfa),
                ),
                _SummaryItem(
                  label: 'Gain/Perte',
                  chip: VariationChip(variation),
                ),
                _SummaryItem(
                  label: 'Positions',
                  value: '${summary.positionsCount ?? '—'}',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _SummaryItem extends StatelessWidget {
  const _SummaryItem({
    required this.label,
    this.value,
    this.chip,
  }) : assert(value != null || chip != null, 'value ou chip requis');

  final String label;
  final String? value;
  final Widget? chip;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          label,
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.muted),
        ),
        const SizedBox(height: 4),
        chip ??
            Text(
              value!,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
                fontFeatures: const <FontFeature>[
                  FontFeature.tabularFigures(),
                ],
              ),
            ),
      ],
    );
  }
}

/// Carte de position dépliable : résumé agrégé + liste des lots d'achat.
class _PositionCard extends ConsumerStatefulWidget {
  const _PositionCard({required this.position});

  final Position position;

  @override
  ConsumerState<_PositionCard> createState() => _PositionCardState();
}

class _PositionCardState extends ConsumerState<_PositionCard> {
  bool _expanded = false;

  Position get position => widget.position;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final lots = position.lots;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Column(
        children: <Widget>[
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 8, 12, 8),
              child: Row(
                children: <Widget>[
                  IconButton(
                    tooltip: 'Voir le titre',
                    icon: const Icon(Icons.candlestick_chart_outlined),
                    onPressed: () =>
                        context.push('/marche/symbol/${position.symbol}'),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          position.symbol,
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          <String>[
                            if (position.quantity != null)
                              '${formatAmount(position.quantity)} titres',
                            if (position.avgBuyPrice != null)
                              'achat moy. ${formatFcfa(position.avgBuyPrice)}',
                          ].join(' · '),
                          style: theme.textTheme.bodySmall
                              ?.copyWith(color: theme.colorScheme.muted),
                        ),
                      ],
                    ),
                  ),
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: <Widget>[
                      PriceText(position.currentPrice),
                      const SizedBox(height: 4),
                      VariationChip(position.gainLossPct),
                    ],
                  ),
                  const SizedBox(width: 8),
                  _ExpandChevron(expanded: _expanded, lotsCount: lots.length),
                ],
              ),
            ),
          ),
          AnimatedCrossFade(
            firstChild: const SizedBox(width: double.infinity),
            secondChild: _LotsPanel(position: position),
            crossFadeState: _expanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            duration: const Duration(milliseconds: 200),
          ),
        ],
      ),
    );
  }
}

/// Pastille d'expansion : chevron animé + nombre de lots.
class _ExpandChevron extends StatelessWidget {
  const _ExpandChevron({required this.expanded, required this.lotsCount});

  final bool expanded;
  final int lotsCount;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        AnimatedRotation(
          turns: expanded ? 0.5 : 0,
          duration: const Duration(milliseconds: 200),
          child: Icon(Icons.expand_more, size: 20, color: colors.muted),
        ),
        Text(
          '$lotsCount lot${lotsCount > 1 ? 's' : ''}',
          style: theme.textTheme.labelSmall?.copyWith(color: colors.muted),
        ),
      ],
    );
  }
}

/// Contenu déplié : lots + action « Tout supprimer ».
class _LotsPanel extends ConsumerWidget {
  const _LotsPanel({required this.position});

  final Position position;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final lots = position.lots;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Divider(height: 1, color: theme.colorScheme.outlineVariant),
        if (lots.isEmpty)
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              'Aucun lot détaillé.',
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.muted),
            ),
          )
        else
          for (final lot in lots) _LotRow(lot: lot),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
          child: Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () => _confirmDeleteSymbol(context, ref),
              icon: Icon(Icons.delete_forever_outlined,
                  size: 18, color: theme.colorScheme.loss),
              label: Text(
                'Tout supprimer',
                style: TextStyle(color: theme.colorScheme.loss),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _confirmDeleteSymbol(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Supprimer ${position.symbol} ?'),
        content: const Text(
            'Toutes les lignes d’achat de ce titre seront retirées du portefeuille.'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Tout supprimer'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(portfolioProvider.notifier).deleteSymbol(position.symbol);
    }
  }
}

class _LotRow extends ConsumerWidget {
  const _LotRow({required this.lot});

  final Lot lot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  '${formatAmount(lot.quantity)} titres @ ${formatFcfa(lot.buyPrice)}',
                  style: theme.textTheme.bodyMedium,
                ),
                if (lot.buyDate != null)
                  Text(
                    lot.buyDate!,
                    style: theme.textTheme.labelSmall
                        ?.copyWith(color: theme.colorScheme.muted),
                  ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Modifier le lot',
            icon: const Icon(Icons.edit_outlined, size: 18),
            onPressed: () => _editLot(context, ref, lot),
          ),
          IconButton(
            tooltip: 'Supprimer le lot',
            icon: Icon(Icons.delete_outline,
                size: 18, color: theme.colorScheme.loss),
            onPressed: () => _confirmDeleteLot(context, ref, lot),
          ),
        ],
      ),
    );
  }

  Future<void> _editLot(BuildContext context, WidgetRef ref, Lot lot) async {
    await showDialog<void>(
      context: context,
      builder: (context) => _EditLotDialog(lot: lot),
    );
  }

  Future<void> _confirmDeleteLot(
    BuildContext context,
    WidgetRef ref,
    Lot lot,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Supprimer ce lot ?'),
        content: const Text(
            'Cette ligne d’achat sera retirée de votre portefeuille.'),
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
    if (confirmed == true && lot.id != null) {
      await ref.read(portfolioProvider.notifier).deleteLot(lot.id!);
    }
  }
}

/// Dialogue de modification d'un lot : prix, quantité, date d'achat.
class _EditLotDialog extends ConsumerStatefulWidget {
  const _EditLotDialog({required this.lot});

  final Lot lot;

  @override
  ConsumerState<_EditLotDialog> createState() => _EditLotDialogState();
}

class _EditLotDialogState extends ConsumerState<_EditLotDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _priceController;
  late final TextEditingController _quantityController;
  DateTime? _buyDate;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _priceController =
        TextEditingController(text: widget.lot.buyPrice?.toString() ?? '');
    _quantityController =
        TextEditingController(text: widget.lot.quantity?.toString() ?? '');
    if (widget.lot.buyDate != null) {
      _buyDate = DateTime.tryParse(widget.lot.buyDate!);
    }
  }

  @override
  void dispose() {
    _priceController.dispose();
    _quantityController.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _buyDate ?? DateTime.now(),
      firstDate: DateTime(1998), // Création de la BRVM.
      lastDate: DateTime.now(),
      locale: const Locale('fr', 'FR'),
    );
    if (picked != null) setState(() => _buyDate = picked);
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_buyDate == null) {
      setState(() => _error = 'Sélectionnez la date d’achat.');
      return;
    }
    setState(() {
      _error = null;
      _saving = true;
    });
    final lotId = widget.lot.id;
    if (lotId == null) {
      setState(() {
        _saving = false;
        _error = 'Identifiant du lot manquant.';
      });
      return;
    }
    final message = await ref.read(portfolioProvider.notifier).updateLot(
          lotId,
          buyPrice: double.parse(_priceController.text.replaceAll(',', '.')),
          buyDate: _buyDate!.toIso8601String().substring(0, 10),
          quantity:
              double.parse(_quantityController.text.replaceAll(',', '.')),
        );
    if (!mounted) return;
    setState(() => _saving = false);
    if (message == null) {
      Navigator.of(context).pop();
    } else {
      setState(() => _error = message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Modifier le lot ${widget.lot.symbol}'),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextFormField(
              controller: _priceController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: <TextInputFormatter>[
                FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
              ],
              decoration: const InputDecoration(
                labelText: 'Prix d’achat (FCFA)',
                border: OutlineInputBorder(),
              ),
              validator: (value) {
                final parsed =
                    double.tryParse((value ?? '').replaceAll(',', '.'));
                if (parsed == null || parsed <= 0) {
                  return 'Saisissez un prix valide.';
                }
                return null;
              },
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _quantityController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: <TextInputFormatter>[
                FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
              ],
              decoration: const InputDecoration(
                labelText: 'Quantité',
                border: OutlineInputBorder(),
              ),
              validator: (value) {
                final parsed =
                    double.tryParse((value ?? '').replaceAll(',', '.'));
                if (parsed == null || parsed <= 0) {
                  return 'Saisissez une quantité valide.';
                }
                return null;
              },
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _pickDate,
              icon: const Icon(Icons.calendar_today),
              label: Text(
                _buyDate == null
                    ? 'Date d’achat'
                    : 'Date d’achat : ${_buyDate!.toIso8601String().substring(0, 10)}',
              ),
            ),
            if (_error != null) FormError(message: _error!),
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(),
          child: const Text('Annuler'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: _saving
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Enregistrer'),
        ),
      ],
    );
  }
}

/// Formulaire d'ajout d'une ligne d'achat (lot).
class PositionFormScreen extends ConsumerStatefulWidget {
  const PositionFormScreen({super.key});

  @override
  ConsumerState<PositionFormScreen> createState() =>
      _PositionFormScreenState();
}

class _PositionFormScreenState extends ConsumerState<PositionFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _symbolController;
  late final TextEditingController _priceController;
  late final TextEditingController _quantityController;
  DateTime? _buyDate;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _symbolController = TextEditingController();
    _priceController = TextEditingController();
    _quantityController = TextEditingController();
  }

  @override
  void dispose() {
    _symbolController.dispose();
    _priceController.dispose();
    _quantityController.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _buyDate ?? DateTime.now(),
      firstDate: DateTime(1998), // Création de la BRVM.
      lastDate: DateTime.now(),
      locale: const Locale('fr', 'FR'),
    );
    if (picked != null) setState(() => _buyDate = picked);
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_buyDate == null) {
      setState(() => _error = 'Sélectionnez la date d’achat.');
      return;
    }
    setState(() {
      _error = null;
      _saving = true;
    });
    final symbol = _symbolController.text.trim().toUpperCase();
    final message = await ref.read(portfolioProvider.notifier).addLot(
          symbol,
          double.parse(_priceController.text.replaceAll(',', '.')),
          _buyDate!.toIso8601String().substring(0, 10),
          double.parse(_quantityController.text.replaceAll(',', '.')),
        );
    if (!mounted) return;
    setState(() => _saving = false);
    if (message == null) {
      context.pop();
    } else {
      setState(() => _error = message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final knownSymbols = ref.watch(palmaresSymbolsProvider).valueOrNull ??
        const <String>[];
    return Scaffold(
      appBar: const KoraAppBar(title: Text('Ajouter un achat')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                if (knownSymbols.isNotEmpty)
                  Autocomplete<String>(
                    optionsBuilder: (value) {
                      final query = value.text.toUpperCase();
                      if (query.isEmpty) return knownSymbols;
                      return knownSymbols
                          .where((s) => s.contains(query))
                          .toList();
                    },
                    onSelected: (value) => _symbolController.text = value,
                    fieldViewBuilder:
                        (context, fieldController, focusNode, _) {
                      fieldController.text = _symbolController.text;
                      fieldController.addListener(() {
                        _symbolController.text = fieldController.text;
                      });
                      return TextFormField(
                        controller: fieldController,
                        focusNode: focusNode,
                        textCapitalization: TextCapitalization.characters,
                        decoration: const InputDecoration(
                          labelText: 'Symbole',
                          hintText: 'Ex. SONATEL',
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
                    controller: _symbolController,
                    textCapitalization: TextCapitalization.characters,
                    decoration: const InputDecoration(
                      labelText: 'Symbole',
                      hintText: 'Ex. SONATEL',
                      border: OutlineInputBorder(),
                    ),
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
                            ? 'Saisissez un symbole.'
                            : null,
                  ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _priceController,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  inputFormatters: <TextInputFormatter>[
                    FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
                  ],
                  decoration: const InputDecoration(
                    labelText: 'Prix d’achat (FCFA)',
                    border: OutlineInputBorder(),
                  ),
                  validator: (value) {
                    final parsed =
                        double.tryParse((value ?? '').replaceAll(',', '.'));
                    if (parsed == null || parsed <= 0) {
                      return 'Saisissez un prix valide.';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _quantityController,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  inputFormatters: <TextInputFormatter>[
                    FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
                  ],
                  decoration: const InputDecoration(
                    labelText: 'Quantité',
                    border: OutlineInputBorder(),
                  ),
                  validator: (value) {
                    final parsed =
                        double.tryParse((value ?? '').replaceAll(',', '.'));
                    if (parsed == null || parsed <= 0) {
                      return 'Saisissez une quantité valide.';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: _pickDate,
                  icon: const Icon(Icons.calendar_today),
                  label: Text(
                    _buyDate == null
                        ? 'Date d’achat'
                        : 'Date d’achat : ${_buyDate!.toIso8601String().substring(0, 10)}',
                  ),
                ),
                if (_error != null) FormError(message: _error!),
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Ajouter l’achat'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
