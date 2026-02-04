"""
UTF-8 safe stream decoder for handling incomplete multi-byte sequences.

This module provides utilities for safely decoding UTF-8 byte streams where
chunks may split multi-byte characters across packet boundaries.
"""

from typing import AsyncIterator, Tuple


class StreamDecoder:
    """
    A stateful UTF-8 stream decoder that handles incomplete multi-byte sequences.

    When network data is chunked, UTF-8 multi-byte characters may be split across
    chunks. This decoder buffers incomplete sequences and combines them with the
    next chunk for proper decoding.

    Example:
        >>> decoder = StreamDecoder()
        >>> text, complete = decoder.decode(b"Hello \\xe4\\xb8")  # Incomplete Chinese char
        >>> print(text)  # "Hello "
        >>> text, complete = decoder.decode(b"\\x96\\xe7\\x95\\x8c")  # Rest of "世界"
        >>> print(text)  # "世界"
    """

    def __init__(self) -> None:
        """Initialize the decoder with an empty buffer."""
        self._pending_bytes: bytes = b""

    def decode(self, chunk_bytes: bytes) -> Tuple[str, bool]:
        """
        Decode a chunk of bytes, handling incomplete UTF-8 sequences.

        Args:
            chunk_bytes: The bytes to decode.

        Returns:
            A tuple of (decoded_text, is_complete) where:
            - decoded_text: The successfully decoded text
            - is_complete: True if all bytes were decoded, False if some are pending
        """
        # Combine pending bytes with new chunk
        chunk_bytes = self._pending_bytes + chunk_bytes
        self._pending_bytes = b""

        try:
            # Try to decode the entire chunk
            return chunk_bytes.decode("utf-8"), True
        except UnicodeDecodeError:
            # Find the last valid UTF-8 boundary
            # UTF-8 continuation bytes are 10xxxxxx (0x80-0xBF)
            # We need to find where the incomplete sequence starts
            for i in range(1, min(4, len(chunk_bytes) + 1)):
                try:
                    decoded = chunk_bytes[:-i].decode("utf-8")
                    self._pending_bytes = chunk_bytes[-i:]
                    return decoded, False
                except UnicodeDecodeError:
                    continue

            # If we can't decode even after removing up to 3 bytes,
            # store the entire chunk for the next iteration
            self._pending_bytes = chunk_bytes
            return "", False

    def flush(self) -> str:
        """
        Flush any remaining pending bytes.

        This should be called at the end of the stream to handle any
        remaining bytes. Uses 'replace' error handling for invalid sequences.

        Returns:
            The decoded text from remaining bytes, or empty string if none.
        """
        if self._pending_bytes:
            try:
                result = self._pending_bytes.decode("utf-8", errors="replace")
            except Exception:
                result = ""
            self._pending_bytes = b""
            return result
        return ""

    @property
    def has_pending(self) -> bool:
        """Check if there are pending bytes waiting to be decoded."""
        return len(self._pending_bytes) > 0


async def decode_stream_chunks(
    chunk_iterator: AsyncIterator[bytes],
) -> AsyncIterator[str]:
    """
    Async generator that safely decodes UTF-8 byte chunks.

    This is a convenience wrapper around StreamDecoder for use with
    async iterators.

    Args:
        chunk_iterator: An async iterator yielding byte chunks.

    Yields:
        Decoded text strings.

    Example:
        >>> async for text in decode_stream_chunks(response.content.iter_any()):
        ...     print(text)
    """
    decoder = StreamDecoder()

    async for chunk_bytes in chunk_iterator:
        if chunk_bytes:
            text, _ = decoder.decode(chunk_bytes)
            if text:
                yield text

    # Flush any remaining bytes
    remaining = decoder.flush()
    if remaining:
        yield remaining
