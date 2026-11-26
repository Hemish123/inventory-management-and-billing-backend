import os
import logging
from django.conf import settings
from openai import OpenAI, AsyncOpenAI, AzureOpenAI, AsyncAzureOpenAI

logger = logging.getLogger(__name__)


def is_azure_openai() -> bool:
    """Return True if Azure OpenAI credentials are configured."""
    key = getattr(settings, "AZURE_OPENAI_API_KEY", None) or os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_KEY")
    endpoint = getattr(settings, "AZURE_OPENAI_ENDPOINT", None) or os.environ.get("AZURE_OPENAI_ENDPOINT")
    return bool(key and endpoint)


def get_chat_model() -> str:
    """Return the model deployment / name to use for chat."""
    if is_azure_openai():
        return getattr(settings, "AZURE_OPENAI_DEPLOYMENT", None) or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
    return "gpt-4.1-mini"


def get_embedding_model() -> str:
    """Return the embedding model deployment / name to use."""
    if is_azure_openai():
        return getattr(settings, "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", None) or os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
    return "text-embedding-3-small"


def get_sync_openai_client() -> OpenAI:
    """Return a synchronous OpenAI or AzureOpenAI client."""
    if is_azure_openai():
        key = getattr(settings, "AZURE_OPENAI_API_KEY", None) or os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_KEY")
        endpoint = getattr(settings, "AZURE_OPENAI_ENDPOINT", None) or os.environ.get("AZURE_OPENAI_ENDPOINT")
        version = getattr(settings, "AZURE_OPENAI_API_VERSION", None) or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version=version,
        )
    return OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))


def get_async_openai_client() -> AsyncOpenAI:
    """Return an asynchronous AsyncOpenAI or AsyncAzureOpenAI client."""
    if is_azure_openai():
        key = getattr(settings, "AZURE_OPENAI_API_KEY", None) or os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_KEY")
        endpoint = getattr(settings, "AZURE_OPENAI_ENDPOINT", None) or os.environ.get("AZURE_OPENAI_ENDPOINT")
        version = getattr(settings, "AZURE_OPENAI_API_VERSION", None) or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        return AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version=version,
        )
    return AsyncOpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))
