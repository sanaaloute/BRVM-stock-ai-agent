/// Conversion défensive des valeurs JSON renvoyées par le backend.
/// Toutes les clés des réponses de l'API sont optionnelles.
library;

/// Convertit une valeur quelconque en [double] si possible.
/// Gère les nombres, les chaînes avec virgule décimale française
/// (« 12 345,6 % », « +1,2 »), les espaces insécables et le symbole %.
double? asDouble(dynamic value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  if (value is String) {
    final cleaned = value
        .replaceAll(RegExp(r'[\s\u00A0\u202F]'), '')
        .replaceAll(',', '.')
        .replaceAll('%', '')
        .replaceAll('+', '');
    if (cleaned.isEmpty) return null;
    return double.tryParse(cleaned);
  }
  return null;
}

/// Convertit une valeur quelconque en [int] si possible.
int? asInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) {
    final cleaned = value.replaceAll(RegExp(r'[\s\u00A0\u202F]'), '');
    return int.tryParse(cleaned);
  }
  return null;
}

/// Convertit une valeur quelconque en [String] non vide si possible.
String? asString(dynamic value) {
  if (value == null) return null;
  if (value is String) {
    final trimmed = value.trim();
    return trimmed.isEmpty ? null : trimmed;
  }
  return value.toString();
}

/// Convertit une valeur en [Map<String, dynamic>].
Map<String, dynamic> asMap(dynamic value) {
  if (value is Map) {
    return value.map((key, v) => MapEntry(key.toString(), v));
  }
  return <String, dynamic>{};
}

/// Convertit une valeur en [List] de cartes.
List<Map<String, dynamic>> asMapList(dynamic value) {
  if (value is List) {
    return value.whereType<Map>().map(asMap).toList();
  }
  return <Map<String, dynamic>>[];
}

/// Convertit une valeur en liste de chaînes.
List<String> asStringList(dynamic value) {
  if (value is List) {
    return value.map(asString).whereType<String>().toList();
  }
  return const <String>[];
}

/// Booléen tolérant (« true », 1, true…).
bool asBool(dynamic value, {bool defaultValue = false}) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  if (value is String) return value.toLowerCase() == 'true';
  return defaultValue;
}
