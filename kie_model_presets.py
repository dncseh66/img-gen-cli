"""
Kie Model Presets

This file contains preset configurations for different Kie AI models.
Each model may have different parameter names and supported values.
"""

from typing import Dict, Optional, List, Literal

# Model identifiers
NANO_BANANA_PRO = "nano-banana-pro"
GOOGLE_NANO_BANANA = "google/nano-banana"

# Preset configurations for each model
MODEL_PRESETS: Dict[str, Dict] = {
    NANO_BANANA_PRO: {
        "model_id": "nano-banana-pro",
        "parameters": {
            "prompt": {
                "required": True,
                "type": str,
                "max_length": 5000,
            },
            "image_input": {
                "required": False,
                "type": List[str],
                "max_files": 8,
                "max_file_size_mb": 30,
                "supported_formats": ["jpeg", "png", "webp"],
            },
            "aspect_ratio": {
                "required": False,
                "type": str,
                "default": "16:9",
                "allowed_values": ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "auto"],
            },
            "resolution": {
                "required": False,
                "type": str,
                "default": "1K",
                "allowed_values": ["1K", "2K", "4K"],
            },
            "output_format": {
                "required": False,
                "type": str,
                "default": "png",
                "allowed_values": ["png", "jpg"],
            },
        },
    },
    GOOGLE_NANO_BANANA: {
        "model_id": "google/nano-banana",
        "parameters": {
            "prompt": {
                "required": True,
                "type": str,
            },
            "output_format": {
                "required": False,
                "type": str,
                "default": "png",
                "allowed_values": ["png", "jpeg"],
            },
            "image_size": {
                "required": False,
                "type": str,
                "default": "16:9",
                "allowed_values": ["1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9", "auto"],
            },
        },
    },
}


def get_model_preset(model_id: str) -> Optional[Dict]:
    """
    Get preset configuration for a model.
    
    Args:
        model_id: Model identifier (e.g., "nano-banana-pro", "google/nano-banana")
    
    Returns:
        Preset dictionary or None if model not found
    """
    return MODEL_PRESETS.get(model_id)


def get_parameter_info(model_id: str, param_name: str) -> Optional[Dict]:
    """
    Get parameter information for a specific model.
    
    Args:
        model_id: Model identifier
        param_name: Parameter name (e.g., "aspect_ratio", "image_size", "resolution")
    
    Returns:
        Parameter info dict or None if not found
    """
    preset = get_model_preset(model_id)
    if preset:
        return preset["parameters"].get(param_name)
    return None


def has_parameter(model_id: str, param_name: str) -> bool:
    """
    Check if a model supports a specific parameter.
    
    Args:
        model_id: Model identifier
        param_name: Parameter name
    
    Returns:
        True if parameter is supported, False otherwise
    """
    preset = get_model_preset(model_id)
    if preset:
        return param_name in preset["parameters"]
    return False


def get_allowed_values(model_id: str, param_name: str) -> Optional[List[str]]:
    """
    Get allowed values for a parameter on a specific model.
    
    Args:
        model_id: Model identifier
        param_name: Parameter name
    
    Returns:
        List of allowed values or None
    """
    param_info = get_parameter_info(model_id, param_name)
    if param_info:
        return param_info.get("allowed_values")
    return None


def convert_aspect_ratio_to_image_size(aspect_ratio: str) -> str:
    """
    Convert aspect_ratio format to image_size format.
    Both use the same values, but this provides a clear mapping.
    
    Args:
        aspect_ratio: Aspect ratio string (e.g., "16:9")
    
    Returns:
        Image size string (same format)
    """
    # Both use the same format, so just return as-is
    return aspect_ratio


def get_default_value(model_id: str, param_name: str) -> Optional[str]:
    """
    Get default value for a parameter on a specific model.
    
    Args:
        model_id: Model identifier
        param_name: Parameter name
    
    Returns:
        Default value or None
    """
    param_info = get_parameter_info(model_id, param_name)
    if param_info:
        return param_info.get("default")
    return None

