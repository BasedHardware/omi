import Foundation

#if canImport(FoundationModels)
  import FoundationModels
#endif

/// JSON Schema → `DynamicGenerationSchema` subset used by AFM guided generation.
///
/// Supported (exactly the shapes `LocalInferenceJSONSchema` construction sites emit):
/// - root `type: object`
/// - `properties` maps of nested nodes
/// - `required` string arrays (property must already be declared)
/// - `type: string | integer | boolean | object | array`
/// - `items` as a single schema object (arrays of objects or primitives)
/// - nested objects / arrays (the W1 draft: sections, events, action_items)
/// - optional `description` (passed through, never required)
///
/// Call sites covered: `LocalSummaryDraft.jsonSchema` (nested object/array/string/
/// integer/boolean + required) and the probe schemas in LocalInference tests
/// (`{"type":"object"}` and a required `title` string). Anything else — `enum`,
/// `anyOf`/`oneOf`/`allOf`, `$ref`, `number`, `null`, union `type` arrays,
/// tuple `items`, `additionalProperties`, unknown keywords — throws
/// `LocalInferenceError.capabilityUnavailable` with the keyword/path. No silent
/// degradation.
enum AFMJSONSchemaBridge {
  private static let allowedKeys: Set<String> = ["type", "properties", "required", "items", "description"]
  private static let objectKeys: Set<String> = ["type", "properties", "required", "description"]
  private static let arrayKeys: Set<String> = ["type", "items", "description"]
  private static let scalarKeys: Set<String> = ["type", "description"]
  /// Root is depth 0. LocalSummaryDraft nests object → array → object (depth 2).
  static let maximumNestingDepth = 8

  static func parse(_ schema: LocalInferenceJSONSchema) throws -> AFMJSONSchemaNode {
    let raw: Any
    do {
      raw = try JSONSerialization.jsonObject(with: schema.json)
    } catch {
      throw LocalInferenceError.capabilityUnavailable("malformed_json_schema")
    }
    guard let object = raw as? [String: Any] else {
      throw LocalInferenceError.capabilityUnavailable("schema_must_be_object")
    }
    let node = try parseNode(object, name: schema.name, path: schema.name, depth: 0)
    guard case .object = node else {
      throw LocalInferenceError.capabilityUnavailable("root_must_be_object")
    }
    return node
  }

  #if canImport(FoundationModels)
    @available(macOS 26.0, *)
    static func generationSchema(from schema: LocalInferenceJSONSchema) throws -> GenerationSchema {
      try generationSchema(root: parse(schema))
    }

    @available(macOS 26.0, *)
    static func generationSchema(root: AFMJSONSchemaNode) throws -> GenerationSchema {
      do {
        return try GenerationSchema(root: makeDynamicSchema(root), dependencies: [])
      } catch let error as LocalInferenceError {
        throw error
      } catch {
        throw LocalInferenceError.capabilityUnavailable("generation_schema")
      }
    }

    /// Builds Apple's schema without running a session, so unit tests stay hermetic.
    @available(macOS 26.0, *)
    static func validateGenerationSchema(_ schema: LocalInferenceJSONSchema) throws {
      _ = try generationSchema(from: schema)
    }

    @available(macOS 26.0, *)
    static func makeDynamicSchema(_ node: AFMJSONSchemaNode) -> DynamicGenerationSchema {
      switch node {
      case .string:
        return DynamicGenerationSchema(type: String.self)
      case .integer:
        return DynamicGenerationSchema(type: Int.self)
      case .boolean:
        return DynamicGenerationSchema(type: Bool.self)
      case .array(let items):
        return DynamicGenerationSchema(arrayOf: makeDynamicSchema(items))
      case .object(let name, let properties, let description):
        let props = properties.map { property in
          DynamicGenerationSchema.Property(
            name: property.name,
            description: property.description,
            schema: makeDynamicSchema(property.node),
            isOptional: property.isOptional
          )
        }
        return DynamicGenerationSchema(name: name, description: description, properties: props)
      }
    }
  #endif

