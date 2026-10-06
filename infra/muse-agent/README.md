# Muse agent infrastructure — experimental pilot

Goal: Telegram/WhatsApp → Hermes → 9Router → bridge → a worker running as Muse.
This branch starts with the bridge. It does not claim to have connected Muse,
verified token billing, or deployed a working autonomous agent.

## Why a separate installation step is necessary

The portfolio README documents a restricted SSH deployment command. Its workflow
sends only `deploy`. That credential is not a verified general-purpose SSH shell.
Do not remove that restriction or reuse the production deployment key for root access.
The existing portfolio deployment and Nginx configuration need no changes for this stage.

## Stage 1: install a loopback-only bridge on Tencent

In Tencent's instance terminal, with an account that has sudo privileges:

```bash
git clone --branch infra/muse-agent --single-branch https://github.com/mari1172/portfolio-web.git /tmp/muse-agent-setup
cd /tmp/muse-agent-setup/infra/muse-agent
python3 -m unittest -v test_bridge.py
sudo bash install-bridge.sh
```

If the repository is private, use your existing authorized GitHub access.
Never paste GitHub or VPS credentials into chat. The local setup directory is
temporary; installed code is under /opt/muse-bridge.

The installer requires existing Python 3 and systemd. It creates a dedicated
unprivileged service user and separate random user/worker keys. Secrets stay
in /etc/muse-bridge/keys.json with restricted permissions; they are not printed.
Re-running preserves keys. It enables restart after failure and server reboot.

Checks:

```bash
systemctl is-active muse-bridge
curl --fail --silent http://127.0.0.1:8765/health
```

Expected: bridge ready, Muse connection unverified. A successful health check
means only that the bridge is alive.

## Stage 2: connect an actual Muse worker

This cannot be provisioned by the bridge installer alone. Muse must be configured
in the Muse app to execute a worker task. First verify the account supports running
code / HTTP requests on its hosted computer and repeated task execution.

Initially the bridge only listens on localhost. A Muse worker on another computer
cannot reach it. Before enabling it, set up an authenticated HTTPS endpoint or a
private network reachable from that worker. Do not expose port 8765 directly.
Do not send API credentials over plain HTTP across the internet.

Worker protocol:
1. GET /muse/pending with Bearer worker_key; leases one job for 60 seconds.
2. Read all request.messages and request.tools, including previous tool results.
3. Use Muse to produce a valid assistant message. For a tool request return
   tool_calls with id, type=function, function.name, and JSON-string arguments.
4. POST /muse/answer with {"id": "<job id>", "message": <assistant message>}.
5. Never execute the requested Hermes tools in the worker: return tool calls to
   Hermes, which executes them under its configured permissions.

The worker key is a local bridge credential, not an official Muse model API key.
A simple shell script that polls HTTP cannot itself generate Muse answers.
A repeated Muse task has to supply the model step; availability and reliability
must be verified in the user's account.

## Stage 3: prove the model path before adding services

POST /v1/chat/completions using Bearer user_key, model muse-bridge, stream=false.
Send a unique question and verify it is answered by the real Muse worker.
Then test a harmless tool call and the subsequent tool-result message.
Check Muse usage in the app before/after. No token billing is inferred from
bridge-generated API usage: this bridge omits usage because actual counts are unknown.

Only after these tests pass, add 9Router with the bridge as a custom provider and
Hermes with an explicitly compatible non-streaming transport. Verify the installed
versions' streaming settings; this pilot returns an error on stream=true.

Add Telegram first as a private pilot, with an allowed-user list. WhatsApp is
a subsequent stage. There is no Telegram credential or account linking in this branch.

## Pilot boundaries

- One concurrent completion, 180-second response deadline, 256 KiB body limit.
- Text and function tool calls only; no image/audio attachments or streaming.
- Queue is in memory. Restart loses pending jobs; clients must handle failed requests.
- 60-second worker lease may redeliver a job; answers are accepted once.
- No prompts or keys in HTTP logs.
- Hermes autonomy, tool permission restrictions and long-running worker reliability
  are not yet verified. A tool-call-capable transport is not proof Muse will use tools.
- This is a community-style bridge design, not an officially supported Muse API.

## Stop / uninstall

```bash
sudo systemctl disable --now muse-bridge
sudo rm /etc/systemd/system/muse-bridge.service
sudo systemctl daemon-reload
```

Code remains at /opt/muse-bridge and credentials at /etc/muse-bridge for recovery.
Remove those only when you no longer need them.

## Validation

The unittest suite covers real HTTP round trips with a simulated worker,
authentication separation, overload, timeouts, fake-probe prevention and function
tool-call transport. Simulated-worker tests do not verify the actual Muse account.

Community design reference reviewed:
https://github.com/Kutuyyy/Muse-on-9Router-Hermes-Agent-ai
No upstream bridge code is copied.
