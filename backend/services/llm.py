import httpx
from openai import OpenAI
import os

class LLMService:
    def __init__(self):
        # Create a custom httpx client to avoid proxy issues or version conflicts
        # Older versions of httpx might not support 'proxies', or it might be 'mounts'
        # To be safe, we just create a default client without args if we suspect version issues,
        # but let's try to be specific about trust_env=False to ignore env vars like HTTP_PROXY
        http_client = httpx.Client(trust_env=False)
        
        self.client = OpenAI(
            api_key=os.getenv("AIHUBMIX_API_KEY", "dummy"),
            base_url="https://aihubmix.com/v1",
            http_client=http_client
        )

    def generate_minutes(self, transcript_text: str, context: str = ""):
        prompt = self._build_prompt(transcript_text, context)
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-5.2", # As requested
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating minutes: {e}")
            return "Error generating meeting minutes."

    def stream_minutes_generator(self, transcript_text: str, context: str = ""):
        prompt = self._build_prompt(transcript_text, context)
        
        try:
            stream = self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                stream=True
            )
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content is not None:
                         yield delta.content
        except Exception as e:
            print(f"Error generating minutes stream: {e}")
            # Yield error message so frontend sees it (although not ideal UX, better than silence)
            yield f"\n\n**Error during generation:** {str(e)}"

    def _build_prompt(self, transcript_text: str, context: str = "") -> str:
        return f"""
        You are a professional meeting secretary. 
        Please generate meeting minutes based on the following transcript.
        
        Context/Metadata: {context}
        
        Transcript:
        {transcript_text}
        
        Please format the output as Markdown with the following sections:
        - Meeting Summary
        - Key Discussion Points
        - Action Items
        - Decisions Made
        """
