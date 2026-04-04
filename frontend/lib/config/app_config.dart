/// Application configuration.
///
/// The base API URL is resolved at runtime from the --dart-define flag
/// BASE_API_URL, with a sensible local default.
///
/// To override at build/run time:
///   flutter run --dart-define=BASE_API_URL=https://api.example.com
class AppConfig {
  AppConfig._();

  static const String baseApiUrl = String.fromEnvironment(
    'BASE_API_URL',
    defaultValue: 'http://localhost:8000',
  );
}
