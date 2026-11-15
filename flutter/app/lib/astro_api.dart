// ignore_for_file: unnecessary_brace_in_string_interps

import 'dart:convert';

import 'package:http/http.dart' as http;

enum Activity { rest, sleep, exercise, eva }

enum Severity { info, warning, critical }

T _enum<T extends Enum>(List<T> values, Object? v, T fallback) =>
    values.firstWhere((e) => e.name == v, orElse: () => fallback);


 
class WellnessResponse {
  WellnessResponse({
    required this.summary,
    required this.observations,
    required this.guidance,
    required this.warnings,
    required this.urgency,
    required this.dataWindow,
  });

  final String summary;
  final List<String> observations;
  final List<String> guidance;
  final List<String> warnings;
  final String urgency;
  final String dataWindow;

  factory WellnessResponse.fromJson(Map<String, dynamic> json) {
    return WellnessResponse(
      summary: json['summary'] as String,
      observations: List<String>.from(json['observations'] ?? []),
      guidance: List<String>.from(json['guidance'] ?? []),
      warnings: List<String>.from(json['warnings'] ?? []),
      urgency: json['urgency'] as String,
      dataWindow: json['data_window'] as String,
    );
  }
}

// ---------- models ----------

class Reading {
  Reading({
    this.id,
    required this.astronautId,
    required this.timestamp,
    required this.hr,
    required this.spo2,
    required this.temp,
    required this.bpSys,
    required this.bpDia,
    required this.resp,
    this.activity = Activity.rest,
    this.originId,
  });

  final int? id, originId;
  final String astronautId;
  final DateTime timestamp;
  final double hr, spo2, temp, bpSys, bpDia, resp;
  final Activity activity;

  factory Reading.fromJson(Map<String, dynamic> j) => Reading(
    id: j['id'] as int?,
    originId: j['origin_id'] as int?,
    astronautId: j['astronaut_id'] as String,
    timestamp: DateTime.parse(j['timestamp'] as String),
    hr: (j['hr'] as num).toDouble(), // server sends 70, not 70.0
    spo2: (j['spo2'] as num).toDouble(),
    temp: (j['temp'] as num).toDouble(),
    bpSys: (j['bp_sys'] as num).toDouble(),
    bpDia: (j['bp_dia'] as num).toDouble(),
    resp: (j['resp'] as num).toDouble(),
    activity: _enum(Activity.values, j['activity'], Activity.rest),
  );

  Map<String, dynamic> toJson() => {
    if (id != null) 'id': id,
    'astronaut_id': astronautId,
    'timestamp': timestamp.toUtc().toIso8601String(),
    'hr': hr,
    'spo2': spo2,
    'temp': temp,
    'bp_sys': bpSys,
    'bp_dia': bpDia,
    'resp': resp,
    'activity': activity.name,
  };
}

class Alert {
  Alert({
    this.id,
    this.originId,
    required this.astronautId,
    required this.severity,
    required this.metric,
    required this.message,
    required this.timestamp,
    this.acknowledged = false,
    this.value,
  });

  final int? id, originId;
  final String astronautId, metric, message;
  final Severity severity;
  final DateTime timestamp;
  final bool acknowledged;
  final double? value;

  factory Alert.fromJson(Map<String, dynamic> j) => Alert(
    id: j['id'] as int?,
    originId: j['origin_id'] as int?,
    astronautId: j['astronaut_id'] as String,
    severity: _enum(Severity.values, j['severity'], Severity.info),
    metric: j['metric'] as String,
    message: j['message'] as String,
    timestamp: DateTime.parse(j['timestamp'] as String),
    acknowledged: (j['acknowledged'] as bool?) ?? false,
    value: (j['value'] as num?)?.toDouble(),
  );

  Map<String, dynamic> toJson() => {
    if (id != null) 'id': id,
    'astronaut_id': astronautId,
    'severity': severity.name,
    'metric': metric,
    'message': message,
    'timestamp': timestamp.toUtc().toIso8601String(),
    'acknowledged': acknowledged,
    if (value != null) 'value': value,
  };
}

class User {
  User({this.id, required this.astronautId, required this.name});
  final int? id;
  final String astronautId, name;

  factory User.fromJson(Map<String, dynamic> j) => User(
    id: j['id'] as int?,
    astronautId: j['astronaut_id'] as String,
    name: j['name'] as String,
  );

  Map<String, dynamic> toJson() => {
    if (id != null) 'id': id,
    'astronaut_id': astronautId,
    'name': name,
  };
}

class IngestResult {
  IngestResult(this.id, this.alertIds);
  final int id;
  final List<int> alertIds;

  factory IngestResult.fromJson(Map<String, dynamic> j) => IngestResult(
    j['id'] as int,
    (j['alert_ids'] as List).map((e) => e as int).toList(),
  );
}

// ---------- client ----------

