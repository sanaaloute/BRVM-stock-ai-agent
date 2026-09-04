import 'package:intl/intl.dart';

final NumberFormat _amountFormat = NumberFormat('#,##0.##', 'fr_FR');
final NumberFormat _percentFormat = NumberFormat('0.##', 'fr_FR');
final DateFormat _dateFormat = DateFormat.yMMMd('fr_FR');
final DateFormat _dateTimeFormat = DateFormat.yMMMd('fr_FR').add_Hm();

/// « 12 345 FCFA » ; « — » si null.
String formatFcfa(double? value) =>
    value == null ? '—' : '${_amountFormat.format(value)} FCFA';

/// « +1,2 % » / « -0,8 % » ; « — » si null.
String formatPercent(double? value) {
  if (value == null) return '—';
  final sign = value > 0 ? '+' : '';
  return '$sign${_percentFormat.format(value)} %';
}

/// Montant simple sans symbole.
String formatAmount(double? value) =>
    value == null ? '—' : _amountFormat.format(value);

/// Montant compact : « 12,3 Md », « 4,5 M », « 320 k » ; « — » si null.
String formatCompactAmount(double? value) {
  if (value == null) return '—';
  final abs = value.abs();
  if (abs >= 1e9) return '${_amountFormat.format(value / 1e9)} Md';
  if (abs >= 1e6) return '${_amountFormat.format(value / 1e6)} M';
  if (abs >= 1e3) return '${_amountFormat.format(value / 1e3)} k';
  return _amountFormat.format(value);
}

/// Capitalisation compacte : « 12,3 Md FCFA », « 450 M FCFA » ; « — » si null.
String formatCompactFcfa(double? value) {
  if (value == null) return '—';
  final abs = value.abs();
  if (abs >= 1e9) return '${_amountFormat.format(value / 1e9)} Md FCFA';
  if (abs >= 1e6) return '${_amountFormat.format(value / 1e6)} M FCFA';
  return '${_amountFormat.format(value)} FCFA';
}

String formatDate(DateTime? date) => date == null ? '—' : _dateFormat.format(date);

String formatDateTime(DateTime? date) =>
    date == null ? '—' : _dateTimeFormat.format(date);

/// Date relative : « à l’instant », « il y a 12 min », « il y a 3 h »,
/// « il y a 2 j », sinon date courte. « — » si null.
String formatRelativeTime(DateTime? date, {DateTime? now}) {
  if (date == null) return '—';
  final reference = now ?? DateTime.now();
  final diff = reference.difference(date);
  if (diff.inMinutes < 1) return 'à l’instant';
  if (diff.inHours < 1) return 'il y a ${diff.inMinutes} min';
  if (diff.inDays < 1) return 'il y a ${diff.inHours} h';
  if (diff.inDays < 7) return 'il y a ${diff.inDays} j';
  return formatDate(date);
}

const _diacriticReplacements = <String, String>{
  'à': 'a', 'â': 'a', 'ä': 'a', 'á': 'a', 'ã': 'a', 'å': 'a',
  'è': 'e', 'ê': 'e', 'ë': 'e', 'é': 'e',
  'ì': 'i', 'î': 'i', 'ï': 'i', 'í': 'i',
  'ò': 'o', 'ô': 'o', 'ö': 'o', 'ó': 'o', 'õ': 'o',
  'ù': 'u', 'û': 'u', 'ü': 'u', 'ú': 'u',
  'ç': 'c', 'ñ': 'n',
};

/// Chaîne normalisée pour la recherche : minuscules, sans accents
/// (« SÉNÉGAL » et « senegal » matchent).
String normalizeForSearch(String value) {
  var result = value.toLowerCase();
  _diacriticReplacements.forEach((from, to) {
    result = result.replaceAll(from, to);
  });
  return result;
}
