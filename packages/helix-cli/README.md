# helix-cli

The `helix` command — the operator surface for Helix. Git-like verbs over the engine:

```
helix init            # create your local strand + signing identity
helix connect cursor  # wire Helix into an agent over MCP
helix add / search / forget
helix export / import / merge / log   # the portable .dna strand
helix doctor          # diagnose setup & connections
```

Thin front-end over [`helix-core`](../helix-core); no business logic here. Pre-alpha —
commands are wired and documented; bodies land per [`ROADMAP.md`](../../ROADMAP.md).
