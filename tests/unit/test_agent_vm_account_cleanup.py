import pytest
import sys
from services.users.agent_vm_account_cleanup import _migration_reconcile_lease_active


class TestMigrationReconcileLeaseActive:
    def test_reconcile_lease_oversized_expiry_is_ambiguous_not_overflow(self):
        # Positive oversized int (400-digit)
        vm = {'reconcile': {'lease': {'expiresAt': int('9' * 400)}}}
        with pytest.raises(RuntimeError, match='Agent VM migration reconcile lease is ambiguous'):
            _migration_reconcile_lease_active(vm, [{}], now=1000.0)

        # Negative oversized int (400-digit)
        vm = {'reconcile': {'lease': {'expiresAt': -int('9' * 400)}}}
        with pytest.raises(RuntimeError, match='Agent VM migration reconcile lease is ambiguous'):
            _migration_reconcile_lease_active(vm, [{}], now=1000.0)

        # Oversized decimal string
        vm = {'reconcile': {'lease': {'expiresAt': '1e500'}}}
        with pytest.raises(RuntimeError, match='Agent VM migration reconcile lease is ambiguous'):
            _migration_reconcile_lease_active(vm, [{}], now=1000.0)

    def test_reconcile_lease_normal_expiry_still_evaluates(self):
        # Valid integer
        vm = {'reconcile': {'lease': {'expiresAt': 2000}}}
        assert _migration_reconcile_lease_active(vm, [{}], now=1000.0) is True

        # Valid float
        vm = {'reconcile': {'lease': {'expiresAt': 2000.0}}}
        assert _migration_reconcile_lease_active(vm, [{}], now=1000.0) is True

        # Valid string
        vm = {'reconcile': {'lease': {'expiresAt': '2000.0'}}}
        assert _migration_reconcile_lease_active(vm, [{}], now=1000.0) is True

        # Expired lease
        vm = {'reconcile': {'lease': {'expiresAt': 500}}}
        assert _migration_reconcile_lease_active(vm, [{}], now=1000.0) is False