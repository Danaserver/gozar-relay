"""
Calling OpenRouter and Gemini from inside Iran through Gozar.

If the service has a *managed* key in the panel, pass your Gozar access key as
the api_key — the real provider key never leaves the relay. Otherwise
(passthrough mode) put the access key in the URL and use your own provider key.

    pip install openai google-genai
    RELAY=https://relay.telo.ir RELAY_KEY=gz_xxx python ai_clients.py
"""

import os

RELAY = os.environ.get("RELAY", "https://relay.telo.ir")
RELAY_KEY = os.environ["RELAY_KEY"]


def openrouter_managed():
    from openai import OpenAI

    client = OpenAI(base_url=RELAY + "/openrouter/api/v1", api_key=RELAY_KEY)
    stream = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": "یک جملهٔ کوتاه دربارهٔ تهران بنویس."}],
        stream=True,
    )
    for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="", flush=True)
    print()


def openrouter_passthrough(own_key):
    from openai import OpenAI

    client = OpenAI(base_url="{}/{}/openrouter/api/v1".format(RELAY, RELAY_KEY), api_key=own_key)
    print(client.models.list().data[0].id)


def gemini_managed():
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=RELAY_KEY, http_options=types.HttpOptions(base_url=RELAY + "/gemini"))
    print(client.models.generate_content(model="gemini-2.5-flash", contents="سلام!").text)


if __name__ == "__main__":
    openrouter_managed()
    gemini_managed()
