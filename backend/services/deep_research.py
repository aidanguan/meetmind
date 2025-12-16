import os
import time
import logging
import uuid
from typing import List, Generator, Dict, Any
from .llm import LLMService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeepResearchService:
    def __init__(self):
        self.llm = LLMService()
        # In-memory storage for prompts since we are simulating the agent
        # Note: In a real distributed system, this should be Redis or DB.
        # But since the same instance might be used or created per request, 
        # we need to be careful. Actually, FastAPI creates a new instance per request
        # usually if used as dependency, but here it's instantiated in the router.
        # However, start_research and stream are separate calls? 
        # No, in projects.py it is: 
        # service = DeepResearchService()
        # id = service.start_research(...)
        # for update in service.stream_research_updates(id): ...
        # So we can store state in the instance.
        self.pending_tasks = {}

    def start_research(self, minutes_data: List[Dict[str, Any]]) -> str:
        """
        Starts a deep research task based on the provided meeting minutes.
        Returns the interaction ID.
        """
        logger.info(f"Starting Deep Research with {len(minutes_data)} minutes documents.")
        
        # Combine minutes into a context string
        combined_text = "\n\n".join([f"--- Meeting Minute {i+1} (ID: {m['id']}, File: {m['filename']}) ---\n{m['content']}" for i, m in enumerate(minutes_data)])
        
        system_prompt = """You are a Senior Technical Architect and Product Manager.
Your task is to analyze the provided Meeting Minutes and generate a comprehensive **Project Knowledge Base**.

**CRITICAL REQUIREMENT**: The output MUST be in **Chinese (Simplified)**.

**1. Content Depth & Structure**:
   - **Exhaustive Detail**: Do not summarize superficially. Extract all specific data points, decisions, logic rules, and constraints.
   - **Logic Changes**: If business logic changes are detected between meetings, explicitly structure the output to show: **Old Logic**, **New Logic**, and **Key Change Points**.
   - **Data Models**: If database schemas or fields are discussed, generate a **Data Dictionary** table (Field, Type, Description, Notes).

**2. Visualizations (Mermaid)**:
   - Use `mermaid` code blocks to visualize complex information.
   - **PRD**: 
     - User Journey Maps: `mermaid journey`
     - Process Flowcharts: `mermaid graph TD`
   - **Specs**: 
     - System Architecture: `mermaid C4` or `graph TB`
     - Entity Relationships: `mermaid erDiagram`
   - **Timeline**: 
     - Project Roadmap: `mermaid gantt`

**3. Citations & References**:
   - **Inline Citations**: When stating a fact or decision, you MUST use the following specific format for citations: `Statement [[Minutes_{filename}_{id}]]`. 
     - Do NOT use superscript tags like `<sup>[1]</sup>`. 
     - Do NOT use standard markdown links `[1](...)`.
     - The format `[[Minutes_{filename}_{id}]]` will be automatically rendered as a clickable badge by the frontend.
   - **Reference List**: At the very end of the document, add a section `## 参考文献 (References)`.
   - **Reference Format**: List the sources using the same format:
     `1. [[Minutes_{filename}_{id}]]`
     
     Example:
     > The project deadline is Q4 [[Minutes_KickoffMeeting_12]].
     > ...
     > ## 参考文献 (References)
     > 1. [[Minutes_KickoffMeeting_12]]

The Knowledge Base MUST include the following sections:
1. **Project Requirements Document (PRD)**: Goals, User Stories, User Journey, Functional Requirements.
2. **Technical Specifications**: Architecture, Tech Stack, Data Models (ER Diagram + Dictionary), API Design.
3. **Logic Change Log**: Detailed tracking of logic changes (Old vs New).
4. **Project Timeline**: 
   - **Gantt Chart**: `mermaid gantt`
   - **Timeline Table**: A Markdown table with columns (Phase, Task, Start Date, End Date, Owner, Status).
5. **Glossary**: Key terms and definitions.

Use the information strictly from the provided meeting minutes. 
If information is missing for a section, state that it is "To Be Determined" or infer reasonably from context if possible, but mark as inferred.
"""

        user_prompt = f"""Here are the Meeting Minutes:

{combined_text}
"""
        
        task_id = str(uuid.uuid4())
        self.pending_tasks[task_id] = {
            "system": system_prompt,
            "user": user_prompt
        }
        
        return task_id

    def stream_research_updates(self, interaction_id: str) -> Generator[Dict[str, Any], None, None]:
        """
        Yields status updates and finally the result.
        """
        logger.info(f"Polling interaction: {interaction_id}")
        
        task = self.pending_tasks.get(interaction_id)
        if not task:
            yield {"status": "failed", "message": "Task not found"}
            return

        yield {"status": "running", "message": "Deep Research Agent is analyzing and generating report..."}
        
        # Simulate processing time slightly for UX (optional)
        # time.sleep(1)

        try:
            messages = [
                {"role": "system", "content": task["system"]},
                {"role": "user", "content": task["user"]}
            ]
            
            full_text = ""
            # Use standard LLM streaming
            stream = self.llm.chat_completion_stream(messages, temperature=0.2)
            
            for chunk in stream:
                full_text += chunk
                # We could yield partial results if the frontend supported it, 
                # but the current contract expects "completed" with full result at the end.
                # Or we can just keep yielding "running" updates if needed.
                # Actually, yielding intermediate "running" prevents timeout.
                
            yield {"status": "completed", "result": full_text}
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            yield {"status": "failed", "message": str(e)}

    def parse_result(self, text: str) -> Dict[str, str]:
        """
        Parses the markdown result into sections.
        Expected sections: PRD, Specs, Timeline, Glossary.
        """
        sections = {
            "prd": "",
            "specs": "",
            "timeline": "",
            "glossary": ""
        }
        
        # specific logic to parse the markdown
        # This is a heuristic parser based on the prompt instructions
        
        current_section = None
        lines = text.split('\n')
        
        for line in lines:
             # Check for headers
             stripped_line = line.strip()
             lower_line = stripped_line.lower()
             
             if stripped_line.startswith('#'):
                 if "project requirements document" in lower_line or "prd" in lower_line:
                     current_section = "prd"
                     continue
                 elif "technical specifications" in lower_line or "technical specs" in lower_line:
                     current_section = "specs"
                     continue
                 elif "project timeline" in lower_line:
                     current_section = "timeline"
                     continue
                 elif "glossary" in lower_line:
                     current_section = "glossary"
                     continue
             
             if current_section:
                 sections[current_section] += line + "\n"
        
        # If parsing failed (everything empty), put all in PRD or a fallback
        if not any(sections.values()):
            sections["prd"] = text
            
        return sections
