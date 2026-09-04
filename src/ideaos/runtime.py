from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .commercial import CommercialEvidenceService, CommercialResearchProvider
from .contracts import schema_documents, validate
from .digests import semantic_digest
from .engine import IdeaOSEngine
from .errors import IdeaOSError
from .expansion import gate_expansion
from .lifecycle import build_decision_node_input
from .version import __version__

@dataclass(frozen=True)
class OperationSpec:
    mode:str
    input_schema:str
    output_schema:str
    provider_required:bool=False
    allowed_options:tuple[str,...]=()
    side_effect_class:str="none"
    deterministic:bool=True

_OPERATIONS=(
    OperationSpec("route","idea_classification.schema.json","route_decision.schema.json"),
    OperationSpec("evaluate","idea_decision_packet.schema.json","idea_evaluation.schema.json",allowed_options=("require_ready",)),
    OperationSpec("execution_packet","idea_decision_packet.schema.json","idea_execution_packet.schema.json",allowed_options=("decision_ref","produced_at","require_execution")),
    OperationSpec("commercial_research","commercial_evidence_request.schema.json","commercial_evidence_packet.schema.json",provider_required=True,side_effect_class="external_read",deterministic=False),
    OperationSpec("expansion_gate","expansion_packet.schema.json","expansion_gate_receipt.schema.json"),
    OperationSpec("decision_handoff","decision_handoff_request.schema.json","decision_node_input.schema.json"),
)
_OPERATION_BY_MODE={x.mode:x for x in _OPERATIONS}

@lru_cache(maxsize=1)
def _assert_operation_registry()->None:
    if len(_OPERATION_BY_MODE)!=len(_OPERATIONS): raise IdeaOSError("duplicate IdeaOS runtime operation mode")
    schemas=schema_documents(); req=schemas["ideaos_run_request.schema.json"]
    declared=set(req["properties"]["mode"]["enum"]); registered=set(_OPERATION_BY_MODE)
    if declared!=registered: raise IdeaOSError(f"IdeaOS runtime registry modes do not match request schema: declared={sorted(declared)!r} registered={sorted(registered)!r}")
    declared_options=set(req["properties"]["options"]["properties"])
    registered_options={o for op in _OPERATIONS for o in op.allowed_options}
    if declared_options!=registered_options: raise IdeaOSError("IdeaOS runtime registry options do not match request schema")
    for op in _OPERATIONS:
        for s in (op.input_schema,op.output_schema):
            if s not in schemas: raise IdeaOSError(f"runtime operation {op.mode} references unknown schema {s}")

def runtime_capabilities()->dict[str,Any]:
    _assert_operation_registry(); schemas=schema_documents()
    def dg(n:str)->str: return semantic_digest(schemas[n])
    doc={
      "schema":"ideaos.runtime-capabilities/v1","runtime_version":__version__,
      "canonical_ingress":{"library":"ideaos.IdeaOSRuntime.execute","cli":"ideaos run","request_schema":"ideaos_run_request.schema.json","request_schema_digest":dg("ideaos_run_request.schema.json"),"receipt_schema":"ideaos_run_receipt.schema.json","receipt_schema_digest":dg("ideaos_run_receipt.schema.json")},
      "operations":[{"mode":x.mode,"input_schema":x.input_schema,"input_schema_digest":dg(x.input_schema),"output_schema":x.output_schema,"output_schema_digest":dg(x.output_schema),"provider_required":x.provider_required,"allowed_options":list(x.allowed_options),"side_effect_class":x.side_effect_class,"deterministic":x.deterministic} for x in _OPERATIONS],
      "utilities":["ideaos render-business-plan","ideaos validate"],
      "handoffs":[
        {"artifact":"ExpandedIdeaDossierPacket","schema_name":"expansion_packet.schema.json","schema_digest":dg("expansion_packet.schema.json"),"consumer_role":"expansion_gate"},
        {"artifact":"ExpansionGateReceipt","schema_name":"expansion_gate_receipt.schema.json","schema_digest":dg("expansion_gate_receipt.schema.json"),"consumer_role":"decision_handoff"},
        {"artifact":"IdeaExpanderDecisionNodeInput","schema_name":"decision_node_input.schema.json","schema_digest":dg("decision_node_input.schema.json"),"consumer_role":"idea-expander-decision-node"},
        {"artifact":"IdeaExecutionPacket","schema_name":"idea_execution_packet.schema.json","schema_digest":dg("idea_execution_packet.schema.json"),"consumer_role":"external execution topology compiler"},
        {"artifact":"CommercialEvidencePacket","schema_name":"commercial_evidence_packet.schema.json","schema_digest":dg("commercial_evidence_packet.schema.json"),"consumer_role":"IdeaOS semantic evaluation and human projections"},
      ],
    }
    validate(doc,"runtime_capabilities.schema.json"); return doc

