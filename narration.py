from pathlib import Path
# from openai import OpenAI
from google import genai 
from google.genai import types
from narrate import api_key
import cv2
import numpy as np
import base64
from PIL import Image
import time

start_time = time.perf_counter()

# Initialize OpenAI
client = genai.Client(api_key=api_key())   # key from .env or the GEMINI_API_KEY environment variable

#-----------------------------------------------
# Function to extract NASA earth data frames
#-----------------------------------------------

def load_frames(imgspath):

    folder = Path(imgspath)

    all_imgpaths = [path for path in folder.iterdir() if
                    path.suffix.lower() in '.png']

    print(len(all_imgpaths))

    # Raise error if no imgs present
    if not all_imgpaths:
        raise ValueError(f"No images *.png found in {imgspath}")

    # Sort the images in the folder
    sorted_imgs = sorted(all_imgpaths, key=lambda path: path.name)

    frames_list=[]
    for i, path in enumerate(sorted_imgs):
        img_bgr = cv2.imread(str(path))
        if img_bgr is None:
            print(f"Warning: Failed to load image at {path}. Skipping.")
            continue
            
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        # Generate baseline metrics from visuals
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        frame_variance = float(np.var(gray))
        mean_intensity = float(np.mean(gray))
        
        frames_list.append({
            "sequence_index": i,
            "file_path": str(path),
            "image_array": img_rgb,
            "metrics": {
                "variance": frame_variance,
                "mean_intensity": mean_intensity
            }
        })

    return frames_list

def audio_metrics(frames_list):

    # Generate parameters from musical perspective
    variance = frames_list["variance"]
    mean_intensity = frames_list["mean_intensity"]
    
    min_var, max_var = 100.0, 5000.0
    normalized_var = np.clip((variance - min_var) / (max_var - min_var), 0.0, 1.0)
    
    return {
        "bpm": int(70 + (normalized_var * 70)),
        "root_midi_note": int(36 + (mean_intensity / 255.0) * 36),
        "synth_cutoff_hz": int(200 + (normalized_var * 3800)),
        "energy_level": "high energy / volatile" if normalized_var > 0.6 else "ambient / stable"
    }


def encode_image_to_base64(image_path):
    
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

# Prompt generator
def prompt_generator(all_frames, max_retries=3):
    
    print(f'Total : {len(all_frames)}')
    
    # system_prompt = (
    #     # "You are the poetic narrative voice of the Earth Information Jukebox. "
    #     "Translate global Earth observation frames into a sensory description that a listener can 'feel' the frame without seeing it"
    # )

    compile_prompt = []
    visuals = all_frames[:5]

    for frame in visuals:
        # Gemini natively accepts PIL Image objects, bypassing manual base64 encoding
        pil_img = Image.open(frame["file_path"]).convert("RGB")
        pil_img.thumbnail((512, 256), Image.Resampling.LANCZOS)
        compile_prompt.append(pil_img)
        
    user_prompt = (
        "Analyze the chronological progression as a whole. Write a 1-sentence sensory description:"
    )
    compile_prompt.append(user_prompt)

    image_count = sum(1 for item in compile_prompt if isinstance(item, Image.Image))
    print(f"Sending {image_count} images to Gemini API (Total payload items: {len(compile_prompt)})...")

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",  
                contents=compile_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are the poetic narrative voice of the Earth Information Jukebox. Translate global Earth observation frames into a visceral, sensory description. Do NOT mention calendar dates, years, numbers, or coordinates.",
                    temperature=0.7,
                    max_output_tokens=2000,
                )
            )
            return response.text.strip()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed with error: {e}")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 2  
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return "A sweeping, atmospheric wave shifts silently across the transforming globe."

# Use prompts to generate narrative
def narration(sequenced_frames):
    """Builds individual musical mappings per frame, and pairs them with a unified sequence narrative."""
    timeline = []
    for frame in sequenced_frames:
        music_mapping = audio_metrics(frame["metrics"])
        timeline.append({
            "sequence_index": frame["sequence_index"],
            "audio_controls": music_mapping
        })
        
    overall_narrative = prompt_generator(sequenced_frames)
    
    return {
        "sequence_narrative": overall_narrative, "timeline": timeline
    }

#-----------------------------------------------
# Execution
#-----------------------------------------------
if __name__ == "__main__":
    input_folder = "./Ice Surface Temperature (Day) with base"

    # Extract frames from folder & sort in chronological order
    frames = load_frames(input_folder)

    # Run the narration
    jukebox = narration(frames)

    # Display output
    print(f"\n[Overall Sequence Narrative]")
    print(jukebox["sequence_narrative"])
    
    # print(f"\n[Frame-by-Frame Audio Controls]")
    # for entry in jukebox["timeline"]:
    #     print(f"Index {entry['sequence_index']} -> {entry['audio_controls']}")

end_time = time.perf_counter()
execution_time = end_time - start_time
print(f"Execution time: {execution_time:.6f} seconds")