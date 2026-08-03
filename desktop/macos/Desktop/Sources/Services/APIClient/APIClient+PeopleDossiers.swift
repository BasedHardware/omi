import Foundation

// MARK: - API

extension APIClient {
  /// `POST /v1/people/dossiers` — narrative + provenance for a bounded set of backend person ids.
  ///
  /// The body is ids and fingerprints only. Nothing about the local message store, no names, no
  /// text: the backend summarizes evidence it already holds.
  func fetchPersonDossiers(_ items: [PeopleNarrative.RequestItem]) async throws
    -> PeopleNarrative.DossierResponse
  {
    struct Request: Encodable { let people: [PeopleNarrative.RequestItem] }
    return try await post("v1/people/dossiers", body: Request(people: items))
  }
}
