import asyncio
import random

import zendriver as zd
from zendriver import Tab, cdp


async def wait_for_element(page: Tab, selector: str, timeout: float = 30.0) -> object:
    """Wait for an element to appear on the page."""
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            element = await page.select(selector)
            if element:
                return element
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Element {selector} not found after {timeout} seconds")


async def wait_for_generation_complete(page: Tab) -> None:
    """Wait for the generation to complete by monitoring the break button."""
    await asyncio.sleep(1)

    try:
        break_btns = await page.select_all('[class*="break-btn-"]')

        if break_btns:
            break_btn = break_btns[0]

            while True:
                class_attr = break_btn.attrs.get("class", "")
                if "hidden" in class_attr:
                    break
                await asyncio.sleep(0.5)

                break_btns = await page.select_all('[class*="break-btn-"]')
                if break_btns:
                    break_btn = break_btns[0]
                else:
                    break

            while True:
                break_btns = await page.select_all('[class*="break-btn-"]')
                if not break_btns:
                    break

                break_btn = break_btns[0]
                class_attr = break_btn.attrs.get("class", "")

                if "hidden" not in class_attr:
                    break

                await asyncio.sleep(0.5)

    except Exception as e:
        print(f"Warning: Error waiting for generation to complete: {e}")


async def extract_response(page: Tab) -> str | None:
    """Extract the model's response from message containers."""
    try:
        message_containers = await page.select_all(
            '[class^="message-block-container-"]'
        )

        if message_containers:
            last_message = message_containers[-1]
            response_text = last_message.text_all
            return response_text
        else:
            print("Warning: No message containers found")
            return None
    except Exception as e:
        print(f"Error extracting response: {e}")
        return None


async def send_message(page: Tab, message: str) -> None:
    """Send a message in the chat."""
    textarea = await page.select("textarea.semi-input-textarea")
    await textarea.clear_input()
    await textarea.send_keys(message)

    await page.send(
        cdp.input_.dispatch_key_event(
            type_="keyDown",
            key="Enter",
            code="Enter",
            windows_virtual_key_code=13,
        )
    )
    await page.send(
        cdp.input_.dispatch_key_event(
            type_="keyUp",
            key="Enter",
            code="Enter",
            windows_virtual_key_code=13,
        )
    )


async def main() -> None:
    browser = await zd.start(headless=False)

    try:
        page = await browser.get("https://www.doubao.com/chat/")

        print("Waiting for textarea to appear...")
        await wait_for_element(page, "textarea.semi-input-textarea")

        await asyncio.sleep(2)

        print("Sending initial query...")
        await send_message(page, "上海女健身教练上门推荐")

        iteration = 1

        while True:
            print(f"\n--- Iteration {iteration} ---")

            print("Waiting for generation to complete...")
            await wait_for_generation_complete(page)

            print("Extracting response...")
            response = await extract_response(page)

            if response:
                print(f"Response preview: {response[:200]}...")
            else:
                print("Failed to extract response")

            wait_time = random.randint(5, 10)
            print(f"Waiting {wait_time} seconds before continuing...")
            await asyncio.sleep(wait_time)

            print("Sending 'continue' message...")
            await send_message(page, "继续")

            iteration += 1

    except KeyboardInterrupt:
        print("\nStopping automation...")
    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
