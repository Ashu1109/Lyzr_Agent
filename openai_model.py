
import os
from typing import AsyncGenerator
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from litellm import acompletion
import json

class LiteLlm(BaseLlm):
    """LiteLLM wrapper implementation for ADK."""

    def __init__(self, model: str = "gpt-4o"):
        super().__init__(model=model)

    def _safe_serialize(self, obj):
        """Recursively serialize objects, extracting Result values and converting complex objects."""
        # Handle Result objects
        if hasattr(obj, 'value'):
            return self._safe_serialize(obj.value)

        # Handle dict - recursively process values
        if isinstance(obj, dict):
            return {k: self._safe_serialize(v) for k, v in obj.items()}

        # Handle list - recursively process items
        if isinstance(obj, list):
            return [self._safe_serialize(item) for item in obj]

        # Handle basic JSON types
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj

        # Handle objects with __dict__ - convert to dict and recurse
        if hasattr(obj, '__dict__'):
            try:
                obj_dict = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
                return self._safe_serialize(obj_dict)
            except:
                return str(obj)

        # Fallback to string
        return str(obj)

    def _convert_schema_to_dict(self, schema):
        """Converts ADK Schema object to a JSON schema dictionary for OpenAI."""
        if not schema:
            return None
            
        # Handle Type enum
        schema_type = schema.type.value if hasattr(schema.type, 'value') else str(schema.type)
        
        # Map ADK types to OpenAI types
        type_mapping = {
            "STRING": "string",
            "INTEGER": "integer",
            "NUMBER": "number",
            "BOOLEAN": "boolean",
            "ARRAY": "array",
            "OBJECT": "object"
        }
        
        json_schema = {
            "type": type_mapping.get(schema_type, "string") # Default to string if unknown
        }
        
        if schema.description:
            json_schema["description"] = schema.description
            
        if schema.properties:
            json_schema["properties"] = {
                k: self._convert_schema_to_dict(v) for k, v in schema.properties.items()
            }
            
        if schema.required:
            json_schema["required"] = schema.required
            
        if schema.items:
            json_schema["items"] = self._convert_schema_to_dict(schema.items)
            
        if schema.enum:
            json_schema["enum"] = schema.enum
            
        return json_schema

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        
        messages = []
        
        # Add system instruction if present
        if llm_request.config and llm_request.config.system_instruction:
            messages.append({
                "role": "system",
                "content": llm_request.config.system_instruction
            })

        # Map ADK tools to OpenAI tools
        openai_tools = []
        tools = []
        if llm_request.config and llm_request.config.tools:
            tools = llm_request.config.tools
        
        if tools:
            for tool in tools:
                if hasattr(tool, 'function_declarations'):
                    for func in tool.function_declarations:
                        openai_tools.append({
                            "type": "function",
                            "function": {
                                "name": func.name,
                                "description": func.description,
                                "parameters": self._convert_schema_to_dict(func.parameters) or {"type": "object", "properties": {}}
                            }
                        })

        # Convert ADK contents to OpenAI messages
        for content in llm_request.contents:
            role = "user" if content.role == "user" else "assistant"
            if content.role == "model": role = "assistant"

            # Handle parts
            content_text = ""
            tool_calls = []
            tool_responses = []  # Changed to list to handle multiple tool responses

            for part in content.parts:
                if part.text:
                    content_text += part.text
                elif part.function_call:
                    # Previous model output with tool call
                    tool_calls.append({
                        "id": part.function_call.id or "call_unknown", # OpenAI needs ID
                        "type": "function",
                        "function": {
                            "name": part.function_call.name,
                            "arguments": json.dumps(part.function_call.args) if isinstance(part.function_call.args, dict) else part.function_call.args
                        }
                    })
                elif part.function_response:
                    # Tool output - collect all responses
                    # Handle Result objects from tools using recursive safe serialization
                    response_data = part.function_response.response
                    print(f"DEBUG: Processing function response, type: {type(response_data)}")

                    # Use safe serialization to handle nested Result objects
                    try:
                        serialized_data = self._safe_serialize(response_data)
                        content = json.dumps(serialized_data) if not isinstance(serialized_data, str) else serialized_data
                        print(f"DEBUG: Successfully serialized response, length: {len(content)}")
                    except Exception as e:
                        print(f"ERROR: Failed to serialize response: {e}")
                        content = f"Error: Could not serialize response - {str(response_data)[:100]}"

                    tool_responses.append({
                        "role": "tool",
                        "tool_call_id": part.function_response.id or "call_unknown",
                        "content": content
                    })

            # Append all tool responses (important: each tool response is a separate message)
            if tool_responses:
                for tool_response in tool_responses:
                    messages.append(tool_response)
            elif tool_calls:
                messages.append({
                    "role": role,
                    "content": content_text or None,
                    "tool_calls": tool_calls
                })
            elif content_text:
                messages.append({
                    "role": role,
                    "content": content_text
                })

        # ------------------------------------------------------------------
        # Sanity check + cleanup:
        # LiteLLM/OpenAI require that every assistant message with tool_calls
        # has *corresponding* tool messages with matching tool_call_id.
        #
        # Old or partially-hydrated sessions might contain assistant messages
        # with tool_calls whose IDs have no matching tool responses, which
        # triggers errors like:
        #   "An assistant message with 'tool_calls' must be followed by
        #    tool messages ... tool_call_ids did not have response messages"
        #
        # To make the history robust, we:
        #   1. Collect all tool_call_ids that actually have tool responses.
        #   2. For each assistant message with tool_calls:
        #      - Keep only tool_calls whose id appears in that set.
        #      - If none remain and the message has content, drop tool_calls.
        #      - If none remain and no content, drop the message entirely.
        # ------------------------------------------------------------------
        tool_response_ids = set()
        for msg in messages:
            if msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id")
                if tc_id:
                    tool_response_ids.add(tc_id)

        cleaned_messages = []
        for msg in messages:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                original_tool_calls = msg.get("tool_calls") or []
                # Keep only tool calls that we actually have responses for
                filtered_tool_calls = [
                    tc for tc in original_tool_calls
                    if tc.get("id") in tool_response_ids
                ]

                if filtered_tool_calls:
                    new_msg = dict(msg)
                    new_msg["tool_calls"] = filtered_tool_calls
                    cleaned_messages.append(new_msg)
                else:
                    # No valid tool_calls remain
                    if msg.get("content"):
                        new_msg = dict(msg)
                        new_msg.pop("tool_calls", None)
                        cleaned_messages.append(new_msg)
                    # If there's no content and no valid tool_calls, we skip it
            else:
                cleaned_messages.append(msg)

        messages = cleaned_messages

        try:
            # Call OpenAI API
            # Note: Streaming with tools is complex. For now, disable streaming if tools are present or just handle non-streaming for tools.
            # To keep it simple and robust: if tools are available, force non-streaming for the decision turn.

            use_stream = stream and not openai_tools

            kwargs = {
                "model": self.model,
                "messages": messages,
                "stream": use_stream
            }
            if openai_tools:
                kwargs["tools"] = openai_tools

            # Debug: Log the messages being sent to OpenAI
            print(f"DEBUG: Sending {len(messages)} messages to OpenAI")
            for i, msg in enumerate(messages):
                role = msg.get('role', 'unknown')
                has_tool_calls = 'tool_calls' in msg
                is_tool_response = role == 'tool'
                print(f"  Message {i}: role={role}, tool_calls={has_tool_calls}, tool_response={is_tool_response}")

            response = await acompletion(**kwargs)

            if use_stream:
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content_text = chunk.choices[0].delta.content
                        yield LlmResponse(
                            content=types.Content(
                                role="model",
                                parts=[types.Part(text=content_text)]
                            ),
                            partial=True
                        )
            else:
                message = response.choices[0].message
                parts = []
                
                if message.content:
                    parts.append(types.Part(text=message.content))
                
                if message.tool_calls:
                    for tc in message.tool_calls:
                        parts.append(types.Part(
                            function_call=types.FunctionCall(
                                id=tc.id,
                                name=tc.function.name,
                                args=json.loads(tc.function.arguments)
                            )
                        ))
                
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=parts
                    ),
                    turn_complete=True
                )

        except Exception as e:
            print(f"Litellm Error: {e}")
            yield LlmResponse(
                error_code="OPENAI_ERROR",
                error_message=str(e)
            )
