import 'package:brvm_mobile/core/format.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

void main() {
  // formatDate (repli au-delà d'une semaine) exige les données fr_FR,
  // initialisées par l'app dans main().
  setUpAll(() async => initializeDateFormatting('fr_FR'));
  group('formatRelativeTime', () {
    final now = DateTime(2026, 9, 4, 12, 0, 0);

    test('« — » si null', () {
      expect(formatRelativeTime(null, now: now), '—');
    });

    test('à l’instant / minutes / heures / jours', () {
      expect(
        formatRelativeTime(now.subtract(const Duration(seconds: 30)), now: now),
        'à l’instant',
      );
      expect(
        formatRelativeTime(now.subtract(const Duration(minutes: 12)), now: now),
        'il y a 12 min',
      );
      expect(
        formatRelativeTime(now.subtract(const Duration(hours: 3)), now: now),
        'il y a 3 h',
      );
      expect(
        formatRelativeTime(now.subtract(const Duration(days: 2, hours: 1)), now: now),
        'il y a 2 j',
      );
    });

    test('date courte au-delà d’une semaine', () {
      final old = DateTime(2026, 8, 20, 8, 30);
      final result = formatRelativeTime(old, now: now);
      expect(result, isNot(startsWith('il y a')));
      expect(result, contains('août'));
      expect(result, contains('2026'));
    });
  });

  group('normalizeForSearch', () {
    test('minuscules + suppression des accents', () {
      expect(normalizeForSearch('SÉNÉGAL'), 'senegal');
      expect(normalizeForSearch('Société Générale'), 'societe generale');
      expect(normalizeForSearch('ONATEL'), 'onatel');
      // Apostrophe typographique conservée (recherche cohérente des deux côtés).
      expect(normalizeForSearch('Côte d’Ivoire'), 'cote d’ivoire');
    });

    test('chaîne déjà propre inchangée', () {
      expect(normalizeForSearch('sonatel'), 'sonatel');
    });
  });
}
