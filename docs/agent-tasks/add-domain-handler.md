# Task: Add a domain action handler

```
task: Add action handler "<action_name>"
contracts_to_read:
  - AGENTS.md
  - docs/PARAMETRIC_CURSOR_RULES.md
  - Quantum-L9/Gate_SDK contracts (TransportPacket)
```

## Preconditions

- `make verify` passes
- Action name matches `^[a-z0-9][a-z0-9._-]{0,63}$`
- Action is listed in `spec.yaml` → `node.actions` and `L9_ALLOWED_ACTIONS`

## Steps

1. Implement handler in `src/<pkg>/handlers.py`:

   ```python
   from constellation_node_sdk import register_handler

   @register_handler("your.action")
   async def handle_your_action(tenant: str, payload: dict) -> dict:
       ...
       return {"status": "completed", ...}
   ```

2. Ensure `src/<pkg>/app.py` imports handlers (`from . import handlers`).
3. Update `spec.yaml` actions and `.env` / `.env.example` `L9_ALLOWED_ACTIONS`.
4. Add a unit test under `tests/`.
5. Run `make verify`.

## Never

- Introduce `PacketEnvelope` or peer URL dispatch
- Hand-edit `.github/workflows/*` — use `make sync-ci`
- Copy golden `engine/` / `chassis/` layouts
