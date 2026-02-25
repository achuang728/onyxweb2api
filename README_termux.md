# Termux Deployment

This project is an Onyx-to-OpenAI compatible proxy, following the same layout as your reference project.

## 1) Prepare Termux

```bash
pkg update -y
pkg install -y git
```

Copy this folder to Termux, then run:

```bash
bash termux_setup.sh
```

## 2) Configure `.env`

Copy `.env.example` to `.env`, then set:

- `ONYX_AUTH_COOKIE` (must include valid `fastapiusersauth`)
- `ONYX_BASE_URL` (default `https://cloud.onyx.app`)
- `PORT` (default `8896`)
- `API_KEY` (optional)

## 3) Start service

```bash
bash run.sh
```

Or custom host/port:

```bash
HOST=0.0.0.0 PORT=8896 bash run.sh
```

## 4) Verify

```bash
curl http://127.0.0.1:8896/health
```

If `API_KEY` is set:

```bash
curl -H "Authorization: Bearer <API_KEY>" http://127.0.0.1:8896/v1/models
```

Test chat completion:

```bash
curl -N http://127.0.0.1:8896/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-opus-4.6","stream":true,"messages":[{"role":"user","content":"hello"}]}'
```
