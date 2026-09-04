import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../core/config.dart';
import '../../core/providers.dart';
import '../../core/push_service.dart';
import '../../core/theme_provider.dart';
import '../../core/ui.dart';
import 'settings_providers.dart';

/// Onglet « Moi » (Compte) : profil, apparence (thème), digest,
/// notifications, quota, version, déconnexion.
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
    final digest = ref.watch(digestProvider);
    final quota = ref.watch(quotaProvider);

    return Scaffold(
      appBar: const KoraAppBar(title: Text('Compte')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: <Widget>[
                  CircleAvatar(
                    radius: 24,
                    backgroundColor: Theme.of(context)
                        .colorScheme
                        .primary
                        .withValues(alpha: 0.15),
                    child: Icon(
                      Icons.person_outline,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          user?.displayName ?? 'Utilisateur',
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.bold),
                        ),
                        if (user?.email != null) ...<Widget>[
                          const SizedBox(height: 2),
                          Text(
                            user!.email!,
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(
                                    color:
                                        Theme.of(context).colorScheme.muted),
                          ),
                        ],
                        if (user?.phone != null &&
                            user?.phone != user?.displayName) ...<Widget>[
                          const SizedBox(height: 2),
                          Text(
                            user!.phone!,
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(
                                    color:
                                        Theme.of(context).colorScheme.muted),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('Apparence', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const _AppearanceCard(),
          const SizedBox(height: 16),
          Text('Récapitulatif (digest)',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          digest.when(
            loading: () => const Card(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: LoadingView(),
              ),
            ),
            error: (error, _) => ErrorView(
              message: 'Digest indisponible.\n$error',
              onRetry: () => ref.invalidate(digestProvider),
            ),
            data: (settings) => Card(
              child: Column(
                children: <Widget>[
                  SwitchListTile(
                    title: const Text('Recevoir le digest'),
                    subtitle: const Text(
                        'Résumé périodique du marché par notification.'),
                    value: settings.enabled,
                    onChanged: (value) => ref
                        .read(digestProvider.notifier)
                        .save(settings.frequency, value),
                  ),
                  const Divider(height: 1),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: <Widget>[
                        const Expanded(child: Text('Fréquence')),
                        SegmentedButton<String>(
                          segments: const <ButtonSegment<String>>[
                            ButtonSegment<String>(
                                value: 'daily', label: Text('Quotidien')),
                            ButtonSegment<String>(
                                value: 'weekly', label: Text('Hebdo')),
                          ],
                          selected: <String>{settings.frequency},
                          onSelectionChanged: (selection) => ref
                              .read(digestProvider.notifier)
                              .save(selection.first, settings.enabled),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('Notifications', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.notifications_outlined),
              title: const Text('Autoriser les notifications'),
              subtitle: Text(
                PushService.instance.isAvailable
                    ? 'Alertes de prix et digest push.'
                    : 'Push non configuré sur cet appareil.',
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: () async {
                await PushService.instance.requestPermission();
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                        content: Text('Demande de permission envoyée.')),
                  );
                }
              },
            ),
          ),
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
            error: (error, _) => ErrorView(
              message: 'Quota indisponible.\n$error',
              onRetry: () => ref.invalidate(quotaProvider),
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
          const SizedBox(height: 16),
          const _VersionTile(),
        ],
      ),
    );
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Se déconnecter ?'),
        content: const Text('Vous devrez recevoir un nouveau code pour vous reconnecter.'),
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
