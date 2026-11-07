# Installed downloads

Imported and checked against the running J.A.R.V.I.S. backend on 2026-11-04.
Use **Settings → Brain · local model → Refresh models**, then select a tag below.

| J.A.R.V.I.S. tag | Quantization | Weight size | Context default |
|---|---|---|---|
| `jarvis-qwen35-2b-64k:Q4_K_M` | Q4_K_M | 1.27 GB | 64000 |
| `jarvis-qwen35-2b-64k:q6_k` | Q6_K | 1.56 GB | 64000 |
| `jarvis-qwen35-2b-64k:q8_0` | Q8_0 | 2.01 GB | 64000 |
| `jarvis-qwen3-4b-2507-64k:Q4_K_M` | Q4_K_M | 2.50 GB | 64000 |

Their base tags are `qwen35-2b:Q4_K_M`, `qwen35-2b:q6_k`, `qwen35-2b:q8_0`
and `qwen3-4b-2507:Q4_K_M`. Base/J.A.R.V.I.S. pairs share weights.

All four advertise tool support and a 262144-token architecture limit, and pass
the application's metadata checks with 64000 configured context. They have not
been benchmarked through Hermes on this hardware. These sizes are weight-file
sizes, not inference RAM or VRAM allocations. The installer did not switch the
active Gemma brain or change Hermes identity, memories or permissions.

The exact GGUF filenames and commands are in README.md. Models are already
installed; you do not need to run the import commands again. Full import reports
and checksums are private artifacts in JARVIS/.runtime, rather than committed
weights or personal runtime data.