class AstroApiException implements Exception {
  AstroApiException(this.status, this.body);
  final int status;
  final String body;
  @override
  String toString() => 'AstroApiException($status): $body';
}

class AstroApi {
  AstroApi(String baseUrl, {http.Client? client})
    : _base = Uri.parse(baseUrl),
      _http = client ?? http.Client();

  final Uri _base;
  final http.Client _http;
  static const _json = {'content-type': 'application/json'};

  // pathSegments percent-encodes ids for you
  Uri _u(List<String> seg, [Map<String, String>? q]) => _base.replace(
    pathSegments: [..._base.pathSegments.where((s) => s.isNotEmpty), ...seg],
    queryParameters: (q == null || q.isEmpty) ? null : q,
  );

  Future<http.Response> _check(Future<http.Response> req) async {
    final r = await req.timeout(const Duration(seconds: 10));
    if (r.statusCode >= 400) throw AstroApiException(r.statusCode, r.body);
    return r;
  }

  dynamic _decode(http.Response r) => jsonDecode(utf8.decode(r.bodyBytes));

  // POST /api/dummy/vitals
  Future<({String status, int stored})> postDummyVitals(Reading reading) async {
    final r = await _check(
      _http.post(
        _u(['api', 'dummy', 'vitals']),
        headers: _json,
        body: jsonEncode(reading.toJson()),
      ),
    );
    final j = _decode(r) as Map<String, dynamic>;
    return (status: j['status'] as String, stored: j['stored'] as int);
  }

  // GET /api/astronauts/{id}/vitals?limit=
  Future<List<Reading>> getVitals(String astronautId, {int limit = 300}) async {
    final r = await _check(
      _http.get(
        _u(['api', 'astronauts', astronautId, 'vitals'], {'limit': '$limit'}),
      ),
    );
    return (_decode(r) as List).map((e) => Reading.fromJson(e)).toList();
  }

  // POST /api/astronauts/{id}/vitals  (201)
  Future<IngestResult> postVitals(String astronautId, Reading reading) async {
    final r = await _check(
      _http.post(
        _u(['api', 'astronauts', astronautId, 'vitals']),
        headers: _json,
        body: jsonEncode(reading.toJson()),
      ),
    );
    return IngestResult.fromJson(_decode(r));
  }

  // POST /api/astronauts/{id}/user  -> new row id
  Future<int> postUser(String astronautId, User user) async {
    final r = await _check(
      _http.post(
        _u(['api', 'astronauts', astronautId, 'user']),
        headers: _json,
        body: jsonEncode(user.toJson()),
      ),
    );
    return _decode(r) as int;
  }

  // GET /api/astronauts/{id}/user
  Future<User> getUser(String astronautId) async {
    final r = await _check(
      _http.get(_u(['api', 'astronauts', astronautId, 'user'])),
    );
    return User.fromJson(_decode(r));
  }

  // GET /api/alerts?severity=
  Future<List<Alert>> getAlerts({int? alertId, Severity? severity}) async {
    final r = await _check(
      _http.get(
        _u(
          ['api', 'alerts'],
          {
            if (alertId != null) 'alert_id': "${alertId}",
            if (severity != null) 'severity': severity.name,
          },
        ),
      ),
    );
    return (_decode(r) as List).map((e) => Alert.fromJson(e)).toList();
  }

  // GET /api/alerts/{alert_id}?severity=
  Future<List<Alert>> getAlertsById(int alertId, {Severity? severity}) async {
    final r = await _check(
      _http.get(
        _u(
          ['api', 'alerts', '$alertId'],
          {if (severity != null) 'severity': severity.name},
        ),
      ),
    );
    return (_decode(r) as List).map((e) => Alert.fromJson(e)).toList();
  }

  // POST /api/alerts/{alert_id}/acknowledge  -> id of the new revision row
  Future<int> acknowledge(int alertId) async {
    final r = await _check(
      _http.post(_u(['api', 'alerts', '$alertId', 'acknowledge'])),
    );
    return _decode(r) as int;
  }

  // POST /api/astronauts/{id}/alerts/{metric}/acknowledge  -> returns HTML, not JSON
  Future<void> acknowledgeGroup(String astronautId, String metric) async {
    await _check(
      _http.post(
        _u(['api', 'astronauts', astronautId, 'alerts', metric, 'acknowledge']),
      ),
    );
  }

  // POST /api/astronauts/{id}/mental-wellness
 Future<Map<String, dynamic>> analyzeWellness(
  String astronautId,
  List<Reading> readings,
) async {
  if (readings.isEmpty || readings.length > 100) {
    throw ArgumentError('Readings must contain between 1 and 100 items.');
  }

  final response = await _check(
    _http.post(
      _u(['api', 'astronauts', astronautId, 'mental-wellness']),
      headers: _json,
      body: jsonEncode({
        'readings': readings.map((r) => r.toJson()).toList(),
      }),
    ),
  );

  return _decode(response) as Map<String, dynamic>;
}

  

  void close() => _http.close();
}

