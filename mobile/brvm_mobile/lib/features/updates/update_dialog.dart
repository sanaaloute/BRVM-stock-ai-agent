import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/config.dart';
import '../../core/ui.dart';
import 'app_update_models.dart';

/// Ouvre la fiche store de l'application : App Store sur iPhone, Play Store
/// ailleurs (market:// avec repli HTTPS).
Future<void> openStoreListing() async {
  final isIOS = defaultTargetPlatform == TargetPlatform.iOS;
  final uris = isIOS
      ? <Uri>[
          Uri.parse(
              'https://apps.apple.com/app/id${AppConfig.appleAppStoreId}'),
        ]
      : <Uri>[
          Uri.parse(
              'market://details?id=${AppConfig.androidPackageName}'),
          Uri.parse(
              'https://play.google.com/store/apps/details'
              '?id=${AppConfig.androidPackageName}'),
        ];
  for (final uri in uris) {
    try {
      if (await launchUrl(uri, mode: LaunchMode.externalApplication)) return;
    } catch (_) {
      // Tente l'URL suivante (repli).
    }
  }
}

/// Dialogue « Nouvelle version disponible » : versions installée/store,
/// nouveautés, actions « Plus tard » (reporté au prochain lancement) et
/// « Mettre à jour ».
class UpdateAvailableDialog extends StatelessWidget {
  const UpdateAvailableDialog({super.key, required this.update});

  final AppUpdate update;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final whatsNew = update.whatsNew;
    return AlertDialog(
      scrollable: true,
      title: Row(
        children: <Widget>[
          Icon(Icons.system_update_alt_outlined, color: colors.primary),
          const SizedBox(width: 8),
          const Expanded(child: Text('Mise à jour disponible')),
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _VersionLine(
              label: 'Votre version', version: update.currentVersion),
          const SizedBox(height: 4),
          _VersionLine(
              label: 'Dernière version', version: update.latestVersion),
          if (whatsNew != null && whatsNew.isNotEmpty) ...<Widget>[
            const SizedBox(height: 14),
            Text(
              'Nouveautés',
              style: theme.textTheme.titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              whatsNew,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colors.muted, height: 1.4),
            ),
          ],
        ],
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Plus tard'),
        ),
        FilledButton(
          onPressed: () async {
            await openStoreListing();
            if (context.mounted) Navigator.of(context).pop();
          },
          child: const Text('Mettre à jour'),
        ),
      ],
    );
  }
}

class _VersionLine extends StatelessWidget {
  const _VersionLine({required this.label, required this.version});

  final String label;
  final String version;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: <Widget>[
        Expanded(
          child: Text(
            label,
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: theme.colorScheme.muted),
          ),
        ),
        Text(
          version,
          style: theme.textTheme.bodyMedium?.copyWith(
            fontWeight: FontWeight.w600,
            fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}
