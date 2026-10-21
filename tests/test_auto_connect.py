import pytest

from tests.conftest import ADMIN, make_image
from tests.test_api import create_tour, upload_scene

pytestmark = pytest.mark.anyio


def navs(tour, scene_id):
    scene = next(s for s in tour["scenes"] if s["id"] == scene_id)
    return {h["target_scene_id"]: h for h in scene["hotspots"] if h["type"] == "nav"}


async def auto_connect(client, tour_id):
    r = await client.post(f"/api/admin/tours/{tour_id}/auto-connect", headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


async def test_needs_two_rooms_and_admin(client):
    tour = await create_tour(client)
    await upload_scene(client, tour["id"])
    assert (await client.post(f"/api/admin/tours/{tour['id']}/auto-connect")).status_code == 401
    r = await client.post(f"/api/admin/tours/{tour['id']}/auto-connect", headers=ADMIN)
    assert r.status_code == 422


async def test_chains_rooms_in_list_order_and_is_idempotent(client):
    tour = await create_tour(client)
    a, b, c = [(await upload_scene(client, tour["id"], f"{n}.jpg")).json() for n in "ABC"]

    out = await auto_connect(client, tour["id"])
    assert out["created"] == 4
    t = out["tour"]
    # Ahead of the start view leads on, behind leads back.
    assert navs(t, a["id"])[b["id"]]["yaw"] == pytest.approx(0)
    assert navs(t, b["id"])[a["id"]]["yaw"] == pytest.approx(-180)
    assert navs(t, b["id"])[c["id"]]["yaw"] == pytest.approx(0)
    assert set(navs(t, c["id"])) == {b["id"]}
    assert all(h["pitch"] < -2 for s in t["scenes"] for h in s["hotspots"])  # floor circles

    assert (await auto_connect(client, tour["id"]))["created"] == 0


async def test_floor_plan_positions_set_directions(client):
    tour = await create_tour(client)
    files = {"file": ("plan.png", make_image(1000, 500, "PNG"), "image/png")}
    await client.put(f"/api/admin/tours/{tour['id']}/floorplan", files=files, headers=ADMIN)
    a, b, c = [(await upload_scene(client, tour["id"], f"{n}.jpg")).json() for n in "ABC"]
    # B is 200 px right of A, C 200 px below A (B-C is 1.41x further). B faces east, so "east" is straight ahead in its photo.
    for scene, body in ((a, {"map_x": 0.1, "map_y": 0.2}), (b, {"map_x": 0.3, "map_y": 0.2, "heading": 90}),
                        (c, {"map_x": 0.1, "map_y": 0.6})):
        await client.patch(f"/api/admin/scenes/{scene['id']}", json=body, headers=ADMIN)

    t = (await auto_connect(client, tour["id"]))["tour"]
    assert navs(t, a["id"])[b["id"]]["yaw"] == pytest.approx(90)    # east of A
    assert navs(t, b["id"])[a["id"]]["yaw"] == pytest.approx(-180)  # west = behind B
    assert navs(t, a["id"])[c["id"]]["yaw"] == pytest.approx(-180)  # south of A
    assert c["id"] not in navs(t, b["id"])  # B and C only meet through A


async def test_adds_missing_way_back(client):
    tour = await create_tour(client)
    a, b = [(await upload_scene(client, tour["id"], f"{n}.jpg")).json() for n in "AB"]
    await client.post(
        f"/api/admin/scenes/{a['id']}/hotspots",
        json={"type": "nav", "target_scene_id": b["id"], "yaw": 40, "pitch": -30},
        headers=ADMIN,
    )
    out = await auto_connect(client, tour["id"])
    assert out["created"] == 1
    back = navs(out["tour"], b["id"])[a["id"]]
    assert (back["yaw"], back["pitch"]) == (pytest.approx(-140), pytest.approx(-30))
    assert len(navs(out["tour"], a["id"])) == 1
