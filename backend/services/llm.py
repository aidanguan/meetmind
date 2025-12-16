import httpx
from openai import OpenAI
import os
import google.generativeai as genai
import tempfile
import time
from typing import List, Optional

class LLMService:
    def __init__(self):
        # Google Gemini Configuration
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash-exp")
        
        if self.google_api_key:
            genai.configure(api_key=self.google_api_key)
            self.use_google = True
        else:
            self.use_google = False

        # OpenAI Configuration (Fallback or Legacy)
        http_client = httpx.Client(trust_env=False)
        self.client = OpenAI(
            api_key=os.getenv("AIHUBMIX_API_KEY", "dummy"),
            base_url="https://aihubmix.com/v1",
            http_client=http_client
        )

    def upload_to_gemini(self, content: str, mime_type: str = "text/plain", display_name: str = None) -> Optional[str]:
        """
        Uploads content to Gemini Files API.
        Returns the File URI.
        """
        if not self.use_google:
            print("Google API Key not configured, skipping upload.")
            return None

        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix='.txt') as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            print(f"Uploading file to Gemini: {display_name or 'unknown'}")
            file = genai.upload_file(path=tmp_path, mime_type=mime_type, display_name=display_name)
            
            # Wait for processing if necessary (usually fast for text)
            # active_file = genai.get_file(file.name)
            # while active_file.state.name == "PROCESSING":
            #     time.sleep(1)
            #     active_file = genai.get_file(file.name)

            os.remove(tmp_path)
            return file.uri
        except Exception as e:
            print(f"Error uploading to Gemini: {e}")
            return None

    def chat_with_files(self, messages: list, file_uris: List[str], stream: bool = True):
        """
        Chat with Gemini using uploaded files as context.
        messages: List of {"role": "user"/"model", "content": "..."} (OpenAI format will be converted)
        """
        if not self.use_google:
            yield "Google API Key not configured."
            return

        try:
            model = genai.GenerativeModel(self.gemini_model_name)
            
            # Prepare history and last message
            history = []
            system_instruction = None
            
            # Convert OpenAI messages to Gemini format
            # Gemini expects history as list of Content objects, and system instruction separate
            
            last_user_content = ""
            
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                
                if role == "system":
                    system_instruction = content
                elif role == "user":
                    # If it's the last message, we'll append it with files later
                    last_user_content = content
                    # We don't add the last user message to history here, we send it in generate_content
                elif role == "assistant":
                    history.append({"role": "model", "parts": [content]})
            
            # Add previous user messages to history (excluding the very last one which drives the current turn)
            # Actually, the 'messages' list usually contains the full conversation including the latest user prompt.
            # We need to rebuild the history correctly.
            
            gemini_history = []
            # Iterate all EXCEPT last user message
            # The last message is usually the user prompt
            for i, msg in enumerate(messages[:-1]): 
                role = msg.get("role")
                content = msg.get("content")
                if role == "user":
                    gemini_history.append({"role": "user", "parts": [content]})
                elif role == "assistant":
                    gemini_history.append({"role": "model", "parts": [content]})
            
            # If system instruction exists, we should ideally configure the model with it
            if system_instruction:
                 # Explicitly set system_instruction in model config
                 # Note: system_instruction is supported in newer SDK versions and models
                 model = genai.GenerativeModel(
                     self.gemini_model_name, 
                     system_instruction=system_instruction
                 )
            else:
                 model = genai.GenerativeModel(self.gemini_model_name)

            # Prepare the current message content with files
            current_parts = []
            for uri in file_uris:
                 # The URI format is like: https://generativelanguage.googleapis.com/v1beta/files/c450...
                 # The SDK genai.get_file(name) takes the name `files/NAME`.
                 # We need to extract name from URI or just use the URI if we can convert it to a file object wrapper.
                 
                 # Extract 'files/XXX' from URI
                 try:
                     if "/files/" in uri:
                         file_name = "files/" + uri.split("/files/")[-1]
                         file_ref = genai.get_file(file_name)
                         current_parts.append(file_ref)
                     else:
                         # Fallback if URI format is different or just a name
                         # Assuming it might be just the name or full URI
                         print(f"Warning: Unexpected URI format: {uri}")
                 except Exception as file_err:
                     print(f"Error fetching file ref for {uri}: {file_err}")

            current_parts.append(last_user_content)

            chat = model.start_chat(history=gemini_history)
            
            if stream:
                response = chat.send_message(current_parts, stream=True)
                for chunk in response:
                    # In Gemini, chunk.text contains the newly generated part
                    # We should yield it directly
                    if chunk.text:
                        yield chunk.text
            else:
                response = chat.send_message(current_parts)
                return response.text

        except Exception as e:
            print(f"Error in chat_with_files: {e}")
            yield f"\n\n**Error:** {str(e)}"

    def chat_completion(self, messages: list, model: str = None, temperature: float = 0.2):
        if not model:
            model = self.gemini_model_name if self.use_google else "gpt-3.5-turbo"

        if self.use_google:
            return self._google_chat(messages, model, temperature, stream=False)
        else:
            return self._openai_chat(messages, model, temperature, stream=False)

    def chat_completion_stream(self, messages: list, model: str = None, temperature: float = 0.2):
        if not model:
            model = self.gemini_model_name if self.use_google else "gpt-3.5-turbo"

        if self.use_google:
            yield from self._google_chat(messages, model, temperature, stream=True)
        else:
            yield from self._openai_chat(messages, model, temperature, stream=True)

    def _google_chat(self, messages: list, model_name: str, temperature: float, stream: bool):
        try:
            model = genai.GenerativeModel(model_name)
            
            # Extract system prompt
            system_instruction = None
            history = []
            last_message = ""
            
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                if role == "system":
                    system_instruction = content
                elif role == "user":
                    last_message = content # Assuming strictly alternating or user-led last
                elif role == "assistant":
                    history.append({"role": "model", "parts": [content]})
            
            # Re-construct history correctly (Gemini ChatSession manages history)
            # We need to populate history with pairs if possible or use send_message with full context?
            # start_chat(history=...) expects list of contents.
            
            # Better approach for chat compatibility:
            gemini_history = []
            # Iterate all EXCEPT last user message
            for i, msg in enumerate(messages[:-1]):
                role = msg.get("role")
                content = msg.get("content")
                if role == "user":
                    gemini_history.append({"role": "user", "parts": [content]})
                elif role == "assistant":
                    gemini_history.append({"role": "model", "parts": [content]})
            
            if system_instruction:
                 model = genai.GenerativeModel(model_name, system_instruction=system_instruction)

            chat = model.start_chat(history=gemini_history)
            
            if stream:
                response = chat.send_message(last_message, stream=True, generation_config=genai.types.GenerationConfig(temperature=temperature))
                for chunk in response:
                    # In Gemini, chunk.text contains the newly generated part
                    # We should yield it directly
                    if chunk.text:
                        yield chunk.text
            else:
                response = chat.send_message(last_message, generation_config=genai.types.GenerationConfig(temperature=temperature))
                return response.text

        except Exception as e:
            print(f"Error in Google chat: {e}")
            if stream:
                yield f"\n\n**Error:** {str(e)}"
            else:
                raise e

    def _openai_chat(self, messages: list, model: str, temperature: float, stream: bool):
        try:
            extra_body = {}
            if "gemini-3-pro-preview" in model:
                extra_body["thinking_config"] = {"thinking_budget": 1024}

            if stream:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                    extra_body=extra_body if extra_body else None
                )
                for chunk in response:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta.content is not None:
                            yield delta.content
            else:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    extra_body=extra_body if extra_body else None
                )
                return response.choices[0].message.content
        except Exception as e:
            print(f"Error in OpenAI chat: {e}")
            if stream:
                yield f"\n\n**Error:** {str(e)}"
            else:
                raise e

    def generate_minutes(self, transcript_text: str, context: str = "", meeting_date: str = None):
        prompt = self._build_prompt(transcript_text, context, meeting_date)
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
        return self.chat_completion(messages, temperature=0.2)

    def stream_minutes_generator(self, transcript_text: str, context: str = "", meeting_date: str = None):
        prompt = self._build_prompt(transcript_text, context, meeting_date)
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
        yield from self.chat_completion_stream(messages, temperature=0.2)

    def _build_prompt(self, transcript_text: str, context: str = "", meeting_date: str = None) -> str:
        date_instruction = ""
        if meeting_date:
            date_instruction = f"""
    *   **待办事项日期转换**：会议召开日期为 **{meeting_date}**。请根据此日期，将文中提到的相对时间（如“本周五”、“下周一”）转换为具体的自然日日期（YYYY-MM-DD）。如果没有明确日期或无法推断，请填写“未提及”。"""

        return f"""
你是一名专业的会议秘书，请根据以下会议转写内容生成一份结构化、内容完整且格式规范的会议纪要。

**会议背景信息**：{context}
**会议转写原文**：
{transcript_text}

---

**生成要求**：

1.  **格式要求**：
    *   必须使用标准 Markdown 格式。
    *   **会议标题**使用一级标题 (`# 标题`)。
    *   **主要板块**使用二级标题 (`## 板块名称`)。
    *   **子项**使用无序列表 (`-`) 或有序列表 (`1.`)。
    *   重点内容可加粗 (`**重点**`)。{date_instruction}

2.  **内容完整性**：
    *   全面捕捉会议中的关键信息，**切勿遗漏**重要的讨论点、数据、决策和待办事项。
    *   如果原文较长，请确保纪要反映了会议的全貌，而不是仅针对开头。

3.  **语言风格**：
    *   正式、客观、专业。
    *   去除口语、语气词和重复内容，但保留信息的原意。

4.  **结构模板（请严格参考以下结构输出）**：

# 会议纪要：[会议主题/项目名称]

## 1. 会议概要
- **时间**：[YYYY-MM-DD]（如果原文有，否则不写）
- **参会人员**：[人员名单]（如果原文有，否则不写）
- **会议目的**：[简述会议目标]
- **核心结论**：[一句话总结会议结果]

## 2. 关键讨论事项
- **议题一：[议题名称]**
  - **核心问题**：[描述问题]
  - **讨论观点**：
    - [观点1]
    - [观点2]
  - **结论/现状**：[讨论结果]

- **议题二：[议题名称]**
  ...

## 3. 已达成决议 (Decisions)
- [决议1]：[具体内容] (依据：[简要理由])
- [决议2]：...

## 4. 待办事项 (Action Items)
| 任务内容 | 负责人 | 截止时间 | 备注 |
| :--- | :--- | :--- | :--- |
| [任务描述] | [姓名] | [日期] | [其他] |
| ... | ... | ... | ... |

## 5. 跟进事项
- [事项1]
- ...

---
**注意**：若某板块无相关信息，请写“无”。不要输出“根据提供的文本...”之类的开场白，直接开始输出 Markdown 内容。
"""
