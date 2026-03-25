import urllib.request
import os
import asyncio
import websockets

async def test():
    try:
        from websockets.client import connect
        print("websockets module available")
    except ImportError:
        print("no websockets module")

asyncio.run(test())
