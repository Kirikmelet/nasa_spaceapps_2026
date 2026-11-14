import 'package:material_ui/material_ui.dart';

class LargeHomePage extends StatefulWidget {
  const LargeHomePage({super.key});

  @override
  State<StatefulWidget> createState() {
    return _LargeHomePageState();
  }
}

class _LargeHomePageState extends State<LargeHomePage> {
  @override
  Widget build(BuildContext context) {
    return Row(children: [
        NavigationRail(
          selectedIndex: 0,
          destinations: [
            const NavigationRailDestination(
              icon: Icon(Icons.home),
              label: Text("Home")
            )
          ],
        ),
        Expanded(
          child: Center(child: Text("Big Screen")),
        )
      ]
    );
  }
}
