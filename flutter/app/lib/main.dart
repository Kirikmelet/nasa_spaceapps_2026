import 'dart:async';
import "dart:io";

import 'package:app/mental_wellness.dart';
import 'package:app/settings.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'package:material_ui/material_ui.dart';

import 'api.dart';
import 'astro_api.dart';
import 'home.dart';

// ---------- Toast ----------

final messengerKey = GlobalKey<ScaffoldMessengerState>();

void showAlertToast(List<Alert> alerts, {VoidCallback? onView}) {
  final worst = alerts.reduce(
    (a, b) => a.severity.index >= b.severity.index ? a : b,
  );
  final text = alerts.length == 1
      ? '${worst.astronautId}: ${worst.message}'
      : '${alerts.length} new alerts, worst: ${worst.astronautId} ${worst.metric}';

  messengerKey.currentState
    ?..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(text, maxLines: 2, overflow: TextOverflow.ellipsis),
        backgroundColor: worst.severity == Severity.critical
            ? Colors.red.shade700
            : Colors.amber.shade800,
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 6),
        action: SnackBarAction(label: 'VIEW', onPressed: onView ?? () {}),
      ),
    );
}

// ---------- System notifications ----------

final _notifications = FlutterLocalNotificationsPlugin();

Future<void> initNotifications() async {
  try {
    const init = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      iOS: DarwinInitializationSettings(),
    );
    await _notifications.initialize(settings: init);
    await _notifications
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.requestNotificationsPermission(); // Android 13+
  } catch (e) {
    debugPrint(
      'Notifications unavailable: $e',
    ); // web/desktop, so toasts still work
  }
}

Future<void> notifyAlert(Alert a) async {
  try {
    await _notifications.show(
      id: a.id ?? 0,
      title: '${a.severity.name.toUpperCase()}: ${a.astronautId}',
      body: a.message,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          'health_alerts',
          'Health alerts',
          importance: Importance.max,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(),
      ),
    );
  } catch (e) {
    debugPrint('Notification failed: $e');
  }
}

// ---------- Alert watcher (polls for NEW alerts) ----------

class AlertWatcher {
  AlertWatcher(this._api);
  final AstroApi _api;

  final _controller = StreamController<List<Alert>>.broadcast();
  Stream<List<Alert>> get newAlerts => _controller.stream;

  Timer? _timer;
  int? _maxId; // null until the first poll, so old alerts don't spam on launch

  void start() {
    _poll();
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _poll());
  }

  void stop() {
    _timer?.cancel();
    _controller.close();
  }

  Future<void> _poll() async {
    try {
      final all = await _api.getAlerts();
      final top = all.fold<int>(0, (m, a) => (a.id ?? 0) > m ? a.id! : m);
      final seen = _maxId;

      if (seen != null) {
        final fresh = all
            .where(
              (a) =>
                  !a.acknowledged &&
                  (a.id ?? 0) > seen &&
                  a.severity != Severity.info,
            )
            .toList();
        if (fresh.isNotEmpty && !_controller.isClosed) _controller.add(fresh);
      }
      _maxId = top > (seen ?? 0) ? top : (seen ?? top);
    } catch (_) {
      // network blips are normal, keep polling
    }
  }
}

// ---------- App ----------

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (Platform.isAndroid) {
    final status = await Permission.accessLocalNetwork.request();
    print(status);
  }
  await initializeApi();
  runApp(const MainApp());
}

class MainApp extends StatefulWidget {
  const MainApp({super.key});

  @override
  State<MainApp> createState() => _MainAppState();
}

class _MainAppState extends State<MainApp> with WidgetsBindingObserver {
  static const _homeTab = 0;

  int _selectedIndex = _homeTab;

  final _watcher = AlertWatcher(api);
  StreamSubscription<List<Alert>>? _sub;
  AppLifecycleState _life = AppLifecycleState.resumed;

  final List<BottomNavigationBarItem> _bottomBarList = const [
    BottomNavigationBarItem(icon: Icon(Icons.home), label: "Home"),
    BottomNavigationBarItem(icon: Icon(Icons.sunny), label: "Mental Help"),
    BottomNavigationBarItem(icon: Icon(Icons.settings), label: "Settings"),
  ];

  final List<Widget> _widgetList = const [
    HomeWidget(),
    MentalWellnessPage(),
    SettingsPage(),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    initNotifications();
    _sub = _watcher.newAlerts.listen(_onNewAlerts);
    _watcher.start();
  }

  void _onNewAlerts(List<Alert> alerts) {
    if (_life == AppLifecycleState.resumed) {
      showAlertToast(
        alerts,
        onView: () => setState(() => _selectedIndex = _homeTab),
      );
    } else {
      for (final a in alerts) {
        notifyAlert(a);
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) => _life = state;

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _sub?.cancel();
    _watcher.stop();
    super.dispose();
  }

  void _onItemTapped(int idx) => setState(() => _selectedIndex = idx);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      scaffoldMessengerKey: messengerKey,
      home: Scaffold(
        bottomNavigationBar: BottomNavigationBar(
          currentIndex: _selectedIndex,
          items: _bottomBarList,
          onTap: _onItemTapped,
        ),
        body: _widgetList[_selectedIndex],
      ),
    );
  }
}
