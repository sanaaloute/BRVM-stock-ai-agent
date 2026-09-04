import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/ui.dart';

/// Écran 2 : saisie du code OTP à 6 chiffres.
class OtpScreen extends ConsumerStatefulWidget {
  const OtpScreen({
    super.key,
    required this.identifier,
    required this.channel,
    this.devCode,
  });

  final String identifier;
  final String channel;
  final String? devCode;

  static OtpScreen fromState(GoRouterState state) {
    final extra = state.extra;
    final map = extra is Map ? extra : const <String, dynamic>{};
    return OtpScreen(
      identifier: map['identifier'] as String? ?? '',
      channel: map['channel'] as String? ?? 'email',
      devCode: map['devCode'] as String?,
    );
  }

  @override
  ConsumerState<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends ConsumerState<OtpScreen> {
  final _controllers = List<TextEditingController>.generate(
    6,
    (_) => TextEditingController(),
  );
  final _focusNodes = List<FocusNode>.generate(6, (_) => FocusNode());
  bool _submitting = false;
  String? _error;
  int _cooldown = 0;
  Timer? _cooldownTimer;

  @override
  void initState() {
    super.initState();
    _startCooldown(60);
  }

  @override
  void dispose() {
    _cooldownTimer?.cancel();
    for (final c in _controllers) {
      c.dispose();
    }
    for (final f in _focusNodes) {
      f.dispose();
    }
    super.dispose();
  }

  void _startCooldown(int seconds) {
    _cooldownTimer?.cancel();
    setState(() => _cooldown = seconds);
    _cooldownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() => _cooldown--);
      if (_cooldown <= 0) timer.cancel();
    });
  }

  String get _code => _controllers.map((c) => c.text).join();

  bool get _codeComplete =>
      _code.length == 6 && _controllers.every((c) => c.text.isNotEmpty);

  void _onChanged(int index, String value) {
    if (value.isNotEmpty && index < 5) {
      _focusNodes[index + 1].requestFocus();
    }
    if (_codeComplete && !_submitting) {
      _submit();
    }
  }

  Future<void> _submit() async {
    if (!_codeComplete) {
      setState(() => _error = 'Veuillez saisir les 6 chiffres du code.');
      return;
    }
    setState(() {
      _error = null;
      _submitting = true;
    });
    final result = await ref
        .read(authStateProvider.notifier)
        .verifyCode(widget.identifier, _code);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (!result.isSuccess) {
      setState(() => _error = result.errorMessage);
      for (final c in _controllers) {
        c.clear();
      }
      _focusNodes.first.requestFocus();
    }
    // En cas de succès, le redirect du routeur bascule vers l'accueil.
  }

  Future<void> _resend() async {
    if (_cooldown > 0) return;
    final result =
        await ref.read(authStateProvider.notifier).requestCode(widget.identifier);
    if (!mounted) return;
    if (result.ok) {
      _startCooldown(result.retryAfterSeconds ?? 60);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(widget.channel == 'phone'
              ? 'Nouveau code envoyé par SMS.'
              : 'Nouveau code envoyé par e-mail.'),
        ),
      );
    } else {
      setState(() => _error = result.errorMessage);
      if (result.retryAfterSeconds != null) {
        _startCooldown(result.retryAfterSeconds!);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final destination =
        widget.channel == 'phone' ? 'par SMS' : 'par e-mail';
    return Scaffold(
      appBar: AppBar(title: const Text('Vérification')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Text(
                    'Code de vérification',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Un code à 6 chiffres a été envoyé $destination à\n${widget.identifier}.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium,
                  ),
                  if (widget.devCode != null) ...<Widget>[
                    const SizedBox(height: 12),
                    Card(
                      color: theme.colorScheme.tertiaryContainer,
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Text(
                          'Code de développement : ${widget.devCode}',
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 32),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List<Widget>.generate(6, (i) {
                      return Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 4),
                        child: SizedBox(
                          width: 44,
                          child: TextField(
                            key: Key('otp-field-$i'),
                            controller: _controllers[i],
                            focusNode: _focusNodes[i],
                            textAlign: TextAlign.center,
                            keyboardType: TextInputType.number,
                            maxLength: 1,
                            inputFormatters: <TextInputFormatter>[
                              FilteringTextInputFormatter.digitsOnly,
                            ],
                            decoration: const InputDecoration(
                              counterText: '',
                              border: OutlineInputBorder(),
                            ),
                            onChanged: (value) => _onChanged(i, value),
                          ),
                        ),
                      );
                    }),
                  ),
                  if (_error != null) FormError(message: _error!),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _submitting ? null : _submit,
                    child: _submitting
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Vérifier'),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: _cooldown > 0 ? null : _resend,
                    child: Text(_cooldown > 0
                        ? 'Renvoyer le code (${_cooldown}s)'
                        : 'Renvoyer le code'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
