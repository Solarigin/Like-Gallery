from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    ext: Mapped[str] = mapped_column(String(16), nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exif_taken_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    files: Mapped[list["File"]] = relationship("File", back_populates="asset")


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    rel_path: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    folder: Mapped[str] = mapped_column(String(256), nullable=False)
    mtime: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    asset: Mapped[Asset] = relationship("Asset", back_populates="files")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    post_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def as_dict(self) -> dict[str, str]:
        return {
            "author": self.author,
            "post_id": self.post_id,
            "source": self.source or "",
            "saved_at": self.saved_at.isoformat(),
        }


def get_engine(base_dir: Path) -> any:
    db_path = base_dir / "sia.db"
    base_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine: any) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def ensure_schema(engine: any) -> None:
    Base.metadata.create_all(engine)


def count_files_by_author(session: Session, author: str) -> int:
    stmt = select(func.count(File.id)).join(Item, File.folder == Item.author).where(
        Item.author == author
    )
    return session.scalar(stmt) or 0


@contextlib.contextmanager
def session_scope(engine: any) -> Generator[Session, None, None]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def last_inserted_item(session: Session) -> Optional[Item]:
    stmt = select(Item).order_by(Item.saved_at.desc()).limit(1)
    return session.scalar(stmt)


def vacuum(engine: any) -> None:
    with engine.begin() as conn:
        conn.execute(text("VACUUM"))
