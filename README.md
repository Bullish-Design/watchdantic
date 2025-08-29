# README — Watchdantic

## Overview

**Watchdantic** connects filesystem events to **Pydantic** models with minimal ceremony. Register a function with a decorator that names a model and a glob pattern; when files matching that pattern change, Watchdantic parses the file **into typed models** and calls your function. It auto-detects `.jsonl` vs `.json`, debounces bursts, filters temp files, writes atomically, and—optionally—emits structured JSONL logs for easy ingestion.

## Key features

* **Decorator-driven handlers**: `@w.triggers_on(MyModel, "*.jsonl")` → `def handle(models, path) -> None`.
* **Typed I/O**: files are parsed into `List[MyModel]`; `.jsonl` (JsonLines) & `.json` (single JSON array/object) supported out of the box.
* **Robust runtime**: per-file **debounce**, temp/hidden file filtering, configurable recursion, maximum file size guards.
* **Atomic writes**: `write_models()` safely writes and avoids self-trigger loops.
* **Structured JSONL logging (opt-in)** with level filtering and stdout/file targets.

## Core concepts

* **`Watchdantic`** – Runtime that owns the registry, debounce manager, and observer. Handlers are registered by decorator; `start(path)` attaches Watchdog. (Handlers must be `(List[Model], Path) -> None`.)
* **`HandlerInfo` + `HandlerRegistry`** – Immutable records of each handler (pattern, debounce, excludes, explicit format). Registry filters by path and exclusions.
* **`FormatDetector`** – Chooses `JsonLines` for `.jsonl`(/`.jsonlines`) and `JsonSingle` for `.json`; you can register custom formats.
* **`DebounceManager`** – Coalesces rapid events and manages temporary file exclusions.
* **`WatchdanticLogger`** – Emits one JSON object per line to stdout or a file when enabled.

## Quick start

```python
from pathlib import Path
from typing import List
from pydantic import BaseModel
from watchdantic import Watchdantic, WatchdanticConfig

class Event(BaseModel):
    id: int
    message: str

w = Watchdantic(
    WatchdanticConfig(
        default_debounce=0.5,
        enable_logging=False,   # set True for JSONL logs
    )
)

@w.triggers_on(Event, "logs/*.jsonl", debounce=0.5)
def handle_events(models: List/Event, file_path: Path) -> None:
    for m in models:
        print(f"[{file_path.name}] {m.id}: {m.message}")

w.start(".")
# ... your app continues running; later ...
# w.stop()
```

### What that does

* Watches `logs/*.jsonl`; on changes, parses each non-empty line as JSON → `Event`. Invalid JSON lines are skipped; Pydantic validation errors bubble to your handler context. Debounce collapses bursts and only calls your handler after the quiet period.

## Working with JSON formats

### JSON Lines (`.jsonl`)

Each line is a JSON object; blank lines are ignored; bad JSON lines are skipped (warning logged). Writing produces compact lines and always ends with a trailing newline.

```python
# logs/events.jsonl
{"id": 1, "message": "start"}
{"id": 2, "message": "running"}
```

### Single JSON (`.json`)

Top-level **object** → `[obj]`; top-level **array** → unchanged. On write, Watchdantic always serializes as an array:

```json
[
  {"id": 1, "message": "start"},
  {"id": 2, "message": "running"}
]
```

(Out of the box, extensions map to handlers; you can add your own formats if needed.)

## Writing models (atomic + no self-trigger)

Use `write_models(models, path)` to serialize via the detected format and atomically replace the file. The target file is **temporarily excluded** from processing for \~`default_debounce` seconds so your write does not retrigger your own handlers.

```python
from typing import List
from watchdantic import Watchdantic

def export_snapshot(w: Watchdantic, items: List[Event], path: str | Path) -> None:
    w.write_models(items, path)  # auto-selects .jsonl vs .json; atomic write
```

## Exclusions, recursion, and size limits

* **Exclude patterns**: At decorator time, pass `exclude_patterns=["**/tmp/*", "*_partial.jsonl"]` to suppress a handler for paths matching those globs.
* **Recursion**: Per-handler `recursive=True` and the runtime enables recursion if **any** handler needs it.
* **File size**: Files larger than `max_file_size_mb` are skipped (warned) before read.

## Structured logging (optional)

Enable by passing `WatchdanticConfig(enable_logging=True, log_level="INFO", log_file=Path("watchdantic.log"))`. Logs are JSONL—one object per line—so they’re pipeline-friendly:

```json
{"timestamp":"2025-01-15T10:00:00Z","level":"INFO","message":"File processed successfully","file_path":"...","handler_name":"handle_events","model_count":5}
```

## Error handling

* **`ConfigurationError`** – wrong handler signature, conflicting registration, invalid options.
* **`FileFormatError`** – format/codec problems (bad JSON, unsupported structure, serialization failure).
* **Pydantic `ValidationError`** – schema issues (these bubble; you can choose to continue on error via handler config).

## API sketch

```python
class WatchdanticConfig(BaseModel):
    default_debounce: float = 1.0
    continue_on_error: bool = False
    recursive: bool = True
    max_file_size_mb: int = 100
    enable_logging: bool = False
    log_level: str = "INFO"
    log_file: Optional[Path] = None
```

```python
class Watchdantic(BaseModel):
    def triggers_on(
        self, model_class, pattern, *,
        debounce: float | None = None,
        continue_on_error: bool | None = None,
        recursive: bool = True,
        exclude_patterns: list[str] | None = None,
        format_handler: FileFormatBase | None = None,
    ) -> Callable[[Callable[[List[BaseModel], Path], None]], Any]: ...

    def write_models(self, models: list[BaseModel], file_path: str | Path) -> None: ...
    def start(self, path: str | Path) -> None: ...
    def stop(self) -> None: ...
```

## Example use cases

1. **Streaming logs → metrics**

   * `@w.triggers_on(LogEntry, "service/*.jsonl", debounce=0.25)` → update Prometheus counters upon each parsed batch.

2. **Snapshot ingestion**

   * `@w.triggers_on(UserRecord, "snapshots/*.json")` to rebuild a cache when nightly dumps land as a single JSON array.

3. **Self-writing pipelines without loops**

   * Read `.jsonl`, transform to a summary `Summary(model=…)`, then `write_models([...], "out/summary.json")`—atomic and self-excluded.

4. **Multiple handlers on the same path**

   * One handler computes stats; another forwards to a message bus. The runtime uses the **max** debounce across them to coalesce churn.

5. **Custom format**

   * Register `.csv` with your own `FileFormatBase` impl and pass `format_handler=MyCSV()` to a specific handler if you want to override detection.

---

## Why it’s robust by default

* Filters temp/hidden files (e.g. `.tmp`, `.goutputstream*`), which avoids processing partial writes.
* Coalesces rapid event bursts with a simple, per-file debounce strategy.
* Atomic writes with fsync + rename prevent torn reads; plus a timed exclusion prevents recursion.
* Optional structured logs make production behavior observable.

---

### Notes mapped to code (for maintainers)

* Handler signature & validation rules, plus atomic write implementation. &#x20;
* Debounce scheduling uses the **longest** matching handler delay for a path.&#x20;
* Temp/hidden filtering used by the dispatching handler.&#x20;
* Format detection & inference; built-ins for `.jsonl/.json`.&#x20;
* Structured JSONL logging surface & payload shape.&#x20;


