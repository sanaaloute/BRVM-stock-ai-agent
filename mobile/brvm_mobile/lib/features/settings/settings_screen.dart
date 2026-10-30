import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../core/config.dart';
import '../../core/format.dart';
import '../../core/models/auth_user.dart';
import '../../core/providers.dart';
import '../../core/theme_provider.dart';
import '../../core/ui.dart';
import '../portfolio/portfolio_models.dart';
import '../portfolio/portfolio_providers.dart';
import 'settings_providers.dart';

/// Onglet « Moi » (Compte) : en-tête profil (icône personne, nom, coordonnées),
/// synthèse du portefeuille, préférences (apparence),
/// quota, version, déconnexion et suppression du compte.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authStateProvider);
    final sessionUser = auth is AuthAuthenticated ? auth.user : null;
    // Profil frais du serveur ; repli sur l'utilisateur de session (la carte
    // s'affiche toujours, même pendant AuthLoading ou si /me échoue).
    final me = ref.watch(meProvider).valueOrNull;
    final user = me ?? sessionUser;
    final quota = ref.watch(quotaProvider);

    return Scaffold(
      appBar: const KoraAppBar(title: Text('Compte')),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(meProvider);
          ref.invalidate(accountPortfolioProvider);
          ref.invalidate(quotaProvider);
        },
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: <Widget>[
          _ProfileHeaderCard(user: user),
          const SizedBox(height: 16),
          const _PortfolioOverviewCard(),
          const SizedBox(height: 16),
          Text('Préférences', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const _AppearanceCard(),
          const SizedBox(height: 16),
          Text('Utilisation', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          quota.when(
            loading: () => const Card(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: LoadingView(),
              ),
            ),
            error: (error, _) => Card(
              child: ErrorView(
                message: 'Quota indisponible.\n$error',
                onRetry: () => ref.invalidate(quotaProvider),
              ),
            ),
            data: (q) => Card(
              child: ListTile(
                leading: const Icon(Icons.speed_outlined),
                title: const Text('Quota du chat IA'),
                subtitle: Text(
                  q.exempt
                      ? 'Illimité (compte exempté)'
                      : '${q.used ?? '—'} / ${q.limit ?? '—'} requêtes utilisées',
                ),
              ),
            ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.tonalIcon(
              onPressed: () => _confirmSignOut(context, ref),
              icon: const Icon(Icons.logout),
              label: const Text('Se déconnecter'),
            ),
          ),
          const SizedBox(height: 4),
          SizedBox(
            width: double.infinity,
            child: TextButton.icon(
              onPressed: () => showDialog<void>(
                context: context,
                builder: (context) => _DeleteAccountDialog(
                  hasPassword: user?.hasPassword ?? false,
                ),
              ),
              icon: Icon(
                Icons.delete_forever_outlined,
                color: Theme.of(context).colorScheme.error,
              ),
              label: Text(
                'Supprimer mon compte',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          ),
          const SizedBox(height: 16),
          const _VersionTile(),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Se déconnecter ?'),
        content: const Text('Vous devrez vous reconnecter avec votre e-mail/numéro et votre mot de passe.'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Se déconnecter'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(authStateProvider.notifier).signOut();
    }
  }
}

/// En-tête profil : photo (ou icône personne sur fond plein), nom choisi
/// (sinon l'e-mail/numéro), e-mail/numéro en gris sous le nom, coordonnées,
/// et accès à l'édition du profil et du mot de passe.
class _ProfileHeaderCard extends ConsumerWidget {
  const _ProfileHeaderCard({required this.user});

  final AuthUser? user;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final name = user?.name?.trim() ?? '';
    final hasName = name.isNotEmpty;
    final contact = user?.email ?? user?.phone ?? '';
    // Local final : promu non-null dans les closures après test (le champ
    // `user` du widget, lui, ne se promeut pas).
    final currentUser = user;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _ProfileAvatar(user: user),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        hasName
                            ? name
                            : (contact.isEmpty ? 'Utilisateur' : contact),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleLarge
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                      if (hasName && contact.isNotEmpty) ...<Widget>[
                        const SizedBox(height: 4),
                        Text(
                          contact,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall
                              ?.copyWith(color: colors.muted),
                        ),
                      ],
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Modifier le profil',
                  onPressed: currentUser == null
                      ? null
                      : () => showDialog<void>(
                            context: context,
                            builder: (context) =>
                                _EditProfileDialog(user: currentUser),
                          ),
                  icon: const Icon(Icons.edit_outlined),
                ),
              ],
            ),
            if (user?.hasTelegram ?? false) ...<Widget>[
              const SizedBox(height: 12),
              const _ContactRow(
                  icon: Icons.send_outlined, text: 'Telegram lié'),
            ],
            const Divider(height: 24),
            InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: currentUser == null
                  ? null
                  : () => showDialog<void>(
                        context: context,
                        builder: (context) => _ChangePasswordDialog(
                          hasPassword: currentUser.hasPassword,
                        ),
                      ),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: <Widget>[
                    Icon(Icons.lock_outline, size: 18, color: colors.muted),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        (user?.hasPassword ?? false)
                            ? 'Changer le mot de passe'
                            : 'Définir un mot de passe',
                      ),
                    ),
                    Icon(Icons.chevron_right, color: colors.muted),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Avatar du profil : photo téléversée quand elle existe, sinon icône
