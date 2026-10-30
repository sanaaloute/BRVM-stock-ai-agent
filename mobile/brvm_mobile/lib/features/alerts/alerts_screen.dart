import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import '../market/market_providers.dart';
import 'alerts_providers.dart';

/// Onglet « Alertes » : gestion des alertes de prix.
class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alerts = ref.watch(alertsProvider);
    return Scaffold(
      appBar: const KoraAppBar(title: Text('Alertes de prix')),
      body: alerts.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(
          message: 'Impossible de charger les alertes.\n$error',
          onRetry: () => ref.invalidate(alertsProvider),
        ),
        data: (items) {
          if (items.isEmpty) {
            return RefreshIndicator(
              onRefresh: () async => ref.invalidate(alertsProvider),
              child: const EmptyView(
                message: 'Aucune alerte.\nCréez une alerte pour être notifié quand un titre atteint un cours cible.',
                icon: Icons.notifications_none,
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(alertsProvider),
            child: ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              itemCount: items.length,
              separatorBuilder: (_, _) => const Divider(height: 1, indent: 16),
              itemBuilder: (_, index) {
                final alert = items[index];
                return Dismissible(
                  key: ValueKey('alert-${alert.id}'),
                  direction: DismissDirection.endToStart,
                  background: Container(
                    color: Theme.of(context).colorScheme.error,
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.only(right: 24),
                    child: const Icon(Icons.delete_outline,
                        color: Colors.white),
                  ),
                  confirmDismiss: (_) => _confirmDelete(context, ref, alert.id),
                  onDismissed: (_) =>
                      ref.read(alertsProvider.notifier).delete(alert.id),
                  child: ListTile(
                    leading: Icon(
                      alert.isAbove
                          ? Icons.arrow_upward
                          : Icons.arrow_downward,
                      color: alert.isAbove
                          ? Colors.green.shade700
                          : Theme.of(context).colorScheme.error,
                    ),
                    title: Text(
                      alert.symbol,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    subtitle: Text(
                      alert.isAbove ? 'Au-dessus de' : 'En dessous de',
                    ),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: <Widget>[
                            Text(
                              formatFcfa(alert.targetPrice),
                              style:
                                  const TextStyle(fontWeight: FontWeight.w600),
                            ),
                            if (alert.notified)
                              Text(
                                'Déclenchée',
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(color: Colors.green.shade700),
                              ),
                          ],
                        ),
                        IconButton(
                          tooltip: 'Modifier l’alerte',
                          visualDensity: VisualDensity.compact,
                          icon: const Icon(Icons.edit_outlined, size: 18),
                          onPressed: () => _editAlert(context, alert),
                        ),
                        IconButton(
                          tooltip: 'Supprimer l’alerte',
                          visualDensity: VisualDensity.compact,
                          icon: Icon(
                            Icons.delete_outline,
                            size: 18,
                            color: Theme.of(context).colorScheme.error,
                          ),
                          onPressed: () =>
                              _deleteAlert(context, ref, alert.id),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'alerts-fab',
        onPressed: () => showDialog<void>(
          context: context,
          builder: (context) => const _AlertFormDialog(),
        ),
        icon: const Icon(Icons.add_alert),
        label: const Text('Nouvelle alerte'),
      ),
    );
  }

  void _editAlert(BuildContext context, PriceAlert alert) {
    showDialog<void>(
      context: context,
      builder: (context) => _AlertFormDialog(alert: alert),
    );
  }

  Future<void> _deleteAlert(
    BuildContext context,
    WidgetRef ref,
    String alertId,
  ) async {
    if (await _confirmDelete(context, ref, alertId)) {
      await ref.read(alertsProvider.notifier).delete(alertId);
    }
  }

  Future<bool> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    String alertId,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Supprimer cette alerte ?'),
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
    return confirmed ?? false;
  }
}

/// Dialogue de création/modification d'alerte : contrôleurs possédés par
/// l'état (créés dans initState, disposés dans dispose) — aucun
/// StatefulBuilder, donc aucun écouteur ni texte réinjecté à chaque rebuild.
/// Avec [alert] non nul, le dialogue passe en mode édition : symbole fixe,
/// cours cible et direction pré-remplis.
class _AlertFormDialog extends ConsumerStatefulWidget {
  const _AlertFormDialog({this.alert});

  final PriceAlert? alert;

  @override
  ConsumerState<_AlertFormDialog> createState() => _AlertFormDialogState();
}

class _AlertFormDialogState extends ConsumerState<_AlertFormDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _symbolController;
  late final TextEditingController _priceController;
  String _direction = 'above';
  String? _symbol;
  String? _error;
  bool _saving = false;

  PriceAlert? get _alert => widget.alert;
  bool get _isEdit => _alert != null;

  @override
  void initState() {
    super.initState();
    _symbolController = TextEditingController();
    _priceController = TextEditingController(
      text: _alert?.targetPrice?.toString() ?? '',
    );
    _direction = _alert?.direction ?? 'above';
    _symbol = _alert?.symbol;
  }

  @override
  void dispose() {
    _symbolController.dispose();
    _priceController.dispose();
    super.dispose();
  }

  static final _symbolPattern = RegExp(r'^[A-Za-z0-9&.\- ]{1,15}$');

  Future<void> _save() async {
    if (_saving) return;
    final alert = _alert;
    final symbol =
        _isEdit ? alert!.symbol : _symbolController.text.trim().toUpperCase();
    if (symbol.isEmpty || !_symbolPattern.hasMatch(symbol)) {
      setState(() => _error = 'Saisissez un symbole valide.');
      return;
    }
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _error = null;
      _saving = true;
    });
    final target =
        double.parse(_priceController.text.replaceAll(',', '.'));
    final notifier = ref.read(alertsProvider.notifier);
    final message = _isEdit
        ? await notifier.updateAlert(
            alert!.id,
            targetPrice: target,
            direction: _direction,
          )
        : await notifier.create(symbol, target, _direction);
    if (!mounted) return;
    if (message == null) {
      Navigator.of(context).pop();
    } else {
      setState(() {
        _saving = false;
        _error = message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final symbols = ref.watch(palmaresSymbolsProvider).valueOrNull ??
        const <String>[];
    // Cours actuel du titre sélectionné (indicatif pour le cours cible).
    final quote = _symbol != null
        ? ref.watch(quoteProvider(_symbol!)).valueOrNull
        : null;

    return AlertDialog(
      title: Text(_isEdit ? 'Modifier l’alerte' : 'Nouvelle alerte'),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (_isEdit)
              InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'Symbole',
                  border: OutlineInputBorder(),
                ),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    _alert!.symbol,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
              )
            else if (symbols.isEmpty)
              TextFormField(
                controller: _symbolController,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: 'Symbole',
                  hintText: 'Ex. SONATEL',
                  border: OutlineInputBorder(),
                ),
              )
            else
              DropdownMenu<String>(
                controller: _symbolController,
                enableFilter: true,
                requestFocusOnTap: true,
                expandedInsets: EdgeInsets.zero,
                menuHeight: 240,
                label: const Text('Symbole'),
                inputDecorationTheme: const InputDecorationTheme(
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                dropdownMenuEntries: <DropdownMenuEntry<String>>[
                  for (final symbol in symbols)
                    DropdownMenuEntry<String>(value: symbol, label: symbol),
                ],
                onSelected: (value) => setState(() => _symbol = value),
              ),
            const SizedBox(height: 12),
            TextFormField(
              key: const Key('alert-price-field'),
              controller: _priceController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: <TextInputFormatter>[
                FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
              ],
              decoration: InputDecoration(
                labelText: 'Cours cible (FCFA)',
                helperText:
                    quote != null ? 'Cours actuel : ${formatFcfa(quote)}' : null,
                border: const OutlineInputBorder(),
              ),
              validator: (value) {
                final parsed =
                    double.tryParse((value ?? '').replaceAll(',', '.'));
                if (parsed == null || parsed <= 0) {
                  return 'Saisissez un cours valide.';
                }
                return null;
              },
            ),
            const SizedBox(height: 12),
            SegmentedButton<String>(
              showSelectedIcon: false, // sélection lisible à l'état plein, flèches toujours visibles
              segments: const <ButtonSegment<String>>[
                ButtonSegment<String>(
                  value: 'above',
                  label: Text('Au-dessus'),
                  icon: Icon(Icons.arrow_upward),
                ),
                ButtonSegment<String>(
                  value: 'below',
                  label: Text('En dessous'),
                  icon: Icon(Icons.arrow_downward),
                ),
              ],
              selected: <String>{_direction},
              onSelectionChanged: (selection) =>
                  setState(() => _direction = selection.first),
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
              : Text(_isEdit ? 'Enregistrer' : 'Créer'),
        ),
      ],
    );
  }
}
