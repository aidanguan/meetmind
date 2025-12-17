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

    def start_research(self, minutes_data: List[Dict[str, Any]], documents_data: List[Dict[str, Any]] = None) -> str:
        """
        Starts a deep research task based on the provided meeting minutes and documents.
        Returns the interaction ID.
        """
        if documents_data is None:
            documents_data = []

        logger.info(f"Starting Deep Research with {len(minutes_data)} minutes and {len(documents_data)} documents.")
        
        # Combine minutes into a context string
        minutes_text = "\n\n".join([f"--- Meeting Minute {i+1} (ID: {m['id']}, File: {m['filename']}) ---\n{m['content']}" for i, m in enumerate(minutes_data)])
        
        # Combine documents into a context string
        # Note: If documents are files (PDF, etc.), we ideally need their text content.
        # Since we are using LLMService which supports file URIs, but DeepResearch currently uses string context...
        # We have a dilemma: DeepResearch uses chat_completion which takes text.
        # If we want to support files, we need to use Gemini's file capability in the LLMService.
        # However, deep_research.py's stream_research_updates uses self.llm.chat_completion_stream which defaults to text-only OpenAI format 
        # unless we change how we call it.
        #
        # For now, assuming we can extract text or we pass text content if available.
        # But ProjectDocument only has file_path. We haven't implemented text extraction for docs yet.
        # 
        # To fix this properly:
        # 1. We should support passing file_uris to DeepResearch.
        # 2. Update LLMService.chat_completion_stream to accept file_uris (it handles it for chat_with_files but that's a different method).
        # 
        # Let's modify stream_research_updates to handle file_uris if present in the task.
        
        docs_text_parts = []
        file_uris = []
        
        for i, d in enumerate(documents_data):
            if d.get('content'):
                docs_text_parts.append(f"--- Document {i+1} (ID: {d['id']}, Type: {d['type']}, File: {d['filename']}) ---\n{d['content']}")
            if d.get('gemini_uri'):
                file_uris.append(d['gemini_uri'])
                # We also add a reference marker in text so the model knows about it
                docs_text_parts.append(f"--- Document {i+1} (ID: {d['id']}, Type: {d['type']}, File: {d['filename']}) ---\n[Attached File: {d['filename']}]")

        documents_text = "\n\n".join(docs_text_parts)
        
        system_prompt = """You are a Senior Technical Architect and Product Manager.
Your task is to analyze the provided Meeting Minutes and Project Documents to generate a comprehensive **Project Knowledge Base**.

**CRITICAL REQUIREMENT**: The output MUST be in **Chinese (Simplified)**.

**1. Content Depth & Structure**:
   - **Exhaustive Detail**: Do not summarize superficially. Extract all specific data points, decisions, logic rules, and constraints.
   - **Logic Changes**: If business logic changes are detected between meetings, explicitly structure the output to show: **Old Logic**, **New Logic**, and **Key Change Points**.
   - **Data Models**: If database schemas or fields are discussed, generate a **Data Dictionary** table (Field, Type, Description, Notes).

**2. Visualizations (Mermaid)**:
   - Use `mermaid` code blocks to visualize complex information.
   - **Syntax Constraints**:
     - ALWAYS use quotes for node labels containing spaces or special characters: `A["Node Label"]`.
     - Avoid using brackets `[]` or parentheses `()` inside labels unless quoted.
     - Use `flowchart TD` or `graph TD` for processes.
   - **PRD**: 
     - User Journey Maps: `mermaid journey`
     - Process Flowcharts: `mermaid flowchart TD`
   - **Specs**: 
     - System Architecture: `mermaid C4` or `graph TB`
     - Entity Relationships: `mermaid erDiagram`
   - **Business Logic**:
     - State Machines: `mermaid stateDiagram-v2`
     - Decision Trees: `mermaid flowchart TD`
   - **Timeline**: 
     - Project Roadmap: `mermaid gantt`

**3. Citations & References**:
   - **Inline Citations**: When stating a fact or decision, you MUST use the following specific format for citations: 
     - For Minutes: `Statement [[Minutes_{filename}_{id}]]`
     - For Documents: `Statement [[Document_{filename}_{id}]]`
   - **Reference List**: At the very end of the document, add a section `## 参考文献 (References)`.
   - **Reference Format**: List the sources using the same format:
     `1. [[Minutes_{filename}_{id}]]`
     `2. [[Document_{filename}_{id}]]`

The Knowledge Base MUST include the following sections:
1. **Project Requirements Document (PRD)**: Goals, User Stories, User Journey, Functional Requirements.
2. **Technical Specifications**: Architecture, Tech Stack, Data Models (ER Diagram + Dictionary), API Design.
3. **Business Process & Logic**: 
   - Core Business Workflows (with Mermaid flowcharts).
   - State Transitions (e.g., Order Status).
   - Key Decision Rules and Calculation Logic.
4. **Logic Change Log**: Detailed tracking of logic changes (Old vs New).
5. **Project Timeline**: 
   - **Gantt Chart**: `mermaid gantt`
   - **Timeline Table**: A Markdown table with columns (Phase, Task, Start Date, End Date, Owner, Status).
6. **Glossary**: Key terms and definitions.

Use the information strictly from the provided meeting minutes and documents. 
If information is missing for a section, state that it is "To Be Determined" or infer reasonably from context if possible, but mark as inferred.
"""

        user_prompt = f"""Here are the Meeting Minutes:

{minutes_text}

Here are the Project Documents:

{documents_text}
"""
        
        task_id = str(uuid.uuid4())
        self.pending_tasks[task_id] = {
            "system": system_prompt,
            "user": user_prompt,
            "file_uris": file_uris
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
        
        try:
            # We need to handle file_uris if present
            file_uris = task.get("file_uris", [])
            
            # If we have file URIs, we MUST use Google model and chat_with_files logic
            # But chat_with_files is a generator yielding chunks.
            # LLMService.chat_with_files signature: (messages, file_uris, stream=True)
            
            messages = [
                {"role": "system", "content": task["system"]},
                {"role": "user", "content": task["user"]}
            ]
            
            full_text = ""
            
            if file_uris and self.llm.use_google:
                stream = self.llm.chat_with_files(messages, file_uris, stream=True)
            else:
                stream = self.llm.chat_completion_stream(messages, temperature=0.2)
            
            for chunk in stream:
                full_text += chunk
                # Filter out error messages from stream if any (simple check)
                if "**Error**" in chunk:
                     logger.error(f"Stream error: {chunk}")
            
            yield {"status": "completed", "result": full_text}
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            yield {"status": "failed", "message": str(e)}

    def parse_result(self, text: str) -> Dict[str, str]:
        """
        Parses the markdown result into sections.
        Expected sections: PRD, Specs, Business Flows, Timeline, Glossary.
        """
        sections = {
            "prd": "",
            "specs": "",
            "business_flows": "",
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
                 elif "business process" in lower_line or "business logic" in lower_line or "业务流程" in lower_line:
                     current_section = "business_flows"
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
