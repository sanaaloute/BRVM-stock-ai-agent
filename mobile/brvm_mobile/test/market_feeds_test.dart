import 'package:brvm_mobile/features/market/market_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('NewsFeed.fromSection', () {
    test('enveloppe avec items + warning', () {
      final feed = NewsFeed.fromSection(<String, dynamic>{
        'items': <Map<String, dynamic>>[
          <String, dynamic>{
            'date': '2026-09-01',
            'title': 'Résultats semestriels ONATEL',
            'url': 'https://www.brvm.org/anonce/1',
            'snippet': 'Le groupe publie un CA en hausse de 8 %.',
          },
          <String, dynamic>{'title': 'Sans url ni date'},
        ],
        'warning': 'Source de repli : annonces officielles BRVM.',
        'error': null,
      });

      expect(feed.warning, 'Source de repli : annonces officielles BRVM.');
      expect(feed.error, isNull);
      expect(feed.items, hasLength(2));
      final first = feed.items.first;
      expect(first.date, '2026-09-01');
      expect(first.title, 'Résultats semestriels ONATEL');
      expect(first.url, 'https://www.brvm.org/anonce/1');
      expect(first.summary, 'Le groupe publie un CA en hausse de 8 %.');
      expect(feed.items.last.url, isNull);
    });

    test('erreur seule (items vides)', () {
      final feed = NewsFeed.fromSection(<String, dynamic>{
        'items': <Map<String, dynamic>>[],
        'error': 'Source Sika inaccessible.',
      });
      expect(feed.items, isEmpty);
      expect(feed.error, 'Source Sika inaccessible.');
    });

    test('forme legacy : liste directe', () {
      final feed = NewsFeed.fromSection(<Map<String, dynamic>>[
        <String, dynamic>{'title': 'Titre', 'link': 'https://example.com'},
      ]);
      expect(feed.error, isNull);
      expect(feed.warning, isNull);
      expect(feed.items.single.title, 'Titre');
      expect(feed.items.single.url, 'https://example.com');
    });

    test('section absente', () {
      final feed = NewsFeed.fromSection(null);
      expect(feed.items, isEmpty);
      expect(feed.error, isNull);
      expect(feed.warning, isNull);
    });
  });

  group('NewsArticle.fromJson', () {
    test('article complet (titre, date, url, texte markdown)', () {
      final article = NewsArticle.fromJson(<String, dynamic>{
        'title': 'ONATEL publie ses résultats semestriels',
        'date': '2026-09-02',
        'url': 'https://www.brvm.org/annonce/42',
        'text': '**Communiqué**\n\nLe CA progresse de 8 %.\n\n¶ Détails…',
      });
      expect(article.title, 'ONATEL publie ses résultats semestriels');
      expect(article.date, '2026-09-02');
      expect(article.url, 'https://www.brvm.org/annonce/42');
      expect(article.text, contains('**Communiqué**'));
    });

    test('date vide et champs manquants tolérés', () {
      final empty = NewsArticle.fromJson(<String, dynamic>{
        'title': 'Titre seul',
        'date': '',
      });
      // asString normalise '' → null.
      expect(empty.date, isNull);
      expect(empty.url, isNull);
      expect(empty.text, isNull);

      final minimal = NewsArticle.fromJson(<String, dynamic>{});
      expect(minimal.title, isNull);
      expect(minimal.date, isNull);
    });
  });

  group('brokerEntriesFromSection', () {
    Map<String, dynamic> sgi(String name) => <String, dynamic>{'name': name};

    test('enveloppe avec clé items + count (contrat actuel)', () {
      final entries = brokerEntriesFromSection(<String, dynamic>{
        'items': <Map<String, dynamic>>[
          sgi('CBAO Capital'),
          sgi('Ecobank'),
        ],
        'count': 40,
      });
      expect(entries, hasLength(2));
      expect(entries.first.name, 'CBAO Capital');
    });

    test('enveloppe avec clé sgi (forme intermédiaire)', () {
      final entries = brokerEntriesFromSection(<String, dynamic>{
        'sgi': <Map<String, dynamic>>[sgi('CBAO Capital'), sgi('Ecobank')],
        'count': 40,
        'updated_at': '2026-09-04T10:00:00',
      });
      expect(entries, hasLength(2));
      expect(entries.first.name, 'CBAO Capital');
    });

    test('enveloppe avec clé brokers', () {
      final entries = brokerEntriesFromSection(<String, dynamic>{
        'brokers': <Map<String, dynamic>>[sgi('SGBCI')],
        'count': 1,
      });
      expect(entries.single.name, 'SGBCI');
    });

    test('forme legacy : liste directe', () {
      final entries = brokerEntriesFromSection(<Map<String, dynamic>>[
        sgi('Coris Capital'),
      ]);
      expect(entries.single.name, 'Coris Capital');
    });

    test('section absente → liste vide', () {
      expect(brokerEntriesFromSection(null), isEmpty);
    });
  });

  group('BrokerEntry.fromJson', () {
    test('champs complets du contrat détail', () {
      final broker = BrokerEntry.fromJson(<String, dynamic>{
        'id': 7,
        'name': 'CBAO Capital',
        'country': 'Sénégal',
        'country_code': 'SN',
        'phone': '+221 33 889 00 00',
        'email': 'contact@cbao-capital.com',
        'website': 'https://www.cbao-capital.com',
        'address': 'Route des Almadies, Dakar',
        'min_amount': '100 000 FCFA',
        'note': 'Membre du marché actions',
        'other_countries': <String>['Mali', "Côte d'Ivoire"],
        'info': 'Intermédiaire agréé sur le marché principal.',
        'detail_text': 'Historique et gouvernance de la SGI…',
      });

      expect(broker.id, 7);
      expect(broker.name, 'CBAO Capital');
      expect(broker.country, 'Sénégal');
      expect(broker.countryCode, 'SN');
      expect(broker.phone, '+221 33 889 00 00');
      expect(broker.url, 'https://www.cbao-capital.com');
      expect(broker.email, 'contact@cbao-capital.com');
      expect(broker.address, 'Route des Almadies, Dakar');
      expect(broker.minAmount, '100 000 FCFA');
      expect(broker.note, 'Membre du marché actions');
      expect(broker.otherCountries, <String>['Mali', "Côte d'Ivoire"]);
      expect(broker.info, 'Intermédiaire agréé sur le marché principal.');
      expect(broker.detailText, 'Historique et gouvernance de la SGI…');
    });

    test('other_countries en chaîne séparée par des virgules', () {
      final broker = BrokerEntry.fromJson(<String, dynamic>{
        'other_countries': 'Bénin, Burkina Faso, Niger',
      });
      expect(broker.otherCountries,
          <String>['Bénin', 'Burkina Faso', 'Niger']);
    });

    test('clés françaises + JSON minimal', () {
      final fr = BrokerEntry.fromJson(<String, dynamic>{
        'nom': 'Ecobank Capital',
        'pays': 'Togo',
        'note': 'Intermédiaire agréé',
      });
      expect(fr.name, 'Ecobank Capital');
      expect(fr.country, 'Togo');
      expect(fr.note, 'Intermédiaire agréé');

      final minimal = BrokerEntry.fromJson(<String, dynamic>{});
      expect(minimal.id, isNull);
      expect(minimal.name, isNull);
      expect(minimal.country, isNull);
      expect(minimal.note, isNull);
      expect(minimal.otherCountries, isEmpty);
      expect(minimal.detailText, isNull);
    });
  });
}
