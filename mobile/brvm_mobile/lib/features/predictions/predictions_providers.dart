import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'predictions_models.dart';
import 'predictions_repository.dart';

final predictionsRepositoryProvider = Provider<PredictionsRepository>(
  (ref) => PredictionsRepository(ref.watch(apiClientProvider)),
);

/// Prévisions du jour (onglet « Prévisions » du marché).
final predictionsProvider = FutureProvider.autoDispose<PredictionsFeed>(
  (ref) => ref.watch(predictionsRepositoryProvider).getPredictions(),
);

/// Détail complet d'une prévision, indexé par symbole (fiche modale).
final predictionDetailProvider =
    FutureProvider.autoDispose.family<StockPrediction, String>(
  (ref, symbol) =>
      ref.watch(predictionsRepositoryProvider).getPrediction(symbol),
);
