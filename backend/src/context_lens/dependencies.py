from fastapi import Request

from context_lens.clients.gemini import GeminiClient


def get_gemini_client(request: Request) -> GeminiClient:
    return request.app.state.gemini_client
