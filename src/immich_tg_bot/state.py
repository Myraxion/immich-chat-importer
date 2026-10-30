from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_messages (
    chat_id      INTEGER NOT NULL,
    message_id   INTEGER NOT NULL,
    file_index   INTEGER NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL,
    asset_id     TEXT,
    processed_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (chat_id, message_id, file_index)
);

CREATE TABLE IF NOT EXISTS sha1_cache (
    sha1      TEXT PRIMARY KEY,
    asset_id  TEXT NOT NULL,
    cached_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS processed_items (
    platform TEXT NOT NULL,
    source_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    attachment_id TEXT NOT NULL,
    PRIMARY KEY (platform, source_id, message_id, attachment_id)
);
CREATE TABLE IF NOT EXISTS source_assets (
    platform TEXT NOT NULL, source_id TEXT NOT NULL, message_id TEXT NOT NULL,
    attachment_id TEXT NOT NULL, asset_id TEXT NOT NULL, file_name TEXT NOT NULL,
    PRIMARY KEY (platform, source_id, message_id, attachment_id, asset_id)
);
CREATE TABLE IF NOT EXISTS asset_albums (
    asset_id TEXT NOT NULL, album_key TEXT NOT NULL,
    PRIMARY KEY (asset_id, album_key)
);
"""


class State:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("State.open() was not called")
        return self._db

    async def already_processed(
        self, chat_id: int | str, message_id: int | str, file_index: int = 0
    ) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM processed_messages WHERE chat_id=? AND message_id=? AND file_index=?",
            (chat_id, message_id, file_index),
        )
        return await cur.fetchone() is not None

    async def mark_processed(
        self,
        chat_id: int | str,
        message_id: int | str,
        file_index: int,
        status: str,
        asset_id: str | None,
    ) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO processed_messages "
            "(chat_id, message_id, file_index, status, asset_id) VALUES (?,?,?,?,?)",
            (chat_id, message_id, file_index, status, asset_id),
        )
        await self.db.commit()

    async def asset_for_sha1(self, sha1: str) -> str | None:
        cur = await self.db.execute("SELECT asset_id FROM sha1_cache WHERE sha1=?", (sha1,))
        row = await cur.fetchone()
        return row[0] if row else None

    async def item_processed(
        self, platform: str, source_id: str, message_id: str, attachment_id: str
    ) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM processed_items WHERE platform=? AND source_id=? "
            "AND message_id=? AND attachment_id=?",
            (platform, source_id, message_id, attachment_id),
        )
        return await cur.fetchone() is not None

    async def mark_item_processed(
        self, platform: str, source_id: str, message_id: str, attachment_id: str
    ) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO processed_items VALUES (?,?,?,?)",
            (platform, source_id, message_id, attachment_id),
        )
        await self.db.commit()

    async def cache_sha1(self, sha1: str, asset_id: str) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO sha1_cache (sha1, asset_id) VALUES (?,?)",
            (sha1, asset_id),
        )
        await self.db.commit()

    async def source_assets(self, identity: tuple[str, str, str, str]) -> list[tuple[str, str]]:
        cur = await self.db.execute(
            "SELECT asset_id, file_name FROM source_assets WHERE platform=? AND source_id=? "
            "AND message_id=? AND attachment_id=?", identity
        )
        return [(row[0], row[1]) for row in await cur.fetchall()]

    async def save_source_asset(
        self, identity: tuple[str, str, str, str], asset_id: str, file_name: str
    ) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO source_assets VALUES (?,?,?,?,?,?)",
            (*identity, asset_id, file_name),
        )
        await self.db.commit()

    async def album_completed(self, asset_id: str, album_key: str) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM asset_albums WHERE asset_id=? AND album_key=?", (asset_id, album_key)
        )
        return await cur.fetchone() is not None

    async def mark_album_completed(self, asset_id: str, album_key: str) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO asset_albums VALUES (?,?)", (asset_id, album_key)
        )
        await self.db.commit()
