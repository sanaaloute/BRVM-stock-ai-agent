import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('TabBar du marché : onglets alignés à gauche (pas de décalage M3)',
      (tester) async {
    // Material 3 aligns scrollable TabBars with a 52 dp start offset by
    // default (TabAlignment.startOffset); the market screen opts out with
    // tabAlignment: TabAlignment.start + padding: EdgeInsets.zero. This test
    // pins that geometry using the same TabBar configuration.
    await tester.pumpWidget(
      const MaterialApp(
        home: DefaultTabController(
          length: 5,
          child: Scaffold(
            appBar: KoraAppBar(
              title: Text('Le Marché'),
              bottom: TabBar(
                isScrollable: true,
                tabAlignment: TabAlignment.start,
                padding: EdgeInsets.zero,
                tabs: <Widget>[
                  Tab(text: 'Actions', icon: Icon(Icons.leaderboard_outlined)),
                  Tab(
                      text: 'Prévisions',
                      icon: Icon(Icons.auto_graph_outlined)),
                  Tab(text: 'Suivi', icon: Icon(Icons.star_outline)),
                  Tab(text: 'SGI', icon: Icon(Icons.business_outlined)),
                  Tab(text: 'Actualités', icon: Icon(Icons.newspaper_outlined)),
                ],
              ),
            ),
            body: TabBarView(children: <Widget>[
              SizedBox(),
              SizedBox(),
              SizedBox(),
              SizedBox(),
              SizedBox(),
            ]),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final firstTabLeft =
        tester.getTopLeft(find.widgetWithText(Tab, 'Actions')).dx;
    final titleLeft = tester.getTopLeft(find.text('Le Marché')).dx;
    expect(
      firstTabLeft,
      lessThanOrEqualTo(titleLeft),
      reason:
          'le premier onglet doit être aligné sur le titre de l’app bar '
          '(décalage M3 de 52 dp supprimé), reçu dx=$firstTabLeft vs titre dx=$titleLeft',
    );
  });
}

// Référence locale pour éviter d'importer tout l'écran de marché (et ses
// providers) : même apparence que core/ui.dart.
class KoraAppBar extends StatelessWidget implements PreferredSizeWidget {
  const KoraAppBar({super.key, required this.title, this.bottom});

  final Widget title;
  final PreferredSizeWidget? bottom;

  @override
  Size get preferredSize =>
      Size.fromHeight(kToolbarHeight + (bottom?.preferredSize.height ?? 0));

  @override
  Widget build(BuildContext context) => AppBar(title: title, bottom: bottom);
}
