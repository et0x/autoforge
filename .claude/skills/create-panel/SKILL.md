---
description: "Interactive workflow for creating new evaluation panels — asks about audience and goals, selects agents, assigns weights, writes the YAML file"
when_to_use: "When the user wants to create a new evaluation panel, configure agent weights, or asks about setting up a custom panel"
user-invocable: true
---

# Create Panel

Walk the user through creating a new evaluation panel for autoforge. A panel is a weighted set of evaluator agents whose scores combine into a consensus.

## Step 1: Understand the use case

Ask the user:
1. **What kind of content will this panel evaluate?** (e.g. "government memos", "LinkedIn posts", "API documentation", "sales emails", "internal strategy docs")
2. **Who is the audience for that content?** (e.g. "federal CISOs", "senior engineers", "C-suite executives", "general public")
3. **What matters most?** Ask them to rank what's most important for this audience. For example:
   - Technical accuracy vs. accessibility
   - Formal tone vs. engaging voice
   - Evidence and data vs. strategic framing
   - Emotional resonance vs. clarity

## Step 2: Select agents

Based on the answers, recommend agents from the available set. Show the user the full list:

```bash
autoforge agent list
```

**Built-in agents:**
- `formal-writing` — professional tone, grammar, conventions
- `technical-accuracy` — factual correctness, proper terminology
- `strategic-thinking` — big-picture framing, strategic implications
- `national-security-language` — government/defense terminology
- `evidence-based-reasoning` — quality of evidence, logical soundness
- `audience-engagement` — hooks, pacing, compelling narrative
- `clarity-conciseness` — economy of language, clear message
- `creative-writing` — storytelling, vivid language, narrative craft
- `data-driven-analysis` — quantitative reasoning, data use
- `emotional-intelligence` — emotional tone, empathy

Ask:
4. **Which of these agents should be on the panel?** Recommend 4-7 agents based on their answers to step 1. Explain why each is relevant.
5. **Do you need any custom agents?** If the use case requires domain expertise not covered by built-in agents (e.g. legal compliance, product knowledge), suggest creating one first using `/create-agent`.

## Step 3: Assign weights

Weights must sum to 1.0. Guide the user:

6. **How should we weight these agents?** Propose initial weights based on what they said matters most, then ask for adjustments.

Rules of thumb:
- The 1-2 most important perspectives get **0.20-0.30** each
- Supporting perspectives get **0.10-0.15** each
- No single agent should exceed **0.35** (one voice shouldn't dominate)
- No agent should be below **0.05** (if it's that unimportant, don't include it)
- **Weights must sum to exactly 1.0**

Show the proposed weights as a table and ask for confirmation:

```
Agent                     Weight
─────────────────────     ──────
audience-engagement        0.25
clarity-conciseness        0.20
strategic-thinking         0.20
evidence-based-reasoning   0.15
emotional-intelligence     0.10
creative-writing           0.10
                           ────
                           1.00
```

## Step 4: Generate the panel

Write the YAML file to `library/panels/<name>.yaml` (for built-in) or `.autoforge/panels/<name>.yaml` (for project-local).

### YAML structure

```yaml
name: <kebab-case-name>
description: >
  <1-2 sentences describing the target content and audience>

members:
  - agent: <agent-name>
    weight: <float>
  - agent: <agent-name>
    weight: <float>
  # ... weights must sum to 1.0
```

## Step 5: Review and test

After generating, the user can test it immediately:

```bash
# See the panel
autoforge panel show <name>

# Run it against content
autoforge eval --panel <name>

# Or use it for a full optimization run
autoforge run --panel <name> -n 5
```

Ask if the weights feel right after seeing the first evaluation. Common adjustments:
- **One agent's scores are dominating the consensus?** Lower its weight
- **An important dimension isn't moving the needle?** Raise that agent's weight
- **An agent is scoring everything the same?** It might not be differentiated enough — consider replacing it or refining its system prompt

## Reference: built-in panels

| Panel | Focus | Top agents |
|-------|-------|-----------|
| linkedin-professional | Social media thought leadership | audience-engagement (0.25), clarity (0.20) |
| government-stakeholders | Government/defense communications | national-security (0.25), formal-writing (0.20) |
| technical-blog | Technical articles | technical-accuracy (0.25), clarity (0.25) |
| executive-summary | C-suite communications | strategic-thinking (0.25), clarity (0.25) |
