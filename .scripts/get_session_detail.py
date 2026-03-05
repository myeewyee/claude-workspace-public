#!/usr/bin/env python3
"""Get full session detail."""

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
import sys
import os

async def get_session_detail(session_id: str):
    mcp_dir = r'<your-workspace-path>\.mcp-server'

    server_params = StdioServerParameters(
        command='python',
        args=[os.path.join(mcp_dir, 'src', 'server.py')],
        env=None
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Get session detail
            result = await session.call_tool('vault_util', arguments={
                'action': 'session_detail',
                'session_id': session_id
            })

            # Write to stdout with UTF-8 encoding
            import sys
            sys.stdout.reconfigure(encoding='utf-8')
            print(result.content[0].text)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python get_session_detail.py <session_id>")
        sys.exit(1)

    session_id = sys.argv[1]
    asyncio.run(get_session_detail(session_id))
