# Own test: each row model's field names against EvMigEvelyn/entities/*.create.json, the files `uip df entities create` takes
# (generated from docs/mapping.md section 8 by scripts/entities.py).
#
# Why: Data Fabric drops a field it does not know silently (owner's review, 2026-10-19), so a misnamed field in a model would
# reach the tenant, be dropped, and the value would be lost without an error. FakeEntities refuses an unknown field, which the
# tenant does not (see the testing.py docstring), so this comparison is what guards the names.
# The files carry no system fields (no Id, CreateTime, ...): every field in them is one the model writes, so nothing is excluded.
# `Id` is Data Fabric's own and is not in the files; FakeEntities adds it on a read (testing.py) and the models do not have it.
import json
from pathlib import Path

import pytest

from evmig_nss.core.analytics import ALERT_ENTITY_NAME, HIT_ENTITY_NAME, AlertAnalytics, HitAnalytics
from evmig_nss.core.transaction import ENTITY_NAME as TRANSACTION_ENTITY_NAME
from evmig_nss.core.transaction import Transaction

ENTITY_DIR = Path(__file__).resolve().parents[2] / "EvMigEvelyn" / "entities"


def field_names(entity_name: str) -> list[str]:
    document = json.loads((ENTITY_DIR / f"{entity_name}.create.json").read_text(encoding="utf-8"))
    assert document["displayName"] == entity_name
    return [field["name"] for field in document["fields"]]


@pytest.mark.parametrize(
    ("model", "entity_name"),
    [(Transaction, TRANSACTION_ENTITY_NAME), (AlertAnalytics, ALERT_ENTITY_NAME), (HitAnalytics, HIT_ENTITY_NAME)],
    ids=["Transaction", "AlertAnalytics", "HitAnalytics"],
)
def test_a_row_models_fields_are_the_fields_of_its_entity_file(model, entity_name):
    names = field_names(entity_name)
    assert len(names) == len(set(names)), "a field is declared twice in the entity file"
    assert set(model.model_fields) - set(names) == set(), f"{model.__name__} writes fields the entity does not have (Data Fabric would drop them)"
    assert set(names) - set(model.model_fields) == set(), f"the entity has fields {model.__name__} never writes"


def test_there_are_exactly_the_three_entity_files():
    assert sorted(path.name for path in ENTITY_DIR.glob("*.create.json")) == [
        f"{name}.create.json" for name in sorted([TRANSACTION_ENTITY_NAME, ALERT_ENTITY_NAME, HIT_ENTITY_NAME])
    ]
