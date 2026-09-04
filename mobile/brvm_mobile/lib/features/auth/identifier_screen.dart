import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/ui.dart';
import 'identifier_validation.dart';

/// Écran 1 : saisie de l'identifiant (e-mail ou téléphone).
class IdentifierScreen extends ConsumerStatefulWidget {
  const IdentifierScreen({super.key});

  @override
  ConsumerState<IdentifierScreen> createState() => _IdentifierScreenState();
}

class _IdentifierScreenState extends ConsumerState<IdentifierScreen> {
  final _formKey = GlobalKey<FormState>();
  final _controller = TextEditingController();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final validationError = validateIdentifier(_controller.text);
    if (validationError != null) {
      setState(() => _error = validationError);
      return;
    }
    setState(() {
      _error = null;
      _submitting = true;
    });
    final result =
        await ref.read(authStateProvider.notifier).requestCode(_controller.text.trim());
    if (!mounted) return;
    setState(() => _submitting = false);
    if (result.ok) {
      context.push(
        '/auth/otp',
        extra: <String, dynamic>{
          'identifier': _controller.text.trim(),
          'channel': result.channel,
          'devCode': result.devCode,
        },
      );
    } else {
      setState(() => _error = result.errorMessage);
    }
  }

  bool _demoLoading = false;

  Future<void> _demoLogin() async {
    setState(() {
      _error = null;
      _demoLoading = true;
    });
    final error = await ref.read(authStateProvider.notifier).devLogin();
    if (!mounted) return;
    setState(() => _demoLoading = false);
    if (error != null) {
      setState(() => _error = error);
    }
    // En cas de succès, le redirect du routeur bascule vers l'accueil.
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Icon(
                      Icons.candlestick_chart,
                      size: 64,
                      color: theme.colorScheme.primary,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Kora Bourse',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineMedium
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Kora, votre agent boursier IA pour la bourse régionale d’Afrique de l’Ouest.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 32),
                    TextFormField(
                      key: const Key('identifier-field'),
                      controller: _controller,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.done,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: const InputDecoration(
                        labelText: 'E-mail ou numéro de téléphone',
                        hintText: 'exemple@domaine.com ou +225 07 00 00 00',
                        prefixIcon: Icon(Icons.person_outline),
                        border: OutlineInputBorder(),
                      ),
                    ),
                    if (_error != null) FormError(message: _error!),
                    const SizedBox(height: 20),
                    FilledButton(
                      key: const Key('identifier-submit'),
                      onPressed: _submitting ? null : _submit,
                      child: _submitting
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Recevoir le code'),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Un code de vérification à 6 chiffres vous sera envoyé par e-mail ou SMS.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.muted),
                    ),
                    const SizedBox(height: 24),
                    OutlinedButton.icon(
                      key: const Key('demo-login'),
                      onPressed: _demoLoading ? null : _demoLogin,
                      icon: _demoLoading
                          ? const SizedBox(
                              height: 18,
                              width: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.bolt_outlined),
                      label: const Text('Explorer sans compte (mode démo)'),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Pendant que l’envoi de codes (e-mail/SMS) n’est pas encore configuré.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.muted),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
