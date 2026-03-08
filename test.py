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


def is_auth_error(e):
    msg = str(e).lower()
    return any(x in msg for x in ["auth", "key", "401", "403", "unauthorized"])


async def test():
    print(f"Testing {URL}\n")

    # Test 1: no key — should be rejected
    print("[ no API key — expect failure ]")
    try:
        async with Client(URL) as c:
            await search(c)
            print("✗ request succeeded — server should require X-OpenAI-Key\n")
    except Exception as e:
        if is_auth_error(e):
            print(f"✓ correctly rejected — API key required\n")
        else:
            print(f"✗ rejected but not an auth error — {e}\n")

    # Test 2: valid key — should work
    print("[ valid X-OpenAI-Key header — expect success ]")
    if not OPENAI_API_KEY:
        print("  skipped — OPENAI_API_KEY not in env\n")
    else:
        try:
            async with Client(URL, headers={"X-OpenAI-Key": OPENAI_API_KEY}) as c:
                text = await search(c)
                print(f"✓ worked\n  {text[:100].strip()}...\n")
        except Exception as e:
            print(f"✗ failed — {e}\n")

    # Test 3: bad key — should be rejected with auth error
    print("[ bad X-OpenAI-Key header — expect auth failure ]")
    try:
        async with Client(URL, headers={"X-OpenAI-Key": "sk-bad-key"}) as c:
            await search(c)
            print("✗ bad key was accepted — server is not validating keys\n")
    except Exception as e:
        if is_auth_error(e):
            print(f"✓ correctly rejected — API key error\n")
        else:
            print(f"✗ rejected but not an auth error — {e}\n")


asyncio.run(test())
