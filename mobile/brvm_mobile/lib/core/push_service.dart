import 'package:flutter/foundation.dart';

/// Service de notifications push — DÉSACTIVÉ.
///
/// La plateforme n'utilise pas Firebase. Les alertes de prix et le digest
/// restent disponibles dans l'application ; la notification proactive
/// (push) sera branchée plus tard sur un autre fournisseur (par ex.
/// APNs direct, Supabase Realtime, ou WebSockets).
///
/// L'API publique est conservée (no-op) pour ne pas toucher aux écrans :
/// quand un fournisseur sera choisi, seule cette classe change.
class PushService {
  PushService._();

  static final PushService instance = PushService._();

  bool get isAvailable => false;

  /// Invoqué quand l'utilisateur touche une notification (inutilisé tant
  /// que le push est désactivé).
  void Function(String tab)? onNavigate;

  Future<void> init() async {
    debugPrint('Notifications push désactivées (aucun fournisseur configuré).');
  }

  Future<String?> getToken() async => null;

  Future<void> requestPermission() async {}
}
