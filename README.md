<div align="center">
  <img src="./logo.png" alt="health-agent" width="420" />

  # health-agent

  **🧭 Turn parsed health records into ranked next steps 🧭**
</div>

health-agent is a local, file-based workflow for turning parsed health records into ranked next steps. It connects runtime profiles, labs, exams, health-log entries, medications, supplements, lifestyle notes, genetics, and project Codex skills into one longitudinal planning loop.

The canonical interface is the `what-next-report` skill through the agent. The Python CLI exists as deterministic support for rescans, evidence packets, cached SNP lookups, and draft daily plans.

## Install

```bash
git clone https://github.com/tsilva/health-agent.git
cd health-agent
python3 -m pip install -e ".[dev]"
```

Create a runtime profile outside the repo:

```bash
mkdir -p ~/.config/health-agent/profiles
cp profiles/template.yaml.example ~/.config/health-agent/profiles/myname.yaml
```

Edit `~/.config/health-agent/profiles/myname.yaml` so it points at the parser outputs and optional source files for that profile.

Then invoke the agent from this repo with a prompt like:

```text
Use the what-next-report skill for profile myname and write the refreshed next-steps report.
```

Reports are written under `.output/<profile_slug>/`.

## Commands

```bash
pytest                                      # run tests
health-agent plan --profile myname          # refresh state and render the action plan
health-agent evidence-packet --profile myname
health-agent daily-plan --profile myname --date 2026-04-29
health-agent selfdecode-genotypes --profile myname --rsids rs429358 rs7412
```

Deprecated aliases such as `health-agent intake`, `health-agent review`, and `health-agent outcome-update` still route to `plan` for compatibility.

## Notes

- Requires Python 3.11 or newer.
- Runtime profiles live in `~/.config/health-agent/profiles/`; repo-local `profiles/*.yaml` are development references only.
- Optional API keys belong in `~/.config/health-agent/.env`; `.env.example` documents the supported `NCBI_API_KEY`.
- Profile-linked labs, exams, health-log, genetics, and lifestyle files are read-only source inputs.
- Derived state lives under `.state/profiles/<profile_slug>/`; user-facing reports live under `.output/<profile_slug>/`.
- The primary data sources are `labs-parser`, `medical-exams-parser`, `health-log-parser`, optional raw 23andMe data, optional SelfDecode genotype lookups, and optional lifestyle Markdown files.
- SelfDecode JWTs are transient credentials. The cache stores genotype results only, in `.state/profiles/<profile_slug>/selfdecode-genotypes.json`.
- Project skills live under `.codex/skills/`: `what-next-report`, `root-cause-analysis`, `profile-question-report`, and `medication-history-report`.

## Architecture

![health-agent architecture diagram](./architecture.png)

## License

[MIT](LICENSE)
