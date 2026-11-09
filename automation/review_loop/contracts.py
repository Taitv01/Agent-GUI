"""Strict model contracts: prose containing PASS is never accepted as a verdict."""
import json


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING}
WORKER_SCHEMA = obj({
    "status": {"type": "string", "enum": ["COMPLETED", "BLOCKED"]},
    "summary": STRING, "changed_files": STRINGS, "tests": STRINGS,
    "evidence_paths": STRINGS, "blockers": STRINGS,
})
REVIEW_SCHEMA = obj({
    "verdict": {"type": "string", "enum": ["PASS", "REVISE", "BLOCKED"]},
    "summary": STRING,
    "checks": {"type": "array", "items": obj({"id": STRING, "passed": {"type": "boolean"}, "evidence": STRING})},
    "findings": STRINGS, "required_changes": STRINGS, "evidence_paths": STRINGS,
})


def validate(value, schema, path="result"):
    kind = schema["type"]
    expected = {"object": dict, "array": list, "string": str, "boolean": bool}[kind]
    if type(value) is not expected:
        raise ValueError(f"{path}: cần {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: giá trị không hợp lệ")
    if kind == "object":
        if set(value) != set(schema["properties"]):
            raise ValueError(f"{path}: thiếu/thừa trường JSON")
        for k, v in value.items():
            validate(v, schema["properties"][k], f"{path}.{k}")
    if kind == "array":
        for i, v in enumerate(value):
            validate(v, schema["items"], f"{path}[{i}]")


def _strip_json_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return s


def unwrap(text, schema):
    raw = _strip_json_fence(text)
    value = json.loads(raw)  # No regex extraction / guessing from free text.
    if isinstance(value, dict) and (value.get("is_error") or value.get("status") in {"ERROR", "FAILED"}):
        detail = value.get("error") or value.get("result") or ""
        raise ValueError(f"CLI trả lỗi, không phải kết quả agent: {detail}".rstrip(": "))
    if isinstance(value, dict) and value.get("structured_output") is not None:
        value = value["structured_output"]
    elif isinstance(value, dict) and "response" in value:
        value = value["response"]
    elif isinstance(value, dict) and "result" in value and "verdict" not in value:
        value = value["result"]
    if isinstance(value, str):
        value = json.loads(_strip_json_fence(value))
    validate(value, schema)
    if not value["summary"].strip():
        raise ValueError("Thiếu tóm tắt kết quả")
    return value


def validate_review(value, criteria):
    validate(value, REVIEW_SCHEMA)
    checks = value["checks"]
    ids = [c["id"] for c in checks]
    if len(ids) != len(set(ids)) or set(ids) != {c["id"] for c in criteria}:
        raise ValueError("Reviewer chưa kiểm đủ đúng bộ tiêu chí ban đầu")
    if any(not c["evidence"].strip() for c in checks):
        raise ValueError("Reviewer thiếu bằng chứng cho tiêu chí")
    if value["verdict"] == "PASS":
        if any(not c["passed"] for c in checks) or value["findings"] or value["required_changes"]:
            raise ValueError("PASS mâu thuẫn với tiêu chí/lỗi còn mở")
    if value["verdict"] == "REVISE" and not value["required_changes"]:
        raise ValueError("REVISE phải có yêu cầu sửa cụ thể")
