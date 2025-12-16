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
    def transcribe(file_path: str = "", file_url: str = "", vocabulary_id: str = None):
        """
        Transcribe audio file using Aliyun Dashscope (FunASR/Paraformer).
        """
        if not file_url and not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        try:
            # Use paraformer-v2 for better diarization support
            model_name = 'paraformer-v2'
            kwargs = {'model': model_name, 'diarization_enabled': True}
            
            if vocabulary_id:
                kwargs['vocabulary_id'] = vocabulary_id

            if file_url:
                print(f"DEBUG: Calling Transcription.async_call with file_url={file_url}, kwargs={kwargs}")
                task_response = Transcription.async_call(file_urls=[file_url], **kwargs)
            else:
                print(f"DEBUG: Calling Transcription.async_call with file_path={file_path}, kwargs={kwargs}")
                task_response = Transcription.async_call(files=[file_path], **kwargs)
            return task_response
        except Exception as e:
            print(f"Error starting transcription: {e}")
            raise e

    @staticmethod
    def create_vocabulary(hotwords: list, prefix: str = "meetmind", target_model: str = "paraformer-v2"):
        """
        Create a vocabulary for custom hotwords.
        hotwords: list of dict {text, weight, lang}
        """
        from dashscope.audio.asr import VocabularyService
        
        service = VocabularyService()
        try:
            # VocabularyService.create_vocabulary returns the vocabulary_id
            vocabulary_id = service.create_vocabulary(
                prefix=prefix,
                target_model=target_model,
                vocabulary=hotwords
            )
            return vocabulary_id
        except Exception as e:
            print(f"Error creating vocabulary: {e}")
            raise e

    @staticmethod
    def get_task_result(task_id: str):
        return Transcription.wait(task=task_id)
