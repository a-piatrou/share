"""HTTP routers.

Phase-1 ships only ``health``. The feature routers (chat, feedback, team) are Phase-2 and are
owned by the feature modules; their package structure is left ready here (placeholder modules
with an APIRouter each) so the worktrees only fill in handlers against the frozen OpenAPI.
"""
