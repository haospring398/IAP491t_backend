"""Read the same policy and response schema used by the Next proxy."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
def load_configuration(root=ROOT):
    """Broken administrator-owned configuration must not prevent liveness."""
    documents = []
    for name in ("transport-policy.json", "analysis.schema.json", "transport-policy.schema.json"):
        try:
            document = json.loads((root / "web/contracts" / name).read_text(encoding="utf-8"))
            documents.append(document if isinstance(document, dict) else {})
        except (OSError, ValueError, UnicodeError):
            documents.append({})
    return tuple(documents)


POLICY, SCHEMA, POLICY_SCHEMA = load_configuration()
# Correlation syntax remains usable when the configuration is broken. No inference
# limits are substituted: no worker is started until all shared documents validate.
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
UUID = re.compile(UUID_PATTERN)
UNAVAILABLE_ERROR = {"http": 503, "retryAfterSeconds": 5, "message": "Analysis is unavailable. Try again later."}
RUN_ID = "e7dcdcc3551e46fc93582836f4a74976"


def validate_policy():
    from jsonschema import Draft7Validator
    if not POLICY_SCHEMA or not SCHEMA or not POLICY:
        raise ValueError("Missing shared configuration")
    Draft7Validator.check_schema(POLICY_SCHEMA)
    Draft7Validator.check_schema(SCHEMA)
    Draft7Validator(POLICY_SCHEMA).validate(POLICY)
    definitions = SCHEMA["definitions"]
    if definitions["RequestId"]["pattern"] != UUID_PATTERN:
        raise ValueError("Incompatible request identity schema")
    validator = Draft7Validator(SCHEMA)
    for name in ("RequestId", "ErrorCode", "AnalysisSuccess", "AnalysisError", "AnalysisStatus"):
        if name not in definitions:
            raise ValueError("Incomplete response schema")
    request_id = "672f0ea9-e237-45cd-8c08-8710f89b8258"
    for label in ("legit", "spam_or_phishing", "phishing"):
        validator.validate({"analysis_status": "completed", "label": label})
    validator.validate({"request_id": request_id, "phase": "unknown"})
    for code, entry in POLICY["errors"].items():
        validator.validate({"request_id": request_id, "error": {"code": code, "message": entry["message"]}})
    d, limits = POLICY["deadlines"], POLICY["limits"]
    if not (limits["fileBytes"] < limits["multipartBytes"] and
            d["backendMs"] < d["proxyMs"] < d["browserMs"] < d["handlerSeconds"] * 1000 and
            d["backendReserveMs"] >= d["clockSkewMs"] + d["terminateMs"] + d["killReapMs"]):
        raise ValueError("Inconsistent transport bounds")
    inputs = {"INVALID_REQUEST", "EMAIL_TOO_LARGE", "EMPTY_EMAIL", "INVALID_EMAIL", "INSUFFICIENT_CONTENT", "RESOURCE_LIMIT"}
    for code, entry in POLICY["errors"].items():
        if (entry["retryAfterSeconds"] == 0) != (code in inputs):
            raise ValueError("Inconsistent recovery policy")


class Rejection(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)
