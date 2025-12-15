import json
import re
from typing import List, Dict, Generator, Any

class ProjectQAAgent:
    def __init__(self, llm_service, kb_data: Dict[str, str], minutes_data: List[Dict[str, Any]], transcripts_data: List[Dict[str, Any]] = None):
        self.llm = llm_service
        self.kb_data = kb_data
        self.minutes_data = minutes_data
        self.transcripts_data = transcripts_data or []
        self.history = []
        self.max_steps = 5

    def search_meeting_minutes(self, query: str) -> str:
        """Search the raw meeting minutes."""
        results = []
        query_lower = query.lower()
        
        for m in self.minutes_data:
            content = m.get('content', '')
            date_str = m.get('created_at', 'Unknown Date')
            record_id = m.get('recording_id', 0)
            
            if query_lower in content.lower():
                matches = [match.start() for match in re.finditer(re.escape(query_lower), content.lower())]
                
                for idx in matches[:3]:
                    start = max(0, idx - 150)
                    end = min(len(content), idx + 350)
                    snippet = content[start:end].replace('\n', ' ')
                    results.append(f"SOURCE: [[Meeting Minutes - {date_str} (ID: {record_id})]]\nCONTENT: ...{snippet}...")
        
        if not results:
            return "No direct matches found in Meeting Minutes."
        return "\n\n".join(results)

    def search_transcripts(self, query: str) -> str:
        """Search the raw meeting transcripts."""
        results = []
        query_lower = query.lower()
        
        for t in self.transcripts_data:
            content = t.get('content', '')
            date_str = t.get('created_at', 'Unknown Date')
            record_id = t.get('recording_id', 0)
            
            if query_lower in content.lower():
                matches = [match.start() for match in re.finditer(re.escape(query_lower), content.lower())]
                
                # Limit to first 3 matches to save tokens
                for idx in matches[:3]:
                    start = max(0, idx - 200)
                    end = min(len(content), idx + 400)
                    snippet = content[start:end].replace('\n', ' ')
                    results.append(f"SOURCE: [[Transcript - {date_str} (ID: {record_id})]]\nCONTENT: ...{snippet}...")
        
        if not results:
            return "No direct matches found in Transcripts."
        return "\n\n".join(results)

    def _build_context_string(self) -> str:
        parts = []
        if self.kb_data:
            parts.append("=== PROJECT KNOWLEDGE BASE ===")
            for section, content in self.kb_data.items():
                if content:
                    parts.append(f"\n--- SECTION: {section.upper()} ---\n{content}")
        
        return "\n".join(parts)

    def run_stream(self, user_query: str) -> Generator[str, None, None]:
        context_str = self._build_context_string()
        
        system_prompt = f"""You are a helpful project assistant. 
You have access to the full **Project Knowledge Base** in your context below. 
First, try to answer the user's question using this Knowledge Base.
If the Knowledge Base is insufficient, you can use tools to search specific meeting minutes or raw transcripts.

=== CONTEXT START ===
{context_str}
=== CONTEXT END ===

You have access to the following tools:

1. search_meeting_minutes: Useful for finding specific discussions, decisions, and summarized context from meetings not fully covered in the KB. Input: a search query.
2. search_transcripts: Useful for finding exact quotes, raw discussion details, or information from meetings when summaries are not enough. Input: a search query.

Use the following format strictly:

Question: the input question
Thought: you should always think about what to do. Check if the answer is in the Context first.
Action: the action to take, should be one of [search_meeting_minutes, search_transcripts]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question. 
IMPORTANT: When providing the Final Answer, you MUST cite your sources. Use the format [[Source Name]] at the end of the sentence or paragraph.
Example: The project deadline is Q4 [[Knowledge Base - TIMELINE]]. Discussion happened on Tuesday [[Meeting Minutes - 2023-10-27 (ID: 12)]].
"""
        
        self.history.append({"role": "system", "content": system_prompt})
        self.history.append({"role": "user", "content": f"Question: {user_query}"})
        
        yield f"event: thought\ndata: {json.dumps({'content': '正在分析问题并检索项目知识库...'})}\n\n"

        step = 0
        while step < self.max_steps:
            response_text = self.llm.chat_completion(self.history)
            
            lines = response_text.split('\n')
            action = None
            action_input = None
            final_answer_index = -1
            
            current_thought = []
            
            for i, line in enumerate(lines):
                if line.startswith("Final Answer:"):
                    final_answer_index = i
                    break
                if line.startswith("Action:"):
                    action = line.replace("Action:", "").strip()
                elif line.startswith("Action Input:"):
                    action_input = line.replace("Action Input:", "").strip()
                elif line.startswith("Thought:"):
                    current_thought.append(line.replace("Thought:", "").strip())
            
            if current_thought:
                thought_str = " ".join(current_thought)
                # Translate common thought patterns to Chinese for better UX if needed, or just yield as is
                yield f"event: thought\ndata: {json.dumps({'content': thought_str})}\n\n"

            if final_answer_index != -1:
                final_answer = "\n".join(lines[final_answer_index:]).replace("Final Answer:", "").strip()
                yield f"event: answer\ndata: {json.dumps({'content': final_answer})}\n\n"
                return

            if action and action_input:
                # Notify frontend about the action being taken
                tool_display_name = "搜索会议纪要" if action == "search_meeting_minutes" else "搜索会议转录" if action == "search_transcripts" else action
                yield f"event: action\ndata: {json.dumps({'tool': tool_display_name, 'query': action_input})}\n\n"
                
                observation = ""
                if action == "search_meeting_minutes":
                    observation = self.search_meeting_minutes(action_input)
                elif action == "search_transcripts":
                    observation = self.search_transcripts(action_input)
                else:
                    observation = f"Unknown tool: {action}"
                
                step_context = f"{response_text}\nObservation: {observation}"
                self.history.append({"role": "assistant", "content": step_context})
                
                step += 1
            else:
                yield f"event: answer\ndata: {json.dumps({'content': response_text})}\n\n"
                return

        yield f"event: error\ndata: {json.dumps({'content': 'Agent step limit reached'})}\n\n"
