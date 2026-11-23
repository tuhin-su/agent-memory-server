# Rule: Model Read/Write Authority Over Rules and Skills

The AI model has autonomous read and write authority over all project rules and skills.

## 1. Rules and Skills Are Living Code
- **Rules Directory**: `.agents/rules/*.md`
- **Skills Directory**: `.agents/skills/<skill-name>/SKILL.md`
- Any agent can:
  1. **Search & Read**: Find existing rules or skills matching current requirements.
  2. **Update & Refine**: Edit existing rules when architectural changes, bugfixes, or user preferences occur.
  3. **Create New Rules**: Add new `.md` files under `.agents/rules/` when a new domain, tool, or recurring pattern is introduced.
  4. **Create New Skills**: Add new runbooks under `.agents/skills/<new-skill>/` with frontmatter (`name`, `description`) so future agents can invoke them.

## 2. How to Search Rules and Skills
- Inspect `.agents/rules/` or list `.agents/skills/`.
- Query `agent-memory` with `search_memory(query="...")`.
- Update `.agents/AGENTS.md` index whenever adding or removing rule categories.
