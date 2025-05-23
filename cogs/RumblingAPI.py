import discord
from fastapi import Header, FastAPI, Request, HTTPException
import asqlite
from discord import Embed
import wavelink
from discord.ext import commands
import yaml
import asyncio
from uvicorn import Config, Server
from pydantic import BaseModel


# Misc

with open("config.yml") as f:
    MASTER_KEY = yaml.safe_load(f)["masterKey"]


def format_result(data: list):
    return {
        "plId": data[0],
        "userId": data[1],
        "track": data[2],  # base64 string
    }


# Models


class EditPlaylistPayload(BaseModel):
    name: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None


class CreatePlaylistPayload(BaseModel):
    user_id: str
    name: str
    description: str | None


class AddTrackPayload(BaseModel):
    user_id: str
    encoded: str


class AddTracksPayload(BaseModel):
    user_id: str
    tracks: list[AddTrackPayload]


class GetPlaylistPayload(BaseModel):
    user_id: str | None


class DeletePlaylistPayload(BaseModel):
    user_id: str

class ClearPlaylistPayload(DeletePlaylistPayload):
    pass

class GetRpcDataPayload(BaseModel):
    guild_id: str


async def is_playlist_owner(cur, pl_id: int, user_id: str):

    await cur.execute(
        "SELECT * FROM playlists WHERE userid=? AND id=?", (user_id, pl_id)
    )
    return await cur.fetchone() is not None


