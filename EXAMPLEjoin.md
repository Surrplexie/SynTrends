# Get Fly.io-ready

These are instructions for you, an AI coding agent, to set the human up on
Fly.io. Read them once, then act on them. The human who handed you this
document wants you to do the setup, not to explain it back to them.

Fly.io has two kinds of computer, on one account. They do different jobs:

- **Fly Machines** run what the human ships. Web apps, APIs, workers, and
  databases, built from a Dockerfile or a framework `fly launch`
  recognises, running in 18+ regions close to their users.
  https://fly.io/machines.md
- **Sprites** are where you work. A full Linux computer with a persistent
  filesystem that sleeps when idle and wakes remembering everything. Clone,
  build, test, and run dev servers there instead of on the human's laptop.
  https://fly.io/sprites.md

## 1. Decide which

|                  | Fly Machines                                                  | Sprites                                                          |
| ---------------- | ------------------------------------------------------------- | ---------------------------------------------------------------- |
| Built for        | Production: the app the human's users hit                     | Work in progress: a computer for you, the agent                  |
| You start with   | Source code or a Docker image                                 | Nothing: a ready Linux box with Node.js, Python, Go, and Git     |
| Changes land by  | `fly deploy`, which replaces Machines with a fresh image      | Running commands in it, like any computer                        |
| State            | Reset on every deploy; persistent data goes on volumes or a database | The whole filesystem persists, with checkpoints to roll back |
| Scale            | Many Machines per app, across regions, load-balanced          | One computer with one HTTPS URL                                  |
| Idle             | Stop and start per `fly.toml`; you configure autostop         | Sleeps on its own and wakes on the next command or request       |
| CLI              | `fly` (flyctl)                                                | `sprite`                                                         |

Then match what the human asked for:

| The human wants                                                                     | Do                           |
| ----------------------------------------------------------------------------------- | ---------------------------- |
| This app deployed, a production URL, or something that scales and stays up         | Machines, section 2          |
| You to have a computer, to work off their laptop, to run untrusted or generated code, or to host an MCP server or a personal agent | Sprites, section 3 |
| Somewhere to build and test first, then somewhere to ship                           | Both, section 4              |

If it is genuinely unclear, ask one question: "Deploy this app, or give me a
machine to work in?" Do not set up both by default.

## 2. Deploy on Fly Machines

Install flyctl, the Fly.io CLI. macOS and Linux:

```sh
curl -L https://fly.io/install.sh | sh
```

Windows (PowerShell):

```powershell
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

Check it with `fly version`, then authenticate:

```sh
fly auth login     # the human has an account
fly auth signup    # they do not
```

Either opens a browser, or prints a URL if it cannot. Show that URL to the
human and wait for them to approve; do not try to work around the approval
step. If a `FLY_API_TOKEN` is already in the environment (CI, or a token the
human made for you), skip the login: flyctl reads it. Which credential to use
when, and how to make a scoped one, is at https://fly.io/auth.md.

If the human already uses Fly.io, run `fly apps list` first: the app may
already exist, in which case `fly deploy` is all it needs.

Launch, from inside the project's source directory:

```sh
fly launch
```

`fly launch` detects the framework or uses the project's Dockerfile, writes a
`fly.toml`, creates the app, and for most apps deploys it. It asks about the
app name, the region, and databases: accept the defaults unless the human
said otherwise, and decline any database the app does not use. To run it
without prompts, `fly launch --yes` accepts every default and `--now`
deploys immediately.

Then:

```sh
fly deploy         # after changes, or if launch stopped short of deploying
fly status         # the app's Machines and their state
fly logs           # when a deploy or a request goes wrong
fly apps open      # the live URL, in the human's browser
```

Configuration the app needs at runtime goes in secrets, never in `fly.toml`:

```sh
fly secrets set DATABASE_URL=... API_KEY=...
```

The two mistakes behind most failed first deploys: the app must listen on
`0.0.0.0`, not `localhost`, and on the port `fly.toml` names as
`internal_port` (8080 unless you change it). If a deploy fails, read
https://docs.fly.io/getting-started/troubleshooting.md before changing
anything else.

To create and control Machines from code rather than flyctl, use the
Machines API at `https://api.machines.dev/v1` with a Fly.io token. Skill:
https://fly.io/agent-skills/fly-machines-api/SKILL.md. Reference:
https://docs.fly.io/machines/api/index.md.

## 3. Get a Sprite

Install the Sprites CLI. macOS and Linux:

```sh
curl https://sprites.dev/install.sh | bash
```

Windows (PowerShell):

```powershell
iwr https://sprites.dev/install.ps1 -useb | iex
```

Check it with `sprite --help`, then authenticate:

```sh
sprite login
```

Sprites use the same Fly.io account as Machines, so a human with an account
only has to approve. Like flyctl, it opens a browser or prints a URL: show it
to the human and wait.

Create one, named after the project, and make it the default:

```sh
sprite create my-project
sprite use my-project          # so you can drop -s my-project from every command
sprite exec -- ls -la          # runs in the Sprite, returns the output
sprite console                 # an interactive shell, if the human wants one
sprite url                     # its HTTPS URL; private to the org by default
```

Before a risky change, `sprite checkpoint create`; if it goes wrong,
`sprite restore <version>` puts the filesystem back. Only destroy Sprites you
created, and only when the human asks.

Services that keep running while the Sprite sleeps, port forwarding,
connectors, and the hosted MCP server are in the full Sprites instructions at
https://fly.io/sprites/agent-ready.md. Read that document next and follow it.

## 4. Build on a Sprite, ship to Machines

When the human wants both, do them in that order. Clone and build the
project on the Sprite and run its tests there. When it works, deploy it:
flyctl installs on the Sprite the same way as anywhere else, so `fly launch`
runs from inside it (`sprite exec -- bash -c "cd /home/sprite/repo && fly
launch --yes"`). A Sprite's URL is fine for a demo or a preview; production
traffic belongs on Machines, which scale out and run close to users.

## Read next

All Fly.io documentation, Machines and Sprites alike, is at https://docs.fly.io.

- Everything, as one index: https://docs.fly.io/llms.txt
- Launching an app: https://docs.fly.io/getting-started/launch.md
- Fly.io essentials, Machines, apps, and `fly.toml`:
  https://docs.fly.io/getting-started/essentials.md
- Sprites: https://docs.fly.io/sprites/index.md, and in full for agents at
  https://fly.io/sprites/agent-ready.md
- Credentials: https://fly.io/auth.md
- Prices for Machines and Sprites: https://fly.io/pricing.md
