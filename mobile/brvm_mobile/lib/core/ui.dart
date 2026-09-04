import 'package:flutter/material.dart';

import 'format.dart';

/// Couleurs hausse/baisse cohérentes avec le thème (lisibles en clair
/// comme en sombre). Vert = gain, rouge = perte.
extension MarketColors on ColorScheme {
  Color get gain =>
      brightness == Brightness.dark ? const Color(0xFF2EE6A8) : const Color(0xFF0E9F6E);

  Color get loss => brightness == Brightness.dark
      ? const Color(0xFFFF6E63)
      : const Color(0xFFD23B31);

  /// Texte secondaire / description : repose sur [ColorScheme.onSurfaceVariant],
  /// dont les valeurs du thème garantissent le contraste dans les deux modes.
  Color get muted => onSurfaceVariant;

  /// Variation nulle / signal neutre (texte + bordures de pastille).
  Color get neutral => muted;
}

/// Style commun aux montants : chiffres tabulaires, graisse forte.
TextStyle priceTextStyle(TextStyle? base, ColorScheme colors) =>
    (base ?? const TextStyle()).copyWith(
      fontWeight: FontWeight.bold,
      fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
      color: (base?.color ?? colors.onSurface),
    );

/// Prix en FCFA : graisse forte + chiffres tabulaires.
class PriceText extends StatelessWidget {
  const PriceText(this.value, {super.key, this.style, this.unit = 'FCFA'});

  final double? value;
  final TextStyle? style;
  final String unit;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text =
        value == null ? '—' : '${formatAmount(value)} $unit';
    return Text(text, style: priceTextStyle(style, colors));
  }
}

/// Pastille de variation arrondie : ▲ +1,2 % (vert) / ▼ −0,9 % (rouge).
class VariationChip extends StatelessWidget {
  const VariationChip(this.value, {super.key});

  final double? value;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final v = value;
    final color =
        v == null ? colors.neutral : (v > 0 ? colors.gain : (v < 0 ? colors.loss : colors.neutral));
    final icon = v == null
        ? Icons.remove
        : (v >= 0 ? Icons.arrow_upward : Icons.arrow_downward);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 3),
          Text(
            formatPercent(v),
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: color,
                  fontWeight: FontWeight.w600,
                  fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
                ),
          ),
        ],
      ),
    );
  }
}

/// Petite pastille statistique (libellé + valeur), style « chip » arrondi.
class StatChip extends StatelessWidget {
  const StatChip({super.key, required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.outlineVariant.withValues(alpha: 0.6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            label,
            style: theme.textTheme.labelSmall
                ?.copyWith(color: colors.muted, fontSize: 10.5),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: theme.textTheme.labelMedium?.copyWith(
              fontWeight: FontWeight.w600,
              fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}

/// AppBar standard de l'application avec halo dégradé discret dans la zone
/// d'en-tête (dégradé couleur primaire → transparent).
class KoraAppBar extends StatelessWidget implements PreferredSizeWidget {
  const KoraAppBar({super.key, required this.title, this.actions, this.bottom});

  final Widget title;
  final List<Widget>? actions;
  final PreferredSizeWidget? bottom;

  @override
  Size get preferredSize =>
      Size.fromHeight(kToolbarHeight + (bottom?.preferredSize.height ?? 0));

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return AppBar(
      title: title,
      actions: actions,
      bottom: bottom,
      flexibleSpace: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              colors.primary.withValues(alpha: 0.16),
              Colors.transparent,
            ],
          ),
        ),
      ),
    );
  }
}

/// Indicateur de chargement centré.
class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const CircularProgressIndicator(),
          if (message != null) ...<Widget>[
            const SizedBox(height: 16),
            Text(message!, style: Theme.of(context).textTheme.bodyMedium),
          ],
        ],
      ),
    );
  }
}

/// Vue d'erreur avec bouton « Réessayer ».
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    // Scrollable : le message d'erreur peut dépasser la hauteur disponible
    // sur de petits écrans (la vue vit dans une liste rafraîchissable).
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(Icons.cloud_off_outlined, size: 48, color: colors.error),
                  const SizedBox(height: 12),
                  Text(
                    message,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyLarge,
                  ),
                  if (onRetry != null) ...<Widget>[
                    const SizedBox(height: 16),
                    FilledButton.tonalIcon(
                      onPressed: onRetry,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Réessayer'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Vue pour une liste vide.
class EmptyView extends StatelessWidget {
  const EmptyView({
    super.key,
    required this.message,
    this.icon = Icons.inbox_outlined,
    this.onRetry,
  });

  final String message;
  final IconData icon;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(icon, size: 48, color: colors.muted),
                  const SizedBox(height: 12),
                  Text(
                    message,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyLarge,
                  ),
                  if (onRetry != null) ...<Widget>[
                    const SizedBox(height: 16),
                    FilledButton.tonalIcon(
                      onPressed: onRetry,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Réessayer'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Message d'erreur inline (formulaires).
class FormError extends StatelessWidget {
  const FormError({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Row(
        children: <Widget>[
          Icon(Icons.error_outline, size: 18, color: colors.error),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: colors.error),
            ),
          ),
        ],
      ),
    );
  }
}
