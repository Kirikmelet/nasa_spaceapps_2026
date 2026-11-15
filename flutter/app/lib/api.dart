import 'package:shared_preferences/shared_preferences.dart';
import 'astro_api.dart';

const defaultApiUri = 'http://127.0.0.1:8000';

String apiBaseUrl = defaultApiUri;
AstroApi? _api;

AstroApi get api => _api ??= AstroApi(apiBaseUrl);

Future<void> initializeApi() async {
  final prefs = await SharedPreferences.getInstance();

  apiBaseUrl = prefs.getString('api_base_uri') ?? defaultApiUri;
  _api?.close();
  _api = AstroApi(apiBaseUrl);
}

Future<void> updateApiBaseUrl(String newUri) async {
  final prefs = await SharedPreferences.getInstance();

  await prefs.setString('api_base_uri', newUri);

  _api?.close();
  apiBaseUrl = newUri;
  _api = AstroApi(apiBaseUrl);
}
