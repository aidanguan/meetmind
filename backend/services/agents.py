from .llm import LLMService
import json

class KnowledgeBaseOrchestrator:
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def build_context(self, minutes_list):
        """
        minutes_list: List of objects (or dicts) with 'created_at' and 'content' attributes/keys.
        """
        # Sort by date
        # Assuming minutes_list are ORM objects or have attribute access
        try:
            sorted_minutes = sorted(minutes_list, key=lambda x: x.recording.created_at if x.recording else x.created_at)
        except:
             # Fallback if structure is different
             sorted_minutes = minutes_list

        context = ""
        for m in sorted_minutes:
            # Try to get date from recording, else minutes created_at
            date_val = m.recording.created_at if m.recording else m.created_at
            date_str = date_val.strftime("%Y-%m-%d %H:%M") if hasattr(date_val, 'strftime') else str(date_val)
            
            context += f"\n\n=== Meeting Date: {date_str} ===\n{m.content}\n"
        return context

    def generate_knowledge_base(self, minutes_list):
        context = self.build_context(minutes_list)
        
        tasks = ["prd", "specs", "timeline", "glossary"]
        results = {}
        
        # In a real async agent system, these would run in parallel.
        # For now, sequential execution.
        for task in tasks:
            print(f"Generating {task}...")
            results[task] = self.run_worker_agent(task, context)
            
        return results

    def run_worker_agent(self, task_type, context):
        system_prompt = self._get_system_prompt(task_type)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Project History Context:\n{context}\n\nTask: Generate the {task_type.upper()} document."}
        ]
        return self.llm.chat_completion(messages)

    def run_worker_agent_stream(self, task_type, context):
        system_prompt = self._get_system_prompt(task_type)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Project History Context:\n{context}\n\nTask: Generate the {task_type.upper()} document."}
        ]
        return self.llm.chat_completion_stream(messages)

    def run_worker_agent_stream(self, task_type, context):
        system_prompt = self._get_system_prompt(task_type)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Project History Context:\n{context}\n\nTask: Generate the {task_type.upper()} document."}
        ]
        return self.llm.chat_completion_stream(messages)

    def _get_system_prompt(self, task_type):
        base_prompt = """You are a senior project manager, product manager, and technical architect.
You are tasked with generating project documentation based on a series of meeting minutes.

**CRITICAL RULES:**
1.  **Chronological Priority**: The provided context is ordered chronologically. If there are contradictions or changes in requirements between meetings, **strictly prioritize the information from the LATEST meeting (the ones at the bottom of the context)**. Treat earlier meetings as historical context that might have been superseded.
2.  **Format**: Output strictly in **Markdown**.
3.  **Mermaid Diagrams**: 
    *   You are ENCOURAGED to use Mermaid diagrams to visualize information.
    *   Use ````mermaid` code blocks.
    *   Ensure the Mermaid syntax is correct.
"""

        if task_type == "prd":
            return base_prompt + """
**Task**: Generate a **Project Requirement Document (PRD)**.
**Structure**:
1.  **Project Overview**: Background and Objectives.
2.  **User Roles**: Who are the users?
3.  **User Stories/Features**: Detailed functional requirements.
4.  **Non-Functional Requirements**: Performance, Security, etc.
5.  **Constraints & Assumptions**.

*Use a Mermaid flowchart (`graph TD`) to illustrate the core user flow.*
"""
        elif task_type == "specs":
            return base_prompt + """
**Task**: Generate a **Functional Specification Document**.
**Structure**:
1.  **System Architecture**: High-level design. *Use a Mermaid diagram (e.g., `graph TD` or `C4Context` if possible, or `classDiagram`).*
2.  **Data Model**: Key entities and relationships. *Use a Mermaid `erDiagram` or `classDiagram`.*
3.  **API/Interface Design**: Key endpoints or interaction points.
4.  **Logic/Algorithms**: Key business logic explanation.
"""
        elif task_type == "timeline":
            return base_prompt + """
**Task**: Generate a **Project Timeline & Roadmap**.
**Structure**:
1.  **Phases**: Break down the project into logical phases.
2.  **Milestones**: Key deliverables and dates (if mentioned, otherwise estimate relative timing).
3.  **Gantt Chart**: *MANDATORY: Generate a Mermaid `gantt` chart representing the timeline.*
"""
        elif task_type == "glossary":
            return base_prompt + """
**Task**: Generate a **Project Glossary**.
**Structure**:
*   List all technical terms, acronyms, and project-specific jargon found in the minutes.
*   Provide a clear definition for each.
*   Format as a Markdown table or list.
"""
        
        return base_prompt
