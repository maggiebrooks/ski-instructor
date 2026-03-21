# GitHub: private repo, safety, and first push

This project can hold **uploaded sensor data** and **session IDs**. Treat the remote as **private** unless you intentionally open-source a scrubbed snapshot.

## 1. What must stay out of Git

Already ignored via [`.gitignore`](../.gitignore):

- `sessions/raw/`, `sessions/processed/`, `sessions/plots/` — uploads and reports  
- `data/ski.db` and `*.db` — SQLite with turns/sessions  
- `.env`, `.env.local`, `.env.*` — Redis URLs, API keys, Render secrets  
- `logs/` — may leak paths and errors  
- `venv/`, `frontend/node_modules/`  

**Before every commit**, skim `git status` and `git diff --staged` so no ZIP/CSV/JSON from a real day lands in the repo.

## 2. Create a private repository on GitHub

1. GitHub → **New repository**  
2. Name: e.g. `ski-ai`  
3. Visibility: **Private**  
4. Do **not** add README / .gitignore / license from the wizard if you already have files locally (avoids merge noise).

## 3. SSH (recommended) vs HTTPS

### SSH (recommended)

1. [Generate a key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent) (ed25519):  
   `ssh-keygen -t ed25519 -C "your_email@example.com"`  
2. Add the **public** key (`*.pub`) in GitHub → **Settings → SSH and GPG keys → New SSH key**.  
3. Test: `ssh -T git@github.com`

Use remote URL: `git@github.com:YOUR_USER/ski-ai.git`

### HTTPS + credential helper

Use a [Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token) (classic) with **repo** scope instead of your password when Git prompts.

## 4. Initialize Git and push (from project root)

```bash
cd /path/to/ski-ai

git init
git branch -M main
git add .
git status   # verify no sessions/, no .env, no *.db
git commit -m "Initial commit: ski-ai backend + frontend"

git remote add origin git@github.com:YOUR_USER/ski-ai.git
git push -u origin main
```

If GitHub already created a `README` on the remote:

```bash
git pull origin main --rebase --allow-unrelated-histories
git push -u origin main
```

## 5. Privacy & permissions on GitHub

| Setting | Suggestion |
|--------|------------|
| **Repo visibility** | **Private** until you explicitly want public. |
| **Collaborators** | **Settings → Collaborators** — invite only who needs access; use **Read** vs **Write** deliberately. |
| **Branch protection** (optional) | **Settings → Rules → Rulesets** — require PR reviews on `main` for teams. |
| **Dependabot / Code scanning** | Enable under **Security** for supply-chain and secret scanning (helps catch leaked keys). |

Do **not** store production secrets in the repo. For Render or CI, use **GitHub Actions secrets** or the host’s **environment variables** only.

## 6. Deploy keys (CI/CD only)

If a **server** must clone this repo, prefer a **Deploy key** (read-only) on the repo: **Settings → Deploy keys**, not your personal SSH key.

## 7. If you already leaked a secret

1. Rotate the credential (Redis URL, API key, token).  
2. Remove it from Git history ([BFG](https://rtyley.github.io/bfg-repo-cleaner/) or `git filter-repo`) or ask GitHub Support; then force-push if appropriate.  
3. Enable **secret scanning** on the org/repo.

---

**Quick verify before push**

```bash
git ls-files | grep -E '^\.env|sessions/|\.db$' && echo "STOP: fix .gitignore" || echo "OK"
```

Should print `OK` (no matches).
