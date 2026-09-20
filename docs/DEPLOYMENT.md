# Single-server deployment

The supported deployment is a private Linux user service with operator-run loopback
handlers. Python 3.11+ prepares the installation; the service runs the Rust binary
directly. The host needs systemd with a working user manager. Foreground operation
is also supported. Keep the service account and its deployment directory trusted.

## Build and install

Build from a reviewed commit with passing CI:

```sh
cargo build --locked --release --bins
python3 scripts/install_service.py \
  --config config/gateway.live.example.json \
  --binary-dir target/release \
  --destination "$HOME/braess-router"
```

If Cargo uses a custom target directory, pass its release directory instead.
Configure handler URLs, limits and the rubric before installing. Input rubric paths
resolve from the working directory. The installer copies the binaries and rubric,
writes absolute paths, initializes durable state, and records binary SHA-256 hashes.
It makes no provider calls and neither registers nor starts a service.

The destination must not exist; its parent must exist. The installer refuses input
configurations that already name durable state. Do not use it to upgrade an existing
installation or reset an exhausted budget. Failed installations remain for inspection;
the installer never silently overwrites or removes them.

The new directory is mode 0700. Configuration, journal and budget files are private
to the account. No credentials are copied. For live mode, create
`$HOME/braess-router/config/provider.env` privately (mode 0600) through your secret
manager, containing `TYPESAFE_API_KEY=...`. It uses systemd environment-file syntax,
not shell script syntax. Do not commit that file. Mock mode requires no key.

## Start and stop

```sh
systemctl --user link "$HOME/braess-router/braess-router.service"
systemctl --user daemon-reload
systemctl --user start braess-router.service
systemctl --user status braess-router.service
curl --fail http://127.0.0.1:8080/ready
journalctl --user -u braess-router.service
systemctl --user stop braess-router.service
```

The service is not automatically enabled at login. If wanted, enable it explicitly
with `systemctl --user enable braess-router.service`. Running without a login session
requires host-specific user-manager/lingering policy; configure that separately.

The unit restarts on failure with a five-second delay and a three-starts-per-minute
limit. It sends SIGTERM on stop and allows 30 seconds before forced termination.
A forced stop may preserve unresolved journal entries that consume admission after
restart. It does not establish upstream cancellation or machine power-loss safety.
Follow the [operations and recovery constraints](OPERATIONS.md) before resuming work.

To unregister, stop the service first, then run `systemctl --user disable
braess-router.service` and `systemctl --user daemon-reload`. State files remain.

For foreground operation from any working directory:

```sh
"$HOME/braess-router/bin/braess-router" --config "$HOME/braess-router/config/gateway.json"
```

Supply live credentials in the process environment for foreground operation;
`provider.env` is loaded only by the service manager.

## Verification

CI checks service syntax and exercises installed binaries using synthetic local
fixtures: fresh install, refusal to overwrite state, private permissions, duplicate
owner rejection, in-flight shutdown, restart and retained uncertainty after SIGKILL.
Artifacts include state observations, fixture events, command results and hashes.

For the same checks through an actual user systemd manager:

```sh
python3 scripts/deployment_e2e.py artifacts/systemd \
  --binary target/release/braess-router --systemd
```

This registers a uniquely named temporary service and removes its registration when
finished. It leaves evidence files in the requested new directory. It makes no live
provider calls. Tests cover paths containing spaces, percent and dollar characters.
They do not prove every filesystem, supervisor, host policy or production workload.
