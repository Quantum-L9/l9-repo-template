# When to use which Quantum-L9 template

Three templates live **side by side**. Pick by product role:

| Need | Template |
|------|----------|
| Constellation **node** (Gate-routed worker, handlers, transport) | [L9-Node-Template](https://github.com/Quantum-L9/L9-Node-Template) |
| `constellation_*` **dependency package** birth | [Constellation.PackageTemplate](https://github.com/Quantum-L9/Constellation.PackageTemplate) |
| Quantum-L9 Python **outside** Constellation (runtimes, side projects, experiments, misc services) | **This template** (`l9-repo-template`) |

## Use this museum when

- You want org CI sync, Core Make facade, hygiene, and a thin Python (+ optional FastAPI) start
- The repo is **not** a Constellation node and **not** a `constellation_*` birth dep

## Do not use this museum when

- You need `create_node_app`, Gate handlers, or TransportPacket product law → Node-Template
- You are minting a `constellation_*` library via plays → PackageTemplate