/// personne sur pastille neutre bordée (suit le thème clair/sombre).
class _ProfileAvatar extends ConsumerWidget {
  const _ProfileAvatar({required this.user});

  final AuthUser? user;

  /// Pastille de repli neutre : surface en tonalité du thème + bordure.
  static Widget placeholder(ColorScheme colors, {double size = 64}) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: colors.surfaceContainerHighest,
        border: Border.all(color: colors.outlineVariant),
      ),
      alignment: Alignment.center,
      child: Icon(Icons.person_outline, color: colors.muted, size: size * 0.53),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = Theme.of(context).colorScheme;
    final user = this.user;
    if (user != null && user.hasPhoto) {
      final photo = ref.watch(userPhotoProvider).valueOrNull;
      if (photo != null) {
        return ClipOval(
          child: Image.memory(
            photo,
            width: 64,
            height: 64,
            fit: BoxFit.cover,
            gaplessPlayback: true,
          ),
        );
      }
    }
    return placeholder(colors);
  }
}

/// Champ mot de passe avec icône afficher/masquer.
class _PasswordField extends StatefulWidget {
  const _PasswordField({required this.controller, required this.label});

  final TextEditingController controller;
  final String label;

  @override
  State<_PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<_PasswordField> {
  bool _obscure = true;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: widget.controller,
      obscureText: _obscure,
      decoration: InputDecoration(
        labelText: widget.label,
        border: const OutlineInputBorder(),
        suffixIcon: IconButton(
          tooltip: _obscure
              ? 'Afficher le mot de passe'
              : 'Masquer le mot de passe',
          icon: Icon(
            _obscure
                ? Icons.visibility_outlined
                : Icons.visibility_off_outlined,
            size: 20,
          ),
          onPressed: () => setState(() => _obscure = !_obscure),
        ),
      ),
    );
  }
}

/// Dialogue d'édition du profil : photo, nom, e-mail, téléphone. Les comptes
/// avec mot de passe doivent confirmer le mot de passe actuel pour
/// enregistrer.
class _EditProfileDialog extends ConsumerStatefulWidget {
  const _EditProfileDialog({required this.user});

  final AuthUser user;

  @override
  ConsumerState<_EditProfileDialog> createState() => _EditProfileDialogState();
}

class _EditProfileDialogState extends ConsumerState<_EditProfileDialog> {
  static const int _maxPhotoBytes = 2 * 1024 * 1024;

  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nameController;
  late final TextEditingController _emailController;
  late final TextEditingController _phoneController;
  late final TextEditingController _passwordController;
  Uint8List? _photoBytes;
  String _photoName = 'avatar.jpg';
  bool _photoRemoved = false;
  bool _saving = false;
  String? _error;

