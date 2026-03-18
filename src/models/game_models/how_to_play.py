from pydantic import BaseModel

from src.models.enums.ai_agents_enum import AIAgentEnum


class AgentResponseBase(BaseModel):
    text_response: str
    how_to_play_enum: AIAgentEnum
