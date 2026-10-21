"""Auto-connect: link every room to its neighbours with a pair of walk circles.

Rooms placed on the floor plan are linked to their nearest neighbours (a minimum
spanning tree, so every room is reachable, plus a second neighbour when it is
almost as close), with each circle pointing where the other room really is.
Rooms not placed on the plan are chained in list order: a circle straight ahead
of the start view leads to the next room, and one behind leads back.

Pairs that are already linked are left alone; if only one direction exists,
the way back is added opposite to it.
"""
import math
from dataclasses import dataclass

from app.models import Scene
from app.schemas import wrap180

# Circles go on the floor this far below the horizon: about 3.4 m away for a 1.6 m camera.
DEFAULT_PITCH = -25.0
# A second neighbour is also linked when it is at most this much further than the nearest.
SECOND_NEIGHBOUR_RATIO = 1.35


@dataclass
class Link:
    source_id: int
    target_id: int
    yaw: float
    pitch: float


def _plan_pairs(placed: list[Scene], pos: dict[int, tuple[float, float]]) -> list[tuple[Scene, Scene]]:
    def dist(a: Scene, b: Scene) -> float:
        (ax, ay), (bx, by) = pos[a.id], pos[b.id]
        return math.hypot(bx - ax, by - ay)

    # Kruskal's minimum spanning tree: connects every placed room with the shortest links.
    edges = sorted(
        ((dist(a, b), i, j) for i, a in enumerate(placed) for j, b in enumerate(placed) if i < j),
        key=lambda e: e[0],
    )
    parent = list(range(len(placed)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    chosen: set[tuple[int, int]] = set()
    for _, i, j in edges:
        ri, rj = root(i), root(j)
        if ri != rj:
            parent[ri] = rj
            chosen.add((i, j))

    # Open areas: also link a second neighbour that is nearly as close as the nearest.
    for i, a in enumerate(placed):
        near = sorted((dist(a, b), j) for j, b in enumerate(placed) if j != i)
        if len(near) >= 2 and near[1][0] <= near[0][0] * SECOND_NEIGHBOUR_RATIO:
            j = near[1][1]
            chosen.add((min(i, j), max(i, j)))

    return [(placed[i], placed[j]) for i, j in sorted(chosen)]


def plan_links(
    scenes: list[Scene],
    existing: dict[tuple[int, int], tuple[float, float]],
    plan_size: tuple[int, int] | None,
) -> list[Link]:
    """Walk circles to add. `existing` maps (from, to) room ids to the (compass bearing, pitch)
    of a nav hotspot already there; `plan_size` is the floor plan's pixel size, for true angles."""
    placed = [s for s in scenes if s.map_x is not None and s.map_y is not None]
    pos: dict[int, tuple[float, float]] = {}
    pairs: list[tuple[Scene, Scene]] = []

    if len(placed) >= 2:
        w, h = plan_size or (1, 1)
        pos = {s.id: (s.map_x * w, s.map_y * h) for s in placed}
        pairs += _plan_pairs(placed, pos)
        # Rooms not on the plan hang off the room before them in the list (or after, for the first).
        for i, s in enumerate(scenes):
            if s.id not in pos:
                other = scenes[i - 1] if i > 0 else scenes[i + 1]
                pairs.append((other, s))
    else:
        pairs = list(zip(scenes, scenes[1:]))

    links: list[Link] = []
    for a, b in pairs:
        forward, back = existing.get((a.id, b.id)), existing.get((b.id, a.id))
        if forward is not None and back is not None:
            continue
        pitch = DEFAULT_PITCH
        if forward is not None:
            bearing, pitch = forward
        elif back is not None:
            bearing, pitch = back[0] + 180, back[1]
        elif a.id in pos and b.id in pos:
            (ax, ay), (bx, by) = pos[a.id], pos[b.id]
            bearing = math.degrees(math.atan2(bx - ax, -(by - ay)))  # plan top = bearing 0
        else:
            bearing = a.initial_yaw + a.heading  # straight ahead of the start view

        if forward is None:
            links.append(Link(a.id, b.id, wrap180(bearing - a.heading), pitch))
            existing[(a.id, b.id)] = (bearing, pitch)
        if back is None:
            links.append(Link(b.id, a.id, wrap180(bearing + 180 - b.heading), pitch))
            existing[(b.id, a.id)] = (bearing + 180, pitch)
    return links
