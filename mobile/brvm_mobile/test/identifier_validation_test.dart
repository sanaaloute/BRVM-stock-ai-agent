import 'package:brvm_mobile/features/auth/identifier_validation.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('validateIdentifier', () {
    test('accepte les e-mails valides', () {
      expect(validateIdentifier('user@example.com'), isNull);
      expect(validateIdentifier('prenom.nom+tag@entreprise.ci'), isNull);
    });

    test('accepte les numéros de téléphone valides', () {
      expect(validateIdentifier('+225 07 07 07 07 07'), isNull);
      expect(validateIdentifier('0707070707'), isNull);
      expect(validateIdentifier('+33 6 12 34 56 78'), isNull);
      expect(validateIdentifier('+2250701234567'), isNull);
    });

    test('refuse les chaînes vides', () {
      expect(validateIdentifier(''), isNotNull);
      final result = validateIdentifier('   ');
      expect(result, isNotNull);
      expect(result, contains('saisir'));
    });

    test('refuse les formats invalides', () {
      expect(validateIdentifier('abc'), isNotNull);
      expect(validateIdentifier('pas-un-email'), isNotNull);
      expect(validateIdentifier('a@b'), isNotNull);
      expect(validateIdentifier('12345'), isNotNull); // Trop court.
      expect(validateIdentifier('+225'), isNotNull);
    });
  });

  group('normalizeIdentifier', () {
    test('e-mail : trimmé et mis en minuscules', () {
      expect(
        normalizeIdentifier('  Trader@BRVM.CI  ', '+225'),
        'trader@brvm.ci',
      );
    });

    test('numéro local : indicatif préfixé', () {
      expect(normalizeIdentifier('07 01 23 45 67', '+225'), '+2250701234567');
    });

    test('numéro local avec séparateurs variés : indicatif préfixé', () {
      expect(
        normalizeIdentifier('(07).01-23 45 67', '+225'),
        '+2250701234567',
      );
    });

    test('numéro déjà international : inchangé', () {
      expect(
        normalizeIdentifier('+221771234567', '+225'),
        '+221771234567',
      );
    });
  });

  group('isEmail / isPhone', () {
    test('classification correcte', () {
      expect(isEmail('a@b.co'), isTrue);
      expect(isEmail('0707070707'), isFalse);
      expect(isPhone('+225 07 07 07 07 07'), isTrue);
      expect(isPhone('a@b.co'), isFalse);
    });
  });
}
