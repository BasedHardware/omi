// (Trecho relevante da modificação no cliente)
// ... (código existente)
Future<void> reconcile(SyncJobResult result) async {
  if (result.status == 'speech_without_text') {
    // Marca como processado, mas não limpa o arquivo local
    await _markAsSyncedWithoutAutoRemove(result.walId);
    return;
  }
  // ... lógica padrão de acknowledge ...
}

Future<void> _markAsSyncedWithoutAutoRemove(String walId) async {
  // Atualiza o banco local para exibir "No speech found — audio kept"
  await db.updateWal(walId, status: 'no_speech_found', syncedAt: DateTime.now());
}
