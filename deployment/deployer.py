"""ONNX Runtime deployer for the travel-planner multi-agent system.

This module replaces previous NeMo-specific deployment utilities with an
ONNX Runtime-based deployer. It provides a small, testable interface for
optimizing (mocked) and serving ONNX models. The implementation falls back
to a mock mode when `onnxruntime` is not available so repository code can
run without optional native dependencies.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional
import json
import logging

try:
    import onnxruntime as ort
    ORT_AVAILABLE = True
except Exception:
    ort = None
    ORT_AVAILABLE = False

logger = logging.getLogger(__name__)


class DeploymentStrategy(str, Enum):
    LOCAL = "local"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    CLOUD = "cloud"
    EDGE = "edge"


class OptimizationLevel(str, Enum):
    NONE = "none"
    LIGHT = "light"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class DeploymentConfig:
    strategy: DeploymentStrategy = DeploymentStrategy.LOCAL
    optimization_level: OptimizationLevel = OptimizationLevel.MODERATE
    num_gpus: int = 1
    batch_size: int = 4
    model_precision: str = "fp16"
    enable_quantization: bool = True
    enable_parallel: bool = False
    max_seq_length: int = 512
    cache_strategy: str = "static"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "optimization_level": self.optimization_level.value,
            "num_gpus": self.num_gpus,
            "batch_size": self.batch_size,
            "model_precision": self.model_precision,
            "enable_quantization": self.enable_quantization,
            "enable_parallel": self.enable_parallel,
            "max_seq_length": self.max_seq_length,
            "cache_strategy": self.cache_strategy,
        }

    def to_json(self, filepath: Optional[str] = None) -> str:
        json_str = json.dumps(self.to_dict(), indent=2)
        if filepath:
            with open(filepath, "w") as f:
                f.write(json_str)
            return filepath
        return json_str


class Deployer:
    """ONNX Runtime-backed deployer (mock when ORT unavailable)."""

    def __init__(self, config: Optional[DeploymentConfig] = None):
        self.config = config or DeploymentConfig()
        self.models: Dict[str, Dict[str, Any]] = {}
        self.deployment_status: Dict[str, Dict[str, Any]] = {}

        if ORT_AVAILABLE:
            logger.info("Deployer initialized (ONNX Runtime available)")
        else:
            logger.warning("Deployer initialized in mock mode (onnxruntime not available)")

    def optimize_model(self, model_name: str, model_path: str, optimization_level: Optional[OptimizationLevel] = None) -> Dict[str, Any]:
        opt_level = optimization_level or self.config.optimization_level
        status = "optimized" if ORT_AVAILABLE else "mock"
        result = {
            "model": model_name,
            "model_path": model_path,
            "optimization_level": opt_level.value,
            "status": status,
            "improvements": {},
        }

        # Mock optimizations; replace with real onnx optimizer / quantization calls as needed
        if opt_level == OptimizationLevel.LIGHT:
            result["improvements"] = {"latency": "5%"}
        elif opt_level == OptimizationLevel.MODERATE:
            result["improvements"] = {"latency": "15%", "memory": "10%"}
        elif opt_level == OptimizationLevel.AGGRESSIVE:
            result["improvements"] = {"latency": "30%", "memory": "25%", "size": "40%"}

        self.models[model_name] = result
        logger.info("Model '%s' optimized (level=%s)", model_name, opt_level.value)
        return result

    def configure_inference(self, batch_size: Optional[int] = None, max_seq_length: Optional[int] = None) -> Dict[str, Any]:
        batch_size = batch_size or self.config.batch_size
        max_seq_length = max_seq_length or self.config.max_seq_length
        cfg = {
            "batch_size": batch_size,
            "max_seq_length": max_seq_length,
            "model_precision": self.config.model_precision,
            "cache_strategy": self.config.cache_strategy,
        }
        logger.info("Inference configured - batch=%s, seq_len=%s", batch_size, max_seq_length)
        return cfg

    def deploy(self, model_name: str, model_path: str, service_name: Optional[str] = None) -> Dict[str, Any]:
        service_name = service_name or f"{model_name}_service"
        deployment = {
            "service_name": service_name,
            "model_name": model_name,
            "model_path": model_path,
            "strategy": self.config.strategy.value,
            "status": "deployed" if ORT_AVAILABLE else "mock_deployed",
            "endpoint": self._get_endpoint(service_name),
            "metrics": {
                "num_gpus": self.config.num_gpus,
                "batch_size": self.config.batch_size,
                "model_precision": self.config.model_precision,
            },
        }
        self.deployment_status[service_name] = deployment
        logger.info("Model '%s' deployed as '%s'", model_name, service_name)
        return deployment

    def _get_endpoint(self, service_name: str) -> str:
        strategy = self.config.strategy
        if strategy == DeploymentStrategy.LOCAL:
            return "http://localhost:8000"
        elif strategy == DeploymentStrategy.DOCKER:
            return f"http://{service_name}:8000"
        elif strategy == DeploymentStrategy.KUBERNETES:
            return f"https://{service_name}.svc.cluster.local"
        elif strategy == DeploymentStrategy.CLOUD:
            return f"https://{service_name}.cloud.provider"
        elif strategy == DeploymentStrategy.EDGE:
            return f"http://{service_name}.local"
        return "http://localhost:8000"


def get_recommended_config(strategy: DeploymentStrategy = DeploymentStrategy.LOCAL, num_gpus: int = 1) -> DeploymentConfig:
    if strategy == DeploymentStrategy.LOCAL:
        return DeploymentConfig(strategy=strategy, optimization_level=OptimizationLevel.MODERATE, num_gpus=num_gpus, batch_size=4, model_precision="fp16", enable_parallel=(num_gpus > 1))
    elif strategy == DeploymentStrategy.DOCKER:
        return DeploymentConfig(strategy=strategy, optimization_level=OptimizationLevel.MODERATE, num_gpus=min(num_gpus, 2), batch_size=8, model_precision="fp16")
    elif strategy == DeploymentStrategy.KUBERNETES:
        return DeploymentConfig(strategy=strategy, optimization_level=OptimizationLevel.AGGRESSIVE, num_gpus=num_gpus, batch_size=16, model_precision="int8", enable_parallel=(num_gpus > 1), max_seq_length=512)
    elif strategy == DeploymentStrategy.EDGE:
        return DeploymentConfig(strategy=strategy, optimization_level=OptimizationLevel.AGGRESSIVE, num_gpus=1, batch_size=1, model_precision="int8", max_seq_length=256)
    else:
        return DeploymentConfig(strategy=strategy, optimization_level=OptimizationLevel.AGGRESSIVE, num_gpus=num_gpus, batch_size=32, model_precision="fp16", enable_parallel=True)
