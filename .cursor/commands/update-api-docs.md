# Update API Docs

Update API reference documentation.

## Purpose

Update API reference documentation when endpoints change or new endpoints are added.

## API Documentation Location

- **Developer API**: `docs/doc/developer/api/`
- **API Reference**: `docs/api-reference/`
- **Internal Reference**: `.cursor/API_REFERENCE.md`

## Updating Endpoint Documentation

### Adding New Endpoint

1. **Update API reference**
   - Add endpoint to `.cursor/API_REFERENCE.md`
   - Include method, path, parameters, response

2. **Update developer docs**
   - Add detailed docs in `docs/doc/developer/api/`
   - Include examples and use cases

3. **Update endpoint files**
   - Create or update endpoint file in `docs/api-reference/endpoint/`

### Endpoint Documentation Format

```mdx
## Endpoint Name

#### `GET /v1/resource`

Get resource description.

**Query Parameters**:
- `limit` (int): Number of results (default: 25)
- `offset` (int): Pagination offset

**Returns**: List of resource objects

**Example**:
```bash
curl -H "Authorization: Bearer token" \
  https://api.omi.me/v1/resource?limit=10
```
```

## Documentation Standards

- Use MDX format
- Include code examples
- Document all parameters
- Show response formats
- Include error cases

## Related Documentation

- Documentation Standards: `.cursor/rules/documentation-standards.mdc`
- API Reference: `.cursor/API_REFERENCE.md`
