"""
ZeroDrive — Multi-Repo OTA Safety Analyzer
===========================================
Reads zerodrive.config.json, pulls diffs from every repo in an OTA release,
combines them into one context, sends it to Groq AI (llama-3.3-70b-versatile),
and posts a unified risk report as a PR comment.

Exits non-zero if risk meets or exceeds the configured threshold → blocks the pipeline.
"""

import os
import sys
import json
import requests

# Force UTF-8 encoding for standard output to prevent crash on Windows terminals when printing emojis
if sys.stdout.encoding != 'utf-8':
    try:
        import sys
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback for Python versions or environments where reconfigure is not supported
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

def load_config(path="zerodrive.config.json"):
    """Load the multi-repo config file."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Config file not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config: {e}")
        sys.exit(1)


# ─────────────────────────────────────────────
# GITHUB API HELPERS
# ─────────────────────────────────────────────

def github_headers(token, accept="application/vnd.github.v3+json"):
    """Standard headers for GitHub REST API calls."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
    }


def get_pr_diff(owner, repo, pr_number, token):
    """Fetch the raw diff for a specific pull request."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    resp = requests.get(url, headers=github_headers(token, "application/vnd.github.v3.diff"))
    if resp.status_code == 200:
        return resp.text
    print(f"  ⚠️  Could not fetch diff for {owner}/{repo} PR #{pr_number} ({resp.status_code})")
    return None


def get_open_pr_diffs(owner, repo, token, base_branch="main"):
    """Fetch diffs from all open PRs targeting `base_branch` in a repo."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    params = {"state": "open", "base": base_branch, "per_page": 5}
    resp = requests.get(url, headers=github_headers(token), params=params)

    if resp.status_code != 200:
        print(f"  ⚠️  Could not list PRs for {owner}/{repo} ({resp.status_code})")
        return None

    prs = resp.json()
    if not prs:
        return None

    parts = []
    for pr in prs:
        diff = get_pr_diff(owner, repo, pr["number"], token)
        if diff:
            parts.append(f"PR #{pr['number']}: {pr['title']}\n{diff}")
    return "\n".join(parts) if parts else None


def get_default_branch_diff(owner, repo, token, branch="main", depth=3):
    """Fallback: get the diff of the last `depth` commits on the default branch."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    params = {"sha": branch, "per_page": depth}
    resp = requests.get(url, headers=github_headers(token), params=params)

    if resp.status_code != 200 or not resp.json():
        return None

    commits = resp.json()
    if len(commits) < 2:
        return None

    # Compare oldest → newest in the batch
    oldest_sha = commits[-1]["sha"]
    newest_sha = commits[0]["sha"]
    compare_url = f"https://api.github.com/repos/{owner}/{repo}/compare/{oldest_sha}...{newest_sha}"
    resp = requests.get(compare_url, headers=github_headers(token, "application/vnd.github.v3.diff"))
    if resp.status_code == 200:
        return resp.text
    return None


# ─────────────────────────────────────────────
# CONTEXT BUILDER
# ─────────────────────────────────────────────

def build_combined_context(config, token, current_owner, current_repo, current_pr):
    """
    Walk every repo in config, pull its diff, and stitch them into one
    combined context string that the AI can reason over.
    """
    sections = []

    for repo_cfg in config["repos"]:
        owner  = repo_cfg["owner"]
        repo   = repo_cfg["repo"]
        module = repo_cfg["module"]
        branch = repo_cfg.get("branch", "main")

        is_trigger = (
            owner.lower() == current_owner.lower()
            and repo.lower() == current_repo.lower()
        )

        if is_trigger:
            # ── Current repo: use the triggering PR's diff ──
            diff   = get_pr_diff(owner, repo, current_pr, token)
            source = f"PR #{current_pr} (triggering PR)"
            print(f"  ✅ {owner}/{repo} — triggering PR #{current_pr}")
        else:
            # ── Other repos: try open PRs first, then recent commits ──
            diff = get_open_pr_diffs(owner, repo, token, branch)
            if diff:
                source = "open PRs"
                print(f"  ✅ {owner}/{repo} — open PRs found")
            else:
                diff = get_default_branch_diff(owner, repo, token, branch)
                source = "recent commits" if diff else "no changes"
                status = "✅ recent commits" if diff else "⬜ no changes"
                print(f"  {status} {owner}/{repo}")

        header = (
            f"{'=' * 60}\n"
            f"MODULE: {module}\n"
            f"REPO:   {owner}/{repo}\n"
            f"SOURCE: {source}\n"
            f"{'=' * 60}"
        )

        if diff:
            sections.append(f"{header}\n{diff}")
        else:
            sections.append(f"{header}\nNo code changes detected in this module.")

    return "\n\n".join(sections)


# ─────────────────────────────────────────────
# GROQ AI
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are ZeroDrive, an expert automotive OTA safety engineer.
You analyze code changes across multiple firmware repos 
of an electric vehicle and assess safety risks.

You understand:
- ABS braking systems and response times
- Motor controller and regenerative braking
- Battery management systems
- ECU coordination between modules
- How a change in one module affects other modules

Respond ONLY in this JSON format:
{
  "risk_level": "HIGH" or "MEDIUM" or "LOW",
  "modules_affected": ["list of modules"],
  "what_changed": "simple explanation",
  "cross_module_impact": "how changes in one repo affect others",
  "potential_issues": "what could go wrong on real vehicles",
  "affected_vehicles": "which variants are affected",
  "recommendation": "BLOCK or APPROVE",
  "rollout_plan": "safe steps to deploy if approved"
}"""


