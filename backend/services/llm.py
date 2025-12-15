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

    def chat_completion(self, messages: list, model: str = "gemini-3-pro-preview", temperature: float = 0.2):
        try:
            extra_body = {}
            if "gemini-3-pro-preview" in model:
                extra_body["thinking_config"] = {"thinking_budget": 1024}

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                extra_body=extra_body if extra_body else None
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error in chat_completion: {e}")
            raise e

    def chat_completion_stream(self, messages: list, model: str = "gemini-3-pro-preview", temperature: float = 0.2):
        try:
            extra_body = {}
            if "gemini-3-pro-preview" in model:
                extra_body["thinking_config"] = {"thinking_budget": 1024}

            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=True,
                extra_body=extra_body if extra_body else None
            )
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content is not None:
                        yield delta.content
        except Exception as e:
            print(f"Error in chat_completion_stream: {e}")
            yield f"\n\n**Error:** {str(e)}"

    def chat_completion_stream(self, messages: list, model: str = "gpt-5.1", temperature: float = 0.2):
        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=True
            )
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content is not None:
                        yield delta.content
        except Exception as e:
            print(f"Error in chat_completion_stream: {e}")
            yield f"\n\n**Error:** {str(e)}"

    def generate_minutes(self, transcript_text: str, context: str = ""):
        prompt = self._build_prompt(transcript_text, context)
        
        try:
            extra_body = {"thinking_config": {"thinking_budget": 1024}}
            response = self.client.chat.completions.create(
                model="gemini-3-pro-preview",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                extra_body=extra_body
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating minutes: {e}")
            return "Error generating meeting minutes."

    def stream_minutes_generator(self, transcript_text: str, context: str = ""):
        prompt = self._build_prompt(transcript_text, context)
        
        try:
            extra_body = {"thinking_config": {"thinking_budget": 1024}}
            stream = self.client.chat.completions.create(
                model="gemini-3-pro-preview",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                stream=True,
                temperature=0.2,
                extra_body=extra_body
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
    *   重点内容可加粗 (`**重点**`)。

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
