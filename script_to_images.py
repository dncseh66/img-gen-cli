"""
Script to Images Generator

This script:
1. Reads a script file and divides it into segments (~1000 words each)
   - First paragraph is kept intact
   - Remaining paragraphs are combined and split into ~1000 word segments
   - Segments are split at sentence boundaries (sentences are never broken)
2. Sends each segment to Claude API to generate image prompts
3. Saves the prompts to a JSON file
4. Generates images using kie API (Nano Banana Pro)
5. Saves images with naming convention: segment_number_image_number
"""

import os
import json
import re
import argparse
from typing import List, Dict, Optional
from pathlib import Path
from anthropic import Anthropic
from nano_banana_pro_client import NanoBananaProClient, DEFAULT_KIE_MODEL


class ScriptToImagesGenerator:
    """Generator that converts script paragraphs to images via Claude and kie API."""
    
    def __init__(
        self,
        claude_api_key: str,
        kie_api_key: str,
        kie_model: str = DEFAULT_KIE_MODEL,
        output_folder: str = "generated_images",
        style_suffix: Optional[str] = None,
        collapse_single_newlines: bool = False,
    ):
        """
        Initialize the generator.
        
        Args:
            claude_api_key: Anthropic Claude API key
            kie_api_key: kie.ai API key
            kie_model: Model name for kie API (default: value of DEFAULT_KIE_MODEL in nano_banana_pro_client.py)
            output_folder: Folder to save generated images
            style_suffix: Optional style text to append to every image generation prompt
            collapse_single_newlines: If True, merge single newlines inside paragraphs but keep blank lines as paragraph separators
        """
        self.claude_client = Anthropic(api_key=claude_api_key)
        self.kie_client = NanoBananaProClient(api_key=kie_api_key, model=kie_model)
        self.kie_model = kie_model
        self.output_folder = output_folder
        self.style_suffix = style_suffix.strip() if style_suffix else None
        self.collapse_single_newlines = collapse_single_newlines
        
        # Create output folder if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)
    
    def read_paragraphs(self, script_path: str) -> List[str]:
        """
        Read script file that is already split into paragraphs.
        Paragraphs are separated by blank lines.
        Optionally collapses single newlines inside paragraphs and can
        persist that collapsed form back to the original file when
        collapse_single_newlines is enabled.
        """
        with open(script_path, 'r', encoding='utf-8') as f:
            raw = f.read()

        # Normalize newlines
        raw = raw.replace('\r\n', '\n').replace('\r', '\n')

        lines = raw.split('\n')
        paragraphs: List[str] = []
        current_lines: List[str] = []

        for line in lines:
            if line.strip() == '':
                # Blank line → paragraph separator
                if current_lines:
                    if self.collapse_single_newlines:
                        # Join all lines in this paragraph with spaces
                        para_text = ' '.join(l.strip() for l in current_lines if l.strip())
                    else:
                        # Preserve internal line breaks
                        para_text = '\n'.join(current_lines).strip()
                    if para_text:
                        paragraphs.append(para_text)
                    current_lines = []
            else:
                current_lines.append(line)

        # Flush last paragraph (if no trailing blank line)
        if current_lines:
            if self.collapse_single_newlines:
                para_text = ' '.join(l.strip() for l in current_lines if l.strip())
            else:
                para_text = '\n'.join(current_lines).strip()
            if para_text:
                paragraphs.append(para_text)

        # If collapsing lines, also write the collapsed version back to the script file
        if self.collapse_single_newlines:
            try:
                collapsed_content = '\n\n'.join(paragraphs) + '\n'
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(collapsed_content)
                print(f"Collapsed single newlines and saved script to: {script_path}")
            except Exception as e:
                print(f"Warning: Failed to save collapsed script to {script_path}: {e}")

        return paragraphs
    
    def split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences, respecting sentence endings.
        Sentences end with . ! ? followed by space, newline, or end of string.
        
        Args:
            text: Text to split into sentences
            
        Returns:
            List of sentences
        """
        # Pattern to match sentence endings: . ! ? followed by whitespace or end of string
        sentence_endings = re.compile(r'([.!?])(?:\s+|$)')
        sentences = []
        
        # Find all sentence endings
        last_end = 0
        for match in sentence_endings.finditer(text):
            # Extract sentence including the ending punctuation
            sentence = text[last_end:match.end()].strip()
            if sentence:
                sentences.append(sentence)
            last_end = match.end()
        
        # Add remaining text if any
        remaining = text[last_end:].strip()
        if remaining:
            sentences.append(remaining)
        
        # Filter out empty sentences
        return [s for s in sentences if s]
    
    def count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())
    
    def divide_script_into_segments(self, script_path: str, target_words: int = 1000) -> List[str]:
        """
        Divide script into segments of approximately target_words each.
        First paragraph is kept intact. Remaining paragraphs are combined
        and split into ~target_words segments without breaking sentences.
        
        Args:
            script_path: Path to script file
            target_words: Target number of words per segment (default: 1000)
            
        Returns:
            List of segments (first paragraph + ~1000 word chunks)
        """
        paragraphs = self.read_paragraphs(script_path)
        
        if not paragraphs:
            return []
        
        # Keep first paragraph intact
        segments = [paragraphs[0]]
        
        # If there are more paragraphs, combine them and split into ~target_words chunks
        if len(paragraphs) > 1:
            # Combine all paragraphs after the first one
            remaining_text = ' '.join(paragraphs[1:])
            
            # Split into sentences
            sentences = self.split_into_sentences(remaining_text)
            
            # Group sentences into segments of ~target_words
            current_segment_words = 0
            current_segment_sentences = []
            
            for sentence in sentences:
                sentence_words = self.count_words(sentence)
                
                # Check if adding this sentence would exceed our target
                # We aim for ~target_words, allowing some flexibility
                would_exceed = current_segment_words + sentence_words > target_words
                
                # If we've reached at least 900 words (90% of target) and adding 
                # this sentence would exceed target, start a new segment
                if (current_segment_words > 0 and 
                    current_segment_words >= target_words * 0.9 and 
                    would_exceed):
                    # Save current segment
                    if current_segment_sentences:
                        segments.append(' '.join(current_segment_sentences))
                        current_segment_sentences = []
                        current_segment_words = 0
                
                # Add sentence to current segment
                current_segment_sentences.append(sentence)
                current_segment_words += sentence_words
            
            # Add remaining sentences as final segment
            if current_segment_sentences:
                segments.append(' '.join(current_segment_sentences))
        
        return segments
    
    def generate_image_prompts_with_claude(
        self,
        paragraph: str,
        paragraph_number: int,
        num_images: int,
        system_prompt: str = None,
        script_context: Optional[str] = None,
    ) -> List[str]:
        """
        Send paragraph to Claude API to generate image generation prompts.
        
        Args:
            paragraph: The paragraph text
            paragraph_number: The paragraph number
            num_images: Exact number of image prompts to generate
            system_prompt: Optional custom system prompt
            script_context: Optional full-script context text for consistency
        
        Returns:
            List of image generation prompts (style suffix appended if configured)
        """
        if system_prompt is None:
            system_prompt = """You are an expert at creating detailed, vivid image generation prompts for video scripts.

