# watchdantic

Config-driven file watcher with shell command actions, powered by [watchfiles](https://watchfiles.helpmanual.io/) + [Pydantic](https://docs.pydantic.dev/).

**Linux only.** Watches files/directories for changes and runs shell commands when glob patterns match.

## Quick start

```bash
pip install -e .

# Generate a starter config
watchdantic init

# Validate your config
watchdantic check

# Start watching
watchdantic run
```

## Configuration

Create a `watch.toml` in your repo root:

```toml
version = 1

[engine]
repo_root = "."
debounce_ms = 300
ignore_dirs = [".git", ".venv", "__pycache__"]
ignore_globs = ["**/*.pyc"]
log_level = "INFO"

[[watch]]
name = "repo"
paths = ["."]

[[action]]
name = "run_tests"
type = "command"
cmd = ["pytest", "-x", "-q"]
timeout_s = 300

[[action]]
name = "build_docs"
type = "command"
cmd = ["bash", "-lc", "make -C docs html"]

[[rule]]
name = "test_on_py_change"
watch = "repo"
on = ["added", "modified"]
match = ["src/**/*.py", "tests/**/*.py"]
do = ["run_tests"]

[[rule]]
name = "docs_on_md_change"
watch = "repo"
on = ["added", "modified"]
match = ["docs/**/*.md"]
exclude = ["docs/_build/**"]
do = ["build_docs"]
```

## CLI

| Command | Description |
|---------|-------------|
| `watchdantic run` | Start watching (writes PID to `.watchdantic.pid`) |
| `watchdantic check` | Validate config and exit |
| `watchdantic reload` | Send SIGHUP to reload config for a running instance |
| `watchdantic init` | Generate a starter `watch.toml` |

## Config reference

### `[engine]`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `repo_root` | `str` | `"."` | Repository root (relative to config file) |
| `debounce_ms` | `int` | `300` | Debounce window in milliseconds |
| `use_default_filter` | `bool` | `true` | Use watchfiles DefaultFilter |
| `ignore_dirs` | `list[str]` | `[]` | Directories to ignore |
| `ignore_globs` | `list[str]` | `[]` | Glob patterns to ignore |
| `log_level` | `str` | `"INFO"` | DEBUG, INFO, WARNING, or ERROR |
| `max_workers` | `int` | `1` | Concurrency (1 = sequential) |

### `[[watch]]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | yes | Unique identifier |
| `paths` | `list[str]` | yes | Paths to watch (repo-relative) |
| `debounce_ms` | `int` | no | Override engine debounce |

### `[[action]]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | yes | Unique identifier |
| `type` | `str` | yes | `"command"` |
| `cmd` | `list[str]` | yes | Command argv |
| `cwd` | `str` | no | Working directory (repo-relative) |
| `env` | `dict` | no | Extra environment variables |
| `timeout_s` | `int` | no | Timeout in seconds |
| `shell` | `bool` | no | Run as shell command (default: false) |

### `[[rule]]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | yes | Unique identifier |
| `watch` | `str` | yes | References a `[[watch]].name` |
| `on` | `list[str]` | yes | Event types: `added`, `modified`, `deleted` |
| `match` | `list[str]` | yes | Glob patterns (OR logic) |
| `exclude` | `list[str]` | no | Exclude patterns (OR logic) |
| `do` | `list[str]` | yes | Action names to execute |
| `continue_on_error` | `bool` | no | Continue if action fails (default: false) |

## Action context

Shell commands receive these environment variables:

- `WATCHDANTIC_REPO_ROOT` — absolute path to repo root
- `WATCHDANTIC_RULE_NAME` — name of the matched rule
- `WATCHDANTIC_WATCH_NAME` — name of the watch that detected changes
- `WATCHDANTIC_EVENT_COUNT` — number of file events in the batch
- `WATCHDANTIC_EVENTS_JSON` — JSON array of event details

## Reloading

While `watchdantic run` is active:

```bash
# Edit watch.toml, then:
watchdantic reload
# Or manually: kill -HUP $(cat .watchdantic.pid)
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
