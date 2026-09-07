import 'package:dio/dio.dart';

import 'config.dart';
import 'models/auth_user.dart';
import 'token_storage.dart';

/// Client HTTP autour de Dio.
///
/// - Attache automatiquement le jeton d'accès Bearer aux requêtes
///   authentifiées (tout sauf `/mobile/v1/auth/*`).
/// - Sur 401, tente un renouvellement via le refresh token (une seule
///   tentative, en single-flight), puis rejoue la requête originale.
/// - Si le renouvellement échoue, efface les jetons et notifie
///   [onSessionExpired] pour forcer la reconnexion.
class ApiClient {
  ApiClient(this.storage, {Dio? dio, this.onSessionExpired})
      : dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: AppConfig.apiBaseUrl,
                connectTimeout: const Duration(seconds: 20),
                receiveTimeout: const Duration(seconds: 40),
                sendTimeout: const Duration(seconds: 40),
                headers: <String, dynamic>{'Accept': 'application/json'},
              ),
            ) {
    this.dio.interceptors.add(
          InterceptorsWrapper(
            onRequest: _onRequest,
            onError: _onError,
          ),
        );
  }

  final Dio dio;
  final TokenStorage storage;

  /// Appelé quand la session ne peut plus être rétablie (refresh invalide).
  void Function()? onSessionExpired;

  Future<bool>? _refreshFuture;

  static bool _isAuthPath(String path) => path.contains('${AppConfig.apiPrefix}/auth/');

  Future<void> _onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (!_isAuthPath(options.path)) {
      final token = await storage.readAccessToken();
      if (token != null && token.isNotEmpty) {
        options.headers['Authorization'] = 'Bearer $token';
      }
    }
    handler.next(options);
  }

  Future<void> _onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final status = err.response?.statusCode;
    final options = err.requestOptions;
    final alreadyRetried = options.extra['retried'] == true;
    if (status != 401 || _isAuthPath(options.path) || alreadyRetried) {
      handler.next(err);
      return;
    }

    final refreshed = await refreshTokens();
    if (!refreshed) {
      await storage.clear();
      onSessionExpired?.call();
      handler.next(err);
      return;
    }

    try {
      options.extra['retried'] = true;
      final response = await dio.fetch<dynamic>(options);
      handler.resolve(response);
    } on DioException catch (e) {
      handler.next(e);
    }
  }

  /// Renouvelle les jetons ; les appels concurrents partagent la même
  /// opération (single-flight).
  Future<bool> refreshTokens() {
    final pending = _refreshFuture;
    if (pending != null) return pending;
    final future = _doRefresh();
    _refreshFuture = future;
    future.whenComplete(() => _refreshFuture = null);
    return future;
  }

  Future<bool> _doRefresh() async {
    final refreshToken = await storage.readRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) return false;
    try {
      final response = await dio.post<dynamic>(
        '${AppConfig.apiPrefix}/auth/refresh',
        data: <String, dynamic>{'refresh_token': refreshToken},
      );
      final data = response.data;
      if (data is Map<String, dynamic> &&
          data['access_token'] is String &&
          data['refresh_token'] is String) {
        await storage.saveSession(AuthSession.fromJson(data));
        return true;
      }
      return false;
    } catch (_) {
      return false;
    }
  }

  // ---- Helpers verbe HTTP ----

  Future<Response<dynamic>> get(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) =>
      dio.get<dynamic>(path,
          queryParameters: queryParameters, options: options);

  /// [timeout] permet d'allonger les délais pour les appels longs
  /// (ex. le chat peut mettre jusqu'à 5 minutes).
  Future<Response<dynamic>> post(
    String path, {
    dynamic data,
    Options? options,
    Duration? timeout,
  }) =>
      dio.post<dynamic>(path,
          data: data, options: _withTimeout(options, timeout));

  Future<Response<dynamic>> put(
    String path, {
    dynamic data,
    Options? options,
    Duration? timeout,
  }) =>
      dio.put<dynamic>(path,
          data: data, options: _withTimeout(options, timeout));

  Future<Response<dynamic>> delete(
    String path, {
    Object? data,
    Options? options,
  }) =>
      dio.delete<dynamic>(path, data: data, options: options);

  Options? _withTimeout(Options? options, Duration? timeout) {
    if (timeout == null) return options;
    final opts = options ?? Options();
    opts.receiveTimeout = timeout;
    opts.sendTimeout = timeout;
    return opts;
  }
}