class IdeaOSRuntime:
    def __init__(self,*,engine:IdeaOSEngine|None=None,commercial_provider:CommercialResearchProvider|None=None):
        self.engine=engine or IdeaOSEngine(); self.commercial_provider=commercial_provider
    def execute(self,request:dict[str,Any])->dict[str,Any]:
        _assert_operation_registry(); validate(request,"ideaos_run_request.schema.json")
        mode=request["mode"]; spec=_OPERATION_BY_MODE.get(mode)
        if spec is None: raise IdeaOSError(f"unsupported IdeaOS runtime mode: {mode}")
        artifact=request["inputs"]["artifact"]; options=dict(request.get("options") or {})
        unexpected=sorted(set(options)-set(spec.allowed_options))
        if unexpected: raise IdeaOSError(f"runtime mode {mode} does not accept options: {', '.join(unexpected)}")
        requested=request["output_contract"]["schema_name"]
        if requested!=spec.output_schema: raise IdeaOSError(f"runtime mode {mode} output contract must be {spec.output_schema}, got {requested}")
        validate(artifact,spec.input_schema); output=self._execute_operation(spec,artifact,options); validate(output,spec.output_schema)
        status="succeeded"; stop=None
        if mode=="evaluate" and options.get("require_ready") and output["computed_promotion"]["state"]!="execution_ready": status="blocked"; stop="PROMOTION_NOT_READY"
        if mode=="execution_packet" and options.get("require_execution") and output["status"]=="no_execution_required": status="blocked"; stop="NO_EXECUTION_REQUIRED"
        if mode=="expansion_gate" and output["status"]!="READY": status="blocked"; stop="EXPANSION_NOT_READY"
        receipt={"schema":"ideaos.run-receipt/v1","request_id":request["request_id"],"trace_id":request["trace_id"],"mode":mode,"objective":request["objective"],"status":status,**({"stop_reason":stop} if stop else {}),"input_digest":semantic_digest(artifact),"output_digest":semantic_digest(output),"output_schema":spec.output_schema,"output":output,"validation":{"profile":"strict","input_schema":spec.input_schema,"output_schema":spec.output_schema},"constraints":list(request["constraints"]),"context_refs":list(request["context_refs"]),"authority_rules":list(request["authority_rules"]),"provenance":{"producer":"ideaos.runtime","runtime_version":__version__,"request_digest":semantic_digest(request)}}
        validate(receipt,"ideaos_run_receipt.schema.json"); return receipt
    def _execute_operation(self,spec:OperationSpec,artifact:dict[str,Any],options:dict[str,Any])->dict[str,Any]:
        if spec.mode=="route": return self.engine.route(artifact)
        if spec.mode=="evaluate": return self.engine.evaluate_packet(artifact)
        if spec.mode=="execution_packet": return self.engine.build_execution_packet(artifact,decision_ref=options.get("decision_ref"),produced_at=options.get("produced_at"))
        if spec.mode=="commercial_research":
            if self.commercial_provider is None: raise IdeaOSError("commercial_research requires a CommercialResearchProvider")
            return CommercialEvidenceService(self.commercial_provider).run(artifact)
        if spec.mode=="expansion_gate": return gate_expansion(artifact)
        if spec.mode=="decision_handoff":
            return build_decision_node_input(
                artifact["expansion_packet"],
                artifact["expansion_gate_receipt"],
                artifact["decision_context"],
            )
        raise IdeaOSError(f"unsupported IdeaOS runtime mode: {spec.mode}")
