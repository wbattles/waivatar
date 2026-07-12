#!/usr/bin/env python3
"""
waivatar — quick test
Usage:
    python tst.py                                # local
    python tst.py https://waivatar.waisuite.com  # hosted
"""

import asyncio, sys, os
from fastmcp import Client

URL = (sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080") + "/mcp"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


async def search(client):
    r = await client.call_tool("search_avatar_wiki", {"query": "Jake Sully"})
    return r.content[0].text

async def test():
    print(f"Testing {URL}\n")

    try:
        async with Client(URL, headers={"X-OpenAI-Key": OPENAI_API_KEY}) as c:
            text = await search(c)
            print(f"✓ worked\n  {text[:100].strip()}...\n")
    except Exception as e:
        print(f"✗ failed — {e}\n")

asyncio.run(test())