  bool get _hasPassword => widget.user.hasPassword;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.user.name ?? '');
    _emailController = TextEditingController(text: widget.user.email ?? '');
    _phoneController = TextEditingController(text: widget.user.phone ?? '');
    _passwordController = TextEditingController();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _pickPhoto() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.image,
      allowMultiple: false,
      withData: true,
    );
    if (result == null) return;
    final file = result.files.single;
    final bytes = file.bytes;
    if (bytes == null) {
      setState(() => _error = 'Impossible de lire cette image.');
      return;
    }
    if (bytes.length > _maxPhotoBytes) {
      setState(() => _error = 'La photo dépasse la taille maximale de 2 Mo.');
      return;
    }
    setState(() {
      _error = null;
      _photoBytes = bytes;
      _photoName = file.name;
      _photoRemoved = false;
    });
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_hasPassword && _passwordController.text.isEmpty) {
      setState(() =>
          _error = 'Confirmez votre mot de passe actuel pour enregistrer.');
      return;
    }
    setState(() {
      _error = null;
      _saving = true;
    });
    final notifier = ref.read(authStateProvider.notifier);
    // 1) Profil d'abord : le serveur valide le mot de passe actuel avant
    //    tout changement — si la confirmation échoue, rien n'est modifié.
    final message = await notifier.updateProfile(
      name: _nameController.text.trim(),
      email: _emailController.text.trim(),
      phone: _phoneController.text.trim(),
      currentPassword: _hasPassword ? _passwordController.text : null,
    );
    if (message != null) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = message;
      });
      return;
    }
    // 2) Photo ensuite : remplacement ou suppression.
    try {
      final repo = ref.read(authRepositoryProvider);
      if (_photoBytes != null) {
        await repo.uploadPhoto(_photoBytes!, _photoName);
      } else if (_photoRemoved) {
        await repo.deletePhoto();
      }
    } on AuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = e.message;
      });
      return;
    }
    await notifier.refreshProfile();
    ref.invalidate(meProvider);
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final photo = _photoBytes ??
        (_photoRemoved ? null : ref.watch(userPhotoProvider).valueOrNull);
    return AlertDialog(
      title: const Text('Modifier le profil'),
      // Défilement activé : le clavier réduit la hauteur du dialogue.
      scrollable: true,
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Row(
              children: <Widget>[
                if (photo != null)
                  ClipOval(
                    child: Image.memory(
                      photo,
                      width: 56,
                      height: 56,
                      fit: BoxFit.cover,
                      gaplessPlayback: true,
                    ),
                  )
                else
                  _ProfileAvatar.placeholder(colors, size: 56),
                const SizedBox(width: 12),
                Expanded(
                  child: Wrap(
                    spacing: 8,
                    children: <Widget>[
                      TextButton.icon(
                        onPressed: _saving ? null : _pickPhoto,
                        icon: const Icon(Icons.photo_library_outlined,
                            size: 18),
                        label: const Text('Changer la photo'),
                      ),
                      if (photo != null)
                        TextButton.icon(
                          onPressed: _saving
                              ? null
                              : () => setState(() {
                                    _photoBytes = null;
                                    _photoRemoved = true;
                                  }),
                          icon: Icon(Icons.delete_outline,
                              size: 18, color: colors.error),
                          label: Text(
                            'Retirer',
                            style: TextStyle(color: colors.error),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _nameController,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Nom complet (facultatif)',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _emailController,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'E-mail',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _phoneController,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Téléphone',
                hintText: '+225...',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            if (_hasPassword)
              _PasswordField(
                controller: _passwordController,
                label: 'Mot de passe actuel (confirmation)',
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

/// Dialogue de changement de mot de passe : mot de passe actuel (comptes qui
/// en ont un), nouveau mot de passe et confirmation.
class _ChangePasswordDialog extends ConsumerStatefulWidget {
  const _ChangePasswordDialog({required this.hasPassword});

  final bool hasPassword;

  @override
  ConsumerState<_ChangePasswordDialog> createState() =>
      _ChangePasswordDialogState();
}

class _ChangePasswordDialogState
    extends ConsumerState<_ChangePasswordDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _currentController;
  late final TextEditingController _newController;
  late final TextEditingController _confirmController;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _currentController = TextEditingController();
    _newController = TextEditingController();
    _confirmController = TextEditingController();
  }

  @override
  void dispose() {
    _currentController.dispose();
    _newController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (widget.hasPassword && _currentController.text.isEmpty) {
      setState(() => _error = 'Saisissez votre mot de passe actuel.');
      return;
    }
    final newPassword = _newController.text;
    if (newPassword.length < 6) {
      setState(() => _error =
          'Le nouveau mot de passe doit contenir au moins 6 caractères.');
      return;
    }
    if (newPassword != _confirmController.text) {
      setState(() => _error =
          'La confirmation ne correspond pas au nouveau mot de passe.');
      return;
    }
    setState(() {
      _error = null;
      _saving = true;
    });
    // Capturé avant la fermeture : le contexte du dialogue est désactivé
    // par pop().
    final messenger = ScaffoldMessenger.of(context);
    final message = await ref.read(authStateProvider.notifier).changePassword(
          currentPassword:
              widget.hasPassword ? _currentController.text : null,
          newPassword: newPassword,
        );
    if (!mounted) return;
    setState(() => _saving = false);
    if (message == null) {
      Navigator.of(context).pop();
      messenger.showSnackBar(
        const SnackBar(content: Text('Mot de passe mis à jour.')),
      );
    } else {
      setState(() => _error = message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.hasPassword
          ? 'Changer le mot de passe'
          : 'Définir un mot de passe'),
      scrollable: true,
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (widget.hasPassword) ...<Widget>[
              _PasswordField(
                controller: _currentController,
                label: 'Mot de passe actuel',
              ),
              const SizedBox(height: 12),
            ],
            _PasswordField(
              controller: _newController,
              label: 'Nouveau mot de passe',
            ),
            const SizedBox(height: 12),
            _PasswordField(
              controller: _confirmController,
              label: 'Confirmer le nouveau mot de passe',
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

/// Ligne de contact avec petite icône (e-mail, téléphone…).
class _ContactRow extends StatelessWidget {
  const _ContactRow({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        children: <Widget>[
          Icon(icon, size: 14, color: colors.muted),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              text,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: colors.muted),
            ),
          ),
        ],
      ),
    );
  }
}

/// Carte synthèse du portefeuille : valeur totale, performance, dividendes,
/// nombre de positions, et raccourci vers l'onglet Portefeuille.
class _PortfolioOverviewCard extends ConsumerWidget {
  const _PortfolioOverviewCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final portfolio = ref.watch(accountPortfolioProvider);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: portfolio.when(
          loading: () => const SizedBox(height: 96, child: LoadingView()),
          error: (error, _) => ErrorView(
            message: 'Portefeuille indisponible.\n$error',
            onRetry: () => ref.invalidate(accountPortfolioProvider),
          ),
          data: (data) => _PortfolioOverviewBody(data: data),
        ),
      ),
    );
  }
}

class _PortfolioOverviewBody extends StatelessWidget {
  const _PortfolioOverviewBody({required this.data});

  final PortfolioData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final summary = data.summary;
    final positions = summary.positionsCount ?? data.positions.length;
    final empty = positions == 0 && (summary.totalValueFcfa ?? 0) == 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Icon(Icons.pie_chart_outline, size: 20, color: colors.muted),
            const SizedBox(width: 8),
            Expanded(
              child: Text('Portefeuille', style: theme.textTheme.titleMedium),
            ),
            TextButton(
              key: const Key('account-portfolio-link'),
              onPressed: () => context.go('/portefeuille'),
              child: const Text('Gérer'),
            ),
          ],
        ),
        if (empty) ...<Widget>[
          const SizedBox(height: 4),
          Text(
            'Aucune position pour le moment.',
            style: theme.textTheme.bodyMedium?.copyWith(color: colors.muted),
          ),
        ] else ...<Widget>[
          Text(
            'Valeur totale',
            style: theme.textTheme.bodySmall?.copyWith(color: colors.muted),
          ),
          const SizedBox(height: 2),
          PriceText(
            summary.totalValueFcfa,
            style: theme.textTheme.headlineMedium,
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              StatChip(
                label: 'Gain/Perte',
                value: formatSignedFcfa(summary.totalGainLossFcfa),
              ),
              StatChip(
                label: 'Dividendes',
                value: formatFcfa(summary.dividendsFcfa),
              ),
              StatChip(label: 'Positions', value: '$positions'),
            ],
          ),
        ],
      ],
    );
  }
}

