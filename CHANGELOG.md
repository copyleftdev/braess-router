# Changelog

## 0.1.0-alpha.4

- Add seven observed provider contract fixtures and offline gateway error-response checks.

## 0.1.0-alpha.3

- Add offline journal migration for fully completed histories, preserving budget and request IDs.
- Refuse scope migration while any attempt remains unresolved.
- Add read-only offline inspection for recovery diagnosis.

## 0.1.0-alpha.2

- Add a fresh-install user service bundle with private durable state.
- Verify installed startup, shutdown, restart and conservative uncertainty accounting.
- Declare the tested Rust toolchain requirement.

## 0.1.0-alpha.1

- Initial public packaging of the single-server semantic router.
- Bounded admission, conservative uncertainty accounting, durable call budget and journal.
- Custom route catalogs, local rate enforcement and readiness reporting.
- Synthetic regression suite and explicit release gates.
