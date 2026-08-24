# EPIC-038: Setup Scripts — Install Dir Resolution, Directory Permissions, and Docker Volume User

**Status**: Done

## Goal

Make `deploy/prod/setup.sh` and `deploy/prod-local/setup.sh` resolve an explicit install directory and prepare host-side directories, ownership, and permissions so the bind-mounted `audio/`, `logs/`, and `config.yaml` are actually writable/readable by the non-root container user — instead of just `mkdir -p` with whatever ownership the invoking shell happens to have.

## Background

The `whispercrawl` image (`Dockerfile:17,22`) creates `appuser` at a fixed UID (`useradd -r -u 1000 ... appuser`) and runs the entrypoint as that user. `docker-compose.prod.yml` and `docker-compose.prod-local.yml` bind-mount host directories into the container:

```yaml
volumes:
  - ./audio:/audio
  - ./config.yaml:/config.yaml:ro
  - ./logs:/logs
```

Both `setup.sh` scripts today only do `mkdir -p audio logs` as whichever user runs the script (often root, via `rsync`/`scp` deploy + manual `bash setup.sh`, per `deploy/prod-local/DEPLOY.md`). Bind mounts use host ownership as-is — the container does not remap UIDs. If the host directories end up owned by `root` with restrictive permissions (or by a different UID than the one baked into the image), `appuser` (UID 1000) inside the container cannot write transcripts/logs, and the failure only surfaces at runtime as permission-denied errors, not at setup time.

The target production environment is RedOS 8 (per `CLAUDE.md`), a RHEL-family distro that commonly runs SELinux enforcing — a second, separate source of bind-mount permission denials independent of Unix ownership.

`ollama` and `whisper` services use named Docker volumes (`whisper_cache`, `hf_cache`, `ollama_data`), which Docker manages internally — those are not in scope here; this epic is about the bind-mounted `whispercrawl` service paths only.

---

## Scope

### Install directory resolution (both `setup.sh`)

- Resolve the install directory the same way both scripts already resolve `SCRIPT_DIR` (`cd "$(dirname "$0")" && pwd`), but promote it to a named `INSTALL_DIR` used consistently everywhere (directory creation, chown/chmod targets, printed next-steps) instead of relying on the current-working-directory side effect of `cd "$SCRIPT_DIR"`.
- Allow overriding via an optional first positional argument or `INSTALL_DIR` env var, for cases where `setup.sh` is invoked from outside the bundle directory (e.g. a wrapper/systemd `ExecStartPre`). Default remains the script's own location.
- Print the resolved `INSTALL_DIR` at the top of setup output so operators can confirm it before anything is created.

### Docker-volume user and ownership (both `setup.sh`)

- Read the container's runtime UID/GID (1000/1000, matching `Dockerfile`'s `useradd -r -u 1000 appuser`) from a single place both scripts can reference — either a shared constant in each script or a new `.env` entry (`APP_UID`/`APP_GID`, defaulting to 1000) so it stays in sync if the Dockerfile ever changes.
- If running with sufficient privilege (root/sudo): ensure a host system user/group exists at that UID/GID (create a dedicated `whispercrawl` system user via `useradd -r -u 1000 -U whispercrawl` if no user already owns that UID; reuse the existing one otherwise) and `chown -R` the `audio/` and `logs/` directories to it. `config.yaml` stays readable by that group (mounted `:ro`).
- If not running with sufficient privilege: skip user/chown steps, print a clear warning with the exact `sudo` command the operator needs to run manually, and continue (do not hard-fail setup).
- Set restrictive-but-sufficient permissions on created directories (e.g. `750`) rather than relying on the umask of whoever ran `mkdir`.

### SELinux awareness (RedOS 8 target)

- Detect SELinux enforcing mode (`getenforce` if present) and, when enforcing, either apply the `:Z` mount-label suffix to the `audio`/`logs`/`config.yaml` bind mounts in `docker-compose.prod.yml` / `docker-compose.prod-local.yml`, or `chcon` the host directories appropriately — pick one consistent approach and document it. When SELinux is not present/enforcing (e.g. dev Windows/WSL, non-RedOS Linux), this must be a no-op, not an error.

### Documentation

- `deploy/prod/DEPLOY.md` and `deploy/prod-local/DEPLOY.md`: document the new `INSTALL_DIR` override, the ownership/permission step, the sudo fallback message, and the SELinux behavior under their respective "Run setup" sections.

---

## Acceptance Criteria

- [x] Both `setup.sh` scripts resolve and print an explicit `INSTALL_DIR`, overridable via arg/env var, used for all directory and permission operations
- [x] Both scripts ensure `audio/` and `logs/` are owned by the UID/GID the container actually runs as (1000/1000), when run with sufficient privilege
- [x] Both scripts detect insufficient privilege and print an actionable manual `sudo` command instead of silently leaving directories misowned
- [x] Created directories have explicit, non-default permissions (not dependent on the caller's umask)
- [x] SELinux enforcing mode is handled via `:Z` bind-mount relabeling in both compose files; no-op when SELinux is absent/permissive — implemented as a static compose-file change rather than runtime `getenforce` detection, since Docker itself ignores the label on non-SELinux hosts, making detection logic redundant
- [x] Both scripts remain idempotent — re-running `setup.sh` after ownership/permissions are already correct makes no destructive changes and exits cleanly
- [x] `deploy/prod/DEPLOY.md` and `deploy/prod-local/DEPLOY.md` updated to describe the new behavior

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
