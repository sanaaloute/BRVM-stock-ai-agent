import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/ui.dart';
import 'identifier_validation.dart';

/// Écran d'authentification unique : connexion ou création de compte
/// (identifiant e-mail/téléphone + mot de passe).
class IdentifierScreen extends ConsumerStatefulWidget {
  const IdentifierScreen({super.key});

  @override
  ConsumerState<IdentifierScreen> createState() => _IdentifierScreenState();
}

class _IdentifierScreenState extends ConsumerState<IdentifierScreen> {
  final _formKey = GlobalKey<FormState>();
  final _identifierController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _isRegister = false;
  bool _obscurePassword = true;
  bool _obscureConfirm = true;
  bool _submitting = false;
  bool _demoLoading = false;
  String? _error;

  @override
  void dispose() {
    _identifierController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  static const _weakPasswordMessage =
      'Le mot de passe doit contenir au moins 8 caractères.';

  Future<void> _submit() async {
    final identifierError = validateIdentifier(_identifierController.text);
    if (identifierError != null) {
      setState(() => _error = identifierError);
      return;
    }
    if (_isRegister && _passwordController.text.length < 8) {
      setState(() => _error = _weakPasswordMessage);
      return;
    }
    if (_isRegister &&
        _confirmController.text != _passwordController.text) {
      setState(() => _error = 'Les mots de passe ne correspondent pas.');
      return;
    }
    setState(() {
      _error = null;
      _submitting = true;
    });
    final identifier = _identifierController.text.trim();
    final password = _passwordController.text;
    final error = _isRegister
        ? await ref
            .read(authStateProvider.notifier)
            .register(identifier, password)
        : await ref
            .read(authStateProvider.notifier)
            .login(identifier, password);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (error != null) {
      setState(() => _error = error);
    }
    // En cas de succès, le redirect du routeur bascule vers l'accueil.
  }

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
                    const SizedBox(height: 24),
                    SegmentedButton<bool>(
                      showSelectedIcon: false,
                      segments: const <ButtonSegment<bool>>[
                        ButtonSegment<bool>(
                          value: false,
                          label: Text('Connexion'),
                        ),
                        ButtonSegment<bool>(
                          value: true,
                          label: Text('Créer un compte'),
                        ),
                      ],
                      selected: <bool>{_isRegister},
                      onSelectionChanged: (selection) => setState(
                          () => _isRegister = selection.first),
                    ),
                    const SizedBox(height: 20),
                    TextFormField(
                      key: const Key('identifier-field'),
                      controller: _identifierController,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'E-mail ou numéro de téléphone',
                        hintText: 'exemple@domaine.com ou +225 07 00 00 00',
                        prefixIcon: Icon(Icons.person_outline),
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      key: const Key('password-field'),
                      controller: _passwordController,
                      obscureText: _obscurePassword,
                      textInputAction:
                          _isRegister ? TextInputAction.next : TextInputAction.done,
                      onFieldSubmitted: (_) {
                        if (!_isRegister) _submit();
                      },
                      decoration: InputDecoration(
                        labelText: 'Mot de passe',
                        prefixIcon: const Icon(Icons.lock_outline),
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          tooltip: _obscurePassword
                              ? 'Afficher le mot de passe'
                              : 'Masquer le mot de passe',
                          icon: Icon(_obscurePassword
                              ? Icons.visibility_outlined
                              : Icons.visibility_off_outlined),
                          onPressed: () => setState(
                              () => _obscurePassword = !_obscurePassword),
                        ),
                      ),
                    ),
                    if (_isRegister) ...<Widget>[
                      const SizedBox(height: 12),
                      TextFormField(
                        key: const Key('confirm-field'),
                        controller: _confirmController,
                        obscureText: _obscureConfirm,
                        textInputAction: TextInputAction.done,
                        onFieldSubmitted: (_) => _submit(),
                        decoration: InputDecoration(
                          labelText: 'Confirmer le mot de passe',
                          prefixIcon: const Icon(Icons.lock_outline),
                          border: const OutlineInputBorder(),
                          suffixIcon: IconButton(
                            tooltip: _obscureConfirm
                                ? 'Afficher le mot de passe'
                                : 'Masquer le mot de passe',
                            icon: Icon(_obscureConfirm
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined),
                            onPressed: () => setState(() =>
                                _obscureConfirm = !_obscureConfirm),
                          ),
                        ),
                      ),
                    ],
                    if (_error != null) FormError(message: _error!),
                    const SizedBox(height: 20),
                    FilledButton(
                      key: const Key('auth-submit'),
                      onPressed: _submitting ? null : _submit,
                      child: _submitting
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(_isRegister
                              ? 'Créer mon compte'
                              : 'Se connecter'),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Créez votre compte local : e-mail ou numéro + mot de passe.',
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
                      'Mode démo : accès immédiat quand le serveur l’autorise.',
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
