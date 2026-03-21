# Deprecated: Legacy type definitions for the v2 ARGO gateway pipeline (--legacy-argo).
# In v3.0.0, type handling is performed by llm-rosetta IR types via dispatch.py.
#
# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing import List, Literal, Optional

from pydantic import BaseModel

FINISH_REASONS = Literal["stop", "length", "content_filter"]


class CompletionUsage(BaseModel):
    completion_tokens: int
    """Number of tokens in the generated completion."""

    prompt_tokens: int
    """Number of tokens in the prompt."""

    total_tokens: int
    """Total number of tokens used in the request (prompt + completion)."""


class CompletionChoice(BaseModel):
    finish_reason: FINISH_REASONS
    """The reason the model stopped generating tokens.

    This will be `stop` if the model hit a natural stop point or a provided stop
    sequence, `length` if the maximum number of tokens specified in the request was
    reached, or `content_filter` if content was omitted due to a flag from our
    content filters.
    """

    index: int

    text: str


class Completion(BaseModel):
    id: str
    """A unique identifier for the completion."""

    choices: List[CompletionChoice]
    """The list of completion choices the model generated for the input prompt."""

    created: int
    """The Unix timestamp (in seconds) of when the completion was created."""

    model: str
    """The model used for completion."""

    object: Literal["text_completion"] = "text_completion"
    """The object type, which is always "text_completion" """

    system_fingerprint: Optional[str] = None
    """This fingerprint represents the backend configuration that the model runs with.

    Can be used in conjunction with the `seed` request parameter to understand when
    backend changes have been made that might impact determinism.
    """

    usage: Optional[CompletionUsage] = None
    """Usage statistics for the completion request."""
