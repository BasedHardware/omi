import { describe, expect, it } from 'vitest'
import { resolveAcpPermission, resolveExternalAcpPermission } from './toolPolicyStub'

describe('toolPolicyStub', () => {
  describe('resolveAcpPermission (Claude Code, trusted)', () => {
    it('prefers allow_always, then allow_once, then the first option', () => {
      expect(
        resolveAcpPermission({
          options: [
            { kind: 'allow_once', optionId: 'once' },
            { kind: 'allow_always', optionId: 'always' }
          ]
        }).optionId
      ).toBe('always')

      expect(
        resolveAcpPermission({
          options: [
            { kind: 'reject', optionId: 'no' },
            { kind: 'allow_once', optionId: 'once' }
          ]
        }).optionId
      ).toBe('once')

      expect(
        resolveAcpPermission({ options: [{ kind: 'custom', optionId: 'first' }] }).optionId
      ).toBe('first')
    })

    it('produces the ACP selected-outcome result shape', () => {
      const decision = resolveAcpPermission({
        requestId: 7,
        options: [{ kind: 'allow_once', optionId: 'once' }]
      })
      expect(decision.acpResult).toEqual({ outcome: { outcome: 'selected', optionId: 'once' } })
      expect(decision.auditEvent.policy).toBe('desktop_high_trust')
    })
  })

  describe('resolveExternalAcpPermission (untrusted external adapters)', () => {
    it('prefers a one-shot allow and never a permanent grant', () => {
      const decision = resolveExternalAcpPermission({
        adapterId: 'openclaw',
        options: [
          { kind: 'allow_always', optionId: 'always' },
          { kind: 'allow_once', optionId: 'once' }
        ]
      })
      expect('acpResult' in decision && decision.optionId).toBe('once')
    })

    it('falls back to a deny option over a permanent grant', () => {
      const decision = resolveExternalAcpPermission({
        adapterId: 'codex',
        options: [
          { kind: 'allow_always', optionId: 'always' },
          { kind: 'reject_once', optionId: 'no' }
        ]
      })
      expect('acpResult' in decision && decision.optionId).toBe('no')
    })

    it('rejects with ACP error -32001 when only allow_always is offered', () => {
      const decision = resolveExternalAcpPermission({
        adapterId: 'hermes',
        options: [{ kind: 'allow_always', optionId: 'always' }]
      })
      expect('acpError' in decision).toBe(true)
      if ('acpError' in decision) {
        expect(decision.acpError.code).toBe(-32001)
        expect(decision.auditEvent.type).toBe('approval.rejected')
      }
    })
  })
})
