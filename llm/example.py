"""
Example usage of the OpenAI wrapper.
"""

import asyncio
from llm import OpenAIWrapper


async def main():
    # Example 1: Basic usage
    wrapper = OpenAIWrapper(
        base_url="https://api.openai.com/v1",
        api_key="your-api-key-here",
        model="gpt-4o"
    )

    try:
        response = await wrapper.call("What is Python?")
        print("Response:", response)
    finally:
        await wrapper.close()

    # Example 2: Using context manager (recommended)
    async with OpenAIWrapper(
        base_url="https://api.openai.com/v1",
        api_key="your-api-key-here",
        model="gpt-4o",
        timeout=30.0
    ) as wrapper:
        response = await wrapper.call(
            prompt="Explain recursion in simple terms",
            system_prompt="You are a helpful coding assistant."
        )
        print("Response:", response)

    # Example 3: Using with custom base_url (e.g., for local models or other providers)
    async with OpenAIWrapper(
        base_url="http://localhost:8000/v1",
        api_key="dummy-key",
        model="local-model"
    ) as wrapper:
        response = await wrapper.call("Hello, how are you?")
        print("Response:", response)


if __name__ == "__main__":
    asyncio.run(main())
