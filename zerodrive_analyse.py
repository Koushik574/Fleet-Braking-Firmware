"""
ZeroDrive - OTA Safety Analyzer
Reads the PR diff and uses Groq AI to assess risk
"""

import os
import json
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
MODEL        = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """
You are ZeroDrive, an expert automotive OTA software safety engineer.
You analyze code changes in electric vehicle firmware and assess safety risks.

You understand:
- ABS braking systems and response times
- Motor controller and regenerative braking
- Battery management systems
- ECU coordination between modules
- How a change in one module affects other modules

When analyzing a code diff, you must respond ONLY in this exact JSON format:
{
  "risk_level": "HIGH" or "MEDIUM" or "LOW",
  "module_affected": "name of the module",
  "what_changed": "simple explanation of what changed",
  "potential_issues": "what could go wrong on real vehicles",
  "affected_vehicles": "which vehicle variants are affected",
  "recommendation": "BLOCK or APPROVE",
  "rollout_plan": "safe steps to deploy if approved"
}

Be strict. Safety of riders is the highest priority.
If braking, motor, or battery safety is affected even slightly - mark HIGH risk.
"""

def read_diff():
    with open("pr_diff.txt", "r") as f:
        return f.read()

def analyze_with_groq(diff_content):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": f"Analyze this OTA firmware code change for safety risks:\n\n{diff_content}"
            }
        ],
        "temperature": 0.2
    }

    response = requests.post(GROQ_URL, headers=headers, json=payload)
    response.raise_for_status()

    result      = response.json()
    raw_content = result["choices"][0]["message"]["content"]

    # Parse JSON response
    analysis = json.loads(raw_content)
    return analysis

def build_report(analysis):
    risk      = analysis.get("risk_level", "UNKNOWN")
    emoji_map = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
    emoji     = emoji_map.get(risk, "⚪")

    report = f"""
## {emoji} ZeroDrive OTA Safety Report

| Field | Details |
|---|---|
| **Risk Level** | {emoji} {risk} |
| **Module Affected** | {analysis.get('module_affected', 'N/A')} |
| **What Changed** | {analysis.get('what_changed', 'N/A')} |
| **Potential Issues** | {analysis.get('potential_issues', 'N/A')} |
| **Affected Vehicles** | {analysis.get('affected_vehicles', 'N/A')} |
| **Verdict** | {analysis.get('recommendation', 'N/A')} |

### 📋 Rollout Plan
{analysis.get('rollout_plan', 'N/A')}

---
*Analyzed by ZeroDrive — Validate every update. Drive zero miles.*
"""
    return report, risk

def main():
    print("🛡️ ZeroDrive starting analysis...")

    diff = read_diff()

    if not diff.strip():
        print("No diff found - skipping analysis")
        with open("risk_report.txt", "w") as f:
            f.write("## ✅ ZeroDrive: No code changes detected")
        with open("risk_level.txt", "w") as f:
            f.write("LOW")
        return

    print("📤 Sending diff to Groq AI...")
    analysis = analyze_with_groq(diff)

    print("📊 Building risk report...")
    report, risk_level = build_report(analysis)

    # Save report for GitHub Actions to post as PR comment
    with open("risk_report.txt", "w") as f:
        f.write(report)

    # Save risk level for pipeline pass/fail decision
    with open("risk_level.txt", "w") as f:
        f.write(risk_level)

    print(f"✅ Analysis complete - Risk Level: {risk_level}")
    print(report)

if __name__ == "__main__":
    main()