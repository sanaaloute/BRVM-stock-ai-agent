import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/config.dart';
import 'core/providers.dart';
import 'core/push_service.dart';
import 'core/theme_provider.dart';
import 'features/alerts/alerts_screen.dart';
import 'features/auth/identifier_screen.dart';
import 'features/auth/otp_screen.dart';
import 'features/chat/chat_screen.dart';
import 'features/chat/conversations_screen.dart';
import 'features/market/article_screen.dart';
import 'features/market/broker_detail_screen.dart';
import 'features/market/market_screen.dart';
import 'features/market/stock_detail_screen.dart';
import 'features/portfolio/portfolio_screen.dart';
import 'features/settings/settings_screen.dart';

/// Palette « fintech futuriste » : fond bleu nuit profond, émeraude vive,
/// accent doré. Le thème sombre est le thème par défaut.
class AppPalette {
  const AppPalette._();

  static const emerald = Color(0xFF00C896);
  static const emeraldLight = Color(0xFF10B981);
  static const gold = Color(0xFFD4A94E);

  static const darkScaffold = Color(0xFF0A0E14);
  static const darkSurface = Color(0xFF0D1117);
  static const darkCard = Color(0xFF141C28);
  static const darkOnSurface = Color(0xFFE6EDF3);

  static const lightScaffold = Color(0xFFF5F7FA);
  static const lightCard = Color(0xFFFFFFFF);
  static const lightBorder = Color(0xFFE2E8F0);
}

/// Thème Material 3 : fintech futuriste mais sobre et professionnel.
ThemeData _buildTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: AppPalette.emeraldLight,
    brightness: brightness,
  ).copyWith(
    primary: dark ? AppPalette.emerald : AppPalette.emeraldLight,
    onPrimary: dark ? const Color(0xFF03231A) : Colors.white,
    secondary: AppPalette.gold,
    onSecondary: dark ? const Color(0xFF2A1E06) : const Color(0xFF3B2B07),
    surface: dark ? AppPalette.darkSurface : Colors.white,
    onSurface: dark ? AppPalette.darkOnSurface : const Color(0xFF16202B),
    surfaceContainerHighest:
        dark ? const Color(0xFF182233) : const Color(0xFFE9EEF4),
    // Textes secondaires : contrastes ≥ 4,5:1 sur les surfaces sombres.
    onSurfaceVariant: dark ? const Color(0xFF9BA7B8) : const Color(0xFF57657A),
    outline: dark ? const Color(0xFF5C6675) : const Color(0xFF8A97A8),
    outlineVariant: dark ? const Color(0xFF3A4352) : AppPalette.lightBorder,
    error: dark ? const Color(0xFFFF6E63) : const Color(0xFFD23B31),
  );

  final cardColor = dark ? AppPalette.darkCard : AppPalette.lightCard;
  final borderColor = scheme.outlineVariant;

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor:
        dark ? AppPalette.darkScaffold : AppPalette.lightScaffold,
    appBarTheme: const AppBarTheme(
      centerTitle: false,
      backgroundColor: Colors.transparent,
      scrolledUnderElevation: 0,
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: cardColor,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: borderColor.withValues(alpha: 0.75)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      side: BorderSide(color: borderColor),
      backgroundColor: scheme.surfaceContainerHighest,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: borderColor),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: borderColor),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: scheme.primary, width: 1.6),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: cardColor,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor:
          (dark ? AppPalette.darkSurface : Colors.white).withValues(alpha: 0.92),
      indicatorColor: scheme.primary.withValues(alpha: dark ? 0.22 : 0.16),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w600
              : FontWeight.w400,
          fontSize: 12,
        ),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
  );
}

