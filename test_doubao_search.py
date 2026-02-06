
import os
import asyncio
import json
import httpx
from openai import AsyncOpenAI

# Read config
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        doubao_config = config['providers']['doubao']
        api_key = doubao_config['accounts'][0]['api_key']
        endpoint_id = doubao_config.get('endpoint_id')
except Exception:
    endpoint_id = "your_endpoint_id"
    api_key = "your_api_key"

print(f"Endpoint: {endpoint_id}")

async def test_variants():
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    base_payload = {
        "model": endpoint_id,
        "messages": [{"role": "user", "content": "北京今天天气怎么样"}],
        "stream": False
    }

    # Variant 1: tools with type="web_search" (Original - Failed)
    print("\n--- Variant 1: tools type=web_search ---")
    payload = base_payload.copy()
    payload["tools"] = [{
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_query": "北京今天天气怎么样"
        }
    }]
    await run_request(url, headers, payload)

    # Variant 2: Root web_search object
    print("\n--- Variant 2: Root web_search object ---")
    payload = base_payload.copy()
    payload["web_search"] = {
        "enable": True,
        "search_query": "北京今天天气怎么样"
    }
    await run_request(url, headers, payload)

    # Variant 3: function tooling
    print("\n--- Variant 3: tools type=function name=web_search ---")
    payload = base_payload.copy()
    payload["tools"] = [{
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Call this to search the web",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            }
        }
    }]
    await run_request(url, headers, payload)

async def run_request(url, headers, payload):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            print(f"Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"Error: {resp.text[:500]}") # Print first 500 chars
            else:
                print("Success!")
                print(str(resp.json())[:200] + "...")
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_variants())
