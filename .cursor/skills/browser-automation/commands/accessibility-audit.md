# Accessibility Audit

Use browser automation to audit web accessibility, check WCAG compliance, and identify accessibility issues.

## Usage

```
@browser Check accessibility:
- Color contrast ratios
- Semantic HTML
- ARIA labels
- Keyboard navigation
- Screen reader compatibility
```

## Audit Areas

### Color Contrast

- Check text contrast ratios
- Verify WCAG AA/AAA compliance
- Identify low-contrast elements
- Suggest color adjustments

### Semantic HTML

- Verify proper heading hierarchy
- Check form labels
- Validate button vs link usage
- Ensure proper landmarks

### ARIA Labels

- Check missing ARIA labels
- Verify ARIA attribute usage
- Validate ARIA relationships
- Ensure proper roles

### Keyboard Navigation

- Test tab order
- Verify focus indicators
- Check keyboard shortcuts
- Ensure no keyboard traps

### Screen Reader

- Test with screen reader
- Verify announcements
- Check alt text for images
- Ensure proper reading order

## Example Audit

```
@browser Audit accessibility for /dashboard:
1. Check color contrast for all text
2. Verify semantic HTML structure
3. Test keyboard navigation
4. Check ARIA labels
5. Verify screen reader compatibility
6. Generate accessibility report
```

## Best Practices

1. **Regular audits**: Run checks periodically
2. **Fix systematically**: Address issues by priority
3. **Test keyboard**: Verify keyboard-only usage
4. **Check contrast**: Ensure sufficient contrast ratios
5. **Validate ARIA**: Use ARIA appropriately

## WCAG Guidelines

- **Level A**: Basic accessibility (required)
- **Level AA**: Enhanced accessibility (recommended)
- **Level AAA**: Maximum accessibility (optional)

## Related Resources

- Skill: `.cursor/skills/browser-automation/SKILL.md`
- Agent: `.cursor/skills/browser-automation/agents/browser-automation.md`
- Rule: `.cursor/rules/agent-browser.mdc`
