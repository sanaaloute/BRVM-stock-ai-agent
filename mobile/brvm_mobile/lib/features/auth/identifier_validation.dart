/// Validation et normalisation de l'identifiant de connexion
/// (e-mail OU téléphone).
library;

final RegExp _emailRegex = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
final RegExp _phoneSeparatorsRegex = RegExp(r'[ .\-()]');
final RegExp _digitsOnlyRegex = RegExp(r'^\d+$');

bool isEmail(String value) => _emailRegex.hasMatch(value.trim());

/// Supprime les séparateurs (espaces, points, tirets, parenthèses).
String stripPhoneSeparators(String value) =>
    value.trim().replaceAll(_phoneSeparatorsRegex, '');

bool isPhone(String value) {
  final stripped = stripPhoneSeparators(value);
  final digits =
      stripped.startsWith('+') ? stripped.substring(1) : stripped;
  if (digits.isEmpty || !_digitsOnlyRegex.hasMatch(digits)) return false;
  return digits.length >= 8 && digits.length <= 15;
}

/// Retourne `null` si valide, sinon le message d'erreur en français.
String? validateIdentifier(String input) {
  final value = input.trim();
  if (value.isEmpty) {
    return 'Veuillez saisir votre e-mail ou votre numéro de téléphone.';
  }
  if (isEmail(value) || isPhone(value)) return null;
  return 'Format invalide : saisissez un e-mail ou un numéro de téléphone.';
}

/// Identifiant à envoyer à l'API : e-mail trimmé + mis en minuscules ;
/// téléphone sans séparateurs, préfixé de [dialCode] s'il n'est pas
/// déjà saisi au format international (commençant par « + »).
String normalizeIdentifier(String input, String dialCode) {
  final value = input.trim();
  if (isEmail(value)) return value.toLowerCase();
  final stripped = stripPhoneSeparators(value);
  if (stripped.startsWith('+')) return stripped;
  return '$dialCode$stripped';
}