I am now going to provide you a segment of the video script. I would like you to generate descriptive image prompts that will accompany the voiceover of this script. I would like these image prompts to be extremely descriptive and complement what is being said in the script. These images will set the scene for the viewer and should give them a feel for what that time felt like. These images do not need to necessarily exactly mimic what is being said, however it should absolutely complement it and set the scene. Each image should have people in the background or in the middle ground, but never in the foreground or as the focus of the image.

For each image prompt:
- Be extremely descriptive and detailed about visual elements
- Include style, mood, atmosphere, composition, setting, and environmental details
- Set the scene and evoke the feeling of the time period/context
- Complement the voiceover without necessarily directly illustrating every word
- Ensure people appear in background or middle ground, never as the foreground focus
- Make prompts suitable for AI image generation
- CRITICAL: Each prompt MUST NOT exceed 1000 characters in length
- Return prompts as a JSON array of strings
- Generate EXACTLY the requested number of prompts

Return ONLY a valid JSON array of strings, nothing else. Example format:
["A detailed prompt for the first scene", "A detailed prompt for the second scene"]"""

        if script_context:
            user_prompt = f"""You are given the full script context to help keep settings, locations, and details consistent across all images.
Do NOT repeat the full script in your output, only use it as background context.

FULL SCRIPT CONTEXT:
{script_context}

