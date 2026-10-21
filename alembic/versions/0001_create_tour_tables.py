"""create tours, scenes and hotspots

Revision ID: 0001
Revises:
Create Date: 2026-10-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "tours",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("property_ref", sa.String(100)),
        sa.Column("published", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("start_scene_id", sa.Integer()),
        sa.Column("floorplan_path", sa.String(255)),
        *_timestamps(),
    )
    op.create_index("ix_tours_property_ref", "tours", ["property_ref"])

    op.create_table(
        "scenes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("image_path", sa.String(255), nullable=False),
        sa.Column("preview_path", sa.String(255), nullable=False),
        sa.Column("thumb_path", sa.String(255), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Float(), server_default="0", nullable=False),
        sa.Column("initial_yaw", sa.Float(), server_default="0", nullable=False),
        sa.Column("initial_pitch", sa.Float(), server_default="0", nullable=False),
        sa.Column("map_x", sa.Float()),
        sa.Column("map_y", sa.Float()),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_scenes_tour_id", "scenes", ["tour_id"])

    op.create_foreign_key(
        "fk_tours_start_scene_id", "tours", "scenes", ["start_scene_id"], ["id"], ondelete="SET NULL"
    )

    op.create_table(
        "hotspots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("target_scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="CASCADE")),
        sa.Column("yaw", sa.Float(), nullable=False),
        sa.Column("pitch", sa.Float(), nullable=False),
        sa.Column("label", sa.String(120)),
        sa.Column("description", sa.Text()),
        sa.Column("url", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("type IN ('nav', 'info', 'link')", name="ck_hotspots_type"),
    )
    op.create_index("ix_hotspots_scene_id", "hotspots", ["scene_id"])
    op.create_index("ix_hotspots_target_scene_id", "hotspots", ["target_scene_id"])


def downgrade() -> None:
    op.drop_table("hotspots")
    op.drop_constraint("fk_tours_start_scene_id", "tours", type_="foreignkey")
    op.drop_table("scenes")
    op.drop_table("tours")
