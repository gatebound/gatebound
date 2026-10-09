# Uninstalling gatebound

Removing the plugin and cleaning up a project are separate steps. Removing the
plugin stops every gate everywhere; it does not touch any project's files.

## 1. Remove the plugin

### Claude Code (CLI)

```
/plugin uninstall gatebound@gatebound
/plugin marketplace remove gatebound
```

Restart Claude Code afterwards: a running session keeps the hooks it loaded.
In the Claude desktop app, remove gatebound from the same plugin screen you
installed it from, then start a new session.

### Codex (CLI and app)

```
codex plugin remove gatebound@gatebound
codex plugin marketplace remove gatebound
```

Start a new Codex session afterwards. If a project still has the older
generated layer (`gatebound install --host codex`), clean it up as in step 2;
that layer runs from the project, not from the plugin.

## 2. What stays in your projects

Nothing below is deleted by uninstalling. Decide per project.

| Path | What it is | Usually |
|---|---|---|
| `spec/` | your PRD, screens, architecture, tasks, completion contract, progress | **keep** — it is your project's documentation, committed like any other doc |
| `.gatebound/` | config, approvals, attempts, contract, baseline; `runs/` and `jobs/` are local logs | remove when you no longer want gatebound in this project; `config.json`, `approvals.json` and `attempts.json` may be committed team state — check with your team first |
| `AGENTS.md` block between `<!-- gatebound:begin … -->` and `<!-- gatebound:end -->` | Codex instructions from the generated layer | remove the block; keep the rest of the file |
| `.codex/hooks.json` | Codex hook registrations from the generated layer | delete it if gatebound wrote it and you added nothing; otherwise remove only the entries that run gatebound |
| `.agents/skills/gatebound-*` | Codex skills from the generated layer | delete these directories |

A safe order — remove the plugin (step 1) first, then run these yourself in a
terminal. While gatebound's hooks are active, gatebound refuses an agent's command
that deletes or rewrites its state (everything under `.gatebound/` but
`config.json` and `eval/`, ADR-0027), so `rm -rf .gatebound` from a Claude or
Codex session is denied:

```bash
git status                       # start from a clean tree, so the removal is one reviewable diff
git rm -r --cached .gatebound      # if .gatebound/ files were committed
rm -rf .gatebound
rm -rf .agents/skills/gatebound-*  # only if you used the generated Codex layer
# edit AGENTS.md and .codex/hooks.json by hand as in the table above
git status                       # check that only gatebound's files are going
git commit -m "Remove gatebound state"
```

Leave `spec/` in place unless you are sure nothing else refers to it.

## Turning gatebound off without uninstalling

Every gate stands down in a project that has neither a `.gatebound/` nor a
`.gatekit/` directory: no check runs and no state is created there. So with
the plugin still installed, deleting a project's state directory (both, in a
project that has both) turns gatebound off for that project alone, and other
projects keep their gates. Delete it yourself in a
terminal: the same refusal applies to an agent session while the hooks are
active.

## 한국어 요약

1. **플러그인 제거.** Claude Code: `/plugin uninstall gatebound@gatebound`,
   `/plugin marketplace remove gatebound` 후 재시작. Codex: `codex plugin remove gatebound@gatebound`,
   `codex plugin marketplace remove gatebound` 후 새 세션.
2. **프로젝트에 남는 것.** 제거해도 프로젝트 파일은 지워지지 않습니다. `spec/`은 프로젝트 문서이므로
   보통 남깁니다. `.gatebound/`는 더 쓰지 않을 때 지웁니다(커밋돼 있었다면 `git rm -r --cached .gatebound`).
   플러그인을 먼저 제거한 뒤 터미널에서 직접 지우세요. 훅이 켜져 있는 동안 gatebound는 에이전트가
   자기 상태(`.gatebound/` 아래 `config.json`·`eval/` 외 전부, ADR-0027)를 지우거나 고치는 명령을 거부합니다.
   생성된 Codex 레이어를 썼다면 `AGENTS.md`의 `gatebound:begin`~`gatebound:end` 블록,
   `.codex/hooks.json`의 gatebound 항목, `.agents/skills/gatebound-*`를 지웁니다.
3. **제거하지 않고 끄기.** `.gatebound/`도 `.gatekit/`도 없는 프로젝트에서는 모든 게이트가 물러납니다. 플러그인을
   둔 채 그 프로젝트의 상태 디렉터리(둘 다 있으면 둘 다)만 지우면 그 프로젝트에서만 꺼집니다(터미널에서 직접 지웁니다).
