import os
import dashscope
from dashscope.audio.asr import Transcription

# Ensure API key from multiple env names
dashscope.api_key = (
    os.getenv("DASHSCOPE_API_KEY")
    or os.getenv("ALIYUN_TOKEN")
    or os.getenv("ALIYUN_APPKEY")
    or ""
)

class AliyunService:
    @staticmethod
    def transcribe(file_path: str = "", file_url: str = ""):
        """
        Transcribe audio file using Aliyun Dashscope (FunASR/Paraformer).
        """
        if not file_url and not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        try:
            # Use paraformer-v2 for better diarization support
            model_name = 'paraformer-v2'
            if file_url:
                task_response = Transcription.async_call(model=model_name, file_urls=[file_url], diarization_enabled=True)
            else:
                task_response = Transcription.async_call(model=model_name, files=[file_path], diarization_enabled=True)
            return task_response
        except Exception as e:
            print(f"Error starting transcription: {e}")
            raise e

    @staticmethod
    def get_task_result(task_id: str):
        return Transcription.wait(task=task_id)
