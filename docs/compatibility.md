# Compatibility evidence (2026-10-10)

| Combination | Release/source evidence | Automated mock/MCP evidence | Live evidence |
|---|---|---|---|
| AC25–30 Windows + Tapir 1.7.0 | Matching six `.apx` release assets; native command schemas and implementation inspected at the 1.7.0 tag | AC30-shaped HTTP fixtures; version range guarded | **Not run**: installation, load, native edits, undo, Teamwork and Codex GUI |
| AC25–29 Windows individually | Assets verified; same pinned catalogue with runtime per-command availability | Range accepted in policy; not every version's native response modeled | **Not run** |
| AC30 Windows individually | Release asset exists although inspected README's manual table ends at 29; official JSON docs identify 30.0.0.3000 | Primary fixture version 30; real HTTP mock and stdio workflow | **Not run** |
| AC outside 25–30 | No reviewed contract coverage | Mutating/catalogue execution refused; product discovery still identifies reachable hosts | **Not supported** |
| AC25–30 without Tapir | Official JSON reads remain a distinct backend | Official selection read works; Tapir-dependent workflows fail clearly | **Not run** |
| Tapir different from 1.7.0 | Definitions pinned to released 1.7.0, not development main | Tapir dispatch rejects mismatch; official reads still possible | **Not supported for Tapir dispatch** |
| Python 3.12–3.14 | Package and pinned MCP SDK declare these versions; Windows platform marker dependencies locked | 44 tests passed on Python 3.12.13 and 3.14.0; 3.14 artifact suite used the installed wheel | Native Windows Python process not run |
| Codex local stdio | Official configuration documented; absolute Windows path example | SDK initialization, tool listing/calls and TOML syntax tested | Windows Codex UI registration not run |
| Other MCP local clients | Standard SDK stdio server | Tested with official SDK client only | Individual third-party clients not run |
| macOS native Archicad | Tapir Mac assets exist, but Windows is the product target | Development/mocks on macOS only | No native Archicad workflow |

Native command introduction versions in the Tapir catalogue are not a complete host-major compatibility matrix. Runtime `API.IsAddOnCommandAvailable` and exact installed Tapir version checks are required. Official commands do not expose that same availability API: reviewed input contracts are validated locally and host errors are preserved on execution. No compatibility claim is inferred solely from a README, successful package build, open TCP port or HTTP success envelope.
