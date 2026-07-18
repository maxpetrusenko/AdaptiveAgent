# Adaptive Agent Frontend

Next.js 16 operator and proof interface for AdaptiveAgent.

## Run locally

Start the FastAPI backend first, then:

```bash
pnpm install --frozen-lockfile
PROOF_PROXY_MODE=local \
OPERATOR_PROXY_MODE=local \
pnpm dev
```

Open <http://localhost:3737/proof>.

The proof page uses the same-origin `/api/proof/*` server route. That route
forwards only the knowledge and research proof contracts to
`BACKEND_INTERNAL_URL` and adds `OPERATOR_API_TOKEN` on the server. Never expose
that token through a `NEXT_PUBLIC_*` variable.

The local proxy modes reject non-loopback and cross-origin requests. Do not
enable them on an internet-facing deployment; use authenticated server sessions
or keep protected mutations backend-only.

## Gates

```bash
pnpm test
pnpm lint
pnpm build
pnpm e2e
```

See the [project README](../README.md) for architecture, backend setup, native
Rust gates, benchmark evidence, and deployment.