/// Dialogue de confirmation de suppression du compte (irréversible).
/// Demande le mot de passe uniquement si le compte en a un ([hasPassword]) ;
/// les comptes démo confirment directement. En cas de succès, le dialogue se
/// ferme : l'état auth repasse en non authentifié et la redirection du
/// routeur renvoie vers /auth/identifier.
class _DeleteAccountDialog extends ConsumerStatefulWidget {
  const _DeleteAccountDialog({required this.hasPassword});

  final bool hasPassword;

  @override
  ConsumerState<_DeleteAccountDialog> createState() =>
      _DeleteAccountDialogState();
}

class _DeleteAccountDialogState extends ConsumerState<_DeleteAccountDialog> {
  late final TextEditingController _passwordController;
  String? _error;
  bool _deleting = false;

  @override
  void initState() {
    super.initState();
    _passwordController = TextEditingController();
  }

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  bool get _canConfirm =>
      !_deleting &&
      (!widget.hasPassword || _passwordController.text.isNotEmpty);

  Future<void> _delete() async {
    if (_deleting) return;
    setState(() {
      _error = null;
      _deleting = true;
    });
    final message = await ref.read(authStateProvider.notifier).deleteAccount(
          password: widget.hasPassword ? _passwordController.text : null,
        );
    if (!mounted) return;
    if (message == null) {
      Navigator.of(context).pop();
    } else {
      setState(() {
        _deleting = false;
        _error = message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('Supprimer définitivement ?'),
      scrollable: true,
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Cette action est irréversible : votre compte, votre portefeuille, '
            'votre liste de suivi, vos alertes et vos conversations seront '
            'définitivement supprimés.',
          ),
          if (widget.hasPassword) ...<Widget>[
            const SizedBox(height: 16),
            TextField(
              key: const Key('delete-account-password'),
              controller: _passwordController,
              obscureText: true,
              enabled: !_deleting,
              // Ouvre le clavier dès l'affichage du dialogue : sur certains
              // appareils le tap ne réveille pas le clavier pour un champ
              // mot de passe dans un dialogue (clavier « sécurisé » OEM).
              autofocus: true,
              keyboardType: TextInputType.visiblePassword,
              autofillHints: const <String>[AutofillHints.password],
              textInputAction: TextInputAction.done,
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) {
                if (_canConfirm) _delete();
              },
              decoration: const InputDecoration(
                labelText: 'Mot de passe',
                hintText: 'Confirmez avec votre mot de passe',
                border: OutlineInputBorder(),
              ),
            ),
          ],
          if (_error != null) FormError(message: _error!),
        ],
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _deleting ? null : () => Navigator.of(context).pop(),
          child: const Text('Annuler'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: colors.error,
            foregroundColor: colors.onError,
          ),
          onPressed: _canConfirm ? _delete : null,
          child: _deleting
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Supprimer définitivement'),
        ),
      ],
    );
  }
}

