/// Validation de l'identifiant de connexion (e-mail OU téléphone).
library;

final RegExp _emailRegex = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
final RegExp _phoneRegex = RegExp(r'^\+?[0-9][0-9 .\-()]{6,}$');

bool isEmail(String value) => _emailRegex.hasMatch(value.trim());

bool isPhone(String value) {
  final v = value.trim();
  if (!_phoneRegex.hasMatch(v)) return false;
  final digits = v.replaceAll(RegExp(r'[^0-9]'), '');
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
