import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';
import "package:material_ui/material_ui.dart";

class LocalAvatar extends StatefulWidget {
  const LocalAvatar({super.key, this.radius = 28});

  final double radius;

  @override
  State<LocalAvatar> createState() => _LocalAvatarState();
}

class _LocalAvatarState extends State<LocalAvatar> {
  String? _path;

  @override
  void initState() {
    super.initState();
    _loadAvatar();
  }

  Future<void> _loadAvatar() async {
    final prefs = await SharedPreferences.getInstance();
    final path = prefs.getString('avatar_path');

    if (!mounted) return;

    setState(() => _path = path);
  }

  @override
  Widget build(BuildContext context) {
    final path = _path;
    final file = path == null ? null : File(path);

    return CircleAvatar(
      radius: widget.radius,
      backgroundImage: file != null && file.existsSync()
          ? FileImage(file)
          : null,
      child: file == null || !file.existsSync()
          ? const Icon(Icons.person)
          : null,
    );
  }
}
