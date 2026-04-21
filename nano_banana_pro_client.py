"""
Nano Banana Pro API Client
Connects to kie.ai Nano Banana Pro API to generate and download images.
Based on official API documentation: https://kie.ai/nano-banana-pro
"""

import requests
import os
import time
import json
import base64
from typing import Optional, List, Literal
from pathlib import Path
from kie_model_presets import (
    get_model_preset,
    has_parameter,
    convert_aspect_ratio_to_image_size,
    GOOGLE_NANO_BANANA,
    NANO_BANANA_PRO,
)


# Default Kie model ID.
# Change this ONE constant if you want to use a different model from https://kie.ai/market
DEFAULT_KIE_MODEL = "google/nano-banana"


class NanoBananaProClient:
    """Client for interacting with Nano Banana Pro API."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.kie.ai", model: str = DEFAULT_KIE_MODEL):
        """
        Initialize the client.
        
        Args:
            api_key: Your API key for authentication
            base_url: Base URL for the API (default: https://api.kie.ai)
            model: Model name to use (default: nano-banana-pro)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def create_task(
        self,
        prompt: str,
        image_input: Optional[List[str]] = None,
        aspect_ratio: Optional[Literal["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "auto"]] = None,
        resolution: Optional[Literal["1K", "2K", "4K"]] = None,
        output_format: Optional[Literal["png", "jpg", "jpeg"]] = None,
        callback_url: Optional[str] = None
    ) -> str:
        """
        Create a generation task.
        
        Uses model-specific presets to determine which parameters to send.
        
        Args:
            prompt: Text description of the image to generate (required, max 5000 chars)
            image_input: List of image file paths or URLs to use as reference (max 8 images, max 30MB each)
            aspect_ratio: Aspect ratio of the generated image (used for nano-banana-pro)
            resolution: Resolution of the generated image (1K, 2K, or 4K) - only for nano-banana-pro
            output_format: Format of the output image (png, jpg, or jpeg)
            callback_url: Optional callback URL for task completion notifications
        
        Returns:
            Task ID string
        """
        endpoint = f"{self.base_url}/api/v1/jobs/createTask"
        
        # Get model preset to determine which parameters to use
        preset = get_model_preset(self.model)
        if not preset:
            raise ValueError(f"Unknown model: {self.model}. Check kie_model_presets.py for supported models.")
        
        # Validate prompt length (if model has max_length)
        prompt_info = preset["parameters"].get("prompt", {})
        max_length = prompt_info.get("max_length")
        if max_length and len(prompt) > max_length:
            raise ValueError(f"Prompt exceeds maximum length of {max_length} characters")
        
        # Prepare input object
        input_data = {
            "prompt": prompt
        }
        
        # Handle image_input (only for nano-banana-pro)
        if has_parameter(self.model, "image_input") and image_input:
            image_input_info = preset["parameters"]["image_input"]
            max_files = image_input_info.get("max_files", 8)
            max_file_size_mb = image_input_info.get("max_file_size_mb", 30)
            
            if len(image_input) > max_files:
                raise ValueError(f"Maximum {max_files} images allowed")
            
            image_array = []
            for image_path in image_input:
                if image_path.startswith(('http://', 'https://')):
                    # If it's already a URL, use it directly
                    image_array.append(image_path)
                else:
                    # If it's a file path, validate and convert to base64
                    if not os.path.exists(image_path):
                        raise FileNotFoundError(f"Image file not found: {image_path}")
                    
                    file_size = os.path.getsize(image_path)
                    if file_size > max_file_size_mb * 1024 * 1024:
                        raise ValueError(f"Image file too large (max {max_file_size_mb}MB): {image_path}")
                    
                    # Read and encode image as base64 data URL
                    with open(image_path, 'rb') as f:
                        image_data = f.read()
                    
                    ext = Path(image_path).suffix.lower()
                    mime_type = self._get_mime_type(ext)
                    base64_data = base64.b64encode(image_data).decode('utf-8')
                    data_url = f"data:{mime_type};base64,{base64_data}"
                    image_array.append(data_url)
            
            if image_array:
                input_data["image_input"] = image_array
        
        # Handle aspect_ratio vs image_size based on model
        if self.model == GOOGLE_NANO_BANANA:
            # google/nano-banana uses "image_size" instead of "aspect_ratio"
            if aspect_ratio:
                image_size = convert_aspect_ratio_to_image_size(aspect_ratio)
                input_data["image_size"] = image_size
        elif self.model == NANO_BANANA_PRO:
            # nano-banana-pro uses "aspect_ratio"
            if aspect_ratio:
                input_data["aspect_ratio"] = aspect_ratio
            # nano-banana-pro also supports resolution
            if resolution:
                input_data["resolution"] = resolution
        
        # Handle output_format (normalize jpg to jpeg for google/nano-banana)
        if output_format:
            if self.model == GOOGLE_NANO_BANANA and output_format == "jpg":
                # google/nano-banana uses "jpeg" not "jpg"
                input_data["output_format"] = "jpeg"
            else:
                input_data["output_format"] = output_format
        
        # Prepare request payload
        payload = {
            "model": self.model,
            "input": input_data
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        # Make request
        response = requests.post(endpoint, json=payload, headers=self.headers)
        response.raise_for_status()
        
        result = response.json()
        
        # Check response code
        if result.get("code") != 200:
            raise Exception(f"API error: {result.get('msg', 'Unknown error')} (code: {result.get('code')})")
        
        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            raise Exception("No taskId returned from API")
        
        return task_id
    
    def query_task_status(self, task_id: str) -> dict:
        """
        Query the status of a generation task.
        
        Args:
            task_id: Task ID returned from create_task
        
        Returns:
            Dictionary containing task status and results
        """
        endpoint = f"{self.base_url}/api/v1/jobs/recordInfo"
        params = {"taskId": task_id}
        
        response = requests.get(endpoint, params=params, headers=self.headers)
        response.raise_for_status()
        
        result = response.json()
        
        # Check response code
        if result.get("code") != 200:
            raise Exception(f"API error: {result.get('msg', 'Unknown error')} (code: {result.get('code')})")
        
        return result.get("data", {})
    
    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 5,
        max_wait_time: Optional[int] = None
    ) -> dict:
        """
        Poll task status until completion.
        
        Args:
            task_id: Task ID to poll
            poll_interval: Seconds between status checks (default: 5)
            max_wait_time: Maximum time to wait in seconds (None for no limit)
        
        Returns:
            Task data dictionary when completed
        
        Raises:
            Exception: If task fails or timeout is reached
        """
        start_time = time.time()
        
        while True:
            task_data = self.query_task_status(task_id)
            state = task_data.get("state")
            
            if state == "success":
                return task_data
            elif state == "fail":
                fail_code = task_data.get("failCode")
                fail_msg = task_data.get("failMsg")
                raise Exception(f"Task failed: {fail_msg} (code: {fail_code})")
            
            # Check timeout
            if max_wait_time and (time.time() - start_time) > max_wait_time:
                raise TimeoutError(f"Task did not complete within {max_wait_time} seconds")
            
            # Wait before next poll
            time.sleep(poll_interval)
    
    def get_result_urls(self, task_data: dict) -> List[str]:
        """
        Extract result image URLs from completed task data.
        
        Args:
            task_data: Task data dictionary from wait_for_completion
        
        Returns:
            List of image URLs
        """
        result_json_str = task_data.get("resultJson")
        if not result_json_str:
            raise ValueError("No resultJson in task data")
        
        try:
            result_json = json.loads(result_json_str)
            return result_json.get("resultUrls", [])
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse resultJson: {e}")
    
    def generate_image(
        self,
        prompt: str,
        image_input: Optional[List[str]] = None,
        aspect_ratio: Optional[Literal["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]] = None,
        resolution: Optional[Literal["1K", "2K", "4K"]] = None,
        output_format: Optional[Literal["png", "jpg"]] = None,
        callback_url: Optional[str] = None,
        poll_interval: int = 5,
        max_wait_time: Optional[int] = None
    ) -> bytes:
        """
        Generate an image using Nano Banana Pro API (complete workflow).
        
        This method creates a task, waits for completion, and downloads the result.
        
        Args:
            prompt: Text description of the image to generate (required)
            image_input: List of image file paths or URLs to use as reference (max 8 images, max 30MB each)
            aspect_ratio: Aspect ratio of the generated image
            resolution: Resolution of the generated image (1K, 2K, or 4K)
            output_format: Format of the output image (png or jpg)
            callback_url: Optional callback URL for task completion notifications
            poll_interval: Seconds between status checks (default: 5)
            max_wait_time: Maximum time to wait in seconds (None for no limit)
        
        Returns:
            Image data as bytes
        """
        # Create task
        print(f"Creating generation task...")
        task_id = self.create_task(
            prompt=prompt,
            image_input=image_input,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            output_format=output_format,
            callback_url=callback_url
        )
        print(f"Task created: {task_id}")
        
        # Wait for completion
        print(f"Waiting for task to complete (polling every {poll_interval}s)...")
        task_data = self.wait_for_completion(
            task_id=task_id,
            poll_interval=poll_interval,
            max_wait_time=max_wait_time
        )
        print("Task completed successfully!")
        
        # Get result URLs
        result_urls = self.get_result_urls(task_data)
        if not result_urls:
            raise Exception("No result URLs found in task result")
        
        # Download first image (usually there's only one)
        image_url = result_urls[0]
        print(f"Downloading image from: {image_url}")
        return self._download_image(image_url)
    
    def generate_and_save(
        self,
        prompt: str,
        output_path: str,
        image_input: Optional[List[str]] = None,
        aspect_ratio: Optional[Literal["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]] = None,
        resolution: Optional[Literal["1K", "2K", "4K"]] = None,
        output_format: Optional[Literal["png", "jpg"]] = None,
        callback_url: Optional[str] = None,
        poll_interval: int = 5,
        max_wait_time: Optional[int] = None
    ) -> str:
        """
        Generate an image and save it to a file.
        
        Args:
            prompt: Text description of the image to generate
            output_path: Path where to save the generated image
            image_input: List of image file paths or URLs to use as reference
            aspect_ratio: Aspect ratio of the generated image
            resolution: Resolution of the generated image
            output_format: Format of the output image
            callback_url: Optional callback URL for task completion notifications
            poll_interval: Seconds between status checks (default: 5)
            max_wait_time: Maximum time to wait in seconds (None for no limit)
        
        Returns:
            Path to the saved image file
        """
        image_data = self.generate_image(
            prompt=prompt,
            image_input=image_input,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            output_format=output_format,
            callback_url=callback_url,
            poll_interval=poll_interval,
            max_wait_time=max_wait_time
        )
        
        # Determine file extension if not provided
        if not output_path.endswith(('.png', '.jpg', '.jpeg')):
            ext = output_format or 'png'
            output_path = f"{output_path}.{ext}"
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        
        # Save image
        with open(output_path, 'wb') as f:
            f.write(image_data)
        
        print(f"Image saved to: {output_path}")
        return output_path
    
    def _download_image(self, image_url: str) -> bytes:
        """Download image from URL."""
        response = requests.get(image_url)
        response.raise_for_status()
        return response.content
    
    def _get_mime_type(self, ext: str) -> str:
        """Get MIME type based on file extension."""
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp'
        }
        return mime_types.get(ext, 'image/jpeg')


def main():
    """Example usage of the Nano Banana Pro client."""
    import argparse
    
    # Check for API key in environment variable
    default_api_key = os.getenv('NANO_BANANA_PRO_API_KEY')
    
    parser = argparse.ArgumentParser(description='Generate images using Nano Banana Pro API')
    parser.add_argument('--api-key', default=default_api_key, 
                       help='API key for authentication (or set NANO_BANANA_PRO_API_KEY env var)')
    parser.add_argument('--prompt', required=True, help='Text description of the image')
    parser.add_argument('--output', default='generated_image.png', help='Output file path')
    parser.add_argument('--images', nargs='*', help='Reference image file paths or URLs (max 8)')
    parser.add_argument('--aspect-ratio', choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
                       help='Aspect ratio of the generated image')
    parser.add_argument('--resolution', choices=["1K", "2K", "4K"], help='Resolution of the generated image')
    parser.add_argument('--format', choices=["png", "jpg"], help='Output format')
    parser.add_argument('--callback-url', help='Callback URL for task completion notifications')
    parser.add_argument('--poll-interval', type=int, default=5, help='Seconds between status checks (default: 5)')
    parser.add_argument('--max-wait-time', type=int, help='Maximum time to wait in seconds (default: no limit)')
    parser.add_argument('--base-url', default='https://api.kie.ai', help='Base URL for the API')
    
    args = parser.parse_args()
    
    # Validate API key
    if not args.api_key:
        print("Error: API key is required. Provide --api-key or set NANO_BANANA_PRO_API_KEY environment variable.")
        return 1
    
    # Initialize client
    client = NanoBananaProClient(api_key=args.api_key, base_url=args.base_url)
    
    # Generate and save image
    try:
        output_path = client.generate_and_save(
            prompt=args.prompt,
            output_path=args.output,
            image_input=args.images,
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            output_format=args.format,
            callback_url=args.callback_url,
            poll_interval=args.poll_interval,
            max_wait_time=args.max_wait_time
        )
        print(f"Successfully generated and saved image to: {output_path}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
