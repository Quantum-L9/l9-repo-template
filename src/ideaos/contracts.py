from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import json
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from .errors import ContractValidationError, PolicyError
_SCHEMA_DIR=Path(__file__).parent/'resources'/'schemas'
@lru_cache(maxsize=1)
def _docs()->dict[str,Any]:
    out={}; ids={}
    for p in sorted(_SCHEMA_DIR.glob('*.json')):
        raw=json.loads(p.read_text())
        sid=raw.get('$id')
        if not sid: raise PolicyError(f'schema lacks $id: {p.name}')
        if sid in ids: raise PolicyError(f'duplicate schema id {sid}')
        Draft202012Validator.check_schema(raw); out[p.name]=raw; ids[sid]=p.name
    return out
def schema_documents()->dict[str,Any]:
    copied:dict[str,Any]=json.loads(json.dumps(_docs())); return copied
@lru_cache(maxsize=1)
def registry()->Registry:
    r=Registry()
    for s in _docs().values(): r=r.with_resource(s['$id'],Resource.from_contents(s))
    return r
def validate(instance:Any,name:str)->None:
    if name not in _docs(): raise PolicyError(f'unknown schema: {name}')
    v=Draft202012Validator(_docs()[name],registry=registry(),format_checker=FormatChecker())
    errs=[]
    for e in sorted(v.iter_errors(instance),key=lambda e:list(e.absolute_path)):
        path='.'.join(str(x) for x in e.absolute_path) or '<root>'; errs.append(f'{path}: {e.message}')
    if errs: raise ContractValidationError(name,errs)
