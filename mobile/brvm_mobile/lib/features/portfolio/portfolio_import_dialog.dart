import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/ui.dart';
import 'portfolio_models.dart';
import 'portfolio_providers.dart';

class SgiImportDialog extends ConsumerStatefulWidget {
  const SgiImportDialog({super.key});

  static Future<bool> show(BuildContext context) async {
    return await showDialog<bool>(
          context: context,
          builder: (_) => const SgiImportDialog(),
        ) ??
        false;
  }

  @override
  ConsumerState<SgiImportDialog> createState() => _SgiImportDialogState();
}

class _SgiImportDialogState extends ConsumerState<SgiImportDialog> {
  SgiImportPreview? _preview;
  String? _error;
  bool _parsing = false;
  bool _applying = false;

  Future<void> _pickAndParse() async {
    setState(() {
      _parsing = true;
      _error = null;
    });
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: <String>['pdf', 'docx'],
        allowMultiple: false,
        withData: true,
      );
      if (result == null) {
        if (mounted) setState(() => _parsing = false);
        return;
      }
      final file = result.files.single;
      final bytes = file.bytes;
      if (bytes == null) {
        throw StateError('Impossible de lire le document sélectionné.');
      }
      if (bytes.length > 10 * 1024 * 1024) {
        throw StateError('Le document dépasse la taille maximale de 10 Mo.');
      }
      final preview = await ref
          .read(portfolioRepositoryProvider)
          .parseImport(bytes, file.name);
      if (!mounted) return;
      setState(() => _preview = preview);
    } on StateError catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Impossible d’analyser ce document.');
      }
    } finally {
      if (mounted) setState(() => _parsing = false);
    }
  }

  Future<void> _confirm() async {
    final preview = _preview;
    if (preview == null || preview.transactions.isEmpty) return;
    setState(() => _applying = true);
    try {
      await ref
          .read(portfolioRepositoryProvider)
          .confirmImport(preview.contentHash, preview.transactions);
      if (!mounted) return;
      ref.invalidate(portfolioProvider);
      ref.invalidate(portfolioHistoryProvider);
      Navigator.of(context).pop(true);
    } on StateError catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _applying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final preview = _preview;
    return AlertDialog(
      title: const Text('Importer un document SGI'),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              if (preview == null) ...<Widget>[
                Text(
                  'Sélectionnez un relevé PDF ou DOCX contenant du texte. '
                  'Les achats, ventes et dividendes seront extraits puis affichés pour vérification.',
                  style: theme.textTheme.bodyMedium,
                ),
                const SizedBox(height: 8),
                Text(
                  'Le document n’est pas conservé. Taille maximale : 10 Mo.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.muted,
                  ),
                ),
              ] else ...<Widget>[
                if (preview.warnings.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      preview.warnings.join('\n'),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.tertiary,
                      ),
                    ),
                  ),
                if (preview.transactions.isEmpty)
                  const Text('Aucune transaction valide détectée.')
                else
                  for (final tx in preview.transactions)
                    _TransactionRow(transaction: tx),
              ],
              if (_parsing)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Center(child: CircularProgressIndicator()),
                ),
              if (_error != null) FormError(message: _error!),
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _applying ? null : () => Navigator.of(context).pop(false),
          child: const Text('Annuler'),
        ),
        if (preview == null)
          FilledButton(
            onPressed: _parsing ? null : _pickAndParse,
            child: const Text('Choisir le document'),
          )
        else ...<Widget>[
          TextButton(
            onPressed: (_parsing || _applying) ? null : _pickAndParse,
            child: const Text('Autre document'),
          ),
          FilledButton(
            onPressed: (_applying || preview.transactions.isEmpty)
                ? null
                : _confirm,
            child: _applying
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Confirmer l’import'),
          ),
        ],
      ],
    );
  }
}

class _TransactionRow extends StatelessWidget {
  const _TransactionRow({required this.transaction});

  final SgiTransaction transaction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: 64,
            child: Text(
              transaction.symbol,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
          SizedBox(width: 52, child: Text(transaction.sideLabel)),
          Expanded(
            child: Text(
              transaction.side == 'dividend'
                  ? '${formatFcfa(transaction.amount)}\n${transaction.date}\n${transaction.sgi}'
                  : '${formatAmount(transaction.quantity)} titres @ '
                        '${formatFcfa(transaction.price)}\n${transaction.date}\n${transaction.sgi}',
              style: theme.textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}
