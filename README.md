# flux-collab

A2A-first, repo-first agent cooperation framework.

**The core insight:** Aider/Claude Code/Crush are single-agent chat tools. FLUX Collab is multi-agent, git-native, and coordination-free.

## How It Works

1. Agent claims a task (branch + issue)
2. Agent works on branch, commits, pushes
3. GitHub Actions runs tests automatically (free CI/CD)
4. If green, agent creates PR
5. Another agent reviews PR (verification)
6. Captain approves merge (human in loop)
7. Agent updates taskboard, claims next task

**No chat. No coordination overhead. Just commits.**

## Fleet Roles

| Role | Agent | Description |
|------|-------|-------------|
| Coordinator | Oracle1 | Assigns tasks, reviews architecture |
| Writer | JetsonClaw1 | Writes code, implements features |
| Tester | Babel | Writes tests, reviews PRs |

## Features

- **Auto-assign** tasks based on agent skills and trust scores
- **GitHub Actions workflow** generation (free CI/CD)
- **GitHub Projects v2** configuration (kanban boards)
- **Issue-driven development** (tasks as GitHub Issues)
- **PR-based verification** (writer/tester/reviewer split)
- **Trust scoring** (agents earn trust through completed tasks)

11 tests passing.

Part of the [FLUX Fleet](https://github.com/SuperInstance/oracle1-index).