/// Notifie go_router des changements d'état d'authentification.
class _AuthRefreshNotifier extends ChangeNotifier {
  _AuthRefreshNotifier(Ref ref) {
    ref.listen(authStateProvider, (_, _) => notifyListeners());
  }
}

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _AuthRefreshNotifier(ref);
  ref.onDispose(refresh.dispose);
  return GoRouter(
    initialLocation: '/chat',
    refreshListenable: refresh,
    redirect: (context, state) {
      final auth = ref.read(authStateProvider);
      final location = state.matchedLocation;
      final onAuthRoute = location.startsWith('/auth');
      if (auth is AuthLoading) return null;
      if (auth is! AuthAuthenticated && !onAuthRoute) {
        return '/auth/identifier';
      }
      if (auth is AuthAuthenticated && onAuthRoute) {
        return '/chat';
      }
      return null;
    },
    routes: <RouteBase>[
      GoRoute(
        path: '/auth/identifier',
        builder: (context, state) => const IdentifierScreen(),
      ),
      GoRoute(
        path: '/auth/otp',
        builder: (context, state) => OtpScreen.fromState(state),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            HomeShell(navigationShell: navigationShell),
        branches: <StatefulShellBranch>[
          StatefulShellBranch(
            routes: <RouteBase>[
              // Onglet Chat : conversation vierge par défaut (icône
              // « Historique » dans l'AppBar pour la liste).
              GoRoute(
                path: '/chat',
                builder: (context, state) => const ChatScreen(),
              ),
              GoRoute(
                path: '/chat/historique',
                builder: (context, state) => const ConversationsScreen(),
              ),
              GoRoute(
                path: '/chat/thread/:threadId',
                builder: (context, state) => ChatScreen(
                  threadId: state.pathParameters['threadId'],
                ),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/marche',
                builder: (context, state) => const MarketScreen(),
              ),
              GoRoute(
                path: '/marche/symbol/:symbol',
                builder: (context, state) => StockDetailScreen(
                  symbol: state.pathParameters['symbol'] ?? '',
                ),
              ),
              GoRoute(
                path: '/marche/courtier/:id',
                builder: (context, state) => BrokerDetailScreen(
                  id: int.tryParse(state.pathParameters['id'] ?? '') ?? 0,
                ),
              ),
              GoRoute(
                path: '/marche/actualite',
                builder: (context, state) => ArticleScreen(
                  url: state.uri.queryParameters['url'] ?? '',
                ),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/portefeuille',
                builder: (context, state) => const PortfolioScreen(),
              ),
              GoRoute(
                path: '/portefeuille/form',
                builder: (context, state) => const PositionFormScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/alertes',
                builder: (context, state) => const AlertsScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/moi',
                builder: (context, state) => const SettingsScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
});

/// Coquille principale : barre de navigation inférieure (5 onglets).
class HomeShell extends StatelessWidget {
  const HomeShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  static const _destinations = <_Destination>[
    _Destination('Chat', Icons.chat_bubble_outline, Icons.chat_bubble),
    _Destination('Marché', Icons.candlestick_chart_outlined, Icons.candlestick_chart),
    _Destination('Portefeuille', Icons.pie_chart_outline, Icons.pie_chart),
    _Destination('Alertes', Icons.notifications_outlined, Icons.notifications),
    _Destination('Moi', Icons.person_outline, Icons.person),
  ];

  void _onTap(int index) => navigationShell.goBranch(
        index,
        initialLocation: index == navigationShell.currentIndex,
      );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: _onTap,
        destinations: <Widget>[
          for (final d in _destinations)
            NavigationDestination(
              icon: Icon(d.icon),
              selectedIcon: Icon(d.selectedIcon),
              label: d.label,
            ),
        ],
      ),
    );
  }
}

class _Destination {
  const _Destination(this.label, this.icon, this.selectedIcon);

  final String label;
  final IconData icon;
  final IconData selectedIcon;
}

class KoraApp extends ConsumerStatefulWidget {
  const KoraApp({super.key});

  @override
  ConsumerState<KoraApp> createState() => _KoraAppState();
}

class _KoraAppState extends ConsumerState<KoraApp> {
  @override
  void initState() {
    super.initState();
    // Navigation sur ouverture d'une notification push (deep link simple).
    PushService.instance.onNavigate = (tab) {
      final router = ref.read(routerProvider);
      const valid = <String>{
        'chat', 'marche', 'portefeuille', 'alertes', 'moi',
      };
      router.go(valid.contains(tab) ? '/$tab' : '/chat');
    };
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    // Réglage utilisateur (Compte → Apparence) ; défaut : sombre.
    final themeMode = ref.watch(themeModeProvider).value ?? ThemeMode.dark;
    return MaterialApp.router(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: _buildTheme(Brightness.light),
      darkTheme: _buildTheme(Brightness.dark),
      themeMode: themeMode,
      locale: const Locale('fr', 'FR'),
      supportedLocales: const <Locale>[Locale('fr', 'FR'), Locale('en')],
      localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      routerConfig: router,
    );
  }
}
