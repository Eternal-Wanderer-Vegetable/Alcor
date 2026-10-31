"""Validate planning assets only; does not exercise a service or a model."""

import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    for name in ("request", "response"):
        schema = read_json(ROOT / f"schemas/decision-{name}.schema.json")
        Draft202012Validator.check_schema(schema)
        example = read_json(ROOT / f"examples/decision-{name}.json")
        Draft202012Validator(schema).validate(example)

    request = read_json(ROOT / "examples/decision-request.json")
    response = read_json(ROOT / "examples/decision-response.json")
    canonical = json.dumps(
        request["context"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    assert request["context_digest"] == digest, "request context digest mismatch"
    assert response["context_digest"] == digest, "response context digest mismatch"
    assert response["request_id"] == request["request_id"], "request binding mismatch"

    features = read_json(ROOT / "feature_list.json")["features"]
    assert len({f["id"] for f in features}) == len(features), "duplicate feature ID"
    for feature in features:
        assert feature["status"] in {"documented", "planned", "blocked"}
        for dep in feature["depends_on"]:
            assert dep in {f["id"] for f in features}, f"missing dependency: {dep}"
    assert all(f["status"] != "documented" for f in features if f["id"] != "P00")

    links = 0
    for path in ROOT.rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        assert content.count("```") % 2 == 0, f"unclosed fence: {path}"
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", content):
            if re.match(r"(?:https?|mailto|codex)://", target) or target.startswith("#"):
                continue
            target = target.split("#", 1)[0].strip("<>")
            target = re.sub(r":\d+$", "", target)
            if target.startswith("/E:/"):
                target = target[1:]
            resolved = Path(target) if re.match(r"[A-Za-z]:[/\\]", target) else path.parent / target
            assert resolved.exists(), f"missing local link in {path}: {target}"
            links += 1
    print(f"PASS: 2 schemas, 2 examples, digest binding, {len(features)} work packages, {links} local links")
    print("Scope: design assets only; no service/model/host/runtime acceptance")


if __name__ == "__main__":
    main()
