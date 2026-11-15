import 'dart:io';

import 'package:material_ui/material_ui.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _uriController = TextEditingController();
  final _picker = ImagePicker();

  final _astronautController = TextEditingController();

  bool _savingAstronautId = false;

  String? _avatarPath;
  bool _loading = true;
  bool _savingUri = false;
  bool _savingAvatar = false;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  @override
  void dispose() {
    _uriController.dispose();
    _astronautController.dispose();
    super.dispose();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();

    if (!mounted) return;

    setState(() {
      _uriController.text = apiBaseUrl;
      _astronautController.text = prefs.getString('astronaut_id') ?? 'astro_1';

      _avatarPath = prefs.getString('avatar_path');
      _loading = false;
    });
  }

  Future<void> _saveApiUri() async {
    final value = _uriController.text.trim();
    final uri = Uri.tryParse(value);

    if (uri == null ||
        !uri.hasAuthority ||
        uri.host.isEmpty ||
        (uri.scheme != 'http' && uri.scheme != 'https')) {
      _showMessage('Enter a valid HTTP or HTTPS URL.');
      return;
    }

    setState(() => _savingUri = true);

    try {
      await updateApiBaseUrl(value);

      if (!mounted) return;

      _showMessage('API address updated.');
    } catch (e) {
      if (!mounted) return;
      _showMessage('Could not save API address: $e');
    } finally {
      if (mounted) {
        setState(() => _savingUri = false);
      }
    }
  }

  Future<void> _saveAstronautId() async {
    final value = _astronautController.text.trim();

    if (value.isEmpty) {
      _showMessage('Astronaut ID cannot be empty.');
      return;
    }

    if (value.contains(RegExp(r'\s'))) {
      _showMessage('Astronaut ID cannot contain spaces.');
      return;
    }

    setState(() => _savingAstronautId = true);

    try {
      final prefs = await SharedPreferences.getInstance();

      await prefs.setString('astronaut_id', value);

      if (!mounted) return;

      _showMessage('Astronaut ID updated.');
    } catch (e) {
      if (!mounted) return;

      _showMessage('Could not save Astronaut ID: $e');
    } finally {
      if (mounted) {
        setState(() => _savingAstronautId = false);
      }
    }
  }

  Future<void> _chooseAvatar() async {
    try {
      final selected = await _picker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 85,
        maxWidth: 1024,
      );

      if (selected == null) return;

      setState(() => _savingAvatar = true);

      // Copy the selected image into persistent app-local storage.
      final directory = await getApplicationDocumentsDirectory();
      final extension = selected.path.contains('.')
          ? selected.path.split('.').last
          : 'jpg';

      final destination = File(
        '${directory.path}/avatar_${DateTime.now().millisecondsSinceEpoch}.$extension',
      );

      await File(selected.path).copy(destination.path);

      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('avatar_path', destination.path);

      if (!mounted) return;

      setState(() {
        _avatarPath = destination.path;
      });

      _showMessage('Avatar saved on this device.');
    } catch (e) {
      if (mounted) {
        _showMessage('Could not select avatar: $e');
      }
    } finally {
      if (mounted) {
        setState(() => _savingAvatar = false);
      }
    }
  }

  Future<void> _removeAvatar() async {
    final prefs = await SharedPreferences.getInstance();
    final oldPath = _avatarPath;

    await prefs.remove('avatar_path');

    if (oldPath != null) {
      final file = File(oldPath);
      if (await file.exists()) {
        await file.delete();
      }
    }

    if (!mounted) return;

    setState(() => _avatarPath = null);
    _showMessage('Avatar removed.');
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  ImageProvider? _avatarImage() {
    final path = _avatarPath;
    if (path == null) return null;

    final file = File(path);
    if (!file.existsSync()) return null;

    return FileImage(file);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final avatar = _avatarImage();

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Profile section
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Profile',
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 20),

                    Center(
                      child: Column(
                        children: [
                          CircleAvatar(
                            radius: 54,
                            backgroundColor: theme.colorScheme.primaryContainer,
                            backgroundImage: avatar,
                            child: avatar == null
                                ? Icon(
                                    Icons.person,
                                    size: 54,
                                    color: theme.colorScheme.onPrimaryContainer,
                                  )
                                : null,
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'Local profile avatar',
                            style: theme.textTheme.bodyMedium,
                          ),
                          const SizedBox(height: 12),

                          Wrap(
                            alignment: WrapAlignment.center,
                            spacing: 8,
                            children: [
                              FilledButton.icon(
                                onPressed: _savingAvatar ? null : _chooseAvatar,
                                icon: _savingAvatar
                                    ? const SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(Icons.image),
                                label: const Text('Choose image'),
                              ),
                              if (_avatarPath != null)
                                OutlinedButton.icon(
                                  onPressed: _savingAvatar
                                      ? null
                                      : _removeAvatar,
                                  icon: const Icon(Icons.delete_outline),
                                  label: const Text('Remove'),
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 12),

                    Text(
                      'Your avatar is stored locally on this device. '
                      'It is not uploaded to the API.',
                      style: theme.textTheme.bodySmall,
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(height: 20),

            // Mission configuration
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Mission Configuration',
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),

                    const SizedBox(height: 8),

                    Text(
                      'Choose which astronaut account this device monitors.',
                      style: theme.textTheme.bodyMedium,
                    ),

                    const SizedBox(height: 20),

                    TextField(
                      controller: _astronautController,
                      autocorrect: false,
                      enableSuggestions: false,
                      decoration: const InputDecoration(
                        labelText: 'Astronaut ID',
                        hintText: 'astro_1',
                        prefixIcon: Icon(Icons.person_outline),
                        border: OutlineInputBorder(),
                      ),
                    ),

                    const SizedBox(height: 16),

                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: _savingAstronautId ? null : _saveAstronautId,
                        icon: _savingAstronautId
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.save),
                        label: const Text('Save Astronaut ID'),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // API section
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'API Connection',
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Configure the backend server used for telemetry, '
                      'alerts, and astronaut profiles.',
                      style: theme.textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 20),

                    TextField(
                      controller: _uriController,
                      keyboardType: TextInputType.url,
                      autocorrect: false,
                      enableSuggestions: false,
                      decoration: const InputDecoration(
                        labelText: 'API Base URI',
                        hintText: 'http://192.168.1.100:8000',
                        prefixIcon: Icon(Icons.link),
                        border: OutlineInputBorder(),
                      ),
                    ),

                    const SizedBox(height: 8),

                    Text(
                      'Current address: $apiBaseUrl',
                      style: theme.textTheme.bodySmall,
                    ),

                    const SizedBox(height: 16),

                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: _savingUri ? null : _saveApiUri,
                        icon: _savingUri
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.save),
                        label: const Text('Save API address'),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(height: 20),

            // About section
            Card(
              child: ListTile(
                leading: const Icon(Icons.info_outline),
                title: const Text('Application'),
                subtitle: const Text('Astronaut Telemetry Dashboard'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  showAboutDialog(
                    context: context,
                    applicationName: 'Astronaut Telemetry',
                    applicationVersion: '1.0.0',
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
