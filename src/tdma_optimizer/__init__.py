"""TDMA schedule planner: distance-2 graph coloring for collision-free slot assignment.

Pipeline (see docs/architecture.md):

    coordinates -> communication graph G -> conflict graph H = G^2
                -> heuristic coloring -> exact bound / certificate
                -> independent validation -> report / EMANE export
"""

__version__ = "1.0.0"
