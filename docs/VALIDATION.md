# Validation record

Authoring date: 4 November 2026.

- Independent test runner: bundled CPython 3.12.14, Windows. Runtime target remains Python 3.14 on supported v16 bench.
- 85 independent tests pass: 27 calculation, 14 legacy tax-row validation, 15 mixed-line VAT, 12 payload/acknowledgement, 10 dispatch-state and 7 Fawtara provider-data mapping cases.
- Adapter tests use invoice-shaped objects and import stubs for Frappe. They execute the real validation, payload mapping and dispatch functions. Dispatch tests mock persistence, provider and queue dependencies; they do not verify a real database or network.
- Additional package integrity checks cover Python syntax, JSON assets, controller names and hooks, and JavaScript syntax.
- No running Frappe, ERPNext, MariaDB, Redis, bench, or browser session was available. Installation, permissions, generated UI, ledger entries and transactional period locking remain acceptance checks on the target site.

The core app has no built-in network provider or payment action. A configured trusted adapter performs external transmission in background jobs. Worker transactions explicitly commit Sending before an external side effect and persist acknowledgements afterward. Source document transactions do not commit manually. Account configuration requires Accounts Manager; provider/credential configuration requires System Manager. No real taxpayer credential, provider sandbox or Authority receipt was available.