def call_groq(api_key, combined_context):
    """Send the combined multi-repo context to Groq for risk analysis."""

    user_message = (
        "Analyze the following code changes from a multi-repo OTA update "
        "for an electric vehicle fleet.\n"
        "Assess the safety risk of deploying these changes together.\n\n"
        f"{combined_context}"
    )

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            "temperature": 0.2,
        },
    )

    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]

    print(f"❌ Groq API error: {resp.status_code}")
    print(resp.text)
    sys.exit(1)


def parse_risk_response(raw):
    """Extract the JSON object from Groq's response (handles markdown fences)."""
    text = raw.strip()

    # Strip ```json ... ``` wrappers if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]                       # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]                   # drop closing fence
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last resort: try to find a JSON block anywhere in the text
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {
            "risk_level": "HIGH",
            "recommendation": "BLOCK",
            "modules_affected": ["unknown"],
            "what_changed": "Unable to parse AI response",
            "cross_module_impact": "Manual review required",
            "potential_issues": raw[:500],
            "affected_vehicles": "All variants — manual review needed",
            "rollout_plan": "Do not deploy until manual review is complete",
        }


# ─────────────────────────────────────────────
# PR COMMENT FORMATTER
# ─────────────────────────────────────────────

def format_pr_comment(risk_data, config):
    """Build a rich Markdown comment for the pull request."""

    risk_level     = risk_data.get("risk_level", "UNKNOWN")
    recommendation = risk_data.get("recommendation", "UNKNOWN")

    badges = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "CRITICAL": "⛔"}
    badge  = badges.get(risk_level, "⚪")
    rec_emoji = "✅" if recommendation == "APPROVE" else "🚫"

    modules = risk_data.get("modules_affected", ["Unknown"])
    if isinstance(modules, list):
        modules_str = ", ".join(modules)
    else:
        modules_str = str(modules)

    repo_rows = "\n".join(
        f"| {r['module']} | `{r['owner']}/{r['repo']}` |"
        for r in config["repos"]
    )

    return f"""## {badge} ZeroDrive OTA Safety Analysis

| | |
|---|---|
| **Risk Level** | {badge} **{risk_level}** |
| **Recommendation** | {rec_emoji} **{recommendation}** |

---

### 📦 Modules Affected
{modules_str}

### 🔍 What Changed
{risk_data.get('what_changed', 'No details available')}

### 🔗 Cross-Module Impact
{risk_data.get('cross_module_impact', 'No cross-module impact detected')}

### ⚠️ Potential Issues
{risk_data.get('potential_issues', 'None identified')}

### 🚗 Affected Vehicles
{risk_data.get('affected_vehicles', 'Unknown')}

### 📋 Rollout Plan
{risk_data.get('rollout_plan', 'No rollout plan provided')}

---

<details>
<summary>📊 Repos Analyzed ({len(config['repos'])})</summary>

| Module | Repository |
|--------|-----------|
{repo_rows}

</details>

---
> 🤖 *Powered by **ZeroDrive** — Automated Multi-Repo OTA Safety Analysis*
> *Model: `llama-3.3-70b-versatile` · Threshold: `{config.get("risk_threshold", "HIGH")}`*
"""


