from __future__ import annotations
import hashlib,json
from typing import Any
def canonical_json_bytes(value:Any)->bytes:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
def semantic_digest(value:Any)->str:
    return "sha256:"+hashlib.sha256(canonical_json_bytes(value)).hexdigest()
