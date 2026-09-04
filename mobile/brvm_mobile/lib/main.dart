import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'app.dart';
import 'core/push_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('fr_FR');
  // Les notifications push sont optionnelles : sans fichiers de config
  // Firebase, l'app fonctionne normalement (le push est désactivé).
  await PushService.instance.init();
  runApp(const ProviderScope(child: KoraApp()));
}
