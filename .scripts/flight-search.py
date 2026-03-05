#!/usr/bin/env python3
"""Search flights via the Kiwi.com MCP endpoint (mcp.kiwi.com).

Calls the Kiwi MCP server using the MCP Streamable HTTP protocol (JSON-RPC
over HTTP). Returns flight results as JSON to stdout.

Usage:
    python scripts/flight-search.py --from LHR --to MAD --date 01/06/2026
    python scripts/flight-search.py --from LHR --to LIS --date 01/06/2026 --return-date 21/06/2026 --passengers 2
    python scripts/flight-search.py --from LHR --to MAD --date 01/06/2026 --cabin C --sort price --currency USD
"""

import argparse
import json
import sys
import uuid

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)

MCP_ENDPOINT = "https://mcp.kiwi.com/mcp"
MCP_PROTOCOL_VERSION = "2025-03-26"
TOOL_NAME = "search-flight"


def make_jsonrpc(method: str, params: dict | None = None, is_notification: bool = False) -> dict:
    """Build a JSON-RPC 2.0 message."""
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not is_notification:
        msg["id"] = str(uuid.uuid4())
    return msg


def parse_sse_response(text: str) -> dict | None:
    """Parse SSE response to extract JSON-RPC data."""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str:
                try:
                    return json.loads(data_str)
                except json.JSONDecodeError:
                    continue
    return None


def parse_response(response: httpx.Response) -> dict | None:
    """Parse MCP response, handling both plain JSON and SSE formats."""
    content_type = response.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        return parse_sse_response(response.text)
    else:
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            return parse_sse_response(response.text)


def search_flights(args: argparse.Namespace) -> dict:
    """Execute the flight search via MCP protocol."""
    # Build tool arguments matching the Kiwi MCP schema
    tool_args = {
        "flyFrom": args.fly_from,
        "flyTo": args.fly_to,
        "departureDate": args.date,
        "sort": args.sort,
        "curr": args.currency,
        "locale": args.locale,
        "passengers": {
            "adults": args.passengers,
            "children": 0,
            "infants": 0,
        },
    }

    if args.cabin:
        tool_args["cabinClass"] = args.cabin
    if args.return_date:
        tool_args["returnDate"] = args.return_date
    if args.flex:
        tool_args["departureDateFlexRange"] = args.flex
        if args.return_date:
            tool_args["returnDateFlexRange"] = args.flex

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }

    with httpx.Client(timeout=60.0) as client:
        # Step 1: Initialize
        init_msg = make_jsonrpc("initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "flight-search-script", "version": "1.0.0"},
        })

        resp = client.post(MCP_ENDPOINT, json=init_msg, headers=headers)
        resp.raise_for_status()

        init_result = parse_response(resp)
        if not init_result:
            print("Error: Failed to parse initialize response", file=sys.stderr)
            sys.exit(1)

        # Check for session ID
        session_id = resp.headers.get("mcp-session-id")
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        # Step 2: Send initialized notification
        initialized_msg = make_jsonrpc("notifications/initialized", is_notification=True)
        client.post(MCP_ENDPOINT, json=initialized_msg, headers=headers)

        # Step 3: Call the search tool
        call_msg = make_jsonrpc("tools/call", {
            "name": TOOL_NAME,
            "arguments": tool_args,
        })

        resp = client.post(MCP_ENDPOINT, json=call_msg, headers=headers)
        resp.raise_for_status()

        result = parse_response(resp)
        if not result:
            print("Error: Failed to parse search response", file=sys.stderr)
            sys.exit(1)

        return result


def main():
    parser = argparse.ArgumentParser(
        description="Search flights via Kiwi.com MCP endpoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s --from LHR --to MAD --date 01/06/2026
  %(prog)s --from LHR --to LIS --date 01/06/2026 --return-date 21/06/2026 --passengers 2
  %(prog)s --from LHR --to MAD --date 01/06/2026 --cabin C --sort price --currency USD
        """,
    )

    parser.add_argument("--from", dest="fly_from", required=True,
                        help="Departure city or airport code (e.g. LHR, London, LHR)")
    parser.add_argument("--to", dest="fly_to", required=True,
                        help="Destination city or airport code (e.g. MAD, LIS, Paris)")
    parser.add_argument("--date", required=True,
                        help="Departure date in dd/mm/yyyy format")
    parser.add_argument("--return-date", default=None,
                        help="Return date in dd/mm/yyyy format (omit for one-way)")
    parser.add_argument("--passengers", type=int, default=1,
                        help="Number of adult passengers (default: 1)")
    parser.add_argument("--cabin", choices=["M", "W", "C", "F"], default=None,
                        help="Cabin class: M=economy, W=premium, C=business, F=first")
    parser.add_argument("--sort", choices=["price", "duration", "quality", "date"],
                        default="price", help="Sort results by (default: price)")
    parser.add_argument("--currency", default="EUR",
                        help="Currency code (default: EUR)")
    parser.add_argument("--locale", default="en",
                        help="Language for city names and links (default: en)")
    parser.add_argument("--flex", type=int, choices=[0, 1, 2, 3], default=0,
                        help="Date flexibility in days (0-3, default: 0)")

    args = parser.parse_args()

    try:
        result = search_flights(args)
        print(json.dumps(result, indent=2))
    except httpx.HTTPStatusError as e:
        print(f"Error: HTTP {e.response.status_code} from MCP endpoint", file=sys.stderr)
        if e.response.text:
            print(f"Response: {e.response.text[:500]}", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print("Error: Could not connect to mcp.kiwi.com. Check your internet connection.", file=sys.stderr)
        sys.exit(1)
    except httpx.TimeoutException:
        print("Error: Request timed out (60s). Try again.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
