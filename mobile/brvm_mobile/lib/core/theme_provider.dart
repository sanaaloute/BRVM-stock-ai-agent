import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Thème de l'application (système / clair / sombre), persisté localement.
/// Le sombre reste le réglage par défaut tant que l'utilisateur n'a pas
/// choisi explicitement un autre mode.
class ThemeModeNotifier extends AsyncNotifier<ThemeMode> {
  static const _key = 'theme_mode';

  @override
  Future<ThemeMode> build() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return _parse(prefs.getString(_key));
    } catch (_) {
      // Stockage indisponible (tests) : défaut sombre.
      return ThemeMode.dark;
    }
  }

  Future<void> setMode(ThemeMode mode) async {
    // Mise à jour optimiste : l'UI réagit immédiatement.
    state = AsyncData<ThemeMode>(mode);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_key, mode.name);
    } catch (_) {
      // Non bloquant : le mode reste appliqué pour la session courante.
    }
  }

  static ThemeMode _parse(String? value) => switch (value) {
        'system' => ThemeMode.system,
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.dark,
      };
}

final themeModeProvider =
    AsyncNotifierProvider<ThemeModeNotifier, ThemeMode>(ThemeModeNotifier.new);
