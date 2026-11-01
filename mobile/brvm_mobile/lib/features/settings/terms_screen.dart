import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/config.dart';
import '../../core/ui.dart';

/// Conditions générales d'utilisation, accessibles depuis Compte → À propos.
/// La politique de confidentialité (hébergée) est liée en fin de page.
class TermsScreen extends StatelessWidget {
  const TermsScreen({super.key});

  static const _sections = <_TermsSection>[
    _TermsSection(
      '1. Éditeur',
      'Kora Bourse est une application éditée par NeoByte Technology '
          '(« l’Éditeur »). Contact : ${AppConfig.contactEmail}.',
    ),
    _TermsSection(
      '2. Objet',
      'L’application fournit des informations sur la Bourse Régionale des '
          'Valeurs Mobilières (BRVM) : cotations, palmarès, actualités, '
          'prévisions et analyses générées par un assistant d’intelligence '
          'artificielle, ainsi que des outils de suivi de portefeuille et '
          'd’alertes.',
    ),
    _TermsSection(
      '3. Absence de conseil en investissement',
      'Les contenus de l’application, y compris ceux générés par l’assistant '
          'IA, sont fournis à titre purement informatif. Ils ne constituent ni '
          'un conseil en investissement, ni une recommandation, ni une '
          'sollicitation d’achat ou de vente de valeurs mobilières. Toute '
          'décision d’investissement relève de votre seule responsabilité : '
          'rapprochez-vous d’une Société de Gestion et d’Intermédiation (SGI) '
          'agréée par le CREPMF.',
    ),
    _TermsSection(
      '4. Données de marché',
      'Les cours et informations proviennent de sources tierces (BRVM, sites '
          'd’information financière) et peuvent être différés, incomplets ou '
          'erronés. L’Éditeur ne garantit ni leur exactitude, ni leur '
          'exhaustivité, ni leur disponibilité.',
    ),
    _TermsSection(
      '5. Assistant IA',
      'Les réponses de l’assistant sont générées automatiquement et peuvent '
          'contenir des erreurs ou des imprécisions. Vérifiez toujours les '
          'informations avant toute décision.',
    ),
    _TermsSection(
      '6. Compte utilisateur',
      'Vous êtes responsable de la confidentialité de vos identifiants et de '
          'l’exactitude des informations fournies. Vous pouvez supprimer votre '
          'compte à tout moment depuis l’écran « Compte » de l’application.',
    ),
    _TermsSection(
      '7. Propriété intellectuelle',
      'L’application, sa marque et ses contenus (hors données de marché '
          'tierces) sont la propriété de NeoByte Technology. Toute '
          'reproduction ou réutilisation sans autorisation préalable est '
          'interdite.',
    ),
    _TermsSection(
      '8. Limitation de responsabilité',
      'L’Éditeur ne saurait être tenu responsable des pertes financières, '
          'directes ou indirectes, résultant de l’utilisation de l’application '
          'ou de l’indisponibilité du service.',
    ),
    _TermsSection(
      '9. Modifications des conditions',
      'Les présentes conditions peuvent être mises à jour à tout moment ; la '
          'version en vigueur est celle accessible dans l’application. '
          'Dernière mise à jour : 1ᵉʳ novembre 2026.',
    ),
  ];

  Future<void> _openPrivacyPolicy(BuildContext context) async {
    final uri = Uri.parse(AppConfig.privacyPolicyUrl);
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Impossible d’ouvrir le lien.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Scaffold(
      appBar: const KoraAppBar(title: Text('Conditions générales')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          Text(
            'Conditions générales d’utilisation',
            style: theme.textTheme.titleLarge
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Text(
            AppConfig.appName,
            style: theme.textTheme.bodySmall?.copyWith(color: colors.muted),
          ),
          const SizedBox(height: 16),
          for (final section in _sections) ...<Widget>[
            Text(
              section.title,
              style: theme.textTheme.titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              section.body,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: colors.muted, height: 1.45),
            ),
            const SizedBox(height: 16),
          ],
          Text(
            '10. Politique de confidentialité',
            style: theme.textTheme.titleSmall
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Text(
            'Le traitement de vos données personnelles est décrit dans notre '
            'politique de confidentialité.',
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: colors.muted, height: 1.45),
          ),
          const SizedBox(height: 12),
          FilledButton.tonalIcon(
            onPressed: () => _openPrivacyPolicy(context),
            icon: const Icon(Icons.open_in_new, size: 18),
            label: const Text('Consulter la politique de confidentialité'),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _TermsSection {
  const _TermsSection(this.title, this.body);

  final String title;
  final String body;
}
