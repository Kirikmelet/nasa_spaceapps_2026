
import 'package:material_ui/material_ui.dart';

import 'astro_api.dart';
import 'api.dart';

class MentalWellnessPage extends StatefulWidget {
  const MentalWellnessPage({
    super.key,
    this.astronautId = 'astro_1',
  });

  final String astronautId;

  @override
  State<MentalWellnessPage> createState() =>
      _MentalWellnessPageState();
}

class _MentalWellnessPageState extends State<MentalWellnessPage> {
  Map<String, dynamic>? _analysis;

  bool _loading = false;
  String? _error;

  int _readingCount = 0;
  DateTime? _analysisTime;


Future<void> _analyze() async {
  if (_loading) return;

  setState(() {
    _loading = true;
    _error = null;
  });

  try {
    final fetched = await api.getVitals(
      widget.astronautId,
      limit: 5000,
    );

    // Keep only readings belonging to this astronaut with valid
    // finite numeric measurements.
    final validReadings = fetched.where((r) {
      return r.astronautId == widget.astronautId &&
          r.hr.isFinite &&
          r.spo2.isFinite &&
          r.temp.isFinite &&
          r.bpSys.isFinite &&
          r.bpDia.isFinite &&
          r.resp.isFinite;
    }).toList();

    // Sort newest first, then retain at most 100.
    validReadings.sort(
      (a, b) => b.timestamp.compareTo(a.timestamp),
    );

    final selectedReadings = validReadings.take(100).toList();

    if (selectedReadings.isEmpty) {
      throw Exception('No valid vital readings are available.');
    }

    final result = await api.analyzeWellness(
      widget.astronautId,
      selectedReadings,
    );

    if (!mounted) return;

    setState(() {
      _analysis = result;
      _readingCount = selectedReadings.length;
      _analysisTime = DateTime.now();
    });
  } catch (e) {
    if (!mounted) return;

    setState(() {
      _error = 'Unable to generate wellness insights: $e';
    });
  } finally {
    if (mounted) {
      setState(() {
        _loading = false;
      });
    }
  }
}

  Color _urgencyColor(String urgency) {
    switch (urgency.toLowerCase()) {
      case 'urgent':
        return Colors.red;
      case 'attention':
        return Colors.orange;
      default:
        return Colors.green;
    }
  }

  IconData _urgencyIcon(String urgency) {
    switch (urgency.toLowerCase()) {
      case 'urgent':
        return Icons.error;
      case 'attention':
        return Icons.warning_amber_rounded;
      default:
        return Icons.check_circle_outline;
    }
  }

  Widget _section({
    required String title,
    required IconData icon,
    required List<dynamic> items,
    required Color color,
  }) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (items.isEmpty)
              Text(
                'No additional information.',
                style: theme.textTheme.bodyMedium,
              )
            else
              ...items.map(
                (item) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Icon(
                          Icons.circle,
                          size: 7,
                          color: color,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          item.toString(),
                          style: theme.textTheme.bodyMedium,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _disclaimer() {
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: const Padding(
        padding: EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.info_outline),
            SizedBox(width: 12),
            Expanded(
              child: Text(
                'These insights are AI-generated educational wellness '
                'information, not a medical diagnosis or treatment plan. '
                'Vital signs cannot determine mental health conditions. '
                'Do not delay professional or emergency care because '
                'of an AI-generated result.',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAnalysis() {
    final result = _analysis!;
    final theme = Theme.of(context);

    final urgency = result['urgency']?.toString() ?? 'normal';
    final color = _urgencyColor(urgency);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Overall status
        Card(
          elevation: 3,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: BorderSide(color: color, width: 2),
          ),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      _urgencyIcon(urgency),
                      color: color,
                      size: 30,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'WELLNESS STATUS: ${urgency.toUpperCase()}',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: color,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(
                  result['summary']?.toString() ??
                      'No summary provided.',
                  style: theme.textTheme.bodyLarge,
                ),
              ],
            ),
          ),
        ),

        const SizedBox(height: 12),

        _section(
          title: 'Observations',
          icon: Icons.analytics_outlined,
          items: result['observations'] is List
              ? result['observations'] as List
              : [],
          color: Colors.blue,
        ),

        _section(
          title: 'Wellness Guidance',
          icon: Icons.self_improvement,
          items: result['guidance'] is List
              ? result['guidance'] as List
              : [],
          color: Colors.green,
        ),

        _section(
          title: 'Warnings',
          icon: Icons.warning_amber_rounded,
          items: result['warnings'] is List
              ? result['warnings'] as List
              : [],
          color: Colors.orange,
        ),

        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Analysis information',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text('Readings analyzed: $_readingCount'),
                Text(
                  'Data window: ${result['data_window'] ?? 'Not specified'}',
                ),
                if (_analysisTime != null)
                  Text(
                    'Generated: ${_analysisTime!.toLocal()}',
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mental Wellness'),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Introduction
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.psychology,
                          size: 32,
                          color: theme.colorScheme.primary,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            'Wellness Insights',
                            style: theme.textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Review recent physiological readings and receive '
                      'AI-generated observations and general wellness '
                      'guidance.',
                      style: theme.textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: _loading ? null : _analyze,
                        icon: _loading
                            ? const SizedBox(
                                height: 18,
                                width: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.auto_awesome),
                        label: Text(
                          _loading
                              ? 'Analyzing readings...'
                              : 'Generate wellness analysis',
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(height: 16),

            if (_error != null)
              Card(
                color: theme.colorScheme.errorContainer,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    _error!,
                    style: TextStyle(
                      color: theme.colorScheme.onErrorContainer,
                    ),
                  ),
                ),
              ),

            if (_analysis != null) ...[
              Text(
                'Latest Analysis',
                style: theme.textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              _buildAnalysis(),
            ] else if (!_loading && _error == null) ...[
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Column(
                    children: [
                      Icon(
                        Icons.monitor_heart_outlined,
                        size: 48,
                      ),
                      SizedBox(height: 12),
                      Text(
                        'No analysis generated yet',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      SizedBox(height: 6),
                      Text(
                        'Generate an analysis to review recent '
                        'telemetry and receive wellness guidance.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ],

            const SizedBox(height: 16),
            _disclaimer(),
          ],
        ),
      ),
    );
  }
}
