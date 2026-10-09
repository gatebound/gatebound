# ADR-0037: Pasted text carries no language signal, and a gate with no session language falls back to the spec

Status: accepted 2026-10-05 (owner, after the Windows rounds of 2026-10-05).
Amends ADR-0026 (language from the spec) and the prompt gate's language
rules in ARCHITECTURE §3 and §8.

## Context

Two ways the output language went wrong were seen on 2026-10-05.

**A paste switched a Korean session to English.** The owner pasted
PowerShell and Codex terminal output, mostly English, as whole messages.
Each turn the prompt gate set `output_lang=en`. When the same kind of paste
ended with the owner's own `확인해줘`, the session stayed `ko` (ADR-0031's
Korean-predicate rule). Claude Code stores such a message with the pasted
part wrapped in `<pasted_content id="…">` … `</pasted_content id="…">`
(seen in the session transcript); the words outside the wrapper are the
user's, the words inside are someone else's — terminal output, a document,
a log. The prompt gate already ignores host-generated text that is not the
user's (`HARNESS_MARKERS`, ADR-0031); a paste is the same kind of text.

**Gate messages came out in English in a Korean project.** In the Codex
test project the write gate denied in English. The write, Bash and
PowerShell gates read the language through `write.session_lang`, which
returns the session ledger's `output_lang` and so `en` whenever there is no
ledger. The prompt gate writes the ledger only in a project with a state
directory (0.11.2), while rule (a) of the write gate now acts as soon as
`spec/` holds a gatekit spec file (ADR-0036). Between the first spec file
and `/gatekit:setup` or `/gatekit:gate` there is no ledger, so every deny
of the interview → tasks stretch was English. ADR-0026 had solved the same
gap for the prompt gate with `lang.from_spec`, and `lang.spec_lang` (the
`lang --spec` command) already applies its precedence.

## Decision

1. **Pasted blocks are not the user's words.** `prompt.language_signal`
   removes every `<pasted_content …>` … `</pasted_content …>` block (an
   unclosed one to the end of the text) before the language is detected.
   What remains is judged as before: harness messages give no signal,
   a slash command's `<command-args>`, ADR-0031's Korean predicate. A
   prompt that is only a paste carries no signal, so the stored language
   stays and `lang_source` is not set to `prompt` by it.
2. **A gate with no prompt-set language uses the spec.** `write.session_lang`
   applies ADR-0026's precedence to this session's ledger: its
   `output_lang` when a prompt set it (`lang_source == "prompt"`), else
   `lang.from_spec(root)`, else the ledger's `output_lang`, else `en`.
   Every caller (write, Bash, PowerShell, spawn and stop messages) follows.
   Loading the ledger still writes nothing.

## Consequences

- A Korean session stays Korean across terminal pastes; a user who writes
  in English around a Korean paste still gets English.
- In a Korean project with no state directory yet, gate denials are Korean
  once `spec/01-prd.md` (or `00-discovery.md`) is.
- Unverified: that the hook's `prompt` field carries the same
  `<pasted_content>` wrapper as the transcript. If a host sends the paste
  unwrapped, decision 1 changes nothing and the old behaviour remains;
  neither case can turn a language the wrong way.
- Tests: paste-only prompts in a Korean session, a paste with Korean or
  English words around it, an unclosed wrapper, a paste as the first
  prompt; write and Bash denials in a project with a Korean spec and no
  state directory, a prompt-set English language winning over a Korean
  spec, and no spec giving English.
