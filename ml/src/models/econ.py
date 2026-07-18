"""Economic assumptions for the service business — disclosed, not hidden.

Order-of-magnitude figures reused from Fleet Pulse v1. Every dashboard money
number traces back to these; they are written into `impact_daily.assumptions`
so the story always shows its working.
"""

ASSUMPTIONS = {
    "downtime_cost_per_day": 27000,   # lost scanning revenue while a scanner is down
    "proactive_visit_cost": 800,      # a planned inspection / pre-emptive repair
    "planned_downtime_days": 0.5,     # a caught issue → short planned intervention
    "worklist_k": 20,                 # inspections the team can action per week
    "note": "Synthetic, order-of-magnitude. A caught failure converts unplanned "
            "downtime into a planned visit; savings = avoided unplanned downtime "
            "minus the visit cost.",
}


def savings_if_caught(downtime_days: float) -> float:
    """Net saving from catching one failure proactively."""
    a = ASSUMPTIONS
    avoided = (downtime_days - a["planned_downtime_days"]) * a["downtime_cost_per_day"]
    return max(0.0, avoided) - a["proactive_visit_cost"]
