from typing import Any, Dict, List

import storage
from models import AccountabilityRuleIn, AccountabilityRuleUpdate


def create_accountability_rule(rule: AccountabilityRuleIn) -> Dict[str, Any]:
    return storage.create_rule(rule.omi_user_id, rule.model_dump(mode="json"))


def list_accountability_rules(omi_user_id: str) -> List[Dict[str, Any]]:
    return storage.list_rules(omi_user_id)


def update_accountability_rule(rule_id: int, update: AccountabilityRuleUpdate) -> Dict[str, Any]:
    return storage.update_rule(rule_id, update.model_dump(exclude_unset=True, mode="json"))


def delete_accountability_rule(rule_id: int) -> Dict[str, Any]:
    return {"deleted": storage.delete_rule(rule_id)}
