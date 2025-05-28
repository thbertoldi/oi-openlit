"""
title: OpenLIT monitoring pipeline
author: open-webui
date: 2024-05-30
version: 1.0
license: MIT
description: A pipeline for monitoring open-webui with openlit.
requirements: openlit==1.33.8, openai==1.61.1
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from openai import OpenAI
import openlit


class Pipeline:
    def __init__(self):
        self.name = "Instrumented"
        pass

    async def on_startup(self):
        print(f"on_startup:{__name__}")

        # Start openlit collecting metrics
        OTEL_ENDPOINT = (
            "http://opentelemetry-collector.observability.svc.cluster.local:4318"
        )
        openlit.init(
            otlp_endpoint=OTEL_ENDPOINT,
            disable_batch=True,
            trace_content=True,
            application_name="OI Pipeline",
            collect_gpu_stats=False,
        )
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        client = OpenAI(
            base_url="http://ollama.suse-private-ai.svc.cluster.local:11434/v1",
            api_key="token-abc123",  # ignored by Ollama
        )

        completion = client.chat.completions.create(
            model="gemma:2b",
            messages=[{"role": "user", "content": user_message}],
        )

        print(completion.choices[0].message.content)

        return completion.choices[0].message.content
