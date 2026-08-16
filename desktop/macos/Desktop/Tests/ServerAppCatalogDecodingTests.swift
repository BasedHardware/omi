import XCTest

@testable import Omi_Computer

final class ServerAppCatalogDecodingTests: XCTestCase {
  func testAppDetailsIgnoresLegacyTwitterObject() throws {
    let json = """
      {
        "id": "app1",
        "name": "Catalog App",
        "description": "Does things",
        "image": "https://example.com/icon.png",
        "category": "productivity",
        "author": "Someone",
        "email": "author@example.com",
        "capabilities": ["chat"],
        "uid": "owner1",
        "approved": true,
        "private": false,
        "status": "approved",
        "installs": 12,
        "rating_avg": 4.5,
        "rating_count": 2,
        "is_paid": false,
        "price": 0,
        "username": "owner",
        "twitter": {"handle": "legacy-object"},
        "enabled": true,
        "external_integration": {
          "auth_steps": [{"name": "Connect", "url": "https://example.com/oauth"}]
        }
      }
      """.data(using: .utf8)!

    let app = try JSONDecoder().decode(OmiAppDetails.self, from: json)

    XCTAssertEqual(app.id, "app1")
    XCTAssertNil(app.twitter)
    XCTAssertEqual(app.externalIntegration?.authSteps.first?.name, "Connect")
  }

  func testV2AppsResponseDecodesCatalogItems() throws {
    let json = """
      {
        "groups": [
          {
            "capability": {"id": "chat", "title": "Chat"},
            "data": [
              {
                "id": "app1",
                "name": "Catalog App",
                "description": "Does things",
                "image": "https://example.com/icon.png",
                "category": "productivity",
                "author": "Someone",
                "capabilities": ["chat"],
                "approved": true,
                "private": false,
                "installs": 12,
                "rating_avg": 4.5,
                "rating_count": 2,
                "is_paid": false,
                "price": 0,
                "enabled": true
              }
            ],
            "pagination": {"total": 1, "count": 1, "offset": 0, "limit": 20}
          }
        ],
        "meta": {"capabilities": [{"id": "chat", "title": "Chat"}], "groupCount": 1, "limit": 20, "offset": 0}
      }
      """.data(using: .utf8)!

    let response = try JSONDecoder().decode(OmiAppsV2Response.self, from: json)

    XCTAssertEqual(response.groups.first?.data.first?.id, "app1")
    XCTAssertEqual(response.groups.first?.data.first?.ratingAvg, 4.5)
  }
}
