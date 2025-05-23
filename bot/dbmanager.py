import asqlite

async def dbsetup():
    async with asqlite.connect("userplaylists.db") as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """CREATE TABLE IF NOT EXISTS playlists (
                                  id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                                  userid VARCHAR(100) NOT NULL,
                                  name VARCHAR(80) NOT NULL,
                                  description VARCHAR(100),
                                  thumbnail_url VARCHAR(255)
                                  )"""
            )
            await cur.execute(
                """CREATE TABLE IF NOT EXISTS tracks (
                                  id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                                  plid INTEGER NOT NULL,
                                  userid INTEGER NOT NULL,
                                  encoded VARCHAR(255) NOT NULL                         
                                  )"""
            )
            await conn.commit()
    async with asqlite.connect("dynamiccooldowns.db") as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """CREATE TABLE IF NOT EXISTS cooldowns (
                                  userid VARCHAR(100) PRIMARY KEY NOT NULL,
                                  expires_at TIMESTAMP NOT NULL
                                  )"""

            )
            await conn.commit() 
