import 'package:brvm_mobile/features/market/stock_detail_models.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _ficheJson() => <String, dynamic>{
      'symbol': 'SNTS',
      'company_name': 'SONATEL',
      'code': 'SN0000000019 - SNTS',
      'presentation': 'Résumé réécrit par le backend.',
      'dirigeants':
          'Président du Conseil : Alioune NDIAYE Directeur Général : Brelotte BA',
      'nombre_titres': '100 000 000',
      'flottant': '22,47%',
      'valorisation': '3 100 000 MFCFA',
      'shareholders': <Map<String, dynamic>>[
        <String, dynamic>{'name': 'ORANGE', 'pct': '42,33'},
        <String, dynamic>{'name': 'DIVERS', 'pct': '57,67'},
      ],
      'performance': <String, dynamic>{
        'dividende': <String, dynamic>{'2024': '1 655,00', '2025': '1 740,00'},
        'chiffre_affaires': <String, dynamic>{
          '2024': '1 776 443',
          '2025': '1 923 122',
        },
        'per': <String, dynamic>{'2024': '7,87', '2025': '7,50'},
        'metrique_inconnue': <String, dynamic>{'2025': 'x'},
      },
      'market': <String, dynamic>{
        'beta_1an': 1.31,
        'rsi_14': 86.03,
        'capital_echange_pct': 0.01,
        'valorisation_millions': 3698000.0,
        'day': <String, dynamic>{
          'ouverture': 34400.0,
          'plus_haut': 36980.0,
          'plus_bas': 34400.0,
          'volume_titres': 13615.0,
        },
        'ranges': <String, dynamic>{
          '1_an': <String, dynamic>{
            'plus_haut': 36980.0,
            'plus_bas': 24400.0,
            'variation_pct': 49.14,
          },
          '1_semaine': <String, dynamic>{
            'plus_haut': 36980.0,
            'plus_bas': 31900.0,
            'variation_pct': 15.92,
          },
        },
        'dividend_history': <Map<String, dynamic>>[
          <String, dynamic>{'year': 2025, 'montant': 1740.0, 'rendement_pct': 7.25},
          <String, dynamic>{'year': 2024, 'montant': 1655.0, 'rendement_pct': 9.2},
        ],
      },
      'technical_analysis': <String, dynamic>{
        'signals': <Map<String, dynamic>>[
          <String, dynamic>{'group': 'tendance', 'direction': 'up', 'text': '…'},
          <String, dynamic>{'group': 'tendance', 'direction': 'up', 'text': '…'},
          <String, dynamic>{'group': 'tendance', 'direction': 'neutral', 'text': '…'},
          <String, dynamic>{'group': 'momentum', 'direction': 'down', 'text': '…'},
          <String, dynamic>{'group': 'oscillateurs', 'direction': 'up', 'text': '…'},
        ],
      },
      'sector': <String, dynamic>{'name': 'TELECOMMUNICATIONS'},
    };

void main() {
  group('CompanyProfile.fromJson', () {
    test('fiche complète : identité, performance, marché, signaux', () {
      final profile = CompanyProfile.fromJson(_ficheJson());

      expect(profile.isEmpty, isFalse);
      expect(profile.hasIdentity, isTrue);
      expect(profile.hasFundamentals, isTrue);

      // Identité.
      expect(profile.presentation, contains('réécrit'));
      expect(profile.code, 'SN0000000019 - SNTS');
      expect(profile.sectorName, 'Telecommunications'); // casse normalisée
      expect(profile.nombreTitres, '100 000 000');
      expect(profile.flottant, '22,47%');
      expect(profile.valorisation, '3 100 000 MFCFA');

      // Dirigeants éclatés en (rôle, nom).
      expect(profile.dirigeants, hasLength(2));
      expect(profile.dirigeants.first.role, 'Président du Conseil');
      expect(profile.dirigeants.first.name, 'Alioune NDIAYE');
      expect(profile.dirigeants[1].role, 'Directeur Général');
      expect(profile.dirigeants[1].name, 'Brelotte BA');

      // Actionnaires.
      expect(profile.shareholders, hasLength(2));
      expect(profile.shareholders.first.name, 'ORANGE');
      expect(profile.shareholders.first.pct, '42,33');

      // Performance : années triées, ordre canonique puis inconnues.
      final performance = profile.performance!;
      expect(performance.years, <String>['2024', '2025']);
      expect(
        performance.rows.map((r) => r.key).toList(),
        <String>['chiffre_affaires', 'per', 'dividende', 'metrique_inconnue'],
      );
      expect(performance.rows.first.label, "Chiffre d'affaires (MFCFA)");
      expect(performance.rows.first.byYear['2025'], '1 923 122');
      expect(performance.rows.last.label, 'Metrique inconnue');

      // Marché + séance du jour.
      final market = profile.market!;
      expect(market.beta1an, 1.31);
      expect(market.rsi14, 86.03);
      expect(market.valorisationMillions, 3698000.0);
      expect(market.day!.open, 34400.0);
      expect(market.day!.volume, 13615.0);

      // Fourchettes : ordre canonique des périodes (pas l'ordre du JSON).
      expect(
        profile.ranges.map((r) => r.label).toList(),
        <String>['1 semaine', '1 an'],
      );
      expect(profile.ranges.last.variationPct, 49.14);

      // Dividendes annuels.
      expect(profile.dividendHistory, hasLength(2));
      expect(profile.dividendHistory.first.year, 2025);
      expect(profile.dividendHistory.first.rendementPct, 7.25);
    });

    test('signaux techniques agrégés par groupe, sans le texte source', () {
      final profile = CompanyProfile.fromJson(_ficheJson());
      final technical = profile.technical!;

      expect(technical.up, 3);
      expect(technical.down, 1);
      expect(technical.neutral, 1);
      expect(technical.total, 5);
      expect(technical.majority, 'up');

      expect(
        technical.groups.map((g) => g.label).toList(),
        <String>['Tendance', 'Momentum', 'Oscillateurs'],
      );
      final tendance = technical.groups.first;
      expect(tendance.up, 2);
      expect(tendance.neutral, 1);
      expect(tendance.majority, 'up');
      expect(tendance.majorityCount, 2);
      expect(technical.groups[1].majority, 'down');
    });

    test('signaux : repli sur les totaux quand la liste est absente', () {
      final technical = TechnicalSummary.fromJson(<String, dynamic>{
        'up': 4,
        'down': 2,
        'neutral': 1,
      });
      expect(technical.total, 7);
      expect(technical.majority, 'up');
      expect(technical.groups, isEmpty);
    });

    test('sections absentes ou vides tolérées', () {
      final empty = CompanyProfile.fromJson(const <String, dynamic>{});
      expect(empty.isEmpty, isTrue);
      expect(empty.hasIdentity, isFalse);
      expect(empty.hasFundamentals, isFalse);
      expect(empty.technical, isNull);
      expect(empty.performance, isNull);
      expect(empty.market, isNull);
    });

    test('dirigeants au format inattendu : masqués plutôt que bruts', () {
      final profile = CompanyProfile.fromJson(<String, dynamic>{
        'dirigeants': 'Information non structurée',
      });
      expect(profile.dirigeants, isEmpty);
    });

    test('SymbolDetail expose la fiche structurée', () {
      final detail = SymbolDetail.fromJson('SNTS', <String, dynamic>{
        'symbol': 'SNTS',
        'profile': _ficheJson(),
      });
      expect(detail.profileError, isNull);
      expect(detail.companyProfile.hasIdentity, isTrue);
      expect(detail.companyProfile.technical, isNotNull);
    });
  });
}
