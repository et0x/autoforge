---
description: "Interactive workflow for creating new evaluator agents — asks questions, generates system prompt and scoring rubric, writes the YAML file"
when_to_use: "When the user wants to create a new evaluator agent, add an expert persona, or asks about making a custom agent"
user-invocable: true
---

# Create Agent

Walk the user through creating a new evaluator agent for autoforge. Ask the questions below, then generate the YAML file.

## Step 1: Understand the expertise

Ask the user:
1. **What domain does this agent evaluate?** (e.g. "formal writing", "technical accuracy", "product messaging", "legal compliance", "accessibility")
2. **Who is this agent pretending to be?** (e.g. "a senior security engineer", "a CMO reviewing marketing copy", "a federal compliance officer")
3. **What specific things should this agent look for when scoring?** Get 4-6 concrete evaluation criteria.

## Step 2: Determine tools needed

Ask:
4. **Does this agent need tools to do its job?** For example:
   - Does it need to search the web to fact-check claims? → Add WebSearch
   - Does it need to read files from a knowledge base? → Add Read + Skill
   - Does it just read the content and judge it? → Default tools are fine

If it needs skills, ask what tools and skill directories it needs.

## Step 3: Choose the model

Ask:
5. **How complex is the evaluation?**
   - Simple/fast scoring → `haiku` (default, cheapest)
   - Nuanced judgment → `sonnet`
   - Highest quality evaluation → `opus`

## Step 4: Generate the agent

Write the YAML file to `library/agents/<name>.yaml` (for built-in) or suggest `.autoforge/agents/<name>.yaml` (for project-local).

### YAML structure

```yaml
name: <kebab-case-name>
description: <one line — this appears in listings>
model: <haiku|sonnet|opus or full model ID>
temperature: 0.3

# Optional — configure if the agent needs tools beyond defaults:
tools: [Read, Grep, Skill, WebSearch]  # as needed
skill_dirs: [~/path/to/skills]          # if using skills
skills: [specific-skill-name]           # filter to specific skills
max_turns: 10

system_prompt: |
  You are a <persona description>. You have <background/experience>.

  You evaluate content for:
  - <criterion 1>
  - <criterion 2>
  - <criterion 3>
  - <criterion 4>
  - <criterion 5>

scoring_rubric: |
  0-2: <what this range means for this domain>
  3-4: <what this range means>
  5-6: <what this range means>
  7-8: <what this range means>
  9-10: <what this range means>
```

## Step 5: Review and iterate

After generating the agent YAML, ask the user to review it. Common refinements:
- **System prompt too generic?** Add more specific evaluation criteria or domain knowledge
- **Rubric too vague?** Add concrete examples of what each score level looks like
- **Missing perspective?** The agent should have a clear, distinct viewpoint — not generic "evaluate quality"

The user can test the agent immediately:
```bash
autoforge eval --agent <name> -f content.md
```

## Guidelines for good agents

- **Distinct perspective**: Each agent should score from a specific angle. "formal-writing" and "audience-engagement" will give different scores to the same content — that's the point.
- **Concrete criteria**: "evaluate quality" is bad. "Check for active voice, parallel structure, and appropriate formality level" is good.
- **Calibrated rubric**: 5 should mean "adequate" not "average". Most content should land 5-7. A 9 should be rare and genuinely exceptional.
- **No overlap**: If you already have a "clarity-conciseness" agent, don't make a "clear-writing" agent. Check existing agents first with `autoforge agent list`.

## Reference: existing built-in agents

formal-writing, technical-accuracy, strategic-thinking, national-security-language, evidence-based-reasoning, audience-engagement, clarity-conciseness, creative-writing, data-driven-analysis, emotional-intelligence

All use `model: haiku`, `temperature: 0.3`.
