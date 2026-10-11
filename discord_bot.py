"""Discord bot: a warm, calming companion that answers questions about your UBC
status using local RAG retrieval over src/context/ (falls back to the whole brief
if the RAG server isn't running).

Cost control (Gemini API is pay-per-token, with a free tier):
  - Uses Gemini Flash by default (cheapest/fastest tier) -- override with DISCORD_BOT_MODEL.
  - Single-turn requests only (no tool-use loop, no conversation history kept),
    so each message costs roughly one input+output pass, not a growing chain.
  - Only responds to DMs or when @mentioned, so it doesn't answer every message
    in a busy server channel.
  - RAG retrieval sends only the top few relevant chunks, not the whole brief, so
    prompts stay small even as more context files get added under src/context/.

Duo push notifications are handled separately by src/cwl.py via a Discord webhook
(DISCORD_DUO_WEBHOOK_URL) -- that doesn't need this bot process running at all.
"""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
import requests
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("DISCORD_BOT_MODEL", "gemini-3.6-flash")
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://127.0.0.1:5056")

# Only this user, only in DMs, may chat with the bot -- everyone/everything else is declined.
OWNER_ID = 695703574465740851

BRIEF_PATH = Path(__file__).resolve().parent / "src" / "context" / "ubc-brief.txt"
BRIEF_MAX_CHARS = 6000

# UBC's local timezone -- used to tell the model "now" explicitly rather than relying
# on the brief's own stale timestamp or the model's training-data sense of time.
TIMEZONE = ZoneInfo("America/Vancouver")

SYSTEM_PROMPT = """You are Willow, a warm, sweet, and calming study companion for a UBC student.
Speak gently and reassuringly, and stay calm and encouraging even when discussing overdue work
or tight deadlines -- never alarmist, never guilt-tripping. Use soft, cozy language and the
occasional gentle emoji, but don't overdo it. Keep answers concise and easy to read on a phone.
Prefer short paragraphs or a few bullet points over long walls of text.

Current date/time: {now}

You have the following retrieved context relevant to the student's question. Answer using it,
and use the current date/time above (not any "updated" timestamp inside the context) to reason
about how much time is left before deadlines. If asked about something not covered here, say so
gently rather than guessing.

--- CONTEXT ---
{brief}
--- END CONTEXT ---
"""

EMBED_COLOR = 0xF6C9D0  # soft pink

genai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def _load_brief() -> str:
    if BRIEF_PATH.exists():
        return BRIEF_PATH.read_text(encoding="utf-8")[:BRIEF_MAX_CHARS]
    return "(no brief available yet)"


def _retrieve_context(question: str) -> str:
    """Ask the local RAG server for the chunks most relevant to this question.
    Falls back to the whole brief if the RAG server is down/unreachable."""
    try:
        resp = requests.post(f"{RAG_SERVER_URL}/query", json={"question": question, "top_k": 4}, timeout=5)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return "\n\n".join(f"[{r['source']}]\n{r['text']}" for r in results)
    except Exception:
        pass
    return _load_brief()


def _current_time_str() -> str:
    return datetime.now(TIMEZONE).strftime("%A, %B %d, %Y, %I:%M %p %Z")


def _ask_gemini(question: str) -> str:
    if not genai_client:
        return "I don't have my Gemini API key set up yet (GEMINI_API_KEY in .env), so I can't chat just yet."
    response = genai_client.models.generate_content(
        model=MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT.format(brief=_retrieve_context(question), now=_current_time_str())
        ),
    )
    return response.text or "..."


@client.event
async def on_ready():
    print(f"logged in as {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    mentioned = bool(client.user and client.user in message.mentions)
    if not is_dm and not mentioned:
        return  # unrelated channel chatter -- ignore entirely, no API call

    if not is_dm or message.author.id != OWNER_ID:
        await message.reply("I'm only able to chat privately with my person right now, so I can't help here.")
        return

    question = message.content.replace(f"<@{client.user.id}>", "").strip() if client.user else message.content

    async with message.channel.typing():
        answer = _ask_gemini(question)

    embed = discord.Embed(description=answer, color=EMBED_COLOR)
    embed.set_author(name="Willow")
    embed.set_footer(text="take a breath, you've got this")
    await message.reply(embed=embed)


if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        raise SystemExit("Set DISCORD_BOT_TOKEN in .env first.")
    client.run(DISCORD_BOT_TOKEN)
