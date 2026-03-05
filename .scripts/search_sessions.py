#!/usr/bin/env python3
"""Search vault sessions for specific content."""

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
import json
import sys
import os

async def search_sessions(query: str, limit: int = 10):
    # Use Windows-style path
    mcp_dir = r'<your-workspace-path>\.mcp-server'

    server_params = StdioServerParameters(
        command='python',
        args=[os.path.join(mcp_dir, 'src', 'server.py')],
        env=None
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Search for sessions
            result = await session.call_tool('vault_sessions', arguments={
                'query': query,
                'limit': limit
            })

            # The result is already a string, just print it
            print(result.content[0].text)

if __name__ == '__main__':
    query = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'Context7 MCP framework terminology procedural memory'
    asyncio.run(search_sessions(query))
