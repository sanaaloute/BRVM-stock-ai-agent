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
            return const EmptyView(
              message: 'Aucune alerte.\nCréez une alerte pour être notifié quand un titre atteint un cours cible.',
              icon: Icons.notifications_none,
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
                    trailing: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: <Widget>[
                        Text(
                          formatFcfa(alert.targetPrice),
                          style: const TextStyle(fontWeight: FontWeight.w600),
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
          builder: (context) => const _CreateAlertDialog(),
        ),
        icon: const Icon(Icons.add_alert),
        label: const Text('Nouvelle alerte'),
      ),
    );
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

/// Dialogue de création d'alerte : contrôleurs possédés par l'état
/// (créés dans initState, disposés dans dispose) — aucun StatefulBuilder,
/// donc aucun écouteur ni texte réinjecté à chaque rebuild.
class _CreateAlertDialog extends ConsumerStatefulWidget {
  const _CreateAlertDialog();

  @override
  ConsumerState<_CreateAlertDialog> createState() =>
      _CreateAlertDialogState();
}

class _CreateAlertDialogState extends ConsumerState<_CreateAlertDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _symbolController;
  late final TextEditingController _priceController;
  String _direction = 'above';
  String? _symbol;
  String? _error;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _symbolController = TextEditingController();
    _priceController = TextEditingController();
  }

  @override
  void dispose() {
    _symbolController.dispose();
    _priceController.dispose();
    super.dispose();
  }

  static final _symbolPattern = RegExp(r'^[A-Za-z0-9&.\- ]{1,15}$');

  Future<void> _create() async {
    if (_saving) return;
    final symbol = _symbolController.text.trim().toUpperCase();
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
    final message = await ref
        .read(alertsProvider.notifier)
        .create(symbol, target, _direction);
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
      title: const Text('Nouvelle alerte'),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (symbols.isEmpty)
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
          onPressed: _saving ? null : _create,
          child: _saving
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Créer'),
        ),
      ],
    );
  }
}
