# Local GGUF installer for Ollama

The four requested downloads are already imported. See
[INSTALLED_MODELS.md](INSTALLED_MODELS.md) for their ready-to-select tags. The
commands below are for future imports or deliberate replacements.

Requires Python 3.11 or newer and a running local Ollama server. No Python
packages, root access or remote inference services are needed. The installer
streams existing GGUF weights through Ollama's documented blob/create API.
It preserves your downloaded files and does not start services, edit systemd,
download weights, requantize files or change J.A.R.V.I.S.'s active brain.

## Quick start

```bash
cd "/home/marneilx/new project marneilx/ollama stuff"
bash install-gguf.sh --help

# Preview names without contacting Ollama:
bash install-gguf.sh --jarvis --dry-run "$HOME/Downloads"

# Import every single-file GGUF immediately inside that directory:
bash install-gguf.sh --jarvis "$HOME/Downloads"
```

You can run `python3 install_gguf.py` with the same arguments. Directory scans
are not recursive. Quote paths containing spaces. Split/sharded GGUF files are
refused; this utility supports ordinary single-file GGUF v2/v3 models.

## One file with a short name

```bash
bash install-gguf.sh --jarvis --name qwen35-2b:q4_k_m \
  "$HOME/Downloads/Qwen3.5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
```

This creates two tags sharing the weight blob:

- `qwen35-2b:q4_k_m`: the original imported base.
- `jarvis-qwen35-2b-64k:q4_k_m`: the J.A.R.V.I.S. version with 64,000 context.

For the other downloaded files, use the same command with these names:

| File | `--name` |
|---|---|
| `Qwen3.5-2B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf` | `qwen35-2b:q6_k` |
| `Qwen3.5-2B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf` | `qwen35-2b:q8_0` |
| `Qwen3-4B-2507-Instruct-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf` | `qwen3-4b-2507:q4_k_m` |

Without `--name`, names come from the full filename. `--name` accepts one file
only. Duplicate generated names are refused before any upload. Existing Ollama
tags, including different capitalization, are also refused before import; choose a different name, or deliberately
add `--replace` to replace the planned tags. Nothing deletes the original GGUF.

## Use them in J.A.R.V.I.S.

Open **Settings → Brain · local model → Refresh models**, select a `jarvis-` tag,
then **Use this model**. Installation alone does not switch the active model.

J.A.R.V.I.S. tags have a short fallback system instruction for plain `ollama run`.
The web assistant still uses Hermes' actual SOUL.md, native memory and reviewed
tools. The installer does not modify those files. A model tag does not install
Hermes, tools or persistent memory by itself.

The application requires advertised tool support and at least 64,000 context.
`metadata_ready_for_hermes` reports those metadata checks only. Import never loads
the model for inference and does not prove tool reliability, latency or available
VRAM/RAM. Use the project's `npm test -- --hardware` after selecting a model for a
real native-agent test. Large contexts can consume substantial RAM.

## Options and troubleshooting

```bash
# Plain Ollama import without a J.A.R.V.I.S. alias:
bash install-gguf.sh --name my-model:local "/path/to/model.gguf"

# Custom local server port and a new JSON report:
bash install-gguf.sh --jarvis --url http://127.0.0.1:11435 \
  --report import-report.json "/path/to/model.gguf"

# A smaller context for ordinary Ollama use (not sufficient for Hermes):
bash install-gguf.sh --jarvis --context 8192 "/path/to/model.gguf"
```

Only loopback HTTP endpoints are accepted. `OLLAMA_HOST` is respected when `--url`
is omitted; proxy environment variables are ignored. If connection fails, check
`ollama list` and your existing Ollama service. If you manage Ollama manually,
start `ollama serve` in its usual terminal. This utility never enables startup.

Ollama needs disk space for its own weight blob in addition to the downloaded
file; base/J.A.R.V.I.S. tags share that blob. Uploaded bytes are checked by SHA-256.
Both tags are built directly from the uploaded local blob, avoiding Ollama's
implicit registry pull when a named base is missing or spelled differently.
Ollama can canonicalize tag capitalization, for example `q4_k_m` to `Q4_K_M`;
the final report records the actual names returned by the installed server.
Do not import the same names concurrently in another tool: the Ollama API does
not provide an atomic create-without-overwrite operation.
The local header check is preliminary: Ollama performs the actual model-format
validation. Unsupported architectures/templates surface as errors rather than
being replaced with guessed chat templates or forced tool capabilities.

If alias creation fails, an already imported base remains installed. The report
identifies the failure; no existing models are deleted to roll back partial work.
Batch imports continue after individual model failures and return a nonzero exit
code if any failed. `--report` creates a new private JSON file and refuses to
overwrite files. Repeating an import requires new model names or `--replace`.

References: [Ollama GGUF import](https://docs.ollama.com/import),
[Create API](https://docs.ollama.com/api/create).
