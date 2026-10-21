from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Tour(Base):
    __tablename__ = "tours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Free-form link to a listing on the main site (e.g. a FirstLease property id or slug).
    property_ref: Mapped[str | None] = mapped_column(String(100), index=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    start_scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL", use_alter=True, name="fk_tours_start_scene_id")
    )
    floorplan_path: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="tour",
        foreign_keys="Scene.tour_id",
        order_by=lambda: [Scene.sort_order, Scene.id],
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    preview_path: Mapped[str] = mapped_column(String(255), nullable=False)
    thumb_path: Mapped[str] = mapped_column(String(255), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)

    # Compass bearing (degrees) that the centre of the photo faces. Lines every room up
    # with the floor plan and with each other, so walking keeps the same direction.
    heading: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    # Starting view, in photo coordinates (0 = photo centre, + = right / up).
    initial_yaw: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    initial_pitch: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    # Position on the floor plan as fractions of its width/height (0..1).
    map_x: Mapped[float | None] = mapped_column(Float)
    map_y: Mapped[float | None] = mapped_column(Float)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tour: Mapped[Tour] = relationship(back_populates="scenes", foreign_keys=[tour_id])
    hotspots: Mapped[list["Hotspot"]] = relationship(
        back_populates="scene",
        foreign_keys="Hotspot.scene_id",
        order_by=lambda: Hotspot.id,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Hotspot(Base):
    __tablename__ = "hotspots"
    __table_args__ = (CheckConstraint("type IN ('nav', 'info', 'link')", name="ck_hotspots_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True, nullable=False)
    # "nav" walks to target_scene_id, "info" shows label/description, "link" opens url.
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    target_scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    yaw: Mapped[float] = mapped_column(Float, nullable=False)
    pitch: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scene: Mapped[Scene] = relationship(back_populates="hotspots", foreign_keys=[scene_id])
