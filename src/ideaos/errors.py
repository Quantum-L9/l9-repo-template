from __future__ import annotations
class IdeaOSError(Exception):
    """Base exception for deterministic IdeaOS runtime failures."""
class ContractValidationError(IdeaOSError):
    def __init__(self, contract: str, errors: list[str]):
        self.contract=contract; self.errors=list(errors)
        super().__init__(f"{contract} validation failed: {'; '.join(self.errors)}")
class PolicyError(IdeaOSError):
    """Raised when a machine-owned policy is missing or malformed."""
