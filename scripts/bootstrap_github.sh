#!/usr/bin/env bash
# Cria labels, milestones e issues do backlog inicial no GitHub (rodar no Mac, com gh autenticado).
# Uso: bash scripts/bootstrap_github.sh [owner/repo]
set -euo pipefail
REPO="${1:-ViniciusAguiar15/bdgd-light}"
cd "$(dirname "$0")/.."

label() { gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force >/dev/null && echo "label $1"; }
label "area:ingest"  "1d76db" "Download, exportação e recorte da BDGD"
label "area:grid"    "0e8a16" "Grafo/topologia do alimentador"
label "area:twin"    "5319e7" "Gêmeo digital OpenDSS"
label "area:console" "fbca04" "Console web (mapa, eventos)"
label "area:agent"   "d93f0b" "Agente, MCP, LLM"
label "area:docs"    "c5def5" "Documentação e ADRs"
label "phase:F1"     "bfd4f2" "Fase 1: dados + mapa"
label "phase:F2"     "bfd4f2" "Fase 2: grafo + gêmeo"
label "phase:F3"     "bfd4f2" "Fase 3: agente"
label "phase:F4"     "bfd4f2" "Fase 4: benchmark + governança"
label "copilot"      "8b5cf6" "Pronta para o Copilot coding agent"
label "spike"        "e4e669" "Investigação com resultado documentado"

ms() { gh api "repos/$REPO/milestones" -f title="$1" -f description="$2" >/dev/null 2>&1 && echo "milestone $1" || echo "milestone $1 (já existe)"; }
ms "F1 Dados + mapa"          "Exportar camadas, inventário, recorte por CTMT, console MapLibre no Pages"
ms "F2 Grafo + gêmeo"         "networkx + OpenDSS dos alimentadores escolhidos"
ms "F3 Agente"                "MCP server, orquestrador/verificador HITL, simulador de eventos, FLISR"
ms "F4 Benchmark + governança" "Tarefas/métricas estilo PowerChain, logs, RACI-A, demo"

# Issues a partir de docs/backlog/*.md (front matter: title, labels, milestone)
for f in docs/backlog/*.md; do
  title=$(sed -n 's/^title: *"\(.*\)"/\1/p' "$f")
  labels=$(sed -n 's/^labels: *//p' "$f" | tr -d ' ')
  milestone=$(sed -n 's/^milestone: *//p' "$f")
  body=$(awk 'BEGIN{c=0} /^---$/{c++; next} c>=2{print}' "$f")
  if gh issue list --repo "$REPO" --state all --limit 500 --json title --jq '.[].title' | grep -Fxq "$title"; then
    echo "issue já existe: $title"; continue
  fi
  gh issue create --repo "$REPO" --title "$title" --label "$labels" --milestone "$milestone" --body "$body"
done
echo "Pronto. Próximo passo: abrir as issues no GitHub e atribuir ao Copilot (Assignees → Copilot)."
