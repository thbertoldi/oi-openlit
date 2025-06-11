"""
title: SUSE AI Monitoring Pipeline
author: Thiago Bertoldi (SUSE)
date: 2025-05-30
version: 1.0
license: Apache 2.0
description: A pipeline for monitoring Open WebUI inside SUSE AI
requirements:  opentelemetry-distro[otlp]==0.54b1
"""

from typing import Optional, List
from pydantic import BaseModel

import json
import uuid
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry import context
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.propagate import inject, extract

class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        pass

    def __init__(self):
        self.type = "filter"
        self.name = "Instrumentation"
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
            }
        )
        self.client = None
        self.tracer = None
        self.tracer_provider = None
        self.chat_traces = {}
        pass

    def setup_client(self):
        self.log("Setting up client")

        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=os.getenv("OTLP_ENDPOINT", "http://opentelemetry-collector.observability.svc.cluster.local:4318/v1/traces")
        )

        # Configure tracer provider
        resource = Resource.create({
            ResourceAttributes.SERVICE_NAME: "suse-ai-filter",
            ResourceAttributes.SERVICE_VERSION: "1.0"
        })
        self.tracer_provider = TracerProvider(resource=resource)
        self.tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(self.tracer_provider)

    async def on_startup(self):
        self.log(f"on_startup:{__name__}")
        self.setup_client()
        pass

    async def on_shutdown(self):
        self.log(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        self.log(f"on_valves_updated:{__name__}")
        self.setup_client()
        pass

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log(f"Inlet function called with body: {body} and user: {user}")
        self.log(json.dumps(body, indent=2))
        metadata = body.get("metadata", {})
        task = metadata.get("task", "")

        if task:
            self.log(f"Skipping {task} task.")
            return body
        if "chat_id" not in metadata:
            chat_id = str(uuid.uuid4())  # Regular chat messages
            self.log(f"Assigned normal chat_id: {chat_id}")

            metadata["chat_id"] = chat_id
            body["metadata"] = metadata
        else:
            chat_id = metadata["chat_id"]

        required_keys = ["model", "messages"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = (
                f"Error: Missing keys in the request body: {', '.join(missing_keys)}"
            )
            self.log(error_message)
            raise ValueError(error_message)

        user_email = "undefined"
        if user is not None:
            user_email = user.get("email")

        #assert chat_id not in self.chat_traces, (
        #    f"There shouldn't be a trace already exists for chat_id {chat_id}"
        #)

        # Create a new trace and span
        self.log(f"Creating new chat trace for chat_id: {chat_id}")

        # Body copy for traces and span
        trace_body = body.copy()
        span_body = body.copy()

        # Extract metadata from body
        metadata = trace_body.pop("metadata", {})
        metadata.update({"chat_id": chat_id, "user_id": user_email})

        # We don't need the model at the trace level
        trace_body.pop("model", None)

        trace_payload = {
            "name": f"{__name__}",
            "input": trace_body,
            "metadata": metadata,
            "thread_id": chat_id,
        }

        self.log(f"[DEBUG] My trace request: {json.dumps(trace_payload, indent=2)}")

        span_metadata = metadata.copy()
        span_metadata.update({"interface": "open-webui"})

        # Extract the model from body
        span_body.pop("model", None)
        # We don't need the metadata in the input for the span
        span_body.pop("metadata", None)

        self.log(f"Span metadata is: {span_metadata}")

        # Extract the model and provider from metadata
        model = body.get("model") or "undefined"
        provider = "ollama"

        span_payload = {
            "name": chat_id,
            "model": model,
            "provider": provider,
            "input": span_body,
            "metadata": span_metadata,
            "type": "llm",
        }

        self.log(f"[DEBUG] My span request: {json.dumps(span_payload, indent=2)}")

        with trace.get_tracer(__name__).start_as_current_span(chat_id) as span:
            # Set attributes on the span
            span.set_attribute("model", model)
            span.set_attribute("provider", provider)
            span.set_attribute("user_email", user_email)
            span.set_attribute("chat_id", chat_id)

            # Inject context into the body (optional, for downstream services)
            ctx = context.get_current()
            inject(metadata)
            body["metadata"] = metadata

            # Add event with body information
            span.add_event("request_body", attributes=body)

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log(f"Outlet function called with body: {body}")
        with trace.get_tracer(__name__).start_as_current_span("outlet") as span:
            span.add_event("response_body", attributes=body)
        return body

    def log(self, message: str):
        print(f"[DEBUG] {message}")
