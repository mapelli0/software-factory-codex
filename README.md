# Software Factory for Codex on Windows

A Windows-first port of the ZazenCodes Software Factory v2 for Claude Code. It uses a Codex skill and custom subagents to take a request through intake, specification, implementation, project checks and review. A person makes the final merge in GitHub or in local Git.

<a name="install-by-pointing-codex-at-this-repo"></a>

## Install from a Codex chat

Open any local Codex chat on Windows and paste this message. Codex handles the download and installs the factory once for your Windows account.

```text
Install Software Factory for all my Codex projects on this Windows computer.
Download the main branch of https://github.com/mapelli0/software-factory-codex
to a temporary folder, run install.py, and verify that the factory skill and
all nine agents are installed.
```

When Codex confirms the installation, open a fresh chat in one of your Git projects and type `$factory status`. It shows the selected project and the installed factory version. If the project already has an older factory, type `$factory cleanup` to preview its migration.

The global installer and current usage instructions are on the [main branch](https://github.com/mapelli0/software-factory-codex/tree/main). For prerequisites, project settings and updates, see the [installation guide](https://github.com/mapelli0/software-factory-codex/blob/main/INSTALL.md).

## Thanks and license

Thanks to [ZazenCodes](https://github.com/zazencodes) for creating and sharing [Software Factory for Claude Code v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2). This port builds on its GitHub workflow, job state machine, quality gates and dashboard.

Distributed under [GPLv3](LICENSE). The upstream author offers separate commercial licensing.
