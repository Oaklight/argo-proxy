"""
Deprecated functions from output_handle.py

This file contains deprecated streaming-related functions that are no longer used
in the main codebase but are preserved for reference.
"""

import inspect
import json
from typing import (
    Union,
    cast,
    overload,
)
from collections.abc import AsyncIterator, Iterator


class DeprecatedToolInterceptor:
    """Deprecated streaming-based tool interceptor"""

    def __init__(self):
        self.buffer = ""
        self.in_tool_call = False
        self.tool_call_buffer = ""

    def _could_be_partial_tag(self, text: str) -> bool:
        """Check if text could be a partial tag"""
        # Check for partial opening tag
        for i in range(1, min(len(text) + 1, 12)):  # '<tool_call>' is 11 chars
            if text.endswith("<tool_call>"[:i]):
                return True

        # Check for partial closing tag
        for i in range(1, min(len(text) + 1, 13)):  # '</tool_call>' is 12 chars
            if text.endswith("</tool_call>"[:i]):
                return True

        return False

    def _process_chunk_logic(self, chunk: str) -> list[tuple[dict | None, str | None]]:
        """Core logic for processing a single chunk, returns list of (tool_call, text) tuples"""
        results = []
        self.buffer += chunk

        while True:
            if not self.in_tool_call:
                start_idx = self.buffer.find("<tool_call>")
                if start_idx == -1:
                    # No complete tool call start found
                    if self._could_be_partial_tag(self.buffer):
                        # Might be partial tag at end, keep in buffer
                        break
                    else:
                        # Safe to emit all as text
                        if self.buffer:
                            results.append((None, self.buffer))
                        self.buffer = ""
                        break
                else:
                    # Emit text before tool call
                    if start_idx > 0:
                        results.append((None, self.buffer[:start_idx]))
                    self.buffer = self.buffer[start_idx + len("<tool_call>") :]
                    self.in_tool_call = True
                    self.tool_call_buffer = ""
            else:
                end_idx = self.buffer.find("</tool_call>")
                if end_idx == -1:
                    # End tag not found yet
                    if self._could_be_partial_tag(self.buffer):
                        # Might have partial end tag, keep some in buffer
                        safe_length = max(
                            0, len(self.buffer) - 11
                        )  # Length of '</tool_call>'
                        if safe_length > 0:
                            self.tool_call_buffer += self.buffer[:safe_length]
                            self.buffer = self.buffer[safe_length:]
                    else:
                        # No partial tag possible, buffer all
                        self.tool_call_buffer += self.buffer
                        self.buffer = ""
                    break
                else:
                    # Found end tag
                    self.tool_call_buffer += self.buffer[:end_idx]
                    try:
                        tool_call_json = json.loads(self.tool_call_buffer.strip())
                        results.append((tool_call_json, None))
                    except json.JSONDecodeError:
                        # Invalid JSON
                        results.append(
                            (None, f"<invalid>{self.tool_call_buffer}</invalid>")
                        )

                    self.buffer = self.buffer[end_idx + len("</tool_call>") :]
                    self.in_tool_call = False
                    self.tool_call_buffer = ""

        return results

    def _finalize_processing(self) -> list[tuple[dict | None, str | None]]:
        """Handle any remaining content after all chunks are processed"""
        results = []
        if self.in_tool_call:
            # Unclosed tool call
            if self.tool_call_buffer or self.buffer:
                results.append(
                    (None, f"<invalid>{self.tool_call_buffer}{self.buffer}</invalid>")
                )
        elif self.buffer:
            results.append((None, self.buffer))
        return results

    @overload
    def process_stream(
        self, chunk_iterator: Iterator[str]
    ) -> Iterator[tuple[dict | None, str | None]]: ...

    @overload
    def process_stream(
        self, chunk_iterator: AsyncIterator[str]
    ) -> AsyncIterator[tuple[dict | None, str | None]]: ...

    def process_stream(
        self, chunk_iterator: Union[Iterator[str], AsyncIterator[str]]
    ) -> Union[
        Iterator[tuple[dict | None, str | None]],
        AsyncIterator[tuple[dict | None, str | None]],
    ]:
        """
        Process chunks and yield tool calls or text as they complete.

        The return type matches the input iterator type:
        - If chunk_iterator is sync Iterator, returns sync Iterator
        - If chunk_iterator is async AsyncIterator, returns AsyncIterator

        Yields:
            (tool_call_dict, None) when a tool_call is fully parsed
            (None, text_chunk) for regular text between tool calls
        """
        # Reset state
        self.buffer = ""
        self.in_tool_call = False
        self.tool_call_buffer = ""

        # Check if the iterator is async
        if hasattr(chunk_iterator, "__aiter__") or inspect.isasyncgen(chunk_iterator):
            return self._process_async_iterator(
                cast(AsyncIterator[str], chunk_iterator)
            )
        else:
            return self._process_sync_iterator(cast(Iterator[str], chunk_iterator))

    def _process_sync_iterator(
        self, chunk_iterator: Iterator[str]
    ) -> Iterator[tuple[dict | None, str | None]]:
        """Process synchronous iterator"""
        for chunk in chunk_iterator:
            results = self._process_chunk_logic(chunk)
            for result in results:
                yield result

        # Handle any remaining content
        final_results = self._finalize_processing()
        for result in final_results:
            yield result

    async def _process_async_iterator(
        self, chunk_iterator: AsyncIterator[str]
    ) -> AsyncIterator[tuple[dict | None, str | None]]:
        """Process asynchronous iterator"""
        async for chunk in chunk_iterator:
            results = self._process_chunk_logic(chunk)
            for result in results:
                yield result

        # Handle any remaining content
        final_results = self._finalize_processing()
        for result in final_results:
            yield result
