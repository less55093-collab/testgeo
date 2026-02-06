"""
OpenAI-compatible LLM wrapper for making async API calls.
"""

from typing import Optional
from openai import AsyncOpenAI


class OpenAIWrapper:
    """
    An async wrapper class for making OpenAI-compatible API calls.

    Example:
        wrapper = OpenAIWrapper(
            base_url="https://api.openai.com/v1",
            api_key="your-api-key",
            model="gpt-4o"
        )
        response = await wrapper.call("What is Python?")
        print(response)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 2,
        organization: Optional[str] = None,
        project: Optional[str] = None,
    ):
        """
        Initialize the OpenAI wrapper.

        Args:
            base_url: The base URL for the API endpoint
            api_key: API key for authentication
            model: Model name to use for completions
            timeout: Request timeout in seconds (default: 60.0)
            max_retries: Maximum number of retries (default: 2)
            organization: Optional organization ID
            project: Optional project ID
        """
        self.model = model
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            organization=organization,
            project=project,
        )

    async def call(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Call the LLM with a prompt and return the response.

        Args:
            prompt: The user prompt to send to the model
            system_prompt: Optional system prompt to set model behavior

        Returns:
            The model's response as a string

        Raises:
            openai.APIError: If the API request fails
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Model returned empty response")
        return content

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.close()

    async def __aenter__(self):
        """Support async context manager protocol."""
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Support async context manager protocol."""
        await self.close()
