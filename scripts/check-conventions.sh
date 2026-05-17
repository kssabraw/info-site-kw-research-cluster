#!/usr/bin/env bash
# ============================================================================
# check-conventions.sh
# ============================================================================
# Enforces the "Critical Conventions" listed in CLAUDE.md by grepping the
# codebase for known violations. Exits non-zero on any violation so it
# can be wired into pre-commit and CI.
#
# This script is intentionally simple — grep + bash. It catches the
# obvious slips, not all possible violations. Type-aware enforcement
# (e.g., site_id must be in every public phase function signature)
# belongs in a real linter; this is the cheap fence.
# ============================================================================

set -uo pipefail

cd "$(dirname "$0")/.."

# ANSI colors only if stdout is a terminal
if [[ -t 1 ]]; then
    RED='\033[0;31m'; YELLOW='\033[0;33m'; GREEN='\033[0;32m'; NC='\033[0m'
else
    RED=''; YELLOW=''; GREEN=''; NC=''
fi

VIOLATIONS=0

# ----------------------------------------------------------------------------
# check_grep: run a grep command, optionally filter out allowed lines, fail
# if anything remains.
#   $1: human-readable check name
#   $2: rule explanation
#   $3: filter regex to exclude allowed lines (empty string = no filter)
#   $4..N: grep args (no leading 'grep')
# ----------------------------------------------------------------------------
check_grep() {
    local name="$1"
    local rule="$2"
    local filter="$3"
    shift 3

    local output
    output=$(grep "$@" 2>/dev/null || true)

    if [[ -n "$filter" && -n "$output" ]]; then
        output=$(echo "$output" | grep -vE "$filter" || true)
    fi

    # collapse pure-blank result to empty
    output=$(printf '%s' "$output" | sed '/^$/d')

    if [[ -n "$output" ]]; then
        echo -e "${RED}FAIL${NC}: ${name}"
        echo "  Rule: ${rule}"
        echo "  Offending lines:"
        printf '%s\n' "$output" | sed 's/^/    /'
        echo ""
        VIOLATIONS=$((VIOLATIONS + 1))
    else
        echo -e "${GREEN}PASS${NC}: ${name}"
    fi
}

# ----------------------------------------------------------------------------
# Skip if there's no pipeline/ directory yet. The hooks are valuable as
# declared intent before code lands, but they can't grep what doesn't exist.
# ----------------------------------------------------------------------------
if [[ ! -d pipeline ]]; then
    echo -e "${YELLOW}note${NC}: pipeline/ does not exist yet; convention checks would have nothing to grep."
    echo "       Re-run this script after pipeline modules are added. The intent is locked in regardless."
    exit 0
fi

# ----------------------------------------------------------------------------
# Convention checks — each maps to a bullet in CLAUDE.md → Critical Conventions
# ----------------------------------------------------------------------------

# R1: All DB access through pipeline/utils/database.py.
check_grep "db-imports-only-in-utils-database" \
    "CLAUDE.md R1: 'All database operations go through pipeline/utils/database.py'" \
    "^pipeline/utils/database\\.py:" \
    -rnE "^(from|import) (psycopg2|psycopg|supabase|sqlalchemy)" \
    --include="*.py" \
    --exclude-dir=.venv \
    pipeline/

# R2: API clients live in pipeline/utils/. Phases must not call vendor SDKs.
check_grep "no-anthropic-imports-outside-claude-client" \
    "CLAUDE.md R2: 'All API clients are in pipeline/utils/'" \
    "^pipeline/utils/claude_client\\.py:" \
    -rnE "^(from|import) anthropic" \
    --include="*.py" \
    pipeline/

check_grep "no-openai-imports-outside-openai-client" \
    "CLAUDE.md R2: 'All API clients are in pipeline/utils/'" \
    "^pipeline/utils/openai_client\\.py:" \
    -rnE "^(from|import) openai" \
    --include="*.py" \
    pipeline/

check_grep "no-dataforseo-imports-outside-dataforseo-client" \
    "CLAUDE.md R2: 'All API clients are in pipeline/utils/'" \
    "^pipeline/utils/dataforseo\\.py:" \
    -rnE "^(from|import) (dataforseo|dfs)" \
    --include="*.py" \
    pipeline/

# R3: Config loading goes through pipeline/utils/config.py.
check_grep "no-direct-yaml-load-outside-config" \
    "CLAUDE.md R3: 'Config loading goes through pipeline/utils/config.py'" \
    "^pipeline/utils/config\\.py:" \
    -rnE "yaml\\.(safe_load|load|full_load)" \
    --include="*.py" \
    pipeline/

# Env vars only loaded through config layer.
check_grep "no-direct-env-reads-outside-config" \
    "CLAUDE.md R3: env access belongs in pipeline/utils/config.py" \
    "^pipeline/utils/config\\.py:" \
    -rnE "os\\.environ|os\\.getenv" \
    --include="*.py" \
    pipeline/

# R6: Raw SQL strings in phases (heuristic: SELECT/INSERT/UPDATE/DELETE
# preceded by a quote).
check_grep "no-raw-sql-in-phases" \
    "CLAUDE.md R1: phases must not embed raw SQL — go through pipeline/utils/database.py" \
    "" \
    -rnE "['\"]\\s*(SELECT|INSERT|UPDATE|DELETE)\\s+" \
    --include="*.py" \
    pipeline/phases/

# R4: Every phase entry point uses @track_job.
# Heuristic: find 'def run(' or 'async def run(' in pipeline/phases/*.py
# whose immediately preceding non-blank line is not '@track_job'.
if compgen -G "pipeline/phases/*.py" > /dev/null; then
    bad=""
    for f in pipeline/phases/*.py; do
        result=$(awk '
            /^@track_job/ { decorated_at = NR; next }
            /^(async )?def run\(/ {
                if (decorated_at != NR - 1) print FILENAME ":" NR ": " $0
                decorated_at = 0
                next
            }
            /^$/ { next }
            { decorated_at = 0 }
        ' "$f")
        if [[ -n "$result" ]]; then
            bad+="${result}"$'\n'
        fi
    done
    bad=$(printf '%s' "$bad" | sed '/^$/d')
    if [[ -n "$bad" ]]; then
        echo -e "${RED}FAIL${NC}: phase-run-must-use-track-job"
        echo "  Rule: CLAUDE.md R4: 'Use the @track_job decorator' on every phase entry point"
        echo "  Offending lines:"
        printf '%s\n' "$bad" | sed 's/^/    /'
        echo ""
        VIOLATIONS=$((VIOLATIONS + 1))
    else
        echo -e "${GREEN}PASS${NC}: phase-run-must-use-track-job"
    fi
fi

# ----------------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------------
echo ""
if [[ $VIOLATIONS -eq 0 ]]; then
    echo -e "${GREEN}All convention checks passed.${NC}"
    exit 0
else
    echo -e "${RED}${VIOLATIONS} convention violation(s).${NC}"
    echo "See CLAUDE.md → 'Critical Conventions' for context."
    exit 1
fi