class _AppearanceCard extends ConsumerWidget {
  const _AppearanceCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // En cours de chargement (prefs), on affiche le défaut sombre.
    final themeMode = ref.watch(themeModeProvider).value ?? ThemeMode.dark;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: <Widget>[
            Icon(Icons.brightness_6_outlined,
                size: 20, color: Theme.of(context).colorScheme.muted),
            const SizedBox(width: 12),
            Expanded(
              child: SegmentedButton<ThemeMode>(
                showSelectedIcon: false,
                style: const ButtonStyle(
                  visualDensity: VisualDensity.compact,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                segments: const <ButtonSegment<ThemeMode>>[
                  ButtonSegment<ThemeMode>(
                    value: ThemeMode.system,
                    label: Text('Système'),
                  ),
                  ButtonSegment<ThemeMode>(
                    value: ThemeMode.light,
                    label: Text('Clair'),
                  ),
                  ButtonSegment<ThemeMode>(
                    value: ThemeMode.dark,
                    label: Text('Sombre'),
                  ),
                ],
                selected: <ThemeMode>{themeMode},
                onSelectionChanged: (selection) => ref
                    .read(themeModeProvider.notifier)
                    .setMode(selection.first),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _VersionTile extends StatefulWidget {
  const _VersionTile();

  @override
  State<_VersionTile> createState() => _VersionTileState();
}

class _VersionTileState extends State<_VersionTile> {
  String _version = AppConfig.appName;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final info = await PackageInfo.fromPlatform();
      if (mounted) {
        setState(() => _version = '${AppConfig.appName} v${info.version}');
      }
    } catch (_) {
      // Version indisponible (tests) : on garde le nom de l'app.
    }
  }

  @override
  Widget build(BuildContext context) {
    return Text(
      _version,
      textAlign: TextAlign.center,
      style: Theme.of(context)
          .textTheme
          .bodySmall
          ?.copyWith(color: Theme.of(context).colorScheme.muted),
    );
  }
}
