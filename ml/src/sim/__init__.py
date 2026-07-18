"""Incremental (resumable) fleet simulator.

The v1 generator (`fleetgen/`) plans each machine's whole trajectory in one shot
and fills precursor drift retroactively. This package inverts that into a
*resumable daily state machine*: given a machine's latent state as of day D, it
emits day D+1 and returns the updated state. The same failure physics
(Weibull hazard on effective age, precursor leakage, imperfect repair, false
episodes) are reused — evaluated one day at a time so the system can run live and
persist state to Postgres between days.
"""
