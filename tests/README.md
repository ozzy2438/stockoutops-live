# Tests

The suite covers deterministic unit contracts and integration against real
PostgreSQL 16. SQLite and mocked database substitutes are not used.

M2 coverage includes execute-false controls, case/manifest contracts, canonical
missing-required-evidence measurement, genuine-case schema validation, deterministic
diff/report output, tenant isolation, idempotency and conflict handling,
mutation-controlled results, restart recovery, real-PostgreSQL same-case
concurrency, genuine-UAT intake fail-closed behaviour, and the rule that synthetic
cases cannot count toward official M2-05.

```bash
make test
```

OpenAI adapter tests inject a recording mock. Tests do not require network access,
an OpenAI credential, AWS, or any external write.
