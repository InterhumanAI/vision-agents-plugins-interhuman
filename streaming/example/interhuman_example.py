"""Run a Vision Agents bot with Interhuman streaming analysis enabled.

Usage:
    cd streaming/example
    cp env.example .env  # fill in keys
    uv run interhuman_example.py
"""

import logging

from dotenv import load_dotenv
from vision_agents.core import Agent, Runner, User
from vision_agents.core.agents import AgentLauncher
from vision_agents.plugins import (
    deepgram,
    elevenlabs,
    getstream,
    interhuman_streaming as interhuman,
    openai,
)

logger = logging.getLogger(__name__)

load_dotenv()


async def create_agent(**kwargs) -> Agent:
    """Create the agent with Interhuman analysis enabled."""
    interhuman_processor = interhuman.InterhumanProcessor(
        include=[
            "conversation_quality_overall",
            "conversation_quality_timeline",
        ],
        window_seconds=5.0,
    )

    agent = Agent(
        edge=getstream.Edge(),
        agent_user=User(name="Interhuman Demo Bot", id="interhuman-bot"),
        instructions=(
            "You are an empathetic conversation partner. When the user shows "
            "confusion, slow down and clarify. When they show agreement, build "
            "on their last point."
        ),
        llm=openai.LLM(model="gpt-4o-mini"),
        stt=deepgram.STT(),
        tts=elevenlabs.TTS(),
        processors=[interhuman_processor],
    )

    @agent.events.subscribe
    async def on_signal(event: interhuman.InterhumanSignalEvent) -> None:
        if event.phase == "detected":
            logger.info(
                "Interhuman signal: %s (%s) at %.1fs — %s",
                event.signal_type,
                event.probability,
                event.start,
                event.rationale,
            )

    @agent.events.subscribe
    async def on_engagement(event: interhuman.InterhumanEngagementEvent) -> None:
        logger.info("Interhuman engagement: %s at %.1fs", event.state, event.start)

    @agent.events.subscribe
    async def on_quality(event: interhuman.InterhumanConversationQualityEvent) -> None:
        if event.overall is not None:
            logger.info(
                "CQI: %d (clarity=%d authority=%d energy=%d rapport=%d learning=%d)",
                event.overall.quality_index,
                event.overall.clarity,
                event.overall.authority,
                event.overall.energy,
                event.overall.rapport,
                event.overall.learning,
            )

    return agent


async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs) -> None:
    """Join the call and start the agent."""
    call = await agent.create_call(call_type, call_id)

    async with agent.join(call):
        await agent.finish()


if __name__ == "__main__":
    Runner(AgentLauncher(create_agent=create_agent, join_call=join_call)).cli()