---

SEGMENT {paragraph_number}:
{paragraph}

Generate exactly {num_images} descriptive image prompt(s) for this script segment. The prompts should be extremely descriptive and complement the voiceover, setting the scene and giving viewers a feel for what that time felt like. Each image should have people in the background or middle ground, never in the foreground or as the focus. IMPORTANT: Each prompt must NOT exceed 1000 characters in length. Return a JSON array with exactly {num_images} prompt string(s)."""
        else:
            user_prompt = f"""SEGMENT {paragraph_number}:
{paragraph}

Generate exactly {num_images} descriptive image prompt(s) for this script segment. The prompts should be extremely descriptive and complement the voiceover, setting the scene and giving viewers a feel for what that time felt like. The images should be chronologically spaced throughout the segment. Each image should have people in the background or middle ground, never in the foreground or as the focus. IMPORTANT: Each prompt must NOT exceed 1000 characters in length. Return a JSON array with exactly {num_images} prompt string(s)."""
        
        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            )
            
            # Extract content
            content = message.content[0].text
            
            # Try to parse JSON from the response
            # Remove markdown code blocks if present
            content = content.strip()
            if content.startswith("```"):
                # Remove code block markers
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1]) if len(lines) > 2 else content
            
            # Parse JSON
            try:
                prompts = json.loads(content)
                if isinstance(prompts, list):
                    prompt_list = prompts
                elif isinstance(prompts, str):
                    # If it's a single string, wrap it in a list
                    prompt_list = [prompts]
                else:
                    raise ValueError(f"Unexpected response format: {type(prompts)}")
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract prompts from text
                # Look for array-like patterns
                array_match = re.search(r'\[(.*?)\]', content, re.DOTALL)
                if array_match:
                    # Try to extract strings from the array
                    prompt_list = []
                    string_matches = re.findall(r'"([^"]+)"', array_match.group(1))
                    if string_matches:
                        prompt_list = string_matches
                    else:
                        # Fallback: split by common delimiters
                        prompt_list = [p.strip() for p in content.split('\n') if p.strip() and not p.strip().startswith('#')]
                else:
                    # Last resort: split by newlines
                    prompt_list = [p.strip() for p in content.split('\n') if p.strip()]
                
                if not prompt_list:
                    # If still no prompts, use the whole content as one prompt
                    prompt_list = [content]
                
                # fall through to style processing below

            # Apply optional style suffix
            if self.style_suffix:
                styled_prompts = []
                for p in prompt_list:
                    if not p:
                        continue
                    styled_prompts.append(f"{p.rstrip()} {self.style_suffix}")
                prompt_list = styled_prompts

            # Ensure no prompt exceeds 1000 characters (truncate if necessary)
            final_prompts = []
            for p in prompt_list:
                if not p:
                    continue
                if len(p) > 1000:
                    print(f"Warning: Prompt exceeded 1000 characters ({len(p)} chars), truncating...")
                    p = p[:1000].rsplit(' ', 1)[0]  # Truncate at last word boundary
                final_prompts.append(p)
            
            return final_prompts
        
        except Exception as e:
            print(f"Error generating prompts for paragraph {paragraph_number}: {e}")
            # Fallback: use paragraph as prompt (with optional style suffix)
            base_prompt = paragraph
            if self.style_suffix:
                base_prompt = f"{base_prompt.rstrip()} {self.style_suffix}"
            return [base_prompt]

    def generate_video_prompt_with_claude(
        self,
        image_prompt: str,
        paragraph_number: int,
        image_number: int,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate a video generation prompt for a given image prompt.

        Args:
            image_prompt: The image generation prompt (describes the starting frame)
            paragraph_number: Paragraph number (for logging/metadata)
            image_number: Image index within the paragraph
            system_prompt: Optional system prompt override

        Returns:
            A single video generation prompt as a string
        """
        if system_prompt is None:
            system_prompt = (
                "You are an expert at writing detailed video generation prompts for video generator AIs. "
                "Given an image description that represents the starting frame, you write a single, "
                "coherent video generation prompt. Describe camera movement, character movements, and "
                "expressions in a natural way. The total length MUST be at most 1500 characters. "
                "Return ONLY the prompt text, no explanations, no quotes, no formatting."
            )

        user_prompt = (
            f"Paragraph {paragraph_number}, image {image_number}.\n\n"
            "This is the image description (starting frame prompt):\n"
            f"{image_prompt}\n\n"
            "Write a video generation prompt for a video generator AI where this image is the starting frame. "
            "Describe the camera movement, character movements and expressions in the video generation prompt. "
            "Write max 1500 characters long prompts."
        )

        try:
            message = self.claude_client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ],
            )

            content = message.content[0].text.strip()
            return content
        except Exception as e:
            print(f"Error generating VIDEO prompt for paragraph {paragraph_number}, image {image_number}: {e}")
            # Fallback: wrap the image prompt into a minimal video prompt
            return (
                "Video starting from the following frame: "
                f"{image_prompt}. The camera slowly moves and characters move naturally."
            )
                
    
    def process_script(
        self,
        script_path: str,
        first_paragraph_images: int,
        other_paragraphs_images: int,
        system_prompt: str = None,
        save_prompts_json: str = "image_prompts.json",
        resolution: str = "2K",
        aspect_ratio: str = "16:9",
        output_format: str = "png",
        only_paragraph: Optional[int] = None,
        continue_from: Optional[int] = None,
        regenerate: Optional[int] = None,
    ) -> Dict:
        """
        Process entire script: generate prompts and create images.
        
        Args:
            script_path: Path to script file (already split into paragraphs)
            first_paragraph_images: Number of images to generate for the first paragraph (X)
            other_paragraphs_images: Number of images to generate for other paragraphs (Y)
            only_paragraph: If set, only this paragraph number will be processed
            continue_from: If set, process from this paragraph number onwards (skips earlier paragraphs)
            regenerate: If set, regenerate this specific paragraph (overwrites existing images)
            system_prompt: Optional custom system prompt for Claude
            save_prompts_json: Path to save prompts JSON file
            resolution: Image resolution (1K, 2K, 4K)
            aspect_ratio: Image aspect ratio
            output_format: Output format (png, jpg)
        
        Returns:
            Dictionary with processing results
        """
        print(f"Reading script from: {script_path}")
        segments = self.divide_script_into_segments(script_path, target_words=1000)
        print(f"Divided script into {len(segments)} segment(s)")
        if segments:
            print(f"  Segment 1 (first paragraph): {self.count_words(segments[0])} words")
            for i, seg in enumerate(segments[1:], start=2):
                print(f"  Segment {i}: {self.count_words(seg)} words")

        # Build a budget-friendly full-script context for Claude (for consistency)
        script_context: Optional[str] = None
        if segments:
            # Join segments with blank lines; optionally truncate for token/budget safety
            joined = "\n\n".join(segments).strip()
            max_context_chars = 8000  # adjust if needed
            if len(joined) > max_context_chars:
                script_context = joined[:max_context_chars]
            else:
                script_context = joined
        # Determine processing mode
        if only_paragraph is not None:
            print(f"Only processing segment {only_paragraph}")
        elif continue_from is not None:
            print(f"Continuing from segment {continue_from} onwards")
        elif regenerate is not None:
            print(f"Regenerating segment {regenerate}")
        
        print(f"First segment (paragraph) will generate {first_paragraph_images} image(s)")
        print(f"Other segments will generate {other_paragraphs_images} image(s) each")
        
        # Store all prompts
        all_prompts_data = {
            "script_path": script_path,
            "paragraphs": [],  # Keep key name for backward compatibility
            "total_images": 0
        }

        # Collect video prompts for first paragraph (if any)
        video_prompts_first_paragraph: List[str] = []
        
        # List of pending image generation tasks (for async processing)
        pending_tasks: List[Dict] = []

        # Process each segment
        for seg_num, segment in enumerate(segments, start=1):
            # Skip segments that are not the target when only_paragraph is set
            if only_paragraph is not None and seg_num != only_paragraph:
                continue
            
            # Skip segments before continue_from
            if continue_from is not None and seg_num < continue_from:
                print(f"\n--- Skipping Segment {seg_num}/{len(segments)} (before continue_from={continue_from}) ---")
                continue
            
            # For regenerate mode, skip all except the target segment
            if regenerate is not None and seg_num != regenerate:
                continue
            
            print(f"\n--- Processing Segment {seg_num}/{len(segments)} ---")
            print(f"Segment word count: {self.count_words(segment)}")
            print(f"Segment text: {segment[:100]}...")
            
            # Determine number of images for this segment
            if seg_num == 1:
                num_images = first_paragraph_images
            else:
                num_images = other_paragraphs_images
            
            # Generate image prompts with Claude
            print(f"Generating {num_images} image prompt(s) with Claude...")
            image_prompts = self.generate_image_prompts_with_claude(
                paragraph=segment,
                paragraph_number=seg_num,
                num_images=num_images,
                system_prompt=system_prompt,
                script_context=script_context,
            )
            
            # Ensure we have the correct number of prompts
            if len(image_prompts) < num_images:
                print(f"Warning: Generated {len(image_prompts)} prompts, expected {num_images}. Using what was generated.")
            elif len(image_prompts) > num_images:
                print(f"Warning: Generated {len(image_prompts)} prompts, expected {num_images}. Using first {num_images}.")
                image_prompts = image_prompts[:num_images]
            
            print(f"Using {len(image_prompts)} image prompt(s)")
            
            # Store segment data (keeping "paragraph_number" key for backward compatibility)
            para_data = {
                "paragraph_number": seg_num,
                "paragraph_text": segment,
                "image_prompts": image_prompts,
                "images": []
            }
            
            # Queue image generation tasks for each prompt
            for img_num, prompt in enumerate(image_prompts, start=1):
                print(f"\n  Queuing image {img_num}/{len(image_prompts)}...")
                print(f"  Prompt: {prompt[:80]}...")

                # Create filename: segment_number_image_number
                filename = f"{seg_num}_{img_num}.{output_format}"
                output_path = os.path.join(self.output_folder, filename)

                try:
                    # Create async generation task using kie API
                    # The client automatically uses correct parameter names based on model preset
                    task_id = self.kie_client.create_task(
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        output_format=output_format,
                    )
                    print(f"  ✓ Queued task: {task_id}")

                    # Prepare image entry (will fill in or update after download)
                    image_entry = {
                        "image_number": img_num,
                        "prompt": prompt,
                        "filename": filename,
                        "path": output_path,
                        "task_id": task_id,
                    }
                    para_data["images"].append(image_entry)

                    # Track pending task for later polling/downloading
                    pending_tasks.append(
                        {
                            "task_id": task_id,
                            "output_path": output_path,
                            "filename": filename,
                            "paragraph_number": seg_num,  # Keep key name for backward compatibility
                            "image_number": img_num,
                            "prompt": prompt,
                            "image_entry": image_entry,
                        }
                    )

                    # For first segment (paragraph) images, also generate video prompts (doesn't depend on image file)
                    if seg_num == 1:
                        video_prompt = self.generate_video_prompt_with_claude(
                            image_prompt=prompt,
                            paragraph_number=seg_num,
                            image_number=img_num,
                        )
                        header = f"Segment {seg_num}, Image {img_num} ({filename})"
                        video_prompts_first_paragraph.append(header)
                        video_prompts_first_paragraph.append(video_prompt)
                        video_prompts_first_paragraph.append("")  # blank line separator

                except Exception as e:
                    print(f"  ✗ Error queuing image task: {e}")
                    para_data["images"].append(
                        {
                            "image_number": img_num,
                            "prompt": prompt,
                            "filename": filename,
                            "path": output_path,
                            "error": str(e),
                        }
                    )
            
            all_prompts_data["paragraphs"].append(para_data)
            all_prompts_data["total_images"] += len(image_prompts)

        # Process all pending image tasks: wait for completion and download
        if pending_tasks:
            print(f"\nWaiting for {len(pending_tasks)} image task(s) to complete...")

        for task in pending_tasks:
            task_id = task["task_id"]
            filename = task["filename"]
            output_path = task["output_path"]
            para_num = task["paragraph_number"]
            img_num = task["image_number"]
            image_entry = task["image_entry"]

            print(f"\n  Waiting for task {task_id} (Segment {para_num}, Image {img_num})...")
            try:
                task_data = self.kie_client.wait_for_completion(task_id)
                result_urls = self.kie_client.get_result_urls(task_data)
                if not result_urls:
                    raise Exception("No result URLs returned from task")

                image_url = result_urls[0]
                print(f"  Downloading image from: {image_url}")
                image_data = self.kie_client._download_image(image_url)

                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

                with open(output_path, "wb") as f:
                    f.write(image_data)

                print(f"  ✓ Saved: {filename}")

            except Exception as e:
                print(f"  ✗ Error generating image for task {task_id}: {e}")
                image_entry["error"] = str(e)
        
        # Save prompts to JSON
        print(f"\nSaving prompts to: {save_prompts_json}")
        with open(save_prompts_json, 'w', encoding='utf-8') as f:
            json.dump(all_prompts_data, f, indent=2, ensure_ascii=False)

        # Save video prompts for first paragraph (if any) into images folder
        if video_prompts_first_paragraph:
            video_prompts_path = os.path.join(self.output_folder, "video_prompts_p1.txt")
            print(f"Saving video prompts for first paragraph to: {video_prompts_path}")
            try:
                with open(video_prompts_path, "w", encoding="utf-8") as vf:
                    vf.write("\n".join(video_prompts_first_paragraph))
            except Exception as e:
                print(f"Warning: Failed to save video prompts file {video_prompts_path}: {e}")
        
        print(f"\n✓ Processing complete!")
        print(f"  Total segments: {len(segments)}")
        print(f"  Total images: {all_prompts_data['total_images']}")
        print(f"  Images saved to: {self.output_folder}")
        print(f"  Prompts saved to: {save_prompts_json}")
        
        return all_prompts_data


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description='Generate images from script paragraphs using Claude API and kie API'
    )
    
    # API Keys
    parser.add_argument(
        '--claude-api-key',
        default=os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY'),
        help='Claude API key (or set ANTHROPIC_API_KEY or CLAUDE_API_KEY env var)',
    )
    parser.add_argument(
        '--kie-api-key',
        default=os.getenv('NANO_BANANA_PRO_API_KEY'),
        help='kie API key (or set NANO_BANANA_PRO_API_KEY env var)',
    )

    # Positional arguments: base path, project prefix, project number, and shorthand image counts
    parser.add_argument(
        'base_path_pos',
        nargs='?',
        help='Base path that contains the videos folder',
    )
    parser.add_argument(
        'project_prefix_pos',
        nargs='?',
        help='Project prefix, e.g. MO',
    )
    parser.add_argument(
        'project_number_pos',
        nargs='?',
        help='Project number, e.g. 0001 or 1',
    )
    parser.add_argument(
        'extra_positional',
        nargs='*',
        help="Optional shorthand: 1st X op Y (e.g. '1st 3 op 2')",
    )

    # Optional flags (still supported) for number of images per paragraph
    parser.add_argument(
        '--first-paragraph-images',
        '--1st',
        dest='first_paragraph_images',
        type=int,
        help='Number of images to generate for the first paragraph (X). Shorthand: --1st',
    )
    parser.add_argument(
        '--other-paragraphs-images',
        '--op',
        dest='other_paragraphs_images',
        type=int,
        help='Number of images to generate for other paragraphs (Y). Shorthand: --op',
    )
    
    # Image generation settings
    parser.add_argument(
        '--resolution',
        choices=['1K', '2K', '4K'],
        default='2K',
        help='Image resolution (default: 2K)',
    )
    parser.add_argument(
        '--aspect-ratio',
        choices=['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9'],
        default='16:9',
        help='Image aspect ratio (default: 16:9)',
    )
    parser.add_argument(
        '--format',
        choices=['png', 'jpg'],
        default='png',
        help='Output image format (default: png)',
    )

    # Advanced
    parser.add_argument(
        '--system-prompt-file',
        help='Path to file containing custom system prompt for Claude',
    )
    parser.add_argument(
        '--kie-model',
        default=DEFAULT_KIE_MODEL,
        help='kie API model name (default: value of DEFAULT_KIE_MODEL in nano_banana_pro_client.py)',
    )
    parser.add_argument(
        '--paragraph',
        '-p',
        dest='paragraph',
        type=int,
        help='Only generate images for this paragraph number',
    )
    parser.add_argument(
        '--continue-from',
        dest='continue_from',
        type=int,
        help='Continue processing from this paragraph number onwards (skips earlier paragraphs)',
    )
    parser.add_argument(
        '--regenerate',
        dest='regenerate',
        type=int,
        help='Regenerate images for this specific paragraph number (overwrites existing images)',
    )
    parser.add_argument(
        '--collapse-lines',
        action='store_true',
        help='Collapse single newlines inside paragraphs, keep blank lines as paragraph separators',
    )
    
    args = parser.parse_args()

    # Map positional project info if provided
    if args.base_path_pos and not getattr(args, 'base_path', None):
        args.base_path = args.base_path_pos
    if args.project_prefix_pos and not getattr(args, 'project_prefix', None):
        args.project_prefix = args.project_prefix_pos
    if args.project_number_pos and not getattr(args, 'project_number', None):
        args.project_number = args.project_number_pos

    # Parse shorthand positional for image counts: 1st X op Y
    extras = args.extra_positional or []
    i = 0
    while i < len(extras):
        token = extras[i].lower()
        if token in ('1st', 'first', 'first-paragraph'):
            if i + 1 < len(extras):
                try:
                    val = int(extras[i + 1])
                    if args.first_paragraph_images is None:
                        args.first_paragraph_images = val
                except ValueError:
                    pass
                i += 2
                continue
        if token in ('op', 'other', 'other-paragraphs'):
            if i + 1 < len(extras):
                try:
                    val = int(extras[i + 1])
                    if args.other_paragraphs_images is None:
                        args.other_paragraphs_images = val
                except ValueError:
                    pass
                i += 2
                continue
        i += 1

    # Validate API keys
    if not args.claude_api_key:
        print(
            "Error: Claude API key is required. Provide --claude-api-key "
            "or set ANTHROPIC_API_KEY (or CLAUDE_API_KEY) environment variable."
        )
        return 1

    if not args.kie_api_key:
        print(
            "Error: kie API key is required. Provide --kie-api-key "
            "or set NANO_BANANA_PRO_API_KEY environment variable."
        )
        return 1

    # Validate project info
    if not getattr(args, 'base_path', None):
        print("Error: base path is required. Usage: python script_to_images.py [base_path] [project_prefix] [project_number] 1st X op Y")
        return 1
    if not getattr(args, 'project_prefix', None):
        print("Error: project prefix is required. Usage: python script_to_images.py [base_path] [project_prefix] [project_number] 1st X op Y")
        return 1
    if not getattr(args, 'project_number', None):
        print("Error: project number is required. Usage: python script_to_images.py [base_path] [project_prefix] [project_number] 1st X op Y")
        return 1

    # Validate image counts
    if args.first_paragraph_images is None:
        print("Error: number of images for FIRST paragraph is required. Usage: ... 1st X ...")
        return 1
    if args.other_paragraphs_images is None:
        print("Error: number of images for OTHER paragraphs is required. Usage: ... op Y")
        return 1

    # Resolve project paths from base path, prefix, and number
    project_number_str = str(args.project_number)
    project_name = f"{args.project_prefix}{project_number_str}"
    project_root = os.path.join(args.base_path, "videos", project_name)
    script_path = os.path.join(project_root, "script", f"{project_name}.txt")
    output_folder = os.path.join(project_root, "images")
    prompts_json = os.path.join(project_root, "image_prompts.json")

    # Validate script file
    if not os.path.exists(script_path):
        print(f"Error: Script file not found: {script_path}")
        return 1
    
    # Read system prompt if provided
    system_prompt = None
    if args.system_prompt_file:
        if os.path.exists(args.system_prompt_file):
            with open(args.system_prompt_file, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
        else:
            print(f"Warning: System prompt file not found: {args.system_prompt_file}")
    
    # Read optional style string: base_path/image_gen/style_string.txt
    style_suffix = None
    style_path = os.path.join(args.base_path, "image_gen", "style_string.txt")
    if os.path.exists(style_path):
        try:
            with open(style_path, "r", encoding="utf-8") as sf:
                style_suffix = sf.read().strip()
            if style_suffix:
                print(f"Loaded style string from: {style_path}")
            else:
                style_suffix = None
        except Exception as e:
            print(f"Warning: Failed to read style string from {style_path}: {e}")

    # Initialize generator
    generator = ScriptToImagesGenerator(
        claude_api_key=args.claude_api_key,
        kie_api_key=args.kie_api_key,
        kie_model=args.kie_model,
        output_folder=output_folder,
        style_suffix=style_suffix,
        collapse_single_newlines=args.collapse_lines,
    )

    # Validate flags (mutually exclusive options)
    if args.paragraph and args.continue_from:
        print("Error: --paragraph and --continue-from cannot be used together")
        return 1
    if args.paragraph and args.regenerate:
        print("Error: --paragraph and --regenerate cannot be used together. Use --regenerate instead.")
        return 1
    if args.continue_from and args.regenerate:
        print("Error: --continue-from and --regenerate cannot be used together")
        return 1
    
    # Process script
    try:
        generator.process_script(
            script_path=script_path,
            first_paragraph_images=args.first_paragraph_images,
            other_paragraphs_images=args.other_paragraphs_images,
            system_prompt=system_prompt,
            save_prompts_json=prompts_json,
            resolution=args.resolution,
            aspect_ratio=args.aspect_ratio,
            output_format=args.format,
            only_paragraph=args.paragraph,
            continue_from=args.continue_from,
            regenerate=args.regenerate,
        )
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())

