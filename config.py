"""Configuration loader for Raspbotv2 Treasure Hunt."""

import os
from dataclasses import dataclass
from typing import Callable

from azure.identity import ClientSecretCredential, get_bearer_token_provider
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ServicePrincipalConfig:
    tenant_id: str = os.getenv("AZURE_SP_TENANT_ID", "")
    client_id: str = os.getenv("AZURE_SP_CLIENT_ID", "")
    client_secret: str = os.getenv("AZURE_SP_CLIENT_SECRET", "")

    def get_credential(self) -> ClientSecretCredential:
        """Create a ClientSecretCredential from the service principal config."""
        return ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

    def get_token_provider(self) -> Callable[[], str]:
        """Create a bearer token provider for Azure OpenAI."""
        credential = self.get_credential()
        return get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )


@dataclass
class AzureOpenAIConfig:
    endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    orchestrator_deployment: str = os.getenv("AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT", "gpt-5.4-mini")
    vision_deployment: str = os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT", "gpt-5.4")
    planner_deployment: str = os.getenv("AZURE_OPENAI_PLANNER_DEPLOYMENT", "o3")
    embedding_deployment: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")


@dataclass
class AzureSpeechConfig:
    key: str = os.getenv("AZURE_SPEECH_KEY", "")
    region: str = os.getenv("AZURE_SPEECH_REGION", "australiaeast")
    resource_id: str = os.getenv("AZURE_SPEECH_RESOURCE_ID", "")


@dataclass
class AzureSearchConfig:
    endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    key: str = os.getenv("AZURE_SEARCH_KEY", "")
    index_name: str = os.getenv("AZURE_SEARCH_INDEX", "ringo-memory")


@dataclass
class SafetyConfig:
    max_motor_speed: int = int(os.getenv("MAX_MOTOR_SPEED", "75"))
    obstacle_stop_distance_mm: int = int(os.getenv("OBSTACLE_STOP_DISTANCE_MM", "150"))
    max_session_minutes: int = int(os.getenv("MAX_SESSION_MINUTES", "15"))


@dataclass
class HardwareConfig:
    voice_module_port: str = os.getenv("VOICE_MODULE_PORT", "/dev/ttyUSB0")
    voice_module_baud: int = int(os.getenv("VOICE_MODULE_BAUD", "115200"))
    camera_index: int = int(os.getenv("CAMERA_INDEX", "0"))
    camera_width: int = int(os.getenv("CAMERA_WIDTH", "640"))
    camera_height: int = int(os.getenv("CAMERA_HEIGHT", "480"))


@dataclass
class AppConfig:
    service_principal: ServicePrincipalConfig
    azure_openai: AzureOpenAIConfig
    azure_speech: AzureSpeechConfig
    azure_search: AzureSearchConfig
    safety: SafetyConfig
    hardware: HardwareConfig


def load_config() -> AppConfig:
    return AppConfig(
        service_principal=ServicePrincipalConfig(),
        azure_openai=AzureOpenAIConfig(),
        azure_speech=AzureSpeechConfig(),
        azure_search=AzureSearchConfig(),
        safety=SafetyConfig(),
        hardware=HardwareConfig(),
    )
