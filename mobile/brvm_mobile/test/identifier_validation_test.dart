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
    });

    test('refuse les chaînes vides', () {
      final result = validateIdentifier('   ');
      expect(result, isNotNull);
      expect(result, contains('saisir'));
    });

    test('refuse les formats invalides', () {
      expect(validateIdentifier('pas-un-email'), isNotNull);
      expect(validateIdentifier('a@b'), isNotNull);
      expect(validateIdentifier('12345'), isNotNull); // Trop court.
      expect(validateIdentifier('+225'), isNotNull);
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
