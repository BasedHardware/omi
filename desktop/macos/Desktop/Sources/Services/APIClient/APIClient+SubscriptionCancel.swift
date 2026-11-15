import Foundation

/// Cancel-flow client calls for the mobile cancel-flow parity work (SCA-2171).
/// The endpoints are the existing mobile ones: no new backend surface.
extension APIClient {

  /// `DELETE /v1/payments/subscription` with the mobile payload. The backend
  /// stores `reason`/`reason_details` before cancelling in Stripe.
  func cancelSubscription(reason: String, reasonDetails: String?) async throws {
    struct Request: Encodable {
      let reason: String
      let reasonDetails: String?

      enum CodingKeys: String, CodingKey {
        case reason
        case reasonDetails = "reason_details"
      }
    }
    let body = try JSONEncoder().encode(Request(reason: reason, reasonDetails: reasonDetails))
    try await delete("v1/payments/subscription", body: body)
  }

  /// `GET /v1/payments/retention-offer`: the mobile stay offer. Ineligible
  /// readers receive `eligible: false` rather than an error.
  func getRetentionOffer() async throws -> RetentionOfferResponse {
    return try await get("v1/payments/retention-offer")
  }

  /// `POST /v1/payments/retention-offer`: apply the stay offer.
  func acceptRetentionOffer() async throws -> RetentionOfferResponse {
    return try await post("v1/payments/retention-offer")
  }
}

/// Mirrors `backend/routers/retention_offer.py::RetentionOfferResponse`.
struct RetentionOfferResponse: Codable, Equatable, Sendable {
  let eligible: Bool
  let percentOff: Int
  let durationMonths: Int
  let regularAmount: Int?
  let discountedAmount: Int?
  let currency: String?

  enum CodingKeys: String, CodingKey {
    case eligible
    case percentOff = "percent_off"
    case durationMonths = "duration_months"
    case regularAmount = "regular_amount"
    case discountedAmount = "discounted_amount"
    case currency
  }
}
