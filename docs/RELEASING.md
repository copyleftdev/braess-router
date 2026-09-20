# Releasing

1. Merge a reviewed version bump and changelog entry with all CI checks passing.
2. Create a `v<package-version>` tag on that main-branch commit.
3. Push the tag to trigger Release. It repeats validation and verifies packaging
   before requesting the `crates-io` environment and publishing.

The workflow validates that the tag matches Cargo.toml, belongs to main, and passes
all checks. Concurrent releases are serialized. crates.io prevents overwriting an
existing version. Keep the initial package marked alpha until v1 acceptance closes.

Configure `CARGO_REGISTRY_TOKEN` only in the `crates-io` GitHub environment, with
publish permission scoped to braess-router where supported. Never use it in pull
request CI. Configure environment reviewers and main-branch protections in GitHub.

After the first publication, prefer crates.io trusted publishing: register this
repository, `release.yml`, and the `crates-io` environment in the crate settings,
then replace the token secret step with the official crates-io-auth-action and
grant id-token: write only to the publish job. Delete the long-lived secret after
verifying that transition. Trusted-publisher registration is external configuration;
a workflow file alone does not create it.

The source package uses an explicit include list. Local artifacts, credentials,
CI scripts and historical experiment archives are excluded from the crate.
