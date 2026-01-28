# Update API Docs

Update API reference documentation.

## Purpose

Update API reference documentation when endpoints change or new endpoints are added.

## API Documentation Location

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

- **Developer API**: `docs/doc/developer/api/` - [View online](https://docs.omi.me/doc/developer/api/)
- **API Reference**: `docs/api-reference/` - [View online](https://docs.omi.me/api-reference/)
- **OpenAPI Schema**: `docs/api-reference/openapi.json`

## Updating Endpoint Documentation

### Adding New Endpoint

1. **Update developer docs** (source of truth)
   - Add detailed docs in `docs/doc/developer/api/`
   - Include examples and use cases
   - Follow MDX format

2. **Update endpoint files** (source of truth)
   - Create or update endpoint file in `docs/api-reference/endpoint/`
   - Include method, path, parameters, response

3. **Update OpenAPI schema**
   - Update `docs/api-reference/openapi.json` if needed

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
- API Overview: `docs/doc/developer/api/overview.mdx` - [View online](https://docs.omi.me/doc/developer/api/overview)
- API Endpoints: `docs/api-reference/` - [View online](https://docs.omi.me/api-reference/)

## Related Cursor Resources

### Rules
- `.cursor/rules/documentation-standards.mdc` - Documentation standards
- `.cursor/rules/backend-api-patterns.mdc` - API patterns

### Skills
- `.cursor/skills/omi-api-integration/` - API integration patterns

### Subagents
- `.cursor/agents/backend-api-developer/` - Can help with API documentation

### Commands
- `/docs` - Generate documentation
- `/validate-docs` - Validate documentation
