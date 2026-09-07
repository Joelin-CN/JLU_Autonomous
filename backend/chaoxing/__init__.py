"""
Chaoxing (超星学习通) Automation Package.

A CLI automation tool that drives browser automation (playwright-cli + Chrome)
to auto-complete courses on the Chaoxing e-learning platform.

Architecture (6 layers):
    CLI (chaoxing_cli.ps1/.bat)
    → Orchestrator (orchestrator.py)
    → Executors (solvers/quiz + solvers/content)
    → Foundation (browser/ + platform/)
    → AI Backend (ai/doubao)
    → Engine (playwright-cli + Chrome)
"""

__version__ = "2.0.0"
__author__ = "Chaoxing Automation Project"