  private static func parseNode(_ raw: [String: Any], name: String, path: String, depth: Int) throws
    -> AFMJSONSchemaNode
  {
    guard depth <= maximumNestingDepth else {
      throw LocalInferenceError.capabilityUnavailable("nesting_too_deep:\(path)")
    }
    try rejectUnknownKeys(raw, allowed: allowedKeys, path: path)
    guard let typeRaw = raw["type"] else {
      throw LocalInferenceError.capabilityUnavailable("missing_type:\(path)")
    }
    guard let type = typeRaw as? String else {
      throw LocalInferenceError.capabilityUnavailable("unsupported_type at \(path)")
    }
    switch type {
    case "string":
      try rejectUnknownKeys(raw, allowed: scalarKeys, path: path)
      _ = try stringDescription(raw, path: path)
      return .string
    case "integer":
      try rejectUnknownKeys(raw, allowed: scalarKeys, path: path)
      _ = try stringDescription(raw, path: path)
      return .integer
    case "boolean":
      try rejectUnknownKeys(raw, allowed: scalarKeys, path: path)
      _ = try stringDescription(raw, path: path)
      return .boolean
    case "object":
      try rejectUnknownKeys(raw, allowed: objectKeys, path: path)
      return try parseObject(raw, name: name, path: path, depth: depth)
    case "array":
      try rejectUnknownKeys(raw, allowed: arrayKeys, path: path)
      _ = try stringDescription(raw, path: path)
      return try parseArray(raw, name: name, path: path, depth: depth)
    default:
      throw LocalInferenceError.capabilityUnavailable("unsupported_type:\(type) at \(path)")
    }
  }

  private static func parseObject(_ raw: [String: Any], name: String, path: String, depth: Int) throws
    -> AFMJSONSchemaNode
  {
    let propertiesRaw = raw["properties"] ?? [String: Any]()
    guard let propertiesObject = propertiesRaw as? [String: Any] else {
      throw LocalInferenceError.capabilityUnavailable("properties_must_be_object:\(path)")
    }
    let required: [String]
    if let requiredRaw = raw["required"] {
      guard let names = requiredRaw as? [String] else {
        throw LocalInferenceError.capabilityUnavailable("required_must_be_string_array:\(path)")
      }
      required = names
    } else {
      required = []
    }
    let requiredSet = Set(required)
    var properties: [AFMJSONSchemaNode.ObjectProperty] = []
    properties.reserveCapacity(propertiesObject.count)
    for key in propertiesObject.keys.sorted() {
      guard let childRaw = propertiesObject[key] as? [String: Any] else {
        throw LocalInferenceError.capabilityUnavailable("property_must_be_object:\(path).\(key)")
      }
      let childName = "\(path)_\(key)"
      let child = try parseNode(childRaw, name: childName, path: "\(path).\(key)", depth: depth + 1)
      properties.append(
        AFMJSONSchemaNode.ObjectProperty(
          name: key,
          node: child,
          isOptional: !requiredSet.contains(key),
          description: try stringDescription(childRaw, path: "\(path).\(key)")
        ))
    }
    for name in required where propertiesObject[name] == nil {
      throw LocalInferenceError.capabilityUnavailable("required_unknown_property:\(name) at \(path)")
    }
    return .object(name: name, properties: properties, description: try stringDescription(raw, path: path))
  }

  private static func parseArray(_ raw: [String: Any], name: String, path: String, depth: Int) throws
    -> AFMJSONSchemaNode
  {
    guard let itemsRaw = raw["items"] else {
      throw LocalInferenceError.capabilityUnavailable("array_missing_items:\(path)")
    }
    guard let itemsObject = itemsRaw as? [String: Any] else {
      throw LocalInferenceError.capabilityUnavailable("items_must_be_object:\(path)")
    }
    let item = try parseNode(itemsObject, name: "\(name)_item", path: "\(path).items", depth: depth + 1)
    return .array(items: item)
  }

  private static func stringDescription(_ raw: [String: Any], path: String) throws -> String? {
    guard let value = raw["description"] else { return nil }
    guard let text = value as? String else {
      throw LocalInferenceError.capabilityUnavailable("description_must_be_string:\(path)")
    }
    return text
  }

  private static func rejectUnknownKeys(_ raw: [String: Any], allowed: Set<String>, path: String) throws {
    for key in raw.keys where !allowed.contains(key) {
      throw LocalInferenceError.capabilityUnavailable("unsupported_keyword:\(key) at \(path)")
    }
  }
}

indirect enum AFMJSONSchemaNode: Sendable, Equatable {
  case string
  case integer
  case boolean
  case object(name: String, properties: [ObjectProperty], description: String?)
  case array(items: AFMJSONSchemaNode)

  struct ObjectProperty: Sendable, Equatable {
    var name: String
    var node: AFMJSONSchemaNode
    var isOptional: Bool
    var description: String?
  }
}
