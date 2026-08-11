# Tests

The suite covers deterministic unit contracts and integration against real
PostgreSQL 16. SQLite and mocked database substitutes are not used.

```bash
make test
```

OpenAI adapter tests inject a recording mock. Tests do not require network access,
an OpenAI credential, AWS, or any external write.
