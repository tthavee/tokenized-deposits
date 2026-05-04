import 'package:flutter/foundation.dart' show kIsWeb;

/// Application configuration.
///
/// The base API URL is resolved at runtime from the --dart-define flag
/// BASE_API_URL, with a sensible local default.
///
/// All API routes are under /api prefix (both locally and in production).
/// When deployed to Firebase Hosting, /api requests are proxied to Cloud Run.
///
/// To override at build/run time:
///   flutter run --dart-define=BASE_API_URL=https://api.example.com/api
///   flutter build web --dart-define=BASE_API_URL=/api
class AppConfig {
  AppConfig._();

  static String get baseApiUrl {
    const envUrl = String.fromEnvironment('BASE_API_URL');
    if (envUrl.isNotEmpty) {
      return envUrl;
    }
    // Default: use /api for web (proxied by Firebase Hosting), localhost:8000/api for other platforms
    return kIsWeb ? '/api' : 'http://localhost:8000/api';
  }
}
