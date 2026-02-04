# Validate Docs

Check documentation links and formatting.

## Purpose

Validate documentation for broken links, formatting errors, and consistency issues.

## Validation Checks

### Link Validation

1. **Check internal links**
   - Verify all `href` links work
   - Check for broken references
   - Ensure relative paths are correct

2. **Check external links**
   - Verify external URLs are accessible
   - Check for broken external references

### Formatting Validation

1. **MDX syntax**
   - Verify MDX components are used correctly
   - Check component props
   - Ensure proper nesting

2. **Code blocks**
   - Verify syntax highlighting
   - Check code examples are valid

3. **Mermaid diagrams**
   - Verify diagram syntax
   - Check for syntax errors

## Manual Checks

1. **Read through documentation**
   - Check for typos
   - Verify accuracy
   - Ensure completeness

2. **Test examples**
   - Run code examples
   - Verify commands work
   - Check API examples

3. **Check consistency**
   - Verify terminology is consistent
   - Check formatting is uniform
   - Ensure style matches

## Related Documentation

- Documentation Standards: `.cursor/rules/documentation-standards.mdc`

## Related Cursor Resources

### Rules
- `.cursor/rules/documentation-standards.mdc` - Documentation standards

### Commands
- `/docs` - Generate documentation
- `/update-api-docs` - Update API documentation
