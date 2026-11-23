# Rule: Security, Configuration, and Advisory Locks

## 1. Path Traversal & Safety
- All file paths must pass through `security.safe_path()`.
- Never bypass path validation.
- No absolute paths, no `..`, no access to `.git/` or `.meta/`.
- Project names: lowercase letters, numbers, `.`, `_`, `-` only.

## 2. Secrets & `.env`
- Never commit `.env`. It is gitignored.
- Only commit `.env.example`.
- Run `./setup.sh` to initialize secrets and data volume configuration.

## 3. Advisory Locks Collision Awareness
- `pg_advisory_xact_lock(hashtext(...))` uses a 32-bit hash.
- With >65,000 files across projects, hash collisions can occur.
- For hyper-scale setups, migrate to 64-bit advisory locks `(bigint, bigint)`.