# ─────────────────────────────────────────────
# POST COMMENT TO PR
# ─────────────────────────────────────────────

def post_pr_comment(owner, repo, pr_number, body, token):
    """Post (or update) a comment on the pull request."""
    # ── Check for an existing ZeroDrive comment to update ──
    list_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    resp = requests.get(list_url, headers=github_headers(token), params={"per_page": 100})

    comment_id = None
    if resp.status_code == 200:
        for c in resp.json():
            if "ZeroDrive OTA Safety Analysis" in c.get("body", ""):
                comment_id = c["id"]
                break

    if comment_id:
        # Update existing comment
        url  = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
        resp = requests.patch(url, headers=github_headers(token), json={"body": body})
        verb = "updated"
    else:
        # Create new comment
        resp = requests.post(list_url, headers=github_headers(token), json={"body": body})
        verb = "posted"

    if resp.status_code in (200, 201):
        print(f"✅ PR comment {verb} successfully")
    else:
        print(f"❌ Failed to {verb} comment: {resp.status_code} — {resp.text}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("\n🚗 ZeroDrive — Multi-Repo OTA Safety Analyzer\n")

    # ── Environment ──
    github_token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    groq_api_key = os.environ.get("GROQ_API_KEY")

    if not github_token:
        print("❌ GITHUB_TOKEN (or GH_PAT) not set"); sys.exit(1)
    if not groq_api_key:
        print("❌ GROQ_API_KEY not set"); sys.exit(1)

    github_repository = os.environ.get("GITHUB_REPOSITORY", "")   # "owner/repo"
    pr_number         = os.environ.get("PR_NUMBER", "")

    if not github_repository or not pr_number:
        print("❌ GITHUB_REPOSITORY or PR_NUMBER not available"); sys.exit(1)

    current_owner, current_repo = github_repository.split("/", 1)

    # ── Config ──
    print("📖 Loading zerodrive.config.json ...")
    config = load_config()
    print(f"📦 {len(config['repos'])} repos configured\n")

    # ── Pull diffs ──
    print("🔍 Pulling diffs from all repos ...")
    combined = build_combined_context(
        config, github_token, current_owner, current_repo, pr_number,
    )

    # Guard against exceeding Groq's context window
    MAX_CONTEXT = 28000
    if len(combined) > MAX_CONTEXT:
        combined = combined[:MAX_CONTEXT] + "\n\n[TRUNCATED — combined diff too large]"
    print(f"\n📝 Combined context: {len(combined):,} chars")

    # ── AI Analysis ──
    print("🤖 Sending to Groq AI for analysis ...")
    raw_response = call_groq(groq_api_key, combined)
    risk_data    = parse_risk_response(raw_response)
    print("✅ AI analysis complete\n")

    risk_level     = risk_data.get("risk_level", "UNKNOWN")
    recommendation = risk_data.get("recommendation", "UNKNOWN")

    print(f"{'=' * 50}")
    print(f"  🏁 Risk Level:     {risk_level}")
    print(f"  📋 Recommendation: {recommendation}")
    print(f"{'=' * 50}\n")

    # ── Post PR Comment ──
    comment = format_pr_comment(risk_data, config)
    post_pr_comment(current_owner, current_repo, pr_number, comment, github_token)

    # ── Gate: block if risk meets/exceeds threshold ──
    threshold = config.get("risk_threshold", "HIGH")
    levels    = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    if risk_level in levels and threshold in levels:
        if levels.index(risk_level) >= levels.index(threshold):
            print(f"\n🚫 PIPELINE BLOCKED — risk '{risk_level}' ≥ threshold '{threshold}'")
            sys.exit(1)

    print("\n✅ Pipeline approved — risk within acceptable threshold")


if __name__ == "__main__":
    main()
