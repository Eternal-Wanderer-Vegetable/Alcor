from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from alcor.contracts import DecisionRequest, DecisionResponse, context_digest
from tests.helpers import make_request

ROOT = Path(__file__).resolve().parents[1]


def test_request_example_matches_canonical_context_digest() -> None:
    payload = json.loads((ROOT / "examples" / "decision-request.json").read_text(encoding="utf-8"))
    request = DecisionRequest.model_validate(payload)

    assert request.context_digest == context_digest(request.context)
    assert request.context.current_message.text.startswith("帮我查一下")


def test_context_digest_rejects_modified_context() -> None:
    request = make_request()
    payload = request.model_dump(mode="json")
    payload["context"]["current_message"]["text"] = "改过的请求"

    with pytest.raises(ValidationError, match="context_digest"):
        DecisionRequest.model_validate(payload)


def test_request_rejects_unknown_fields() -> None:
    payload = make_request().model_dump(mode="json")
    payload["principal"] = "administrator"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DecisionRequest.model_validate(payload)


def test_request_deadline_does_not_coerce_numeric_strings() -> None:
    payload = make_request().model_dump(mode="json")
    payload["deadline_ms"] = "800"

    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(payload)


def test_request_rejects_cross_user_proposal() -> None:
    payload = make_request().model_dump(mode="json")
    payload["context"]["proposal"] = {
        "proposal_id": "plan-1",
        "owner_id": "another-user",
        "revision": 1,
        "content_digest": "a" * 64,
        "scope": "修改仓库模块",
        "message_ids": ["old-message"],
    }

    from alcor.contracts import DecisionContext

    with pytest.raises(ValidationError, match="proposal owner"):
        DecisionContext.model_validate(
            {
                **payload["context"],
                "current_message": payload["context"]["current_message"],
            }
        )


def test_response_example_passes_contract_validation() -> None:
    payload = json.loads((ROOT / "examples" / "decision-response.json").read_text(encoding="utf-8"))
    response = DecisionResponse.model_validate(payload)

    assert response.recommendation.action.value == "delegate"
    assert response.delegation_probability is None
    assert response.calibration_id is None


def test_response_rejects_unpaired_probability_and_calibration() -> None:
    payload = json.loads((ROOT / "examples" / "decision-response.json").read_text(encoding="utf-8"))
    payload["delegation_probability"] = 0.95

    with pytest.raises(ValidationError, match="must both be null or set"):
        DecisionResponse.model_validate(payload)


def test_response_probability_does_not_coerce_numeric_strings() -> None:
    payload = json.loads((ROOT / "examples" / "decision-response.json").read_text(encoding="utf-8"))
    payload["delegation_probability"] = "0.95"
    payload["calibration_id"] = "calibration-1"

    with pytest.raises(ValidationError):
        DecisionResponse.model_validate(payload)


def test_response_rejects_delegate_with_mismatched_mode() -> None:
    payload = json.loads((ROOT / "examples" / "decision-response.json").read_text(encoding="utf-8"))
    payload["recommendation"]["mode"] = "modify"

    with pytest.raises(ValidationError, match="must match repository_change"):
        DecisionResponse.model_validate(payload)


def test_unknown_response_must_abstain() -> None:
    payload = json.loads((ROOT / "examples" / "decision-response.json").read_text(encoding="utf-8"))
    payload["status"] = "unknown"

    with pytest.raises(ValidationError, match="unknown status requires abstain"):
        DecisionResponse.model_validate(payload)