class RumbleBotAPI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.server: Server = None

    async def start_app(self):
        await self.bot.wait_until_ready()

        app = FastAPI()

        @app.get("/")
        async def root():
            return "Rumble"

        @app.get("/playlist/{pl_id}")
        async def get_user_playlist(pl_id:int,data: GetPlaylistPayload):
            async with asqlite.connect("userplaylists.db") as conn:
                async with conn.cursor() as cur:
                    if data.user_id is not None:
                        await cur.execute(
                            "SELECT * FROM playlists WHERE userid=? AND id=?",
                            (data.user_id, pl_id),
                        )
                    else:
                        await cur.execute(
                            "SELECT * FROM playlists WHERE id=?",
                            (pl_id,),
                        )
                    result = await cur.fetchone()
                    if result is not None:
                        return list(result)
                    else:
                        raise HTTPException(404)

        @app.post("/playlist/")
        async def create_playlist(payload: CreatePlaylistPayload):
            async with asqlite.connect("userplaylists.db") as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO playlists (userid, name, description, thumbnail_url) VALUES (?, ?, ?, ?)",
                        (
                            str(payload.user_id),
                            payload.name,
                            payload.description,
                            None,
                        ),
                    )
                    await conn.commit()
                    return {"pl_id": cur.get_cursor().lastrowid}

        @app.get("/playlist/{pl_id}/tracks")
        async def get_pl_tracks(pl_id: int):
            async with asqlite.connect("userplaylists.db") as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT * FROM tracks WHERE plid=?", (pl_id,))
                    result = await cur.fetchall()
                    if result is not None:
                        # r[0] = trackId 
                        # r[1:] = {"plId": 1234, "userId": '123', "track": "QAAA.."}
                        data = ((r[0], format_result(r[1:])) for r in result)

                        return tuple(data)
                    else:
                        raise HTTPException(404)

        @app.post("/playlist/{pl_id}/track")
        async def add_track_to_pl(
            pl_id: int,
            payload: AddTrackPayload,
            master_key: str | None = Header(default=None, alias="master-key"),
        ):
            if not master_key or master_key != MASTER_KEY:
                raise HTTPException(
                    status_code=403, detail="Master key is missing or incorrect."
                )

            async with asqlite.connect("userplaylists.db") as conn:
                async with conn.cursor() as cur:
                    if await is_playlist_owner(cur, pl_id, payload.user_id):
                        sql = (
                            "INSERT INTO tracks(plid, userid, encoded) VALUES (?, ?, ?)"
                        )
                        params = (
                            pl_id,
                            payload.user_id,
                            payload.encoded,
                        )
                        await cur.execute(sql, params)
                        await conn.commit()
                        return 200
                    else:
                        return HTTPException(
                            status_code=403, detail="You don't own that playlist"
                        )

        @app.post("/playlist/{pl_id}/tracks")
        async def add_tracks_to_pl(
            pl_id: int,
            payload: AddTracksPayload,
            master_key: str | None = Header(default=None, alias="master-key"),
        ):
            if not master_key or master_key != MASTER_KEY:
                raise HTTPException(
                    status_code=403, detail="Master key is missing or incorrect."
                )
            async with asqlite.connect("userplaylists.db") as conn:
                async with conn.cursor() as cur:
                    if await is_playlist_owner(cur, pl_id, payload.user_id):
                        for track in payload.tracks:
                            sql = "INSERT INTO tracks(plid, userid, encoded) VALUES (?, ?, ?)"
                            params = (
                                pl_id,
                                payload.user_id,
                                track.encoded,
                            )
                            await cur.execute(sql, params)
                            await conn.commit()
                        return 200
                    else:
                        return HTTPException(403, detail="You don't own that playlist")

        @app.patch("/playlist/{pl_id}")
        async def edit_playlist(
            pl_id: int,
            payload: EditPlaylistPayload,
            master_key: str | None = Header(default=None, alias="master-key"),
        ):
            if not master_key or master_key != MASTER_KEY:
                raise HTTPException(
                    status_code=403, detail="Master key is missing or incorrect."
                )
            data = payload.model_dump()
            values = tuple(v for v in data.values() if v)
            if len(values) <1: return {}
            set_clause = ', '.join([f'{k}=?' for k,v in data.items() if v])
            values = tuple(v for v in data.values() if v)
            query = f"UPDATE playlists SET {set_clause} WHERE id={pl_id}"
            async with asqlite.connect("userplaylists.db") as db:
                await db.execute(query, tuple(values))
                await db.commit()
                return {"edited": tuple(k for k,v in data.items() if v)}


        @app.delete("/playlist/{pl_id}")
        async def delete_pl(
            pl_id: int,
            payload: DeletePlaylistPayload,
            master_key: str | None = Header(default=None, alias="master-key"),
        ):
            if not master_key or master_key != MASTER_KEY:
                raise HTTPException(
                    status_code=403, detail="Master key is missing or incorrect."
                )
            async with asqlite.connect("userplaylists.db") as conn:
                async with conn.cursor() as cur:
                    if await is_playlist_owner(cur, pl_id, payload.user_id):
                        await cur.execute("DELETE FROM tracks WHERE plid=?", (pl_id,))
                        await cur.execute(
                            "DELETE FROM playlists WHERE id=? AND userid=?",
                            (
                                pl_id,
                                payload.user_id,
                            ),
                        )
                        return 200
                    else:
                        raise HTTPException(404)

        @app.delete("/playlist/{pl_id}/tracks")
        async def clear_playlist_tracks(pl_id: int,payload: ClearPlaylistPayload,  master_key: str | None = Header(default=None, alias="master-key")):
             if not master_key or master_key != MASTER_KEY:
                raise HTTPException(
                    status_code=403, detail="Master key is missing or incorrect."
                )
             async with asqlite.connect("userplaylists.db") as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM tracks WHERE plid=? AND userid=?", (pl_id,payload.user_id))
                    await conn.commit()

        @app.get("/player/")
        async def test(
            payload: GetRpcDataPayload,
            master_key: str | None = Header(default=None, alias="master-key"),
        ):
            if not master_key or master_key != MASTER_KEY:
                raise HTTPException(
                    status_code=403, detail="Master key is missing or incorrect."
                )
            for n in wavelink.Pool.nodes:
                node = wavelink.Pool.get_node(n)
                player = node.get_player(int(payload.guild_id))
                if player:
                    return player.current.raw_data
            else:
                raise HTTPException(404)

        cfg = Config(app, host="0.0.0.0")
        server = Server(cfg)
        self.server = server
        asyncio.create_task(self.server.serve())

    async def cog_load(self):
        self.bot.loop.create_task(self.start_app())

    async def cog_unload(self):
        await self.server.shutdown()


async def setup(bot):
    await bot.add_cog(RumbleBotAPI(bot))
